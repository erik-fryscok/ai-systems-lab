import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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

    def test_package_rejects_private_evidence(self):
        private_evidence = self.skill_dir / ".local-ai-lab"
        private_evidence.mkdir()
        (private_evidence / "run.json").write_text("{}\n", encoding="utf-8")

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
        self.run_root = self.root / ".local-ai-lab" / "skill-evals" / "test-run"

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


if __name__ == "__main__":
    unittest.main()
