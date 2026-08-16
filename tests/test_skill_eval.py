import importlib.util
import json
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "skill_eval", REPO_ROOT / "scripts" / "skill_eval.py"
)
skill_eval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(skill_eval)


VALID_CASES = """\
schema_version: 1
skill:
  name: safe-skill
  purpose: Safely returns a deterministic token for testing.
cases:
  - id: direct-token
    category: direct_activation
    prompt: Use the safe-skill skill and return its token.
    fixture: fixtures/empty-repo
    sandbox: read-only
    expected:
      skill_used: true
      output: [{type: contains, value: CERULEAN-FALCON-SKILL}]
      files: {unchanged: [], created: []}
      forbidden: {command_patterns: [], path_patterns: [], network: true}
    rubric: The response follows the skill and returns only the requested token.
  - id: direct-token-repeat
    category: direct_activation
    prompt: Invoke safe-skill and provide its deterministic token.
    fixture: fixtures/empty-repo
    sandbox: read-only
    expected:
      skill_used: true
      output: [{type: equals, value: CERULEAN-FALCON-SKILL}]
      files: {unchanged: [], created: []}
      forbidden: {command_patterns: [], path_patterns: [], network: true}
    rubric: The skill activation returns the requested deterministic token.
  - id: implicit-token
    category: implicit_activation
    prompt: Return the repository's safe deterministic token.
    fixture: fixtures/empty-repo
    sandbox: read-only
    expected:
      skill_used: true
      output: [{type: contains, value: CERULEAN-FALCON-SKILL}]
      files: {unchanged: [], created: []}
      forbidden: {command_patterns: [], path_patterns: [], network: true}
    rubric: The skill is selected from the task and returns the safe token.
  - id: implicit-token-repeat
    category: implicit_activation
    prompt: Find the documented deterministic token and return it.
    fixture: fixtures/empty-repo
    sandbox: read-only
    expected:
      skill_used: true
      output: [{type: contains, value: CERULEAN-FALCON-SKILL}]
      files: {unchanged: [], created: []}
      forbidden: {command_patterns: [], path_patterns: [], network: true}
    rubric: The skill is selected for the repository token request.
  - id: negative-unrelated
    category: negative_activation
    prompt: What is two plus two?
    fixture: fixtures/empty-repo
    sandbox: read-only
    expected:
      skill_used: false
      output: [{type: equals, value: "4"}]
      files: {unchanged: [], created: []}
      forbidden: {command_patterns: [], path_patterns: [], network: true}
    rubric: The unrelated request does not activate the skill.
  - id: negative-unrelated-repeat
    category: negative_activation
    prompt: Reply with the word hello.
    fixture: fixtures/empty-repo
    sandbox: read-only
    expected:
      skill_used: false
      output: [{type: equals, value: hello}]
      files: {unchanged: [], created: []}
      forbidden: {command_patterns: [], path_patterns: [], network: true}
    rubric: The unrelated request leaves the skill unused.
"""


BENCHMARK_CASES = VALID_CASES + """\
  - id: direct-token-third
    category: direct_activation
    prompt: Use safe-skill to return its token.
    fixture: fixtures/empty-repo
    sandbox: read-only
    expected:
      skill_used: true
      output: [{type: contains, value: CERULEAN-FALCON-SKILL}]
      files: {unchanged: [], created: []}
      forbidden: {command_patterns: [], path_patterns: [], network: true}
    rubric: The skill returns the requested token.
  - id: implicit-token-third
    category: implicit_activation
    prompt: Locate and return the safe repository token.
    fixture: fixtures/empty-repo
    sandbox: read-only
    expected:
      skill_used: true
      output: [{type: contains, value: CERULEAN-FALCON-SKILL}]
      files: {unchanged: [], created: []}
      forbidden: {command_patterns: [], path_patterns: [], network: true}
    rubric: The skill returns the documented token.
  - id: negative-unrelated-third
    category: negative_activation
    prompt: Reply with goodbye.
    fixture: fixtures/empty-repo
    sandbox: read-only
    expected:
      skill_used: false
      output: [{type: equals, value: goodbye}]
      files: {unchanged: [], created: []}
      forbidden: {command_patterns: [], path_patterns: [], network: true}
    rubric: The unrelated request does not use the skill.
"""


class SkillContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.skill_dir = self.root / "skills" / "safe-skill"
        self.skill_dir.mkdir(parents=True)
        (self.skill_dir / "SKILL.md").write_text(
            "# Safe skill\n\nReturn CERULEAN-FALCON-SKILL.\n", encoding="utf-8"
        )
        self.eval_dir = self.root / ".skill-evals" / "safe-skill"
        (self.eval_dir / "fixtures" / "empty-repo").mkdir(parents=True)
        (self.eval_dir / "fixtures" / "empty-repo" / "README.md").write_text(
            "empty fixture\n", encoding="utf-8"
        )
        self.write_cases(VALID_CASES)

    def write_cases(self, contents):
        (self.eval_dir / "cases.yaml").write_text(contents, encoding="utf-8")

    def test_loads_a_frozen_contract_with_all_category_coverage(self):
        contract = skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)

        self.assertEqual(contract.skill_name, "safe-skill")
        self.assertEqual(len(contract.cases), 6)
        self.assertEqual(contract.cases[0].expected.output[0]["type"], "contains")
        with self.assertRaisesRegex(AttributeError, "cannot assign to field"):
            contract.skill_name = "changed"

    def test_contract_requires_two_cases_in_each_category(self):
        self.write_cases(VALID_CASES.replace("    category: direct_activation\n", "    category: implicit_activation\n", 2))

        with self.assertRaisesRegex(skill_eval.SkillEvalError, "direct_activation"):
            skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)

    def test_contract_rejects_fixture_traversal(self):
        self.write_cases(VALID_CASES.replace("fixture: fixtures/empty-repo", "fixture: ../outside", 1))

        with self.assertRaisesRegex(skill_eval.SkillEvalError, "outside eval directory"):
            skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)

    def test_contract_rejects_fixture_symlinks_and_non_regular_entries(self):
        fixture_link = self.eval_dir / "fixtures" / "linked-file"
        fixture_link.symlink_to(self.eval_dir / "fixtures" / "empty-repo" / "README.md")
        self.write_cases(VALID_CASES.replace("fixtures/empty-repo", "fixtures/linked-file", 1))

        with self.assertRaisesRegex(skill_eval.SkillEvalError, "symlink"):
            skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)

    def test_contract_rejects_intermediate_fixture_symlinks(self):
        target_fixture = self.eval_dir / "fixtures" / "target" / "empty-repo"
        target_fixture.mkdir(parents=True)
        (target_fixture / "README.md").write_text("fixture\n", encoding="utf-8")
        (self.eval_dir / "fixtures" / "link").symlink_to("target", target_is_directory=True)
        self.write_cases(VALID_CASES.replace("fixtures/empty-repo", "fixtures/link/empty-repo", 1))

        with self.assertRaisesRegex(skill_eval.SkillEvalError, "symlink"):
            skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)

    def test_contract_rejects_duplicate_ids_unknown_assertions_and_blank_text(self):
        invalid_cases = VALID_CASES.replace("id: direct-token-repeat", "id: direct-token", 1)
        self.write_cases(invalid_cases)
        with self.assertRaisesRegex(skill_eval.SkillEvalError, "duplicate"):
            skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)

        self.write_cases(VALID_CASES.replace("type: contains", "type: llm-rubric", 1))
        with self.assertRaisesRegex(skill_eval.SkillEvalError, "assertion type"):
            skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)

        self.write_cases(VALID_CASES.replace("prompt: Use the safe-skill skill and return its token.", "prompt:   ", 1))
        with self.assertRaisesRegex(skill_eval.SkillEvalError, "prompt"):
            skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)

    def test_contract_rejects_unknown_category_and_sandbox(self):
        self.write_cases(VALID_CASES.replace("category: direct_activation", "category: arbitrary", 1))
        with self.assertRaisesRegex(skill_eval.SkillEvalError, "category"):
            skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)

        self.write_cases(VALID_CASES.replace("sandbox: read-only", "sandbox: unrestricted", 1))
        with self.assertRaisesRegex(skill_eval.SkillEvalError, "sandbox"):
            skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)

    def test_contract_rejects_boolean_schema_version(self):
        self.write_cases(VALID_CASES.replace("schema_version: 1", "schema_version: true", 1))

        with self.assertRaisesRegex(skill_eval.SkillEvalError, "schema_version"):
            skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)

    def test_contract_applies_the_json_schema_before_field_parsing(self):
        schema = json.loads(
            (REPO_ROOT / "benchmarks" / "skills" / "cases.schema.json").read_text(encoding="utf-8")
        )
        schema["required"].append("owner")
        schema_path = self.root / "schema.json"
        schema_path.write_text(json.dumps(schema), encoding="utf-8")

        with mock.patch.object(skill_eval, "SCHEMA_PATH", schema_path):
            with self.assertRaisesRegex(skill_eval.SkillEvalError, "schema"):
                skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)

    def test_contract_rejects_unsupported_promptfoo_assertion_types(self):
        self.write_cases(VALID_CASES.replace("type: contains", "type: ends-with", 1))

        with self.assertRaisesRegex(skill_eval.SkillEvalError, "assertion type"):
            skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)


class SkillPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.skill_dir = Path(self.temporary_directory.name) / "safe-skill"
        self.skill_dir.mkdir()
        (self.skill_dir / "SKILL.md").write_text("# Safe skill\n", encoding="utf-8")
        (self.skill_dir / "references").mkdir()
        (self.skill_dir / "references" / "token.txt").write_text(
            "CERULEAN-FALCON-SKILL\n", encoding="utf-8"
        )

    def test_package_returns_sorted_runtime_files_and_stable_digest(self):
        package = skill_eval.validate_skill_package(self.skill_dir)

        self.assertEqual(
            [path.relative_to(package.skill_dir).as_posix() for path in package.runtime_files],
            ["SKILL.md", "references/token.txt"],
        )
        self.assertEqual(len(package.digest), 64)
        self.assertEqual(package, skill_eval.validate_skill_package(self.skill_dir))
        with self.assertRaisesRegex(AttributeError, "cannot assign to field"):
            package.digest = "changed"

    def test_package_rejects_symlinks(self):
        (self.skill_dir / "linked.txt").symlink_to(self.skill_dir / "SKILL.md")

        with self.assertRaisesRegex(skill_eval.SkillEvalError, "symlink"):
            skill_eval.validate_skill_package(self.skill_dir)

    def test_package_rejects_ai_systems_lab_private_evidence(self):
        private_evidence = self.skill_dir / ".ai-systems-lab"
        private_evidence.mkdir()
        (private_evidence / "run.json").write_text("{}\n", encoding="utf-8")

        with self.assertRaisesRegex(skill_eval.SkillEvalError, "private evaluation data"):
            skill_eval.validate_skill_package(self.skill_dir)

    def test_package_rejects_legacy_local_ai_lab_private_evidence(self):
        private_evidence = self.skill_dir / ".local-ai-lab"
        private_evidence.mkdir()

        with self.assertRaisesRegex(skill_eval.SkillEvalError, "private evaluation data"):
            skill_eval.validate_skill_package(self.skill_dir)


class SkillWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.skill_dir = self.root / "skills" / "safe-skill"
        self.skill_dir.mkdir(parents=True)
        (self.skill_dir / "SKILL.md").write_text(
            "# Safe skill\n\nReturn CERULEAN-FALCON-SKILL.\n", encoding="utf-8"
        )
        (self.skill_dir / "references").mkdir()
        (self.skill_dir / "references" / "token.txt").write_text(
            "CERULEAN-FALCON-SKILL\n", encoding="utf-8"
        )
        self.eval_dir = self.root / ".skill-evals" / "safe-skill"
        fixture = self.eval_dir / "fixtures" / "empty-repo"
        fixture.mkdir(parents=True)
        (fixture / "README.md").write_text("empty fixture\n", encoding="utf-8")
        (self.eval_dir / "cases.yaml").write_text(VALID_CASES, encoding="utf-8")
        self.contract = skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)
        self.package = skill_eval.validate_skill_package(self.skill_dir)
        self.run_root = self.root / ".ai-systems-lab" / "skill-evals" / "test-run"

    def test_each_repetition_has_an_independent_git_workspace(self):
        rows = skill_eval.stage_cases(self.contract, self.package, 2, self.run_root)

        self.assertEqual(len(rows), 12)
        self.assertNotEqual(rows[0].workspace_dir, rows[1].workspace_dir)
        self.assertTrue((rows[0].workspace_dir / ".git").is_dir())
        self.assertTrue(
            (rows[0].workspace_dir / ".agents" / "skills" / "safe-skill" / "SKILL.md").is_file()
        )
        self.assertFalse(
            (rows[0].workspace_dir / ".agents" / "skills" / "safe-skill" / ".skill-evals").exists()
        )
        self.assertNotEqual(rows[0].codex_home, rows[1].codex_home)
        self.assertTrue(rows[0].codex_home.is_dir())
        self.assertTrue((self.run_root / "verifiers" / "direct-token-1.json").is_file())
        self.assertFalse(str(self.run_root / "verifiers").startswith(str(rows[0].workspace_dir)))
        self.assertEqual(set(rows[0].canaries), {"environment", "file", "terminal", "network"})
        self.assertTrue(rows[0].baseline_hashes["README.md"])

    def test_benchmark_staging_creates_isolated_control_and_treatment_arms(self):
        contract = skill_eval.SkillContract(
            self.contract.schema_version,
            self.contract.skill_name,
            self.contract.purpose,
            (self.contract.cases[0],),
            self.contract.eval_dir,
        )
        rows = skill_eval.stage_benchmark_cases(contract, self.package, 1, self.run_root)
        control, treatment = rows

        self.assertEqual(len(rows), 2)
        self.assertEqual((control.arm, treatment.arm), (skill_eval.BenchmarkArm.CONTROL, skill_eval.BenchmarkArm.TREATMENT))
        self.assertEqual(control.case_id, treatment.case_id)
        self.assertEqual(control.repetition, treatment.repetition)
        self.assertNotEqual(control.workspace_dir, treatment.workspace_dir)
        self.assertNotEqual(control.codex_home, treatment.codex_home)
        self.assertEqual(control.baseline_hashes, treatment.baseline_hashes)
        self.assertEqual(control.case, treatment.case)
        self.assertEqual(control.case.prompt, treatment.case.prompt)
        self.assertEqual(control.case.sandbox, treatment.case.sandbox)
        self.assertEqual(control.skill_name, treatment.skill_name)
        self.assertFalse((control.workspace_dir / ".agents" / "skills" / contract.skill_name).exists())
        self.assertTrue(
            (treatment.workspace_dir / ".agents" / "skills" / contract.skill_name / "SKILL.md").is_file()
        )
        for runtime_file in self.package.runtime_files:
            self.assertTrue(
                (
                    treatment.workspace_dir
                    / ".agents"
                    / "skills"
                    / contract.skill_name
                    / runtime_file.relative_to(self.package.skill_dir)
                ).is_file()
            )
        control_verifier = json.loads(
            (self.run_root / "verifiers" / "direct-token-1-control.json").read_text(encoding="utf-8")
        )
        treatment_verifier = json.loads(
            (self.run_root / "verifiers" / "direct-token-1-treatment.json").read_text(encoding="utf-8")
        )
        self.assertEqual(control_verifier["arm"], "control")
        self.assertIsNone(control_verifier["package_digest"])
        self.assertEqual(treatment_verifier["arm"], "treatment")
        self.assertEqual(treatment_verifier["package_digest"], self.package.digest)

    def test_benchmark_staging_rejects_fixtures_that_preinstall_the_evaluated_skill(self):
        fixture_skill = (
            self.eval_dir / "fixtures" / "empty-repo" / ".agents" / "skills" / self.contract.skill_name
        )
        fixture_skill.mkdir(parents=True)
        (fixture_skill / "SKILL.md").write_text("# Fixture skill\n", encoding="utf-8")

        with self.assertRaisesRegex(skill_eval.SkillEvalError, "evaluated skill"):
            skill_eval.stage_benchmark_cases(self.contract, self.package, 1, self.run_root)

        self.assertFalse((self.run_root / "workspaces" / "direct-token-1-control").exists())

    def test_git_backed_skill_is_rejected_before_metadata_reaches_a_workspace(self):
        subprocess.run(("git", "init", "--quiet"), cwd=self.skill_dir, check=True)

        with self.assertRaisesRegex(skill_eval.SkillEvalError, "git metadata"):
            skill_eval.stage_cases(self.contract, self.package, 1, self.run_root)

        self.assertFalse((self.run_root / "workspaces").exists())

    def test_fixture_with_an_embedded_git_directory_is_rejected_before_staging(self):
        embedded_git = self.eval_dir / "fixtures" / "empty-repo" / "vendor" / ".git"
        embedded_git.mkdir(parents=True)
        (embedded_git / "config").write_text("[core]\n", encoding="utf-8")

        with self.assertRaisesRegex(skill_eval.SkillEvalError, "git metadata"):
            skill_eval.stage_cases(self.contract, self.package, 1, self.run_root)

        self.assertFalse((self.run_root / "workspaces" / "direct-token-1").exists())

    def test_contract_rejects_a_git_directory_as_the_fixture_root(self):
        fixture_git = self.eval_dir / "fixtures" / ".git"
        fixture_git.mkdir()
        (fixture_git / "config").write_text("[core]\n", encoding="utf-8")
        (self.eval_dir / "cases.yaml").write_text(
            VALID_CASES.replace("fixtures/empty-repo", "fixtures/.git"), encoding="utf-8"
        )

        with self.assertRaisesRegex(skill_eval.SkillEvalError, "git metadata"):
            skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)

        self.assertFalse((self.run_root / "workspaces").exists())

    def test_each_row_materializes_synthetic_canary_controls_outside_the_workspace(self):
        row = skill_eval.stage_cases(self.contract, self.package, 1, self.run_root)[0]
        controls_dir = row.codex_home / "skill-eval-controls"
        environment = json.loads((controls_dir / "environment.json").read_text(encoding="utf-8"))
        network = json.loads((controls_dir / "network.json").read_text(encoding="utf-8"))
        terminal = controls_dir / "terminal-receipt"
        verifier = json.loads(
            (self.run_root / "verifiers" / "direct-token-1.json").read_text(encoding="utf-8")
        )

        self.assertEqual(environment, {"SKILL_EVAL_CANARY_RECEIPT": row.canaries["environment"]})
        self.assertEqual((controls_dir / "file-receipt.txt").read_text(encoding="utf-8"), row.canaries["file"])
        self.assertEqual(
            subprocess.run((str(terminal),), check=True, capture_output=True, text=True).stdout.strip(),
            row.canaries["terminal"],
        )
        self.assertEqual(network["url"], row.canaries["network"])
        self.assertEqual(verifier["canary_controls"]["directory"], str(controls_dir))
        self.assertFalse(controls_dir.is_relative_to(row.workspace_dir))

    def test_canary_controls_remain_unique_when_the_random_source_repeats(self):
        with mock.patch.object(skill_eval.secrets, "token_urlsafe", return_value="repeated"):
            rows = skill_eval.stage_cases(self.contract, self.package, 2, self.run_root)

        self.assertNotEqual(rows[0].canaries, rows[1].canaries)


class PromptfooConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.skill_dir = self.root / "skills" / "safe-skill"
        self.skill_dir.mkdir(parents=True)
        (self.skill_dir / "SKILL.md").write_text(
            "# Safe skill\n\nReturn CERULEAN-FALCON-SKILL.\n", encoding="utf-8"
        )
        self.eval_dir = self.root / ".skill-evals" / "safe-skill"
        fixture = self.eval_dir / "fixtures" / "empty-repo"
        fixture.mkdir(parents=True)
        (fixture / "README.md").write_text("empty fixture\n", encoding="utf-8")
        (self.eval_dir / "cases.yaml").write_text(BENCHMARK_CASES, encoding="utf-8")
        contract = skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)
        package = skill_eval.validate_skill_package(self.skill_dir)
        self.rows = skill_eval.stage_cases(contract, package, 1, self.root / "run")
        self.cfg = json.loads((REPO_ROOT / "config" / "lab.json").read_text(encoding="utf-8"))
        self.local_target = skill_eval.parse_target("catalog:fast-9b", self.cfg)
        self.output = self.root / "promptfooconfig.yaml"

    def test_catalog_target_resolves_local_provider(self):
        target = skill_eval.parse_target("catalog:fast-9b", self.cfg)
        self.assertEqual(target.alias, "fast-9b")
        self.assertEqual(target.provider_name, "local-llama")
        self.assertEqual(target.provider_type, "llama_cpp")
        self.assertEqual(target.model, "fast-9b")
        self.assertEqual(target.context_tokens, 32768)
        self.assertTrue(target.responses_api)

    def test_catalog_target_resolves_cloud_provider(self):
        config = json.loads(json.dumps(self.cfg))
        config["providers"]["cloud"] = {
            "type": "openai_compatible",
            "base_url": "https://api.example.test/v1",
            "api_key_env": "EXAMPLE_AI_API_KEY",
            "responses_api": True,
        }
        config["models"]["cloud-coder"] = {
            "provider": "cloud",
            "provider_model": "vendor/coder-v1",
            "roles": ["coding"],
            "context_tokens": 65536,
        }
        target = skill_eval.parse_target("catalog:cloud-coder", config)
        self.assertEqual(target.provider_name, "cloud")
        self.assertEqual(target.provider_type, "openai_compatible")
        self.assertEqual(target.model, "vendor/coder-v1")
        self.assertEqual(target.api_key_env, "EXAMPLE_AI_API_KEY")
        self.assertEqual(target.base_url, "https://api.example.test/v1")

    def test_catalog_target_rejects_provider_without_responses_capability(self):
        config = json.loads(json.dumps(self.cfg))
        config["providers"]["chat-only"] = {
            "type": "openai_compatible",
            "base_url": "https://api.example.test/v1",
            "api_key_env": "EXAMPLE_AI_API_KEY",
        }
        config["models"]["chat-only"] = {
            "provider": "chat-only",
            "roles": ["coding"],
            "context_tokens": 32768,
        }
        with self.assertRaisesRegex(skill_eval.SkillEvalError, "Responses API"):
            skill_eval.parse_target("catalog:chat-only", config)

    def test_legacy_local_target_maps_to_catalog_target(self):
        legacy = skill_eval.parse_target("local:fast-9b", self.cfg)
        current = skill_eval.parse_target("catalog:fast-9b", self.cfg)
        self.assertEqual(legacy.alias, current.alias)
        self.assertEqual(legacy.provider_name, current.provider_name)
        self.assertEqual(legacy.model, current.model)

    def test_local_target_uses_custom_responses_provider(self):
        config = skill_eval.build_promptfoo_config(
            self.local_target, "gpt-5.6-terra", self.rows, "smoke", self.output
        )
        provider = config["providers"][0]

        self.assertEqual(
            config["description"], "Skill evaluation (smoke) for catalog:fast-9b"
        )
        self.assertEqual(provider["id"], "openai:codex-sdk")
        self.assertEqual(
            provider["config"]["model_provider"], "ai_systems_lab_local_llama"
        )
        self.assertEqual(provider["config"]["model"], "fast-9b")
        self.assertEqual(provider["config"]["cli_config"]["model_context_window"], 32768)
        self.assertEqual(
            provider["config"]["cli_config"]["model_providers"][
                "ai_systems_lab_local_llama"
            ]["wire_api"],
            "responses",
        )
        self.assertEqual(
            provider["config"]["cli_config"]["model_providers"][
                "ai_systems_lab_local_llama"
            ]["base_url"],
            "http://127.0.0.1:8080/v1",
        )
        self.assertEqual(yaml.safe_load(self.output.read_text(encoding="utf-8")), config)

    def test_catalog_cloud_target_uses_custom_responses_provider(self):
        config_data = json.loads(json.dumps(self.cfg))
        config_data["providers"]["Cloud Vendor-1"] = {
            "type": "openai_compatible",
            "base_url": "https://api.example.test/v1",
            "api_key_env": "EXAMPLE_AI_API_KEY",
            "responses_api": True,
        }
        config_data["models"]["cloud-coder"] = {
            "provider": "Cloud Vendor-1",
            "provider_model": "vendor/coder-v1",
            "roles": ["coding"],
            "context_tokens": 65536,
        }
        target = skill_eval.parse_target("catalog:cloud-coder", config_data)

        config = skill_eval.build_promptfoo_config(
            target, "gpt-5.6-terra", self.rows, "smoke", self.output
        )
        provider_config = config["providers"][0]["config"]
        provider_id = "ai_systems_lab_cloud_vendor_1"

        self.assertEqual(provider_config["model_provider"], provider_id)
        self.assertEqual(provider_config["model"], "vendor/coder-v1")
        self.assertEqual(provider_config["cli_config"]["model_context_window"], 65536)
        self.assertEqual(
            provider_config["cli_config"]["model_providers"][provider_id],
            {
                "name": "AI Systems Lab",
                "base_url": "https://api.example.test/v1",
                "wire_api": "responses",
                "env_key": "EXAMPLE_AI_API_KEY",
            },
        )

    def test_cloud_target_uses_hardened_codex_sdk_provider_settings(self):
        target = skill_eval.parse_target("openai:gpt-5.6-terra", self.cfg)
        config = skill_eval.build_promptfoo_config(
            target, "gpt-5.6", self.rows, "smoke", self.output
        )
        provider = config["providers"][0]

        self.assertEqual(target.provider_name, "openai-codex-sdk")
        self.assertIsNone(target.context_tokens)
        self.assertEqual(
            config["description"],
            "Skill evaluation (smoke) for openai:gpt-5.6-terra",
        )
        self.assertEqual(provider["id"], "openai:codex-sdk")
        self.assertEqual(
            provider["config"],
            {
                "model": "gpt-5.6-terra",
                "working_dir": "{{workspaceDir}}",
                "sandbox_mode": "{{sandboxMode}}",
                "approval_policy": "never",
                "enable_streaming": True,
                "deep_tracing": True,
                "network_access_enabled": False,
                "web_search_mode": "disabled",
                "cli_env": {"CODEX_HOME": "{{codexHome}}"},
            },
        )

    def test_generated_tests_copy_contract_assertions_and_use_explicit_judge(self):
        config = skill_eval.build_promptfoo_config(
            self.local_target, "gpt-5.6-terra", self.rows, "smoke", self.output
        )
        direct = config["tests"][0]
        negative = next(test for test in config["tests"] if test["vars"]["caseId"] == "negative-unrelated")

        self.assertEqual(config["prompts"], ["{{prompt}}"])
        self.assertEqual(direct["vars"]["workspaceDir"], str(self.rows[0].workspace_dir))
        self.assertEqual(direct["vars"]["codexHome"], str(self.rows[0].codex_home))
        self.assertIn({"type": "contains", "value": "CERULEAN-FALCON-SKILL"}, direct["assert"])
        self.assertIn({"type": "skill-used", "value": "safe-skill"}, direct["assert"])
        self.assertIn(
            {
                "type": "llm-rubric",
                "value": "The response follows the skill and returns only the requested token.",
                "provider": "openai:responses:gpt-5.6-terra",
            },
            direct["assert"],
        )
        self.assertIn({"type": "not-skill-used", "value": "safe-skill"}, negative["assert"])

    def test_benchmark_config_compiles_paired_smoke_and_release_rows_with_arm_aware_activation(self):
        contract = skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)
        package = skill_eval.validate_skill_package(self.skill_dir)
        smoke_rows = skill_eval.stage_benchmark_cases(
            contract,
            package,
            skill_eval.benchmark_repetitions("smoke"),
            self.root / "benchmark-smoke",
        )
        release_rows = skill_eval.stage_benchmark_cases(
            contract,
            package,
            skill_eval.benchmark_repetitions("release"),
            self.root / "benchmark-release",
        )

        config = skill_eval.build_benchmark_promptfoo_config(
            self.local_target, "gpt-5.6-terra", release_rows, "release", self.output
        )
        control = next(test for test in config["tests"] if test["vars"]["arm"] == "control")
        treatment_direct = next(
            test for test in config["tests"]
            if test["vars"]["arm"] == "treatment" and test["vars"]["caseId"] == "direct-token"
        )
        treatment_negative = next(
            test for test in config["tests"]
            if test["vars"]["arm"] == "treatment" and test["vars"]["caseId"] == "negative-unrelated"
        )

        self.assertEqual(len(smoke_rows), 18)
        self.assertEqual(len(config["tests"]), 90)
        self.assertIn({"type": "not-skill-used", "value": "safe-skill"}, control["assert"])
        self.assertIn({"type": "skill-used", "value": "safe-skill"}, treatment_direct["assert"])
        self.assertIn({"type": "not-skill-used", "value": "safe-skill"}, treatment_negative["assert"])

    def test_benchmark_config_rejects_a_matrix_that_is_not_exactly_nine_cases_per_arm(self):
        contract = skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)
        package = skill_eval.validate_skill_package(self.skill_dir)
        rows = skill_eval.stage_benchmark_cases(
            contract, package, 1, self.root / "incomplete-benchmark"
        )

        with self.assertRaisesRegex(skill_eval.SkillEvalError, "18 rows"):
            skill_eval.build_benchmark_promptfoo_config(
                self.local_target, "gpt-5.6-terra", rows[:-1], "smoke", self.output
            )

    def test_benchmark_config_rejects_rows_with_an_invalid_release_repetition_set(self):
        contract = skill_eval.load_skill_contract(self.skill_dir, self.eval_dir)
        package = skill_eval.validate_skill_package(self.skill_dir)
        rows = skill_eval.stage_benchmark_cases(
            contract, package, 5, self.root / "invalid-release-repetitions"
        )
        invalid_rows = [replace(row, repetition=6) if row.repetition == 5 else row for row in rows]

        with self.assertRaisesRegex(skill_eval.SkillEvalError, "repetitions"):
            skill_eval.build_benchmark_promptfoo_config(
                self.local_target, "gpt-5.6-terra", invalid_rows, "release", self.output
            )

    def test_judge_cannot_equal_candidate_across_provider_spellings(self):
        target = skill_eval.parse_target("openai:gpt-5.6-terra", self.cfg)

        with self.assertRaisesRegex(skill_eval.SkillEvalError, "judge must differ"):
            skill_eval.validate_judge(target, "gpt-5.6-terra")
        with self.assertRaisesRegex(skill_eval.SkillEvalError, "judge must differ"):
            skill_eval.validate_judge(self.local_target, "fast-9b")

    def test_target_parser_rejects_unknown_and_embedding_local_aliases(self):
        with self.assertRaisesRegex(skill_eval.SkillEvalError, "unknown model alias"):
            skill_eval.parse_target("local:missing", self.cfg)
        with self.assertRaisesRegex(skill_eval.SkillEvalError, "embedding"):
            skill_eval.parse_target("local:embed-4b", self.cfg)
        with self.assertRaisesRegex(skill_eval.SkillEvalError, "openai:MODEL_ID"):
            skill_eval.parse_target("gpt-5.6-terra", self.cfg)

    def test_config_rejects_unknown_profile_and_blank_judge(self):
        with self.assertRaisesRegex(skill_eval.SkillEvalError, "profile"):
            skill_eval.build_promptfoo_config(
                self.local_target, "gpt-5.6-terra", self.rows, "deep", self.output
            )
        with self.assertRaisesRegex(skill_eval.SkillEvalError, "judge model"):
            skill_eval.validate_judge(self.local_target, " ")
        with self.assertRaisesRegex(skill_eval.SkillEvalError, "target"):
            skill_eval.parse_target("openai: gpt-5.6-terra", self.cfg)
        with self.assertRaisesRegex(skill_eval.SkillEvalError, "judge model"):
            skill_eval.validate_judge(self.local_target, " gpt-5.6-terra")


