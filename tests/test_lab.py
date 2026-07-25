import importlib.machinery
import importlib.util
import io
import json
import os
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("local_ai_lab", str(REPO_ROOT / "scripts" / "lab"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
lab = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(lab)


class ConfigTests(unittest.TestCase):
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


class CatalogTests(unittest.TestCase):
    def test_catalog_filters_watchlist_by_role_and_status(self):
        config = {
            "paths": {"models_dir": "/tmp/models"},
            "models": {
                "fast": {
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
            "paths": {"models_dir": "/tmp/models"},
            "fleet": {"installed_weight_cap_gib": 10},
            "models": {
                "candidate": {
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
                "paths": {"models_dir": directory},
                "fleet": {"installed_weight_cap_gib": 1.1},
                "models": {
                    "candidate": {
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
            "roles": ["utility"],
            "status": "candidate",
            "agent_compatibility": {},
            "context_tokens": 32768,
            "preset": {"ctx-size": 8192},
        })

        with self.assertRaisesRegex(lab.LabError, "does not match preset ctx-size"):
            lab.validate_catalog_config({"models": {"candidate": entry}})


class QualityTests(unittest.TestCase):
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
                "paths": {
                    "models_dir": directory,
                    "results_dir": str(Path(directory) / "results"),
                },
                "models": {
                    "missing": {
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
