import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ai_systems_lab.providers import ProviderConfigError


REPO_ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("ai_systems_lab_cli", str(REPO_ROOT / "scripts" / "lab"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
lab = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(lab)


class BrandingTests(unittest.TestCase):
    def test_project_metadata_uses_new_identity(self):
        metadata = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('name = "ai-systems-lab"', metadata)
        self.assertIn("github.com/erik-fryscok/ai-systems-lab", metadata)
        self.assertTrue(readme.startswith("# AI Systems Lab\n"))
        self.assertIn("not production infrastructure", readme)
        self.assertIn("local", readme.lower())
        self.assertIn("cloud", readme.lower())


class IdentityMigrationTests(unittest.TestCase):
    def test_new_environment_name_wins_over_legacy_name(self):
        with mock.patch.dict(
            os.environ,
            {
                "AI_SYSTEMS_LAB_CONFIG": "/new/config.json",
                "LOCAL_AI_LAB_CONFIG": "/legacy/config.json",
            },
            clear=False,
        ):
            self.assertEqual(lab.project_env("CONFIG"), "/new/config.json")

    def test_empty_new_environment_value_still_wins_over_legacy_value(self):
        with mock.patch.dict(
            os.environ,
            {
                "AI_SYSTEMS_LAB_CONFIG": "",
                "LOCAL_AI_LAB_CONFIG": "/legacy/config.json",
            },
            clear=True,
        ):
            self.assertEqual(lab.project_env("CONFIG"), "")

    def test_legacy_environment_name_remains_a_read_fallback(self):
        with mock.patch.dict(
            os.environ,
            {"LOCAL_AI_LAB_CONFIG": "/legacy/config.json"},
            clear=True,
        ):
            self.assertEqual(lab.project_env("CONFIG"), "/legacy/config.json")

    def test_existing_legacy_models_directory_is_used_when_new_directory_is_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "local-ai-lab"
            legacy.mkdir()
            config = {
                "paths": {
                    "models_dir": str(root / "ai-systems-lab"),
                }
            }
            with mock.patch.object(lab, "LEGACY_MODELS_DIR", legacy):
                self.assertEqual(lab.paths(config)["models_dir"], legacy.resolve())

    def test_readme_migration_requires_an_absent_new_models_directory(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "Only run the `mv` command when `~/Models/ai-systems-lab` does not exist.",
            readme,
        )
        self.assertIn(
            "already exists, do not move the legacy directory automatically.",
            readme,
        )
        self.assertIn(
            "runtime continues its legacy fallback/read",
            readme,
        )
        self.assertIn(
            "manually merge verified model\ndirectories",
            readme,
        )

    def test_pull_writes_to_new_models_directory_when_reads_fall_back_to_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            new_models = root / "ai-systems-lab"
            legacy_models = root / "local-ai-lab"
            legacy_models.mkdir()
            config = {
                "providers": {"local": {"type": "llama_cpp"}},
                "paths": {
                    "models_dir": str(new_models),
                    "legacy_models_dir": str(legacy_models),
                },
                "models": {
                    "model": {
                        "provider": "local",
                        "repo_id": "example/model",
                        "files": ["model.gguf"],
                        "local_dir": "model",
                    }
                },
            }

            def download(command, check):
                target = Path(command[command.index("--local-dir") + 1])
                (target / "model.gguf").touch()

            with mock.patch.object(lab, "hf_binary", return_value="/test/hf"), mock.patch.object(
                lab.subprocess, "run", side_effect=download
            ):
                lab.pull_one(config, "model")

            self.assertTrue((new_models / "model" / "model.gguf").exists())
            self.assertFalse((legacy_models / "model").exists())

    def test_new_service_identity_is_used_for_writes(self):
        self.assertEqual(lab.SERVICE_LABEL, "com.erik.ai-systems-lab")
        self.assertEqual(lab.LEGACY_SERVICE_LABEL, "com.erik.local-ai-lab")

    def test_offline_server_message_uses_new_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_path = root / "model.gguf"
            model_path.touch()
            config = {
                "providers": {"local": {"type": "llama_cpp"}},
                "server": {},
                "paths": {"models_dir": str(root)},
                "models": {
                    "model": {
                        "provider": "local",
                        "files": ["model.gguf"],
                        "local_dir": ".",
                    }
                },
            }
            launch_agent_path = mock.Mock()
            launch_agent_path.exists.return_value = False
            with mock.patch.object(lab, "update_service_state"), mock.patch.object(
                lab, "api_is_ready", return_value=False
            ), mock.patch.object(lab, "LAUNCH_AGENT_PATH", launch_agent_path):
                with self.assertRaisesRegex(lab.LabError, "AI Systems Lab server is offline"):
                    lab.cmd_load(Namespace(selector="model", timeout=1), config)

    def test_legacy_state_is_read_only_when_new_state_is_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            new_path = root / "new" / "state.json"
            legacy_path = root / "legacy" / "state.json"
            legacy_path.parent.mkdir()
            legacy_path.write_text(json.dumps({"auto_idle_seconds": 120}), encoding="utf-8")
            with mock.patch.object(lab, "SERVICE_STATE_PATH", new_path), mock.patch.object(
                lab, "LEGACY_SERVICE_STATE_PATH", legacy_path
            ):
                self.assertEqual(lab.load_service_state()["auto_idle_seconds"], 120)
                self.assertFalse(new_path.exists())
                lab.save_service_state(lab.load_service_state())
            self.assertTrue(new_path.exists())
            self.assertTrue(legacy_path.exists())

    def test_legacy_state_environment_path_is_read_only_and_save_migrates_to_new_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            new_path = root / "new" / "state.json"
            legacy_path = root / "legacy" / "state.json"
            legacy_path.parent.mkdir()
            legacy_text = json.dumps({"auto_idle_seconds": 120})
            legacy_path.write_text(legacy_text, encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {"LOCAL_AI_LAB_STATE_PATH": str(legacy_path)},
                clear=True,
            ), mock.patch.object(lab, "SERVICE_STATE_PATH", new_path):
                state = lab.load_service_state()
                state["auto_idle_seconds"] = 121
                lab.save_service_state(state)

            self.assertEqual(legacy_path.read_text(encoding="utf-8"), legacy_text)
            self.assertEqual(
                json.loads(new_path.read_text(encoding="utf-8"))["auto_idle_seconds"], 121
            )

    def test_service_install_rejects_legacy_plist_before_stopping_anything(self):
        legacy_path = mock.Mock()
        legacy_path.exists.return_value = True
        with mock.patch.object(lab, "LEGACY_LAUNCH_AGENT_PATH", legacy_path), mock.patch.object(
            lab, "service_is_legacy_loaded"
        ) as legacy_loaded, mock.patch.object(lab, "stop_ad_hoc_server") as stop_server:
            with self.assertRaisesRegex(lab.LabError, "service-uninstall-legacy"):
                lab.cmd_service_install(Namespace(wait=15, force=False, startup_wait=180), {"models": {}})
        legacy_loaded.assert_not_called()
        stop_server.assert_not_called()

    def test_service_install_rejects_active_legacy_service_without_plist(self):
        legacy_path = mock.Mock()
        legacy_path.exists.return_value = False
        with mock.patch.object(lab, "LEGACY_LAUNCH_AGENT_PATH", legacy_path), mock.patch.object(
            lab, "service_is_legacy_loaded", return_value=True
        ), mock.patch.object(lab, "stop_ad_hoc_server") as stop_server:
            with self.assertRaisesRegex(lab.LabError, "com\\.erik\\.local-ai-lab"):
                lab.cmd_service_install(Namespace(wait=15, force=False, startup_wait=180), {"models": {}})
        stop_server.assert_not_called()

    def test_legacy_service_uninstall_only_boots_out_legacy_target_and_unlinks_legacy_plist(self):
        legacy_path = mock.Mock()
        legacy_path.exists.return_value = True
        output = io.StringIO()
        with mock.patch.object(lab, "LEGACY_LAUNCH_AGENT_PATH", legacy_path), mock.patch.object(
            lab.subprocess, "run"
        ) as run, redirect_stdout(output):
            lab.cmd_service_uninstall_legacy(Namespace(), {})

        run.assert_called_once_with(
            ["launchctl", "bootout", f"gui/{os.getuid()}/com.erik.local-ai-lab"], check=False
        )
        legacy_path.unlink.assert_called_once_with()
        self.assertIn("legacy service removed: com.erik.local-ai-lab", output.getvalue())


class ConfigTests(unittest.TestCase):
    def test_skill_eval_dependencies_require_project_promptfoo(self):
        with mock.patch.object(lab, "which", return_value=None):
            with self.assertRaisesRegex(lab.LabError, "npm ci"):
                lab.require_skill_eval_dependencies()

    def test_skill_eval_dependencies_reject_nested_sdk_version_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package-lock.json").write_text(
                json.dumps(
                    {
                        "packages": {
                            "node_modules/@openai/codex-sdk": {"version": "0.147.0"},
                            "node_modules/promptfoo/node_modules/@openai/codex-sdk": {
                                "version": "0.144.6"
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            promptfoo = root / "node_modules" / ".bin" / "promptfoo"
            with mock.patch.object(lab, "REPO_ROOT", root), mock.patch.object(
                lab, "which", return_value=str(promptfoo)
            ):
                with self.assertRaisesRegex(lab.LabError, "npm ci"):
                    lab.require_skill_eval_dependencies()

    def test_responses_preflight_reports_incompatible_server(self):
        with mock.patch.object(
            lab,
            "json_request",
            side_effect=lab.LabHttpError("POST", "http://127.0.0.1:8080/v1/responses", 404, "missing"),
        ):
            with self.assertRaisesRegex(lab.LabError, "/v1/responses"):
                lab.verify_responses_endpoint(
                    {"server": {"host": "127.0.0.1", "port": 8080}},
                    5,
                )

    def test_doctor_prints_resolved_skill_eval_tool_versions(self):
        config = {
            "_config_path": "test-config.json",
            "paths": {},
            "server": {"host": "127.0.0.1", "port": 8080},
            "benchmarks": {},
        }
        completed = mock.Mock(stdout="0.122.0\n", stderr="", returncode=0)
        output = io.StringIO()

        with mock.patch.object(lab, "validate_catalog_config"), mock.patch.object(
            lab, "which", return_value="/tool"
        ), mock.patch.object(lab, "hf_binary", return_value="/tool"), mock.patch.object(
            lab,
            "skill_eval_dependencies",
            return_value={
                "promptfoo": "/repo/node_modules/.bin/promptfoo",
                "codex_sdk": "0.147.0",
            },
        ), mock.patch.object(lab.subprocess, "run", return_value=completed), redirect_stdout(output):
            lab.cmd_doctor(Namespace(), config)

        self.assertIn("promptfoo: 0.122.0", output.getvalue())
        self.assertIn("codex sdk: 0.147.0", output.getvalue())

    def test_deep_merge_preserves_unrelated_nested_values(self):
        merged = lab.deep_merge(
            {"server": {"host": "127.0.0.1", "port": 8080}, "models": {"a": {"status": "core"}}},
            {"server": {"port": 9090}, "models": {"a": {"path": "${home}/a.gguf"}}},
        )

        self.assertEqual(merged["server"], {"host": "127.0.0.1", "port": 9090})
        self.assertEqual(merged["models"]["a"]["status"], "core")
        self.assertEqual(merged["models"]["a"]["path"], "${home}/a.gguf")

    def test_load_config_applies_explicit_local_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "lab.json"
            overlay = root / "machine.json"
            base.write_text(
                json.dumps({"models": {"a": {"status": "core"}}, "server": {"port": 8080}}),
                encoding="utf-8",
            )
            overlay.write_text(
                json.dumps({"models": {"a": {"path": "${home}/a.gguf"}}}),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"LOCAL_AI_LAB_LOCAL_CONFIG": str(overlay)},
                clear=False,
            ):
                config = lab.load_config(base)

        self.assertEqual(config["models"]["a"]["status"], "core")
        self.assertEqual(config["models"]["a"]["path"], "${home}/a.gguf")
        self.assertEqual(config["_local_config_path"], str(overlay.resolve()))


class InferenceProviderTests(unittest.TestCase):
    def cloud_config(self):
        return {
            "server": {"host": "127.0.0.1", "port": 8080},
            "providers": {
                "cloud": {
                    "type": "openai_compatible",
                    "base_url": "https://api.example.test/v1",
                    "api_key_env": "EXAMPLE_AI_API_KEY",
                }
            },
            "models": {
                "cloud-coder": {
                    "provider": "cloud",
                    "provider_model": "vendor/coder-v1",
                }
            },
        }

    def test_cloud_chat_uses_remote_url_and_skips_local_residency(self):
        response = {
            "choices": [{"finish_reason": "stop", "message": {"content": "hello"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        }
        with mock.patch.dict(os.environ, {"EXAMPLE_AI_API_KEY": "secret-value"}, clear=False):
            with mock.patch.object(lab, "json_request", return_value=response) as request:
                with mock.patch.object(lab, "switch_to_model") as switch:
                    result = lab.chat_completion(
                        self.cloud_config(),
                        "cloud-coder",
                        {"messages": [{"role": "user", "content": "hello"}]},
                        64,
                        0.2,
                        30,
                    )
        switch.assert_not_called()
        self.assertEqual(result["text"], "hello")
        self.assertIsNone(result["model_worker_peak_rss_gib"])
        args, kwargs = request.call_args
        self.assertEqual(args[1], "https://api.example.test/v1/chat/completions")
        self.assertEqual(args[2]["model"], "vendor/coder-v1")
        self.assertEqual(kwargs["headers"], {"Authorization": "Bearer secret-value"})

    def test_local_chat_keeps_switch_and_memory_sampling(self):
        config = {
            "server": {"host": "127.0.0.1", "port": 8080},
            "providers": {"local": {"type": "llama_cpp"}},
            "models": {"fast": {"provider": "local"}},
        }
        response = {
            "choices": [{"finish_reason": "stop", "message": {"content": "local"}}],
            "usage": {"completion_tokens": 1},
        }
        with mock.patch.object(lab, "switch_to_model") as switch:
            with mock.patch.object(
                lab,
                "run_with_server_memory_sample",
                return_value=(response, 2.5),
            ):
                result = lab.chat_completion(
                    config,
                    "fast",
                    {"messages": [{"role": "user", "content": "hello"}]},
                    64,
                    0.2,
                    30,
                )
        switch.assert_called_once_with(config, "fast", timeout=30)
        self.assertEqual(result["text"], "local")
        self.assertEqual(result["model_worker_peak_rss_gib"], 2.5)

    def test_cmd_chat_prints_cloud_response_without_switching(self):
        response = {
            "choices": [{"finish_reason": "stop", "message": {"content": "cloud answer"}}],
            "usage": {"completion_tokens": 2},
        }
        args = Namespace(
            selector="cloud-coder",
            prompt="hello",
            max_tokens=64,
            temperature=0.2,
            timeout=30,
        )
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"EXAMPLE_AI_API_KEY": "secret-value"}, clear=False):
            with mock.patch.object(lab, "json_request", return_value=response):
                with mock.patch.object(lab, "switch_to_model") as switch:
                    with redirect_stdout(output):
                        lab.cmd_chat(args, self.cloud_config())
        switch.assert_not_called()
        self.assertIn("cloud answer", output.getvalue())

    def test_server_benchmark_records_cloud_provider_without_memory_sample(self):
        response = {
            "choices": [{"finish_reason": "stop", "message": {"content": "cloud answer"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt_path = root / "prompts.jsonl"
            prompt_path.write_text(
                json.dumps({"name": "smoke", "messages": [{"role": "user", "content": "hello"}]}) + "\n",
                encoding="utf-8",
            )
            config = self.cloud_config()
            config["paths"] = {"results_dir": str(root / "results")}
            config["benchmarks"] = {"server_repetitions": 1}
            config["_config_path"] = str(root / "config.json")
            args = Namespace(
                selector="cloud-coder",
                all_candidates=False,
                skip_missing=False,
                prompt_file=str(prompt_path),
                repetitions=1,
                max_tokens=64,
                temperature=0.2,
                timeout=30,
                unload_after=False,
            )
            with mock.patch.dict(os.environ, {"EXAMPLE_AI_API_KEY": "secret-value"}, clear=False):
                with mock.patch.object(lab, "json_request", return_value=response):
                    with mock.patch.object(lab, "write_metadata"):
                        with redirect_stdout(io.StringIO()):
                            lab.cmd_bench_server(args, config)
            result_path = next((root / "results").glob("*-server-cloud-coder/results.jsonl"))
            row = json.loads(result_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["provider"], "cloud")
        self.assertEqual(row["provider_model"], "vendor/coder-v1")
        self.assertIsNone(row["model_worker_peak_rss_gib"])

    def test_quality_benchmark_runs_cloud_candidate_without_local_residency(self):
        response = {
            "choices": [{"finish_reason": "stop", "message": {"content": "cloud answer"}}],
            "usage": {"completion_tokens": 2},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt_path = root / "prompts.jsonl"
            prompt_path.write_text(
                json.dumps({"name": "smoke", "messages": [{"role": "user", "content": "hello"}]}) + "\n",
                encoding="utf-8",
            )
            config = self.cloud_config()
            config["paths"] = {"results_dir": str(root / "results")}
            config["benchmarks"] = {"quality_repetitions": 1}
            config["_config_path"] = str(root / "config.json")
            args = Namespace(
                selector="cloud-coder",
                all_candidates=False,
                skip_missing=False,
                prompt_file=str(prompt_path),
                limit_prompts=None,
                repetitions=1,
                max_tokens=64,
                temperature=0.2,
                timeout=30,
                unload_after=False,
                judge_provider="manual",
                judge_base_url=None,
                judge_model=None,
                judge_reasoning_effort=None,
                judge_timeout=None,
            )
            with mock.patch.dict(os.environ, {"EXAMPLE_AI_API_KEY": "secret-value"}, clear=False):
                with mock.patch.object(lab, "json_request", return_value=response):
                    with mock.patch.object(lab, "switch_to_model") as switch:
                        with redirect_stdout(io.StringIO()):
                            lab.cmd_bench_quality(args, config)
            switch.assert_not_called()
            result_path = next((root / "results").glob("*-quality-cloud-coder/results.jsonl"))
            row = json.loads(result_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["provider"], "cloud")
        self.assertEqual(row["provider_model"], "vendor/coder-v1")
        self.assertIsNone(row["model_worker_peak_rss_gib"])


class SkillEvalCommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.skill_dir = REPO_ROOT / "tests" / "fixtures" / "skill-project" / "skills" / "safe-skill"
        self.eval_dir = REPO_ROOT / "tests" / "fixtures" / "skill-project" / ".skill-evals" / "safe-skill"
        self.config = {
            "providers": {
                "local": {"type": "llama_cpp", "responses_api": True}
            },
            "paths": {
                "models_dir": str(self.root / "models"),
                "state_dir": str(self.root / "state"),
            },
            "server": {"host": "127.0.0.1", "port": 8080},
            "models": {
                "fast-9b": {
                    "provider": "local",
                    "context_tokens": 32768,
                    "files": ["fast.gguf"],
                    "local_dir": "fast-9b",
                    "preset": {},
                    "roles": ["utility"],
                }
            },
        }

    def command_args(self, **changes):
        values = {
            "skill_dir": str(self.skill_dir),
            "target": "local:fast-9b",
            "judge_model": "gpt-5.6-terra",
            "eval_dir": str(self.eval_dir),
            "profile": "smoke",
            "timeout": 30,
            "keep_workspaces": False,
        }
        values.update(changes)
        return Namespace(**values)

    def install_local_model(self):
        model_path = self.root / "models" / "fast-9b" / "fast.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.touch()

    def test_skill_eval_parser_requires_target_and_judge(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            lab.build_parser().parse_args(
                ["skill-eval", "tests/fixtures/skill-project/skills/safe-skill"]
            )

    def test_skill_commands_parse_their_public_profiles(self):
        eval_args = lab.build_parser().parse_args(
            [
                "skill-eval",
                "skill-dir",
                "--target",
                "local:fast-9b",
                "--judge-model",
                "gpt-5.6-terra",
            ]
        )
        redteam_args = lab.build_parser().parse_args(
            [
                "skill-redteam",
                "skill-dir",
                "--target",
                "openai:gpt-5.6-terra",
                "--judge-model",
                "gpt-5.6",
                "--profile",
                "deep",
            ]
        )
        benchmark_args = lab.build_parser().parse_args(
            [
                "skill-benchmark",
                "skill-dir",
                "--target",
                "openai:gpt-5.6-terra",
                "--judge-model",
                "gpt-5.6",
                "--profile",
                "release",
            ]
        )

        self.assertEqual(eval_args.profile, "smoke")
        self.assertEqual(eval_args.timeout, 900)
        self.assertFalse(eval_args.keep_workspaces)
        self.assertEqual(redteam_args.profile, "deep")
        self.assertEqual(benchmark_args.profile, "release")
        self.assertEqual(benchmark_args.timeout, 900)
        self.assertFalse(benchmark_args.keep_workspaces)

    def test_successful_cloud_benchmark_skips_local_lifecycle_and_cleans_paired_staging(self):
        with mock.patch.object(
            lab, "require_skill_eval_dependencies", return_value={"promptfoo": "/promptfoo"}
        ), mock.patch.object(
            lab, "verify_skill_benchmark_revision"
        ) as verify_revision, mock.patch.object(
            lab, "verify_responses_endpoint"
        ) as verify_responses, mock.patch.object(
            lab, "benchmark_model_session"
        ) as benchmark_session, mock.patch.object(
            lab.skill_eval, "run_promptfoo"
        ) as run_promptfoo, redirect_stdout(io.StringIO()):
            lab.cmd_skill_benchmark(
                self.command_args(target="openai:gpt-5.6-terra", judge_model="gpt-5.6"),
                self.config,
            )

        run_root = run_promptfoo.call_args.args[1].parent
        verify_revision.assert_called_once_with(self.skill_dir)
        verify_responses.assert_not_called()
        benchmark_session.assert_not_called()
        self.assertEqual(list((run_root / "workspaces").iterdir()), [])
        self.assertEqual(list((run_root / "codex-homes").iterdir()), [])

    def test_skill_eval_rejects_an_invalid_target_before_dependency_or_inference_checks(self):
        args = Namespace(
            skill_dir="skill-dir",
            target="local:missing",
            judge_model="gpt-5.6-terra",
            eval_dir=None,
            profile="smoke",
            timeout=30,
            keep_workspaces=False,
        )
        config = {
            "providers": {
                "local": {"type": "llama_cpp", "responses_api": True}
            },
            "server": {"host": "127.0.0.1", "port": 8080},
            "models": {},
        }

        with mock.patch.object(lab, "require_skill_eval_dependencies") as dependencies:
            with self.assertRaisesRegex(lab.LabError, "unknown model alias"):
                lab.cmd_skill_eval(args, config)

        dependencies.assert_not_called()

    def test_local_skill_eval_missing_assets_fail_before_staging_or_state_changes(self):
        with mock.patch.object(
            lab, "require_skill_eval_dependencies", return_value={"promptfoo": "/promptfoo"}
        ), mock.patch.object(
            lab.skill_eval, "stage_cases"
        ) as stage_cases, mock.patch.object(
            lab, "verify_responses_endpoint"
        ) as verify_responses, mock.patch.object(
            lab, "benchmark_model_session"
        ) as benchmark_session:
            with self.assertRaisesRegex(lab.LabError, "missing files"):
                lab.cmd_skill_eval(self.command_args(), self.config)

        stage_cases.assert_not_called()
        verify_responses.assert_not_called()
        benchmark_session.assert_not_called()

    def test_local_skill_eval_responses_preflight_fails_before_staging_or_state_changes(self):
        self.install_local_model()
        with mock.patch.object(
            lab, "require_skill_eval_dependencies", return_value={"promptfoo": "/promptfoo"}
        ), mock.patch.object(
            lab.skill_eval, "stage_cases"
        ) as stage_cases, mock.patch.object(
            lab,
            "verify_responses_endpoint",
            side_effect=lab.LabError("responses unavailable"),
        ), mock.patch.object(
            lab, "benchmark_model_session"
        ) as benchmark_session:
            with self.assertRaisesRegex(lab.LabError, "responses unavailable"):
                lab.cmd_skill_eval(self.command_args(), self.config)

        stage_cases.assert_not_called()
        benchmark_session.assert_not_called()

    def test_local_catalog_target_uses_alias_for_assets_and_residency(self):
        self.install_local_model()
        self.config["models"]["fast-9b"]["provider_model"] = "served-fast"
        with mock.patch.object(
            lab, "require_skill_eval_dependencies", return_value={"promptfoo": "/promptfoo"}
        ), mock.patch.object(
            lab, "verify_responses_endpoint"
        ), mock.patch.object(
            lab, "benchmark_model_session"
        ) as benchmark_session, mock.patch.object(
            lab.skill_eval, "run_promptfoo"
        ), redirect_stdout(io.StringIO()):
            lab.cmd_skill_eval(
                self.command_args(target="catalog:fast-9b"), self.config
            )

        benchmark_session.assert_called_once_with(self.config, "fast-9b", 30)

    def test_promptfoo_failure_restores_and_removes_staged_workspaces_by_default(self):
        self.install_local_model()
        snapshot = {
            "auto_idle_enabled": True,
            "auto_idle_seconds": 900,
            "manual_unloaded": False,
            "mode": "cline",
            "pinned_model": None,
        }
        promptfoo_error = subprocess.CalledProcessError(9, ["promptfoo"])
        with mock.patch.object(
            lab, "require_skill_eval_dependencies", return_value={"promptfoo": "/promptfoo"}
        ), mock.patch.object(
            lab, "verify_responses_endpoint"
        ), mock.patch.object(
            lab, "load_service_state", return_value=dict(snapshot)
        ), mock.patch.object(
            lab, "active_model_ids", return_value=["previous-13b"]
        ), mock.patch.object(
            lab, "switch_to_model"
        ) as switch_model, mock.patch.object(
            lab, "save_service_state"
        ) as save_state, mock.patch.object(
            lab.skill_eval, "run_promptfoo", side_effect=promptfoo_error
        ) as run_promptfoo:
            with self.assertRaises(subprocess.CalledProcessError):
                lab.cmd_skill_eval(self.command_args(), self.config)

        run_root = run_promptfoo.call_args.args[1].parent
        self.assertEqual(
            switch_model.call_args_list,
            [
                mock.call(self.config, "fast-9b", timeout=30),
                mock.call(self.config, "previous-13b", timeout=30),
            ],
        )
        self.assertEqual(save_state.call_args_list[-1], mock.call(snapshot))
        self.assertEqual(list((run_root / "workspaces").iterdir()), [])
        self.assertEqual(list((run_root / "codex-homes").iterdir()), [])

    def test_promptfoo_interrupt_restores_and_keep_workspaces_retains_staging(self):
        self.install_local_model()
        snapshot = {
            "auto_idle_enabled": True,
            "auto_idle_seconds": 900,
            "manual_unloaded": True,
            "mode": "benchmark",
            "pinned_model": "previous-13b",
        }
        with mock.patch.object(
            lab, "require_skill_eval_dependencies", return_value={"promptfoo": "/promptfoo"}
        ), mock.patch.object(
            lab, "verify_responses_endpoint"
        ), mock.patch.object(
            lab, "load_service_state", return_value=dict(snapshot)
        ), mock.patch.object(
            lab, "active_model_ids", return_value=["previous-13b"]
        ), mock.patch.object(
            lab, "switch_to_model"
        ), mock.patch.object(
            lab, "save_service_state"
        ) as save_state, mock.patch.object(
            lab.skill_eval, "run_promptfoo", side_effect=KeyboardInterrupt
        ) as run_promptfoo:
            with self.assertRaises(KeyboardInterrupt):
                lab.cmd_skill_eval(
                    self.command_args(keep_workspaces=True),
                    self.config,
                )

        run_root = run_promptfoo.call_args.args[1].parent
        self.assertEqual(save_state.call_args_list[-1], mock.call(snapshot))
        self.assertTrue(any((run_root / "workspaces").iterdir()))
        self.assertTrue(any((run_root / "codex-homes").iterdir()))

    def test_successful_cloud_eval_removes_staged_workspaces_without_local_preflight(self):
        with mock.patch.object(
            lab, "require_skill_eval_dependencies", return_value={"promptfoo": "/promptfoo"}
        ), mock.patch.object(
            lab, "verify_responses_endpoint"
        ) as verify_responses, mock.patch.object(
            lab, "benchmark_model_session"
        ) as benchmark_session, mock.patch.object(
            lab.skill_eval, "run_promptfoo"
        ) as run_promptfoo, redirect_stdout(io.StringIO()):
            lab.cmd_skill_eval(
                self.command_args(target="openai:gpt-5.6-terra", judge_model="gpt-5.6"),
                self.config,
            )

        run_root = run_promptfoo.call_args.args[1].parent
        verify_responses.assert_not_called()
        benchmark_session.assert_not_called()
        self.assertEqual(list((run_root / "workspaces").iterdir()), [])
        self.assertEqual(list((run_root / "codex-homes").iterdir()), [])
        self.assertTrue((run_root / "promptfooconfig.yaml").is_file())
        self.assertTrue((run_root / "verifiers").is_dir())

    def test_config_failure_also_cleans_staged_workspaces_by_default(self):
        with mock.patch.object(
            lab, "require_skill_eval_dependencies", return_value={"promptfoo": "/promptfoo"}
        ), mock.patch.object(
            lab.skill_eval,
            "build_promptfoo_config",
            side_effect=lab.skill_eval.SkillEvalError("config rejected"),
        ), mock.patch.object(
            lab.skill_eval,
            "cleanup_staged_cases",
            wraps=lab.skill_eval.cleanup_staged_cases,
        ) as cleanup:
            with self.assertRaisesRegex(lab.LabError, "config rejected"):
                lab.cmd_skill_eval(
                    self.command_args(target="openai:gpt-5.6-terra", judge_model="gpt-5.6"),
                    self.config,
                )

        cleanup.assert_called_once()
        run_root = cleanup.call_args.args[1]
        self.assertEqual(list((run_root / "workspaces").iterdir()), [])
        self.assertEqual(list((run_root / "codex-homes").iterdir()), [])

    def test_same_second_runs_allocate_distinct_roots(self):
        with mock.patch.object(
            lab, "require_skill_eval_dependencies", return_value={"promptfoo": "/promptfoo"}
        ), mock.patch.object(
            lab, "now_stamp", return_value="20260815-120000"
        ), mock.patch.object(
            lab.skill_eval, "run_promptfoo"
        ) as run_promptfoo, redirect_stdout(io.StringIO()):
            args = self.command_args(target="openai:gpt-5.6-terra", judge_model="gpt-5.6")
            lab.cmd_skill_eval(args, self.config)
            lab.cmd_skill_eval(args, self.config)

        run_roots = [call.args[1].parent for call in run_promptfoo.call_args_list]
        self.assertEqual(len(run_roots), 2)
        self.assertNotEqual(run_roots[0], run_roots[1])
        self.assertTrue(all((run_root / "promptfooconfig.yaml").is_file() for run_root in run_roots))

    def test_staging_failure_rolls_back_partial_workspaces_by_default(self):
        with mock.patch.object(
            lab, "require_skill_eval_dependencies", return_value={"promptfoo": "/promptfoo"}
        ), mock.patch.object(
            lab.skill_eval,
            "_initialize_pristine_git_repository",
            side_effect=lab.skill_eval.SkillEvalError("git setup failed"),
        ):
            with self.assertRaisesRegex(lab.LabError, "git setup failed"):
                lab.cmd_skill_eval(
                    self.command_args(target="openai:gpt-5.6-terra", judge_model="gpt-5.6"),
                    self.config,
                )

        run_roots = list((self.root / "state" / "skill-evals").iterdir())
        self.assertEqual(len(run_roots), 1)
        self.assertEqual(list((run_roots[0] / "workspaces").iterdir()), [])
        self.assertEqual(list((run_roots[0] / "codex-homes").iterdir()), [])


class CatalogTests(unittest.TestCase):
    def test_catalog_filters_watchlist_by_role_and_status(self):
        config = {
            "providers": {"local": {"type": "llama_cpp"}},
            "paths": {"models_dir": "/tmp/models"},
            "models": {
                "fast": {
                    "provider": "local",
                    "roles": ["utility"],
                    "status": "core",
                    "files": ["fast.gguf"],
                }
            },
            "watchlist": {
                "future": {
                    "roles": ["utility"],
                    "status": "watch",
                }
            },
        }

        rows = lab.catalog_rows(config, role="utility", status="watch")

        self.assertEqual([row["model"] for row in rows], ["future"])
        self.assertFalse(rows[0]["installed"])

    def test_pull_capacity_rejects_projected_overage(self):
        config = {
            "providers": {"local": {"type": "llama_cpp"}},
            "paths": {"models_dir": "/tmp/models"},
            "fleet": {"installed_weight_cap_gib": 10},
            "models": {
                "candidate": {
                    "provider": "local",
                    "roles": ["utility"],
                    "status": "candidate",
                    "files": ["candidate.gguf"],
                    "expected_disk_gib": 11,
                }
            },
        }

        with self.assertRaisesRegex(lab.LabError, "above the 10 GiB fleet cap"):
            lab.validate_pull_capacity(config, ["candidate"])

    def test_partial_download_counts_toward_fleet_cap_without_double_counting(self):
        with tempfile.TemporaryDirectory() as directory:
            partial = (
                Path(directory)
                / "candidate"
                / ".cache"
                / "huggingface"
                / "download"
                / "weight.gguf.incomplete"
            )
            partial.parent.mkdir(parents=True)
            with partial.open("wb") as file_handle:
                file_handle.truncate(512 * 1024 * 1024)
            complete = Path(directory) / "candidate" / "first.gguf"
            with complete.open("wb") as file_handle:
                file_handle.truncate(256 * 1024 * 1024)
            config = {
                "providers": {"local": {"type": "llama_cpp"}},
                "paths": {"models_dir": directory},
                "fleet": {"installed_weight_cap_gib": 1.1},
                "models": {
                    "candidate": {
                        "provider": "local",
                        "roles": ["utility"],
                        "status": "candidate",
                        "local_dir": "candidate",
                        "files": ["first.gguf", "second.gguf"],
                        "expected_disk_gib": 1,
                    }
                },
            }

            row = lab.catalog_rows(config)[0]
            lab.validate_pull_capacity(config, ["candidate"])
            installed_gib = lab.installed_fleet_gib(config)

        self.assertEqual(row["partial_gib"], 0.5)
        self.assertEqual(row["installed_gib"], 0.25)
        self.assertEqual(installed_gib, 0.75)

    def test_catalog_validation_rejects_context_mismatch(self):
        entry = {field: None for field in lab.CATALOG_REQUIRED_FIELDS}
        entry.update({
            "provider": "local",
            "roles": ["utility"],
            "status": "candidate",
            "agent_compatibility": {},
            "context_tokens": 32768,
            "preset": {"ctx-size": 8192},
        })

        with self.assertRaisesRegex(lab.LabError, "does not match preset ctx-size"):
            lab.validate_catalog_config({
                "providers": {"local": {"type": "llama_cpp"}},
                "models": {"candidate": entry},
            })


class ProviderCatalogTests(unittest.TestCase):
    def test_render_presets_omits_remote_models(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {
                "providers": {
                    "local": {"type": "llama_cpp"},
                    "cloud": {
                        "type": "openai_compatible",
                        "base_url": "https://api.example.test/v1",
                        "api_key_env": "EXAMPLE_AI_API_KEY",
                    },
                },
                "paths": {
                    "models_dir": str(root / "models"),
                    "generated_dir": str(root / "generated"),
                },
                "models": {
                    "local-coder": {
                        "provider": "local",
                        "status": "core",
                        "files": ["local-coder.gguf"],
                        "preset": {"ctx-size": 8192},
                    },
                    "cloud-coder": {
                        "provider": "cloud",
                        "status": "candidate",
                    },
                },
            }

            rendered = lab.render_presets(config).read_text(encoding="utf-8")

        self.assertIn("[local-coder]", rendered)
        self.assertNotIn("[cloud-coder]", rendered)

    def test_render_presets_validates_provider_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {"paths": {"generated_dir": str(Path(directory) / "generated")}}

            with self.assertRaises(ProviderConfigError):
                lab.render_presets(config)

    def test_cloud_catalog_entry_does_not_require_local_preset_or_weight_files(self):
        config = {
            "providers": {
                "cloud": {
                    "type": "openai_compatible",
                    "base_url": "https://api.example.test/v1",
                    "api_key_env": "EXAMPLE_AI_API_KEY",
                }
            },
            "models": {
                "cloud-coder": {
                    "provider": "cloud",
                    "provider_model": "vendor/coder-v1",
                    "release_date": "2026-01",
                    "official_model_id": "vendor/coder-v1",
                    "architecture": "hosted",
                    "parameters_total_b": None,
                    "parameters_active_b": None,
                    "quantization": None,
                    "license": "provider terms",
                    "roles": ["coding"],
                    "status": "candidate",
                    "expected_disk_gib": None,
                    "context_tokens": 32768,
                    "source_url": "https://example.test/models/coder-v1",
                    "last_verified": None,
                    "agent_compatibility": {},
                }
            },
        }
        lab.validate_catalog_config(config)
        row = lab.catalog_rows(config)[0]
        self.assertEqual(row["provider"], "cloud")
        self.assertEqual(row["provider_type"], "openai_compatible")
        self.assertEqual(row["availability"], "remote")
        self.assertIsNone(row["installed"])

    def test_local_only_command_rejects_cloud_model_before_side_effects(self):
        config = {
            "server": {"host": "127.0.0.1", "port": 8080},
            "providers": {
                "cloud": {
                    "type": "openai_compatible",
                    "base_url": "https://api.example.test/v1",
                    "api_key_env": "EXAMPLE_AI_API_KEY",
                }
            },
            "models": {"cloud-coder": {"provider": "cloud"}},
        }
        with self.assertRaisesRegex(lab.LabError, "load requires a local llama.cpp model"):
            lab.require_local_model(config, "cloud-coder", "load")

    def test_benchmark_mode_rejects_cloud_model_before_service_calls(self):
        config = {
            "providers": {
                "cloud": {
                    "type": "openai_compatible",
                    "base_url": "https://api.example.test/v1",
                    "api_key_env": "EXAMPLE_AI_API_KEY",
                }
            },
            "models": {"cloud-coder": {"provider": "cloud"}},
        }
        args = Namespace(mode="benchmark", model="cloud-coder", timeout=30)

        with mock.patch.object(lab, "load_service_state") as load_state, mock.patch.object(
            lab, "api_is_ready"
        ) as api_ready, mock.patch.object(lab, "switch_to_model") as switch_model, mock.patch.object(
            lab, "save_service_state"
        ) as save_state:
            with self.assertRaisesRegex(lab.LabError, "mode requires a local llama.cpp model"):
                lab.cmd_mode(args, config)

        load_state.assert_not_called()
        api_ready.assert_not_called()
        switch_model.assert_not_called()
        save_state.assert_not_called()


class QualityTests(unittest.TestCase):
    def test_gateway_models_route_advertises_only_active_local_targets(self):
        config = {
            "providers": {
                "local": {"type": "llama_cpp"},
                "cloud": {
                    "type": "openai_compatible",
                    "base_url": "https://api.example.test/v1",
                    "api_key_env": "EXAMPLE_AI_API_KEY",
                },
            },
            "models": {
                "local-active": {"provider": "local", "status": "core"},
                "local-retired": {"provider": "local", "status": "retired"},
                "cloud-active": {"provider": "cloud", "status": "candidate"},
            },
        }
        handler = object.__new__(lab.GatewayHandler)
        handler.server = Namespace(gateway=Namespace(cfg=config))
        handler.path = "/v1/models"
        handler.wfile = io.BytesIO()
        handler.send_response = mock.Mock()
        handler.send_header = mock.Mock()
        handler.end_headers = mock.Mock()

        handler.do_GET()

        payload = json.loads(handler.wfile.getvalue())
        self.assertEqual(
            payload,
            {
                "object": "list",
                "data": [
                    {
                        "id": "local-active",
                        "object": "model",
                        "owned_by": "ai-systems-lab",
                    }
                ],
            },
        )

    def test_judge_config_rejects_obsolete_base_url_override(self):
        args = Namespace(
            judge_provider="manual",
            judge_base_url="https://obsolete.example.test/v1",
            judge_model=None,
            judge_reasoning_effort=None,
            judge_timeout=None,
        )

        with self.assertRaisesRegex(
            lab.LabError, r"providers\.<name>\.base_url"
        ):
            lab.judge_config({"benchmarks": {}}, args)

    def test_judge_config_resolves_named_provider(self):
        args = Namespace(
            judge_provider="cloud-openai-compatible",
            judge_base_url=None,
            judge_model="cloud-example",
            judge_reasoning_effort="low",
            judge_timeout=45,
        )
        config = {
            "benchmarks": {"judge": {"provider": "manual"}},
            "providers": {
                "cloud-openai-compatible": {
                    "type": "openai_compatible",
                    "base_url": "https://api.example.test/v1",
                    "api_key_env": "EXAMPLE_AI_API_KEY",
                    "responses_api": True,
                }
            },
            "models": {
                "cloud-example": {
                    "provider": "cloud-openai-compatible",
                    "provider_model": "vendor/judge-v1",
                }
            },
            "server": {"host": "127.0.0.1", "port": 8080},
        }
        result = lab.judge_config(config, args)
        self.assertEqual(result["provider"], "cloud-openai-compatible")
        self.assertEqual(result["model"], "cloud-example")
        self.assertEqual(result["timeout_seconds"], 45)

    def test_quality_rejects_non_responses_judge_before_credentials_or_output_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt_path = root / "prompts.jsonl"
            prompt_path.write_text(
                json.dumps(
                    {
                        "name": "smoke",
                        "messages": [{"role": "user", "content": "hello"}],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            config = {
                "providers": {
                    "candidate-provider": {
                        "type": "openai_compatible",
                        "base_url": "https://candidate.example.test/v1",
                        "api_key_env": "MISSING_CANDIDATE_KEY",
                    },
                    "judge-provider": {
                        "type": "openai_compatible",
                        "base_url": "https://judge.example.test/v1",
                        "api_key_env": "MISSING_JUDGE_KEY",
                    },
                },
                "models": {
                    "candidate": {"provider": "candidate-provider"},
                    "judge": {"provider": "judge-provider"},
                },
                "paths": {"results_dir": str(root / "results")},
                "benchmarks": {"quality_repetitions": 1},
                "server": {"host": "127.0.0.1", "port": 8080},
                "_config_path": str(root / "config.json"),
            }
            args = Namespace(
                selector="candidate",
                all_candidates=False,
                skip_missing=False,
                prompt_file=str(prompt_path),
                limit_prompts=None,
                repetitions=1,
                max_tokens=64,
                temperature=0.2,
                timeout=30,
                unload_after=False,
                judge_provider="judge-provider",
                judge_base_url=None,
                judge_model="judge",
                judge_reasoning_effort="low",
                judge_timeout=45,
            )

            with mock.patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(
                    lab.LabError, "does not support the Responses API judge"
                ):
                    lab.cmd_bench_quality(args, config)

            self.assertFalse((root / "results").exists())

    def test_judge_config_rejects_model_from_another_provider(self):
        args = Namespace(
            judge_provider="cloud-openai-compatible",
            judge_base_url=None,
            judge_model="local-judge",
            judge_reasoning_effort="low",
            judge_timeout=45,
        )
        config = {
            "providers": {
                "local-llama": {"type": "llama_cpp"},
                "cloud-openai-compatible": {
                    "type": "openai_compatible",
                    "base_url": "https://api.example.test/v1",
                    "api_key_env": "EXAMPLE_AI_API_KEY",
                    "responses_api": True,
                },
            },
            "models": {"local-judge": {"provider": "local-llama"}},
            "server": {"host": "127.0.0.1", "port": 8080},
        }

        with self.assertRaisesRegex(lab.LabError, "does not belong to judge provider"):
            lab.judge_config(config, args)

    def test_judge_config_maps_legacy_provider_alias(self):
        args = Namespace(
            judge_provider="local",
            judge_base_url=None,
            judge_model="local-judge",
            judge_reasoning_effort=None,
            judge_timeout=None,
        )
        config = {
            "providers": {"local-llama": {"type": "llama_cpp"}},
            "models": {"local-judge": {"provider": "local-llama"}},
            "server": {"host": "127.0.0.1", "port": 8080},
        }
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            result = lab.judge_config(config, args)

        self.assertEqual(result["provider"], "local-llama")
        self.assertIn("deprecated", stderr.getvalue())

    def test_judge_config_maps_legacy_openai_provider_alias(self):
        args = Namespace(
            judge_provider="openai",
            judge_base_url=None,
            judge_model="cloud-judge",
            judge_reasoning_effort=None,
            judge_timeout=None,
        )
        config = {
            "providers": {
                "cloud-openai-compatible": {
                    "type": "openai_compatible",
                    "base_url": "https://api.example.test/v1",
                    "api_key_env": "EXAMPLE_AI_API_KEY",
                    "responses_api": True,
                }
            },
            "models": {"cloud-judge": {"provider": "cloud-openai-compatible"}},
            "server": {"host": "127.0.0.1", "port": 8080},
        }
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            result = lab.judge_config(config, args)

        self.assertEqual(result["provider"], "cloud-openai-compatible")
        self.assertIn("deprecated", stderr.getvalue())

    def test_remote_judge_uses_resolved_provider_request(self):
        args = Namespace(
            judge_provider="cloud-openai-compatible",
            judge_base_url=None,
            judge_model="cloud-example",
            judge_reasoning_effort="low",
            judge_timeout=45,
        )
        config = {
            "providers": {
                "cloud-openai-compatible": {
                    "type": "openai_compatible",
                    "base_url": "https://api.example.test/v1",
                    "api_key_env": "EXAMPLE_AI_API_KEY",
                    "responses_api": True,
                }
            },
            "models": {
                "cloud-example": {
                    "provider": "cloud-openai-compatible",
                    "provider_model": "vendor/judge-v1",
                }
            },
            "server": {"host": "127.0.0.1", "port": 8080},
        }
        response = {
            "id": "resp_example",
            "output_text": json.dumps({
                "correctness": 5,
                "completeness": 5,
                "instruction_following": 5,
                "clarity": 5,
                "overall": 5,
                "pass": True,
                "confidence": 5,
                "rationale": "Complete.",
                "strengths": ["Accurate"],
                "weaknesses": [],
                "missed_requirements": [],
            }),
        }
        judge_cfg = lab.judge_config(config, args)
        with mock.patch.dict(os.environ, {"EXAMPLE_AI_API_KEY": "secret-value"}, clear=False):
            with mock.patch.object(lab, "json_request", return_value=response) as request:
                result = lab.score_quality_response(
                    config, judge_cfg, {"candidate_response": "answer"}
                )

        self.assertTrue(result["score"]["pass"])
        request_args, request_kwargs = request.call_args
        self.assertEqual(request_args[1], "https://api.example.test/v1/responses")
        self.assertEqual(request_args[2]["model"], "vendor/judge-v1")
        self.assertIn("candidate response", request_args[2]["instructions"])
        self.assertNotIn("local LLM", request_args[2]["instructions"])
        self.assertNotIn("cloud", request_args[2]["instructions"].lower())
        self.assertEqual(request_kwargs["headers"], {"Authorization": "Bearer secret-value"})

    def test_responses_api_judge_error_uses_provider_neutral_wording(self):
        args = Namespace(
            judge_provider="cloud-openai-compatible",
            judge_base_url=None,
            judge_model="cloud-example",
            judge_reasoning_effort="low",
            judge_timeout=45,
        )
        config = {
            "providers": {
                "cloud-openai-compatible": {
                    "type": "openai_compatible",
                    "base_url": "https://api.example.test/v1",
                    "api_key_env": "EXAMPLE_AI_API_KEY",
                    "responses_api": True,
                }
            },
            "models": {
                "cloud-example": {"provider": "cloud-openai-compatible"}
            },
            "server": {"host": "127.0.0.1", "port": 8080},
        }
        judge_cfg = lab.judge_config(config, args)

        with mock.patch.dict(
            os.environ, {"EXAMPLE_AI_API_KEY": "secret-value"}, clear=True
        ), mock.patch.object(lab, "json_request", return_value={}):
            with self.assertRaisesRegex(
                lab.LabError, "Responses API judge returned no output text"
            ):
                lab.score_quality_response(
                    config, judge_cfg, {"candidate_response": "answer"}
                )

    def test_default_quality_judge_is_manual(self):
        args = Namespace(
            judge_provider=None,
            judge_base_url=None,
            judge_model=None,
            judge_reasoning_effort=None,
            judge_timeout=None,
        )

        config = lab.judge_config({"benchmarks": {}}, args)

        self.assertEqual(config["provider"], "manual")
        self.assertIsNone(config["model"])

    def test_extract_json_object_accepts_fenced_json(self):
        score = lab.extract_json_object('```json\n{"overall": 5}\n```')

        self.assertEqual(score, {"overall": 5})

    def test_multimodal_fixture_is_a_png_data_url(self):
        value = lab.red_square_data_url()

        self.assertTrue(value.startswith("data:image/png;base64,iVBOR"))

    def test_empty_visible_completion_is_rejected(self):
        with self.assertRaisesRegex(lab.LabError, "no visible answer"):
            lab.require_visible_completion({
                "text": "",
                "finish_reason": "length",
                "completion_tokens": 384,
            })

    def test_visible_completion_is_accepted(self):
        lab.require_visible_completion({
            "text": "usable answer",
            "finish_reason": "stop",
            "completion_tokens": 8,
        })

    def test_quality_default_allows_reasoning_and_visible_answer(self):
        args = lab.build_parser().parse_args(["bench-quality", "coder"])

        self.assertEqual(args.max_tokens, 4096)


class VerificationTests(unittest.TestCase):
    def test_process_tree_memory_selects_requested_model_worker(self):
        process_list = (
            "100 1 1024 llama-server --models-preset models.ini\n"
            "101 100 8388608 llama-server --alias fast-9b --model fast.gguf\n"
            "102 100 2097152 llama-server --alias embed-4b --embeddings\n"
        )
        completed = mock.Mock(returncode=0, stdout=process_list)
        with mock.patch.object(lab, "pid_running", return_value=True):
            with mock.patch.object(lab.subprocess, "run", return_value=completed):
                memory = lab.process_tree_rss_gib(100, model_id="fast-9b")

        self.assertEqual(memory, 8)

    def test_memory_sampler_runs_operation_without_service_pid(self):
        with mock.patch.object(lab, "read_pid", return_value=None):
            result, peak = lab.run_with_server_memory_sample({}, lambda: "done")

        self.assertEqual(result, "done")
        self.assertIsNone(peak)

    def test_malformed_tool_arguments_fail_cleanly(self):
        with self.assertRaisesRegex(lab.LabError, "malformed arguments"):
            lab.parse_tool_arguments("{not-json")

    def test_missing_model_fails_before_service_state_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {
                "providers": {"local": {"type": "llama_cpp"}},
                "paths": {
                    "models_dir": directory,
                    "results_dir": str(Path(directory) / "results"),
                },
                "models": {
                    "missing": {
                        "provider": "local",
                        "files": ["missing.gguf"],
                        "local_dir": "missing",
                        "preset": {},
                    }
                },
            }
            args = Namespace(selector="missing", timeout=1, keep_loaded=False)

            with mock.patch.object(lab, "update_service_state") as update_state:
                with self.assertRaisesRegex(lab.LabError, "missing files"):
                    lab.cmd_verify(args, config)

        update_state.assert_not_called()


class BenchmarkModelSessionTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "providers": {"local": {"type": "llama_cpp"}},
            "models": {
                "fast-9b": {"provider": "local", "roles": ["utility"]},
                "previous-13b": {"provider": "local", "roles": ["coding"]},
            }
        }
        self.snapshot = {
            "auto_idle_enabled": False,
            "auto_idle_seconds": 321,
            "manual_unloaded": True,
            "mode": "benchmark",
            "pinned_model": "previous-13b",
        }

    def test_benchmark_session_restores_exact_state_and_active_model_after_interrupt(self):
        with mock.patch.object(
            lab, "load_service_state", return_value=dict(self.snapshot)
        ), mock.patch.object(
            lab, "active_model_ids", return_value=["previous-13b"]
        ), mock.patch.object(
            lab, "save_service_state"
        ) as save_state, mock.patch.object(
            lab, "switch_to_model"
        ) as switch_model:
            with self.assertRaises(KeyboardInterrupt):
                with lab.benchmark_model_session(self.config, "fast-9b", 30):
                    raise KeyboardInterrupt

        self.assertEqual(
            switch_model.call_args_list,
            [
                mock.call(self.config, "fast-9b", timeout=30),
                mock.call(self.config, "previous-13b", timeout=30),
            ],
        )
        self.assertEqual(
            save_state.call_args_list,
            [
                mock.call(
                    {
                        "auto_idle_enabled": False,
                        "auto_idle_seconds": 321,
                        "manual_unloaded": False,
                        "mode": "benchmark",
                        "pinned_model": "fast-9b",
                    }
                ),
                mock.call(
                    {
                        "auto_idle_enabled": False,
                        "auto_idle_seconds": 321,
                        "manual_unloaded": False,
                        "mode": "benchmark",
                        "pinned_model": "previous-13b",
                    }
                ),
                mock.call(self.snapshot),
            ],
        )

    def test_benchmark_session_restores_an_unloaded_manual_state(self):
        snapshot = {
            **self.snapshot,
            "mode": "cline",
            "pinned_model": None,
            "manual_unloaded": True,
        }
        active_models = mock.Mock(side_effect=[[], ["fast-9b"]])

        with mock.patch.object(
            lab, "load_service_state", return_value=dict(snapshot)
        ), mock.patch.object(
            lab, "active_model_ids", active_models
        ), mock.patch.object(
            lab, "save_service_state"
        ) as save_state, mock.patch.object(
            lab, "switch_to_model"
        ), mock.patch.object(
            lab, "unload_model"
        ) as unload, mock.patch.object(
            lab, "wait_for_inactive"
        ) as wait_for_inactive:
            with lab.benchmark_model_session(self.config, "fast-9b", 30):
                pass

        unload.assert_called_once_with(self.config, "fast-9b", quiet=True)
        wait_for_inactive.assert_called_once_with(self.config, "fast-9b", timeout=30)
        self.assertEqual(save_state.call_args_list[-1], mock.call(snapshot))

    def test_benchmark_session_restores_when_the_benchmark_state_write_interrupts(self):
        saved_states = []

        def interrupt_after_write(state):
            saved_states.append(dict(state))
            if len(saved_states) == 1:
                raise KeyboardInterrupt

        with mock.patch.object(
            lab, "load_service_state", return_value=dict(self.snapshot)
        ), mock.patch.object(
            lab, "active_model_ids", return_value=["previous-13b"]
        ), mock.patch.object(
            lab, "save_service_state", side_effect=interrupt_after_write
        ), mock.patch.object(
            lab, "switch_to_model"
        ) as switch_model:
            with self.assertRaises(KeyboardInterrupt):
                with lab.benchmark_model_session(self.config, "fast-9b", 30):
                    pass

        self.assertEqual(saved_states[-1], self.snapshot)
        switch_model.assert_called_once_with(self.config, "previous-13b", timeout=30)

    def test_benchmark_session_allows_gateway_to_reload_the_previous_pin(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ,
            {"AI_SYSTEMS_LAB_STATE_PATH": str(Path(directory) / "state.json")},
            clear=False,
        ):
            models_dir = Path(directory) / "models"
            for model_id in ("fast-9b", "previous-13b", "third-7b"):
                model_dir = models_dir / model_id
                model_dir.mkdir(parents=True)
                (model_dir / f"{model_id}.gguf").touch()
            config = {
                "providers": {"local": {"type": "llama_cpp"}},
                "paths": {"models_dir": str(models_dir), "state_dir": str(Path(directory) / "runtime")},
                "models": {
                    model_id: {
                        "provider": "local",
                        "files": [f"{model_id}.gguf"],
                        "local_dir": model_id,
                        "preset": {},
                    }
                    for model_id in ("fast-9b", "previous-13b", "third-7b")
                },
            }
            lab.save_service_state(self.snapshot)
            gateway = lab.Gateway(config)
            self.addCleanup(gateway.close)

            def gateway_switch(_cfg, model_id, timeout):
                if model_id == "previous-13b":
                    with self.assertRaisesRegex(lab.LabError, "automatic switching is disabled"):
                        gateway.ensure_model("third-7b")
                return gateway.ensure_model(model_id)

            with mock.patch.object(
                gateway, "_status", return_value=("loaded", {})
            ), mock.patch.object(
                lab, "active_model_ids", return_value=["previous-13b"]
            ), mock.patch.object(
                lab, "switch_to_model", side_effect=gateway_switch
            ):
                with lab.benchmark_model_session(config, "fast-9b", 30):
                    pass

            self.assertEqual(lab.load_service_state(), self.snapshot)

    def test_empty_residency_restore_rejects_same_target_reload_race(self):
        snapshot = {
            **self.snapshot,
            "mode": "cline",
            "pinned_model": None,
            "manual_unloaded": True,
        }
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ,
            {"AI_SYSTEMS_LAB_STATE_PATH": str(Path(directory) / "state.json")},
            clear=False,
        ):
            models_dir = Path(directory) / "models"
            model_dir = models_dir / "fast-9b"
            model_dir.mkdir(parents=True)
            (model_dir / "fast-9b.gguf").touch()
            config = {
                "providers": {"local": {"type": "llama_cpp"}},
                "paths": {"models_dir": str(models_dir), "state_dir": str(Path(directory) / "runtime")},
                "models": {
                    "fast-9b": {
                        "provider": "local",
                        "files": ["fast-9b.gguf"],
                        "local_dir": "fast-9b",
                        "preset": {},
                    }
                },
            }
            lab.save_service_state(snapshot)
            gateway = lab.Gateway(config)
            self.addCleanup(gateway.close)
            active_models = set()
            reload_rejected = []

            def active_model_ids(_cfg, **_kwargs):
                return sorted(active_models)

            def switch_model(_cfg, model_id, timeout):
                active_models.clear()
                active_models.add(model_id)

            def unload_model(_cfg, model_id, quiet):
                active_models.discard(model_id)

            def wait_for_inactive(_cfg, model_id, timeout):
                self.assertNotIn(model_id, active_models)
                try:
                    gateway.ensure_model(model_id)
                except lab.LabError:
                    reload_rejected.append(model_id)
                else:
                    active_models.add(model_id)

            with mock.patch.object(
                gateway, "_status", return_value=("loaded", {})
            ), mock.patch.object(
                lab, "active_model_ids", side_effect=active_model_ids
            ), mock.patch.object(
                lab, "switch_to_model", side_effect=switch_model
            ), mock.patch.object(
                lab, "unload_model", side_effect=unload_model
            ), mock.patch.object(
                lab, "wait_for_inactive", side_effect=wait_for_inactive
            ):
                with lab.benchmark_model_session(config, "fast-9b", 30):
                    pass

            self.assertEqual(reload_rejected, ["fast-9b"])
            self.assertEqual(active_models, set())
            self.assertEqual(lab.load_service_state(), snapshot)


class GatewayTests(unittest.TestCase):
    def test_backend_uses_private_port_while_gateway_keeps_client_port(self):
        config = {"server": {"host": "127.0.0.1", "port": 8080, "backend_port": 8081}}

        self.assertEqual(lab.api_base(config), "http://127.0.0.1:8080")
        self.assertEqual(lab.backend_api_base(config), "http://127.0.0.1:8081")

    def test_gateway_rejects_automatic_switch_while_benchmark_is_pinned(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ, {"AI_SYSTEMS_LAB_STATE_PATH": str(Path(directory) / "state.json")}, clear=False
        ):
            model_dir = Path(directory) / "fast"
            model_dir.mkdir()
            (model_dir / "fast.gguf").touch()
            config = {
                "providers": {"local": {"type": "llama_cpp"}},
                "paths": {"state_dir": ".ai-systems-lab", "models_dir": directory},
                "models": {"fast": {"provider": "local", "status": "core", "files": ["fast.gguf"], "local_dir": "fast"}},
            }
            lab.save_service_state({
                "auto_idle_enabled": True,
                "auto_idle_seconds": 900,
                "manual_unloaded": False,
                "mode": "benchmark",
                "pinned_model": "other",
            })
            gateway = lab.Gateway(config)
            try:
                with self.assertRaisesRegex(lab.LabError, "automatic switching is disabled"):
                    gateway.ensure_model("fast")
            finally:
                gateway.close()


class PublicExportTests(unittest.TestCase):
    def test_sanitize_public_value_drops_answers_and_local_metadata(self):
        source = {
            "repo": "/Users/example/private",
            "answer": "private response",
            "config_hash": "private-identifier",
            "platform": {"release": "private-environment"},
            "prompt_file": "/Users/example/private/prompts.jsonl",
            "rationale": "May quote private content.",
            "model": "fast-9b",
            "notes": "file at /Users/example/private/file.ts",
            "authorization": "Authorization: Bearer secret-value",
        }

        sanitized = lab.sanitize_public_value(source)

        self.assertNotIn("repo", sanitized)
        self.assertNotIn("answer", sanitized)
        self.assertNotIn("config_hash", sanitized)
        self.assertNotIn("platform", sanitized)
        self.assertNotIn("prompt_file", sanitized)
        self.assertNotIn("rationale", sanitized)
        self.assertEqual(sanitized["model"], "fast-9b")
        self.assertNotIn("/Users/example", sanitized["notes"])
        self.assertIn("Bearer REDACTED", sanitized["authorization"])

    def test_export_public_excludes_raw_answers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_dir = root / "20260724-quality-fast"
            result_dir.mkdir()
            (result_dir / "metadata.json").write_text(
                json.dumps({"repo": "/Users/example/private", "models": ["fast-9b"]}),
                encoding="utf-8",
            )
            (result_dir / "results.jsonl").write_text(
                json.dumps({"model": "fast-9b", "answer": "private", "latency_seconds": 1.2}) + "\n",
                encoding="utf-8",
            )
            output = root / "public.json"

            with redirect_stdout(io.StringIO()):
                lab.cmd_export_public(
                    Namespace(result_dir=str(result_dir), output=str(output)),
                    {},
                )
            exported = json.loads(output.read_text(encoding="utf-8"))

        row = exported["artifacts"]["results.jsonl"][0]
        self.assertEqual(row, {"model": "fast-9b", "latency_seconds": 1.2})
        self.assertNotIn("repo", exported["artifacts"]["metadata.json"])


if __name__ == "__main__":
    unittest.main()