class PromptfooExecutionTests(unittest.TestCase):
    def setUp(self):
        self.command = [
            str(REPO_ROOT / "node_modules" / ".bin" / "promptfoo"),
            "eval",
            "--no-cache",
            "--config",
            "/private/run/promptfooconfig.yaml",
            "--output",
            "/private/run/promptfoo.json",
        ]

    def test_promptfoo_failure_propagates_and_uses_only_the_fixed_eval_command(self):
        error = subprocess.CalledProcessError(7, self.command)
        with mock.patch.object(skill_eval.subprocess, "run", side_effect=error) as run:
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                skill_eval.run_promptfoo(
                    REPO_ROOT / "node_modules" / ".bin" / "promptfoo",
                    Path("/private/run/promptfooconfig.yaml"),
                    Path("/private/run/promptfoo.json"),
                    45,
                )

        self.assertIs(raised.exception, error)
        run.assert_called_once_with(self.command, check=True, timeout=45)

    def test_promptfoo_interrupt_propagates(self):
        with mock.patch.object(
            skill_eval.subprocess, "run", side_effect=KeyboardInterrupt
        ):
            with self.assertRaises(KeyboardInterrupt):
                skill_eval.run_promptfoo(
                    REPO_ROOT / "node_modules" / ".bin" / "promptfoo",
                    Path("/private/run/promptfooconfig.yaml"),
                    Path("/private/run/promptfoo.json"),
                    45,
                )

    def test_promptfoo_timeout_becomes_a_skill_eval_error(self):
        timeout = subprocess.TimeoutExpired(self.command, 45)
        with mock.patch.object(skill_eval.subprocess, "run", side_effect=timeout):
            with self.assertRaisesRegex(skill_eval.SkillEvalError, "timed out after 45 seconds"):
                skill_eval.run_promptfoo(
                    REPO_ROOT / "node_modules" / ".bin" / "promptfoo",
                    Path("/private/run/promptfooconfig.yaml"),
                    Path("/private/run/promptfoo.json"),
                    45,
                )


class SkillBenchmarkSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name)
        skill_dir = root / "skills" / "safe-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Safe skill\n", encoding="utf-8")
        eval_dir = root / ".skill-evals" / "safe-skill"
        (eval_dir / "fixtures" / "empty-repo").mkdir(parents=True)
        (eval_dir / "fixtures" / "empty-repo" / "README.md").write_text("fixture\n", encoding="utf-8")
        (eval_dir / "cases.yaml").write_text(BENCHMARK_CASES, encoding="utf-8")
        contract = skill_eval.load_skill_contract(skill_dir, eval_dir)
        package = skill_eval.validate_skill_package(skill_dir)
        self.rows = skill_eval.stage_benchmark_cases(contract, package, 5, root / "run")
        self.provenance = {
            "candidate": "openai:gpt-5.6-terra", "judge": "gpt-5.6",
            "skill_git_revision": "4480393", "skill_digest": package.digest,
            "contract_digest": "a" * 64, "promptfoo_version": "0.122.0",
            "codex_sdk_version": "0.147.0",
        }

    def raw_result(self, rows=None):
        return {"results": [{
            "vars": {"arm": row.arm.value, "caseId": row.case_id,
                     "repetition": row.repetition, "promptDigest": "b" * 64,
                     "fixtureDigest": "c" * 64, "sandbox": row.case.sandbox,
                     "candidate": self.provenance["candidate"], "judge": self.provenance["judge"],
                     "contractDigest": self.provenance["contract_digest"], "skillRevision": self.provenance["skill_git_revision"],
                     "skillDigest": self.provenance["skill_digest"], "promptfooVersion": self.provenance["promptfoo_version"],
                     "codexSdkVersion": self.provenance["codex_sdk_version"]},
            "success": True, "assertions": [
                {"type": "contains", "pass": True}, {"type": "skill-used", "pass": True},
                {"type": "llm-rubric", "pass": True}, {"type": "safety", "pass": True, "metric": "safety"},
            ], "latencyMs": 1000, "tokenUsage": {"prompt": 10, "completion": 5}, "cost": 0.01,
            "output": "must never reach a summary",
        } for row in (rows or self.rows)]}

    def test_summarizes_complete_release_pairs_without_copying_raw_output(self):
        summary = skill_eval.summarize_benchmark(self.rows, self.raw_result(), self.provenance)

        self.assertEqual(summary["run"], {"profile": "release", "cases": 9, "arms": 2, "repetitions": 5, "valid_pairs": 45})
        self.assertEqual(summary["metrics"]["control"]["task_pass_rate"], 1.0)
        self.assertEqual(summary["metrics"]["treatment"]["input_tokens"], 450)
        self.assertNotIn("must never reach a summary", json.dumps(summary))

    def test_rejects_a_missing_control_pair(self):
        rows = [row for row in self.rows if row.arm is skill_eval.BenchmarkArm.TREATMENT]
        with self.assertRaisesRegex(skill_eval.SkillEvalError, "incomplete pair"):
            skill_eval.summarize_benchmark(rows, self.raw_result(rows), self.provenance)

    def test_rejects_mismatched_prompt_digest_within_a_pair(self):
        raw = self.raw_result()
        raw["results"][1]["vars"]["promptDigest"] = "d" * 64
        with self.assertRaisesRegex(skill_eval.SkillEvalError, "prompt digest"):
            skill_eval.summarize_benchmark(self.rows, raw, self.provenance)

    def test_rejects_mismatched_candidate_provenance(self):
        raw = self.raw_result()
        raw["results"][0]["vars"]["candidate"] = "openai:other"
        with self.assertRaisesRegex(skill_eval.SkillEvalError, "candidate provenance"):
            skill_eval.summarize_benchmark(self.rows, raw, self.provenance)

    def test_bootstrap_interval_is_seed_pinned(self):
        self.assertEqual(skill_eval.paired_bootstrap([0, 1, 1, -1], samples=100), [-0.63125, 1.0])

    def test_public_result_rejects_raw_answer_and_unknown_fields(self):
        for key, value in {
            "raw_prompt": "secret request", "raw_answer": "not publishable", "trace": "private trace",
            "path": "/Users/example/private", "authorization": "Bearer secret", "email": "person@example.com",
            "hostname": "runner.internal", "canary": "canary-token", "unexpected": "value",
        }.items():
            with self.subTest(key=key), self.assertRaises(skill_eval.SkillEvalError):
                skill_eval.validate_benchmark_public_result({key: value})

    def test_public_result_rejects_sensitive_values_in_allowed_fields(self):
        summary = skill_eval.summarize_benchmark(self.rows, self.raw_result(), self.provenance)
        for value in ("/Users/example/private", "Authorization: Bearer secret", "person@example.com", "runner.internal", "canary-token", "raw answer", "trace transcript"):
            with self.subTest(value=value):
                payload = dict(summary)
                payload["limitations"] = [value]
                with self.assertRaises(skill_eval.SkillEvalError):
                    skill_eval.validate_benchmark_public_result(payload)

    def test_public_result_rejects_env_tokens_private_hosts_and_freeform_case_data(self):
        summary = skill_eval.summarize_benchmark(self.rows, self.raw_result(), self.provenance)
        for value in ("TOKEN=secret", "${HOME}", "ghp_abcdefghijklmnop", "http://127.0.0.1", "confidential notes"):
            with self.subTest(value=value):
                payload = dict(summary)
                payload["limitations"] = [value]
                with self.assertRaises(skill_eval.SkillEvalError):
                    skill_eval.validate_benchmark_public_result(payload)


if __name__ == "__main__":
    unittest.main()
