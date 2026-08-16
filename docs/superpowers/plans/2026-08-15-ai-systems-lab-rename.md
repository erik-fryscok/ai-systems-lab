# AI Systems Lab Rename and Provider Generalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the project to `ai-systems-lab` / **AI Systems Lab** and make local llama.cpp and cloud-hosted OpenAI-compatible models interchangeable for provider-agnostic chat and evaluation workflows while retaining the complete local-model lifecycle.

**Architecture:** Keep `scripts/lab` as the orchestration entry point, but move provider resolution and HTTP request construction into a focused `ai_systems_lab.providers` module. Every runnable model names a configured provider; provider-agnostic commands resolve a `ModelTarget`, while local lifecycle commands explicitly require the `llama_cpp` provider. Rename persistent identifiers with read-only fallbacks for legacy state/model locations, then perform the GitHub and checkout rename only after the in-repository migration passes.

**Tech Stack:** Python 3.9+, PyYAML 6.0.2, `unittest`, JSON configuration, Make, llama.cpp, OpenAI-compatible Chat Completions/Responses APIs, Node.js `^20.20.0 || >=22.22.0`, Codex SDK 0.147.0, Promptfoo 0.122.0, macOS `launchd`, Git/GitHub CLI over SSH.

## Global Constraints

- Repository/project name is consistently `ai-systems-lab` / **AI Systems Lab**.
- Documentation explains that both local and cloud models/providers are within scope.
- Core terminology and architecture do not assume that model execution must occur locally.
- Existing local-model workflows continue to work.
- Provider-specific concerns remain isolated from provider-agnostic routing/evaluation logic where practical.
- The project continues to be explicitly positioned as an experimental learning/evaluation testbed, not production infrastructure.
- Relevant tests and validation pass.
- A repository-wide search confirms old naming remains only where intentionally retained for historical/migration context.
- Preserve Python `>=3.9`, `PyYAML==6.0.2`, the existing Node engine floor, and the pinned Codex SDK/Promptfoo versions; add no new dependencies for ERI-19.
- Keep the current `./scripts/lab` command name and local llama.cpp workflow; ERI-19 renames the project, not the CLI.
- Treat cloud inference as explicit opt-in: never commit API keys, never make a paid model the default, and read credentials only from a configured environment-variable name.
- Use SSH for every GitHub Git operation and keep `origin` in `git@github.com:OWNER/REPOSITORY.git` form.
- Implement from current `origin/main`, which already contains the merged skill-evaluation harness. The authoring checkout was at `d8df3c57`, 12 commits behind the inspected `origin/main` at `8e2b5ffd`; do not implement against the stale tree.

---

## File Structure

- Create `ai_systems_lab/__init__.py`: package marker and project display/version constants.
- Create `ai_systems_lab/providers.py`: provider schema validation, model-target resolution, credential lookup, and provider-specific request construction.
- Modify `scripts/lab`: consume provider interfaces, distinguish provider-agnostic inference from local-only lifecycle operations, and migrate branding/persistent identifiers.
- Modify `config/lab.json`: declare providers, bind every runnable model to the local provider, and use the new project paths.
- Create `config/lab.cloud.example.json`: safe opt-in overlay showing one cloud provider and model without a real credential or default workload change.
- Modify `tests/test_lab.py`: rename the loaded module and cover config/path/service migration plus CLI behavior.
- Create `tests/test_providers.py`: focused unit tests for provider validation, target resolution, credentials, and request construction.
- Modify `scripts/skill_eval.py`: resolve skill-evaluation candidates through the shared model/provider catalog and rename private artifact/provider identities.
- Modify `tests/test_skill_eval.py`: cover catalog targets, legacy target compatibility, provider capabilities, and renamed private paths.
- Modify `benchmarks/skills/cases.schema.json`: rename the schema ID/title without changing its validation contract.
- Modify `pyproject.toml`: project/package metadata and GitHub URLs.
- Modify `README.md`: project positioning, provider architecture, local quick start, cloud opt-in, migration notes, and validation.
- Modify `docs/model-fleet.md`: state that the local fleet is one first-class provider rather than the whole system.
- Modify `docs/client-configuration.md`: distinguish the local gateway endpoint from direct cloud-provider configuration.
- Modify `docs/benchmark-methodology.md`: generalize comparisons while retaining local-runtime measurements and cost reporting.
- Modify `docs/superpowers/specs/2026-08-15-codex-skill-benchmark-design.md` and `docs/superpowers/plans/2026-08-15-codex-skill-eval-framework.md`: update future artifact paths and live examples to the new project identity; retain old names only in explicit migration/history prose.

### Task 1: Provider Schema and Model Target Resolution

**Files:**
- Create: `ai_systems_lab/__init__.py`
- Create: `ai_systems_lab/providers.py`
- Create: `tests/test_providers.py`

**Interfaces:**
- Consumes: configuration dictionaries already loaded by `scripts/lab` and a caller-supplied local gateway base URL.
- Produces: `ProviderConfigError`, immutable `ModelTarget`, `validate_provider_config(cfg) -> None`, `resolve_model_target(cfg, alias, local_base_url) -> ModelTarget`, `authorization_headers(target, environ=None) -> dict[str, str]`, and `chat_completions_request(target, messages, max_tokens, temperature) -> tuple[str, dict, dict]`.

- [ ] **Step 1: Write failing provider-resolution tests**

Create `tests/test_providers.py` with concrete local and remote fixtures:

```python
import os
import unittest
from unittest import mock

from ai_systems_lab.providers import (
    ProviderConfigError,
    authorization_headers,
    chat_completions_request,
    resolve_model_target,
    validate_provider_config,
)


class ProviderConfigTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "providers": {
                "local-llama": {"type": "llama_cpp"},
                "cloud-openai": {
                    "type": "openai_compatible",
                    "base_url": "https://api.example.test/v1/",
                    "api_key_env": "EXAMPLE_AI_API_KEY",
                },
            },
            "models": {
                "fast": {"provider": "local-llama"},
                "cloud-coder": {
                    "provider": "cloud-openai",
                    "provider_model": "vendor/coder-v1",
                },
            },
        }

    def test_validate_rejects_model_with_unknown_provider(self):
        self.config["models"]["fast"]["provider"] = "missing"
        with self.assertRaisesRegex(ProviderConfigError, "unknown provider 'missing'"):
            validate_provider_config(self.config)

    def test_resolve_local_target_uses_gateway_and_alias(self):
        target = resolve_model_target(self.config, "fast", "http://127.0.0.1:8080/v1")
        self.assertEqual(target.provider_type, "llama_cpp")
        self.assertEqual(target.base_url, "http://127.0.0.1:8080/v1")
        self.assertEqual(target.model_id, "fast")
        self.assertTrue(target.is_local)

    def test_resolve_cloud_target_uses_provider_model_and_trimmed_url(self):
        target = resolve_model_target(self.config, "cloud-coder", "http://127.0.0.1:8080/v1")
        self.assertEqual(target.provider_type, "openai_compatible")
        self.assertEqual(target.base_url, "https://api.example.test/v1")
        self.assertEqual(target.model_id, "vendor/coder-v1")
        self.assertFalse(target.is_local)

    def test_cloud_credentials_are_loaded_from_configured_environment_name(self):
        target = resolve_model_target(self.config, "cloud-coder", "http://127.0.0.1:8080/v1")
        with mock.patch.dict(os.environ, {"EXAMPLE_AI_API_KEY": "secret-value"}, clear=False):
            self.assertEqual(authorization_headers(target), {"Authorization": "Bearer secret-value"})

    def test_missing_cloud_credentials_fail_without_disclosing_a_value(self):
        target = resolve_model_target(self.config, "cloud-coder", "http://127.0.0.1:8080/v1")
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ProviderConfigError, "EXAMPLE_AI_API_KEY"):
                authorization_headers(target)

    def test_chat_request_contains_resolved_provider_model(self):
        target = resolve_model_target(self.config, "cloud-coder", "http://127.0.0.1:8080/v1")
        with mock.patch.dict(os.environ, {"EXAMPLE_AI_API_KEY": "secret-value"}, clear=False):
            url, payload, headers = chat_completions_request(
                target,
                [{"role": "user", "content": "hello"}],
                max_tokens=64,
                temperature=0.2,
            )
        self.assertEqual(url, "https://api.example.test/v1/chat/completions")
        self.assertEqual(payload["model"], "vendor/coder-v1")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "hello"}])
        self.assertEqual(headers, {"Authorization": "Bearer secret-value"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the focused tests and confirm the module is missing**

Run: `python3 -m unittest tests.test_providers -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'ai_systems_lab'`.

- [ ] **Step 3: Implement the provider package**

Create `ai_systems_lab/__init__.py`:

```python
PROJECT_SLUG = "ai-systems-lab"
PROJECT_NAME = "AI Systems Lab"
```

Create `ai_systems_lab/providers.py`:

```python
import os
from dataclasses import dataclass
from typing import Optional


SUPPORTED_PROVIDER_TYPES = {"llama_cpp", "openai_compatible"}


class ProviderConfigError(Exception):
    pass


@dataclass(frozen=True)
class ModelTarget:
    alias: str
    provider: str
    provider_type: str
    model_id: str
    base_url: str
    api_key_env: Optional[str]
    responses_api: bool

    @property
    def is_local(self):
        return self.provider_type == "llama_cpp"


def validate_provider_config(cfg):
    providers = cfg.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise ProviderConfigError("providers must be a non-empty object")
    for name, provider in providers.items():
        provider_type = provider.get("type")
        if provider_type not in SUPPORTED_PROVIDER_TYPES:
            raise ProviderConfigError(
                f"provider '{name}' has unsupported type {provider_type!r}"
            )
        if provider_type == "openai_compatible":
            if not provider.get("base_url"):
                raise ProviderConfigError(f"provider '{name}' requires base_url")
            if not provider.get("api_key_env"):
                raise ProviderConfigError(f"provider '{name}' requires api_key_env")
    for alias, model in cfg.get("models", {}).items():
        provider_name = model.get("provider")
        if not provider_name:
            raise ProviderConfigError(f"model '{alias}' requires provider")
        if provider_name not in providers:
            raise ProviderConfigError(
                f"model '{alias}' references unknown provider '{provider_name}'"
            )


def resolve_model_target(cfg, alias, local_base_url):
    validate_provider_config(cfg)
    try:
        model = cfg["models"][alias]
    except KeyError as exc:
        raise ProviderConfigError(f"unknown model alias '{alias}'") from exc
    provider_name = model["provider"]
    provider = cfg["providers"][provider_name]
    provider_type = provider["type"]
    base_url = local_base_url if provider_type == "llama_cpp" else provider["base_url"]
    return ModelTarget(
        alias=alias,
        provider=provider_name,
        provider_type=provider_type,
        model_id=model.get("provider_model", alias),
        base_url=base_url.rstrip("/"),
        api_key_env=provider.get("api_key_env"),
        responses_api=provider.get("responses_api") is True,
    )


def authorization_headers(target, environ=None):
    if not target.api_key_env:
        return {}
    environment = os.environ if environ is None else environ
    api_key = environment.get(target.api_key_env)
    if not api_key:
        raise ProviderConfigError(
            f"{target.api_key_env} is required for provider '{target.provider}'"
        )
    return {"Authorization": f"Bearer {api_key}"}


def chat_completions_request(target, messages, max_tokens, temperature):
    payload = {
        "model": target.model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    return (
        f"{target.base_url}/chat/completions",
        payload,
        authorization_headers(target),
    )
```

- [ ] **Step 4: Run the focused provider tests**

Run: `python3 -m unittest tests.test_providers -v`

Expected: all six provider tests PASS.

- [ ] **Step 5: Commit the provider boundary**

```bash
git add ai_systems_lab/__init__.py ai_systems_lab/providers.py tests/test_providers.py
git commit -m "feat: add model provider abstraction"
```

### Task 2: Provider-Aware Catalog and Local-Only Guardrails

**Files:**
- Modify: `config/lab.json:1-520`
- Create: `config/lab.cloud.example.json`
- Modify: `scripts/lab:1-740`
- Modify: `tests/test_lab.py:1-150`

**Interfaces:**
- Consumes: `resolve_model_target(cfg, alias, local_base_url)` and `validate_provider_config(cfg)` from Task 1.
- Produces: `model_target(cfg, model_id) -> ModelTarget`, `require_local_model(cfg, model_id, operation) -> ModelTarget`, provider-aware `validate_catalog_config`, and catalog rows containing `provider`, `provider_type`, and `availability`.

- [ ] **Step 1: Add failing catalog and guardrail tests**

Add imports for `ProviderConfigError` and add these cases to `tests/test_lab.py`:

```python
class ProviderCatalogTests(unittest.TestCase):
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
```

- [ ] **Step 2: Run the focused tests and verify both fail for missing provider behavior**

Run: `python3 -m unittest tests.test_lab.ProviderCatalogTests -v`

Expected: FAIL because cloud entries are sent through local weight/preset logic and `require_local_model` is undefined.

- [ ] **Step 3: Declare provider configuration and bind the local fleet**

At the top of `config/lab.json`, add the provider registry and change project-owned paths:

```json
{
  "providers": {
    "local-llama": {
      "type": "llama_cpp",
      "responses_api": true
    }
  },
  "paths": {
    "models_dir": "~/Models/ai-systems-lab",
    "legacy_models_dir": "~/Models/local-ai-lab",
    "state_dir": ".ai-systems-lab",
    "generated_dir": "config/generated",
    "results_dir": "benchmarks/results"
  }
}
```

Add `"provider": "local-llama"` to every object under `models`; do not add it to `watchlist`, because watchlist entries are not runnable. Create `config/lab.cloud.example.json` as a complete opt-in overlay:

```json
{
  "providers": {
    "cloud-openai-compatible": {
      "type": "openai_compatible",
      "base_url": "https://api.openai.com/v1",
      "api_key_env": "OPENAI_API_KEY",
      "responses_api": true
    }
  },
  "models": {
    "cloud-example": {
      "provider": "cloud-openai-compatible",
      "provider_model": "gpt-5.5",
      "description": "Opt-in cloud-hosted comparison model.",
      "official_model_id": "openai/gpt-5.5",
      "release_date": "2026-04",
      "architecture": "hosted",
      "parameters_total_b": null,
      "parameters_active_b": null,
      "quantization": null,
      "license": "OpenAI services agreement",
      "roles": ["coding", "reasoning", "comparison"],
      "status": "candidate",
      "expected_disk_gib": null,
      "context_tokens": 1050000,
      "source_url": "https://developers.openai.com/api/docs/models/gpt-5.5",
      "last_verified": null,
      "agent_compatibility": {}
    }
  }
}
```

The example is never loaded by default because it is an overlay and no committed use case selects `cloud-example`.

- [ ] **Step 4: Integrate provider validation and local-only guards in `scripts/lab`**

Import the Task 1 interfaces after `REPO_ROOT` is available. Because `./scripts/lab` executes with `scripts/` as `sys.path[0]`, add the repository root before importing the root package, then catch provider errors in `main` and add these helpers:

```python
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_systems_lab.providers import (
    ProviderConfigError,
    resolve_model_target,
    validate_provider_config,
)


def model_target(cfg, model_id):
    return resolve_model_target(cfg, model_id, f"{api_base(cfg)}/v1")


def require_local_model(cfg, model_id, operation):
    target = model_target(cfg, model_id)
    if not target.is_local:
        raise LabError(
            f"{operation} requires a local llama.cpp model; "
            f"'{model_id}' uses provider '{target.provider}'"
        )
    return target
```

Call `validate_provider_config(cfg)` at the start of `validate_catalog_config`. In the `models` branch, enforce `preset.ctx-size == context_tokens` only when `model_target(cfg, model_id).is_local`. In `catalog_rows`, call weight/path functions only for local targets, return `installed=None` and `availability="remote"` for cloud models, and include `provider` plus `provider_type` on every row. Change the text catalog columns to `MODEL`, `PROVIDER`, `STATUS`, `ROLES`, `QUANT`, `PARAMS`, `DISK`, `AVAILABLE`, `VERIFIED`, displaying `remote` for cloud entries.

Add `require_local_model` before any file, process, service, or residency work in `pull_one`, `cmd_bench_llama`, `cmd_load`, `cmd_switch`, `cmd_unload`, `cmd_verify`, `Gateway.ensure_model`, and local judge selection. Preserve `catalog`, `chat`, `bench-server`, and candidate `bench-quality` as provider-agnostic commands.

Update every existing `tests/test_lab.py` fixture that reaches catalog, inference, gateway, or lifecycle code so it declares `"providers": {"local": {"type": "llama_cpp"}}` and gives each runnable fixture model `"provider": "local"`. Do not weaken validation or add an implicit local-provider default just to preserve old test fixtures; committed runnable configuration must make provider ownership explicit.

Change the final error handler to:

```python
    except (LabError, ProviderConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
```

- [ ] **Step 5: Run catalog tests and the full existing suite**

Run: `python3 -m unittest tests.test_lab.ProviderCatalogTests -v`

Expected: both tests PASS.

Run: `make test`

Expected: all existing and new tests PASS; no existing local catalog, gateway, verifier, or export test regresses.

- [ ] **Step 6: Validate both committed configurations parse**

Run: `python3 -m json.tool config/lab.json >/dev/null`

Expected: exit 0.

Run: `python3 -m json.tool config/lab.cloud.example.json >/dev/null`

Expected: exit 0.

- [ ] **Step 7: Commit provider-aware catalog support**

```bash
git add config/lab.json config/lab.cloud.example.json scripts/lab tests/test_lab.py
git commit -m "feat: make model catalog provider aware"
```

### Task 3: Provider-Agnostic Chat and Evaluation

**Files:**
- Modify: `ai_systems_lab/providers.py:1-120`
- Modify: `scripts/lab:1754-1787,2324-2480,2503-2760`
- Modify: `tests/test_providers.py:1-130`
- Modify: `tests/test_lab.py:150-360`

**Interfaces:**
- Consumes: `ModelTarget`, `model_target`, `chat_completions_request`, and the existing `json_request` transport.
- Produces: `chat_completion(cfg, model_id, prompt, max_tokens, temperature, timeout) -> dict`, with normalized response text/usage/latency for either provider; provider-neutral `cmd_chat`, `cmd_bench_server`, and candidate execution in `cmd_bench_quality`.

- [ ] **Step 1: Write failing transport and lifecycle tests**

Add the following to `tests/test_lab.py`:

```python
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
```

- [ ] **Step 2: Run the new tests and confirm the generalized function is absent**

Run: `python3 -m unittest tests.test_lab.InferenceProviderTests -v`

Expected: FAIL with `AttributeError` because `chat_completion` is not defined.

- [ ] **Step 3: Replace local-only completion transport with normalized provider transport**

Replace `local_chat_completion` with the following signature and control flow:

```python
def chat_completion(cfg, model_id, prompt, max_tokens, temperature, timeout):
    target = model_target(cfg, model_id)
    if target.is_local:
        switch_to_model(cfg, model_id, timeout=timeout)
    url, payload, headers = chat_completions_request(
        target,
        prompt["messages"],
        max_tokens,
        prompt.get("temperature", temperature),
    )
    started = time.perf_counter()
    operation = lambda: json_request(
        "POST", url, payload, timeout=timeout, headers=headers
    )
    if target.is_local:
        response, model_worker_peak_rss_gib = run_with_server_memory_sample(
            cfg, operation, model_id=model_id
        )
    else:
        response = operation()
        model_worker_peak_rss_gib = None
    latency = time.perf_counter() - started
    usage = response.get("usage") or {}
    completion_tokens = usage.get("completion_tokens")
    choices = response.get("choices") or []
    message = choices[0].get("message") or {} if choices else {}
    content = message.get("content")
    if isinstance(content, str):
        output_text = content
    elif isinstance(content, list):
        output_text = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    else:
        output_text = ""
    return {
        "response": response,
        "text": output_text,
        "latency_seconds": round(latency, 6),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": completion_tokens,
        "total_tokens": usage.get("total_tokens"),
        "completion_tokens_per_second": (
            round(completion_tokens / latency, 6) if completion_tokens else None
        ),
        "finish_reason": choices[0].get("finish_reason") if choices else None,
        "model_worker_peak_rss_gib": model_worker_peak_rss_gib,
        "provider": target.provider,
        "provider_model": target.model_id,
    }
```

Import `chat_completions_request` from `ai_systems_lab.providers`. Update `cmd_chat` and candidate calls in `cmd_bench_quality` to call `chat_completion`.

In `cmd_bench_server`, remove unconditional `require_model_files` and `switch_to_model`. Filter missing files only for local targets, call `chat_completion` for every request, and run `unload_model` only when `args.unload_after and model_target(cfg, model_id).is_local`. Include `provider` and `provider_model` in each result row.

In `cmd_bench_quality`, apply the same local-only preflight/unload rules to candidate models and include provider identity in result rows and benchmark metadata. Keep local judge residency restoration intact until Task 4 changes judge selection.

Update `benchmark_model_metadata` so each model records `provider`, `provider_type`, `provider_model`, and a runtime object. Local targets record `{"name": "llama.cpp", "version": runtime_version(cfg)}`; remote targets record `{"name": target.provider_type, "version": None}`. Remove the unconditional top-level llama.cpp `runtime` field from `write_metadata`, because it falsely labels cloud-only runs; the per-model runtime is the source of truth for mixed comparisons.

- [ ] **Step 4: Make command routing tests explicit**

Add these command-level tests to `InferenceProviderTests`:

```python
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
```

- [ ] **Step 5: Run provider inference and full regression tests**

Run: `python3 -m unittest tests.test_lab.InferenceProviderTests -v`

Expected: all provider inference tests PASS.

Run: `make test`

Expected: all tests PASS.

- [ ] **Step 6: Commit provider-agnostic inference**

```bash
git add ai_systems_lab/providers.py scripts/lab tests/test_providers.py tests/test_lab.py
git commit -m "feat: run chat and evaluations across providers"
```

### Task 4: Isolate Judge Provider Details

**Files:**
- Modify: `ai_systems_lab/providers.py:1-170`
- Modify: `scripts/lab:2480-2760,3040-3120`
- Modify: `tests/test_providers.py:1-180`
- Modify: `tests/test_lab.py:120-220`
- Modify: `config/lab.json:35-55`

**Interfaces:**
- Consumes: provider registry/model aliases from Tasks 1–3.
- Produces: `responses_json_request(target, instructions, input_value, schema, reasoning_effort) -> tuple[str, dict, dict]`; judge configuration where `provider` is a configured provider name or `manual`; compatibility aliases `local -> local-llama` and `openai -> cloud-openai-compatible` remain accepted by the CLI.

- [ ] **Step 1: Write failing judge-adapter tests**

Extend `tests/test_providers.py` with this concrete adapter test:

```python
    def test_responses_request_uses_provider_capability_and_credentials(self):
        self.config["providers"]["cloud-openai"]["responses_api"] = True
        target = resolve_model_target(
            self.config, "cloud-coder", "http://127.0.0.1:8080/v1"
        )
        schema = {
            "type": "object",
            "properties": {"pass": {"type": "boolean"}},
            "required": ["pass"],
            "additionalProperties": False,
        }
        with mock.patch.dict(os.environ, {"EXAMPLE_AI_API_KEY": "secret-value"}, clear=False):
            url, payload, headers = responses_json_request(
                target,
                "Score the response.",
                "evaluation input",
                schema,
                "low",
            )
        self.assertEqual(url, "https://api.example.test/v1/responses")
        self.assertEqual(payload["model"], "vendor/coder-v1")
        self.assertEqual(payload["text"]["format"]["schema"], schema)
        self.assertEqual(headers, {"Authorization": "Bearer secret-value"})
```

Import `responses_json_request` in the test module. Extend `QualityTests` in `tests/test_lab.py` with:

```python
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
```

- [ ] **Step 2: Run judge tests and confirm they fail under hard-coded OpenAI/local branching**

Run: `python3 -m unittest tests.test_providers tests.test_lab.QualityTests -v`

Expected: FAIL because `responses_json_request` is absent and CLI/config logic only recognizes `manual`, `local`, and `openai`.

- [ ] **Step 3: Move Responses request construction behind the provider module**

Add `responses_json_request` to `ai_systems_lab/providers.py`:

```python
def responses_json_request(
    target,
    instructions,
    input_value,
    schema,
    reasoning_effort,
):
    if not target.responses_api:
        raise ProviderConfigError(
            f"provider '{target.provider}' does not support the Responses API judge"
        )
    payload = {
        "model": target.model_id,
        "instructions": instructions,
        "input": input_value,
        "store": False,
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": "quality_score",
                "strict": True,
                "schema": schema,
            },
        },
    }
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}
    return (
        f"{target.base_url}/responses",
        payload,
        authorization_headers(target),
    )
```

Refactor `openai_score_response` to receive a resolved `ModelTarget` and use the new request builder. Refactor `local_score_response` to call `chat_completion`. Make `score_quality_response` branch only on `manual`, `target.is_local`, or remote target; it must not contain provider URL, environment-variable, or Authorization construction.

Change `--judge-provider` to accept a configured provider name by removing fixed `choices`. Preserve existing invocations by mapping `local` to `local-llama` and `openai` to `cloud-openai-compatible` in `judge_config`, with a deprecation line on stderr. A named judge model must belong to the selected provider; fail before inference when it does not.

- [ ] **Step 4: Update default judge configuration without enabling paid inference**

Keep the committed default exactly provider-neutral and manual:

```json
"judge": {
  "provider": "manual",
  "model": null,
  "reasoning_effort": "low",
  "timeout_seconds": 120
}
```

Remove `base_url` from the judge block because provider configuration owns endpoints and credentials.

- [ ] **Step 5: Run judge tests and the full suite**

Run: `python3 -m unittest tests.test_providers tests.test_lab.QualityTests -v`

Expected: all provider and quality tests PASS.

Run: `make test`

Expected: all tests PASS, including manual judge and legacy local/OpenAI CLI compatibility.

- [ ] **Step 6: Commit judge isolation**

```bash
git add ai_systems_lab/providers.py scripts/lab tests/test_providers.py tests/test_lab.py config/lab.json
git commit -m "refactor: isolate evaluation provider details"
```

### Task 5: Generalize the Codex Skill-Evaluation Target

**Files:**
- Modify: `scripts/skill_eval.py:1-340`
- Modify: `tests/test_skill_eval.py:230-455`
- Modify: `benchmarks/skills/cases.schema.json:1-5`

**Interfaces:**
- Consumes: `resolve_model_target(cfg, alias, local_base_url) -> ModelTarget` and the provider capability fields from Tasks 1–4.
- Produces: provider-neutral `catalog:ALIAS` skill-evaluation targets; legacy `local:ALIAS` and `openai:MODEL_ID` target parsing; `TargetSpec` values containing catalog alias, provider identity/type, provider model, base URL, credential environment name, context limit, and Responses capability.

- [ ] **Step 1: Write failing provider-neutral target tests**

Update `PromptfooConfigTests.setUp` to use `catalog:fast-9b`, and add these tests to `tests/test_skill_eval.py`:

```python
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
```

- [ ] **Step 2: Run the target/config tests and confirm the new syntax fails**

Run: `python3 -m unittest tests.test_skill_eval.PromptfooConfigTests -v`

Expected: FAIL because `parse_target` only accepts `openai:` and `local:` and `TargetSpec` lacks provider fields.

- [ ] **Step 3: Resolve catalog targets through the shared provider module**

Add `re` and `sys` to `scripts/skill_eval.py` imports, then add `REPO_ROOT` to `sys.path` before importing `PROJECT_NAME`, `ProviderConfigError`, and `resolve_model_target`. Replace `TargetSpec` with:

```python
@dataclass(frozen=True)
class TargetSpec:
    selector: str
    alias: Optional[str]
    provider_name: str
    provider_type: str
    model: str
    base_url: Optional[str]
    api_key_env: Optional[str]
    context_tokens: Optional[int]
    responses_api: bool
```

Implement `catalog:ALIAS` by resolving the alias with:

```python
def _local_api_base(cfg):
    server = _require_mapping(cfg.get("server"), "configuration.server")
    return f"http://{server.get('host', '127.0.0.1')}:{server.get('port', 8080)}/v1"


def _catalog_target(alias, cfg, selector):
    try:
        target = resolve_model_target(cfg, alias, _local_api_base(cfg))
    except ProviderConfigError as error:
        raise SkillEvalError(str(error)) from error
    model_config = _require_mapping(cfg["models"][alias], f"configuration.models.{alias}")
    roles = model_config.get("roles")
    if not isinstance(roles, list) or any(not isinstance(role, str) for role in roles):
        raise SkillEvalError(f"model alias has invalid roles: {alias}")
    if "embedding" in roles:
        raise SkillEvalError("skill evaluation target must not use an embedding model")
    context_tokens = model_config.get("context_tokens")
    if not isinstance(context_tokens, int) or isinstance(context_tokens, bool) or context_tokens < 1:
        raise SkillEvalError(f"model alias must define positive context_tokens: {alias}")
    if not target.responses_api:
        raise SkillEvalError(
            f"provider '{target.provider}' must declare Responses API capability"
        )
    return TargetSpec(
        selector=selector,
        alias=alias,
        provider_name=target.provider,
        provider_type=target.provider_type,
        model=target.model_id,
        base_url=target.base_url,
        api_key_env=target.api_key_env,
        context_tokens=context_tokens,
        responses_api=target.responses_api,
    )
```

`parse_target("catalog:ALIAS", cfg)` calls `_catalog_target`. `local:ALIAS` remains a compatibility spelling that calls the same function and then verifies `provider_type == "llama_cpp"`. `openai:MODEL_ID` remains a compatibility path with `alias=None`, `provider_name="openai-codex-sdk"`, `provider_type="openai"`, no custom URL/env/context, and `responses_api=True`. All new docs and examples use `catalog:`.

- [ ] **Step 4: Compile catalog providers without vendor branches**

For a catalog target, derive a sanitized Codex provider ID from `provider_name`, and configure it through the existing Codex SDK provider:

```python
provider_id = "ai_systems_lab_" + re.sub(r"[^a-z0-9_]+", "_", target.provider_name.lower())
provider_definition = {
    "name": PROJECT_NAME,
    "base_url": target.base_url,
    "wire_api": "responses",
}
if target.api_key_env:
    provider_definition["env_key"] = target.api_key_env
provider_config.update(
    {
        "model_provider": provider_id,
        "cli_config": {
            "model_context_window": target.context_tokens,
            "model_providers": {provider_id: provider_definition},
        },
    }
)
```

Keep the legacy direct `openai:MODEL_ID` path on the Codex SDK’s built-in provider. Change descriptions to use `target.selector`. Make `validate_judge` reject self-grading whenever `target.model == judge_model`, regardless of provider spelling.

- [ ] **Step 5: Rename private evaluation identity and schema metadata**

Change the module docstring to **AI Systems Lab**. Treat both `.ai-systems-lab` and `.local-ai-lab` as forbidden private evidence within exported skill packages, but create new run roots only under `.ai-systems-lab/skill-evals`. Change the schema header to:

```json
{
  "$id": "https://ai-systems-lab.dev/schemas/skill-eval-cases-v1.json",
  "title": "AI Systems Lab Skill Evaluation Cases v1"
}
```

Update `tests/test_skill_eval.py` paths and assertions accordingly, retaining one `.local-ai-lab` case solely to prove legacy private evidence remains excluded.

- [ ] **Step 6: Run Python and Node-backed deterministic checks**

Run: `python3 -m unittest tests.test_skill_eval -v`

Expected: all skill contract, workspace, target, Promptfoo config, and execution-mocking tests PASS.

Run: `make test`

Expected: the combined lab/provider/skill-evaluation suite PASS.

- [ ] **Step 7: Commit skill-evaluation provider integration**

```bash
git add scripts/skill_eval.py tests/test_skill_eval.py benchmarks/skills/cases.schema.json
git commit -m "feat: resolve skill evals through model providers"
```

### Task 6: Rename Runtime Identity with Safe Legacy Migration

**Files:**
- Modify: `scripts/lab:24-195,990-1218,2997-3010`
- Modify: `tests/test_lab.py:1-80,240-285`
- Modify: `.gitignore:1-14`

**Interfaces:**
- Consumes: existing legacy environment variables, `.local-ai-lab` state, `~/Models/local-ai-lab`, and `com.erik.local-ai-lab` LaunchAgent if present.
- Produces: `AI_SYSTEMS_LAB_CONFIG`, `AI_SYSTEMS_LAB_LOCAL_CONFIG`, `AI_SYSTEMS_LAB_STATE_PATH`, `AI_SYSTEMS_LAB_IDLE_SECONDS_OVERRIDE`, `.ai-systems-lab`, `~/Models/ai-systems-lab`, and `com.erik.ai-systems-lab`, with explicit read-only legacy fallbacks.

- [ ] **Step 1: Write failing identity and fallback tests**

Rename the SourceFileLoader module from `local_ai_lab` to `ai_systems_lab_cli`. Add tests proving:

```python
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
            self.assertEqual(
                lab.project_env("CONFIG"),
                "/new/config.json",
            )

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
                    "legacy_models_dir": str(legacy),
                }
            }
            self.assertEqual(lab.paths(config)["models_dir"], legacy.resolve())

    def test_new_service_identity_is_used_for_writes(self):
        self.assertEqual(lab.SERVICE_LABEL, "com.erik.ai-systems-lab")
        self.assertEqual(lab.LEGACY_SERVICE_LABEL, "com.erik.local-ai-lab")
```

- [ ] **Step 2: Run migration tests and confirm new names are undefined**

Run: `python3 -m unittest tests.test_lab.IdentityMigrationTests -v`

Expected: FAIL for missing `project_env`, `LEGACY_SERVICE_LABEL`, and new service/path behavior.

- [ ] **Step 3: Implement new identifiers with bounded legacy reads**

Define:

```python
SERVICE_LABEL = "com.erik.ai-systems-lab"
LEGACY_SERVICE_LABEL = "com.erik.local-ai-lab"
SERVICE_STATE_DIR = Path.home() / "Library" / "Application Support" / SERVICE_LABEL
LEGACY_SERVICE_STATE_PATH = (
    Path.home() / "Library" / "Application Support" / LEGACY_SERVICE_LABEL / "state.json"
)
SERVICE_STATE_PATH = SERVICE_STATE_DIR / "state.json"
LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{SERVICE_LABEL}.plist"
LEGACY_LAUNCH_AGENT_PATH = (
    Path.home() / "Library" / "LaunchAgents" / f"{LEGACY_SERVICE_LABEL}.plist"
)


def project_env(suffix):
    return os.environ.get(f"AI_SYSTEMS_LAB_{suffix}") or os.environ.get(
        f"LOCAL_AI_LAB_{suffix}"
    )
```

Use `project_env` for `CONFIG`, `LOCAL_CONFIG`, `STATE_PATH`, and `IDLE_SECONDS_OVERRIDE`. `service_state_path()` must always return the new path for writes unless explicitly overridden; `load_service_state()` may read `LEGACY_SERVICE_STATE_PATH` only when the new path does not exist, and the next `save_service_state()` writes the normalized state to the new path.

In `paths(cfg)`, resolve `models_dir`; if it does not exist and the explicitly configured `legacy_models_dir` does, return the legacy directory and print one migration warning to stderr. Never create, move, or delete the legacy weights automatically.

Update `SERVICE_LABEL`, gateway `owned_by`, human-readable server messages, CLI description, defaults, and `.gitignore` to the new identity. Keep `.local-ai-lab/` ignored only as an annotated migration entry and add `.ai-systems-lab/`.

- [ ] **Step 4: Make service installation reject an active legacy LaunchAgent safely**

Before installing the new LaunchAgent, detect `LEGACY_LAUNCH_AGENT_PATH`. If it exists or `launchctl print gui/$UID/com.erik.local-ai-lab` succeeds, raise:

```text
Legacy com.erik.local-ai-lab service is still installed. Run './scripts/lab service-uninstall-legacy' before installing com.erik.ai-systems-lab.
```

Add `service-uninstall-legacy` as an explicit command that bootouts only `com.erik.local-ai-lab` and unlinks only `LEGACY_LAUNCH_AGENT_PATH`; it must not remove state or model files. Implement the bounded target as:

```python
def cmd_service_uninstall_legacy(args, cfg):
    target = f"gui/{os.getuid()}/{LEGACY_SERVICE_LABEL}"
    subprocess.run(["launchctl", "bootout", target], check=False)
    if LEGACY_LAUNCH_AGENT_PATH.exists():
        LEGACY_LAUNCH_AGENT_PATH.unlink()
    print(f"legacy service removed: {LEGACY_SERVICE_LABEL}")
```

Register only this exact handler in `COMMANDS`, add its parser entry, and cover both target paths with mocks so no test calls real `launchctl` or deletes user files.

- [ ] **Step 5: Run migration tests and full regression suite**

Run: `python3 -m unittest tests.test_lab.IdentityMigrationTests -v`

Expected: all migration tests PASS.

Run: `make test`

Expected: all tests PASS.

- [ ] **Step 6: Commit runtime identity migration**

```bash
git add .gitignore scripts/lab tests/test_lab.py
git commit -m "feat: migrate runtime identity to ai systems lab"
```

### Task 7: Project Metadata and Documentation

**Files:**
- Modify: `pyproject.toml:1-27`
- Modify: `README.md:1-452`
- Modify: `docs/model-fleet.md:1-96`
- Modify: `docs/client-configuration.md:1-96`
- Modify: `docs/benchmark-methodology.md:1-96`
- Modify: `docs/superpowers/specs/2026-08-15-codex-skill-benchmark-design.md:1-160`
- Modify: `docs/superpowers/plans/2026-08-15-codex-skill-eval-framework.md:1-430`

**Interfaces:**
- Consumes: final config names, provider semantics, commands, and migration behavior from Tasks 1–5.
- Produces: accurate package metadata and an operator-facing explanation of AI Systems Lab as an experimental local/cloud systems testbed.

- [ ] **Step 1: Update package metadata exactly**

Set:

```toml
[project]
name = "ai-systems-lab"
version = "0.1.0"
description = "Experimental lab for model providers, routing, compatibility, benchmarking, and evaluation across local and cloud AI systems."
```

Replace keywords `local-ai` and `local-llm` with `ai-systems`, `model-providers`, and `openai-compatible`, while retaining `llama.cpp`, `model-routing`, `llm-evaluation`, and `benchmarking`. Change all three project URLs to `https://github.com/erik-fryscok/ai-systems-lab` variants.

- [ ] **Step 2: Rewrite the README framing and provider configuration**

Use `# AI Systems Lab` as the title. The opening must say all of the following plainly:

- this is an experimental learning and evaluation testbed, not production infrastructure;
- local llama.cpp remains a first-class backend and the default workflow;
- cloud-hosted OpenAI-compatible providers can participate in the same chat and evaluation paths;
- workload aliases choose models, and each model resolves through a provider boundary;
- provider credentials are opt-in environment variables and are never stored in committed configuration.

Retain the complete local quick start and service instructions. Add a “Provider Model” section with this exact overlay workflow:

```sh
cp config/lab.cloud.example.json config/lab.local.json
read -r -s OPENAI_API_KEY
export OPENAI_API_KEY
./scripts/lab chat cloud-example "Compare local and hosted inference tradeoffs."
./scripts/lab bench-server cloud-example --prompt-file benchmarks/prompts/coder.jsonl
```

Explain that `pull`, `presets`, `start`, `load`, `switch`, `unload`, `verify`, and `bench-llama` are local llama.cpp lifecycle commands; `catalog`, `chat`, `bench-server`, and candidate `bench-quality` are provider-agnostic. Update project-owned paths, service labels, and repository links to the new name.

Add a migration section containing the intentionally retained legacy names and exact safe order:

```sh
./scripts/lab service-uninstall-legacy
mv "$HOME/Models/local-ai-lab" "$HOME/Models/ai-systems-lab"
make service-install
```

State that moving weights is optional because the explicit legacy path fallback remains readable; state and credentials are never deleted by the migration command.

- [ ] **Step 3: Align focused documentation**

In `docs/model-fleet.md`, keep the local admission gate and hardware constraints, but introduce it as the `local-llama` provider’s fleet policy. In `docs/client-configuration.md`, label `http://127.0.0.1:8080/v1` as the local gateway rather than the universal endpoint and add direct cloud-provider selection through model aliases. In `docs/benchmark-methodology.md`, replace “Can local AI ship it?” with “Where does each model/provider combination meet the workload contract?” and add provider identity, marginal API cost, and local-runtime version as comparison fields.

Update unimplemented future artifact paths from `.local-ai-lab/skill-evals` to `.ai-systems-lab/skill-evals` in the existing Superpowers spec/plans. Do not rewrite historical case-study facts about local models.

- [ ] **Step 4: Run documentation and metadata checks**

Run: `python3 -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb'))"`

Expected: exit 0 and no parse error.

Run: `python3 -m json.tool config/lab.json >/dev/null && python3 -m json.tool config/lab.cloud.example.json >/dev/null`

Expected: exit 0.

Run: `rg -n 'AI Systems Lab|experimental learning and evaluation|local-llama|cloud-example' README.md docs pyproject.toml config`

Expected: matches in the README/provider docs, package metadata, and example configuration.

- [ ] **Step 5: Commit project messaging and metadata**

```bash
git add pyproject.toml README.md docs config/lab.cloud.example.json
git commit -m "docs: rename project to AI Systems Lab"
```

### Task 8: Acceptance Validation and Stale-Reference Audit

**Files:**
- Modify: `tests/test_lab.py`
- Modify: `tests/test_providers.py`
- Modify: any tracked file identified by the audit whose old reference is neither migration compatibility nor historical context.

**Interfaces:**
- Consumes: all in-repository changes from Tasks 1–6.
- Produces: executable acceptance evidence and an explicit allowlist rationale for every retained legacy identifier.

- [ ] **Step 1: Add a branding regression test over current project metadata**

Add to `tests/test_lab.py`:

```python
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
```

- [ ] **Step 2: Run all deterministic tests**

Run: `make test`

Expected: all tests PASS.

- [ ] **Step 3: Run non-network CLI smoke checks**

Run: `./scripts/lab --help`

Expected: exit 0 and description names AI Systems Lab.

Run: `./scripts/lab catalog --format json`

Expected: exit 0; every runnable row contains `provider` and `provider_type`; local rows report local availability without exposing private paths.

Run: `./scripts/lab presets`

Expected: exit 0 and `config/generated/models.ini` is rendered for local models only.

- [ ] **Step 4: Audit every retained legacy name**

Run:

```bash
git grep -n -E 'local-ai-lab|Local AI Lab|LOCAL_AI_LAB|local_ai_lab|com\.erik\.local-ai-lab'
```

Expected retained categories only:

- `scripts/lab`: legacy environment-variable reads, legacy service constant/path, and legacy model-directory fallback;
- `scripts/skill_eval.py`: rejection of legacy `.local-ai-lab` private evidence and compatibility parsing for `local:ALIAS`;
- `.gitignore`: ignored legacy runtime state;
- `README.md`: migration commands and compatibility explanation;
- `tests/test_lab.py`: assertions for the bounded legacy fallbacks;
- `tests/test_skill_eval.py`: assertions that legacy private evidence stays excluded and the legacy target spelling maps to the catalog;
- this implementation plan: source/target migration instructions.

Any match in package metadata, headings, current URLs, current service output, provider ownership, default state paths, or non-migration documentation is stale and must be changed before proceeding.

- [ ] **Step 5: Review the final scoped diff**

Run: `git status --short`

Expected: only ERI-19 files are modified; ignored local state, generated config, `.idea`, `.venv`, and worktrees are absent.

Run: `git diff --check`

Expected: exit 0 with no whitespace errors.

Run: `git diff --stat origin/main...HEAD`

Expected: changes are limited to provider/config/runtime tests, project metadata, and documentation described by this plan.

- [ ] **Step 6: Commit final acceptance fixes if the audit required any**

If Task 8 changed tracked files, commit only those verified fixes:

```bash
git add tests/test_lab.py tests/test_providers.py scripts/lab README.md pyproject.toml config docs .gitignore ai_systems_lab
git diff --cached --check
git commit -m "test: enforce ai systems lab acceptance criteria"
```

If Task 8 changed nothing, do not create an empty commit.

### Task 9: GitHub Repository and Local Checkout Cutover

**Files:**
- External repository name: `erik-fryscok/local-ai-lab` -> `erik-fryscok/ai-systems-lab`
- Git remote: `origin` -> `git@github.com:erik-fryscok/ai-systems-lab.git`
- Local checkout directory: `local-ai-lab` -> `ai-systems-lab`

**Interfaces:**
- Consumes: a clean, tested ERI-19 branch and existing GitHub SSH credentials.
- Produces: renamed GitHub repository, SSH origin, and matching local checkout directory without changing commit history.

- [ ] **Step 1: Confirm the exact clean cutover target**

Run: `git status --short --branch`

Expected: the ERI-19 implementation branch has no uncommitted files and contains all Task 1–8 commits.

Run: `git remote -v`

Expected before rename: `origin` is `git@github.com:erik-fryscok/local-ai-lab.git` for fetch and push.

- [ ] **Step 2: Verify GitHub SSH access and configure `gh` for SSH**

Run: `ssh -T git@github.com`

Expected: GitHub confirms successful authentication (the command may return GitHub’s documented non-zero status because shell access is disabled).

Run: `gh config set -h github.com git_protocol ssh`

Expected: exit 0.

- [ ] **Step 3: Rename the GitHub repository**

Run:

```bash
gh repo rename ai-systems-lab --repo erik-fryscok/local-ai-lab --yes
```

Expected: the repository is available as `erik-fryscok/ai-systems-lab`; do not create a second repository.

- [ ] **Step 4: Set and verify the new SSH remote**

Run:

```bash
git remote set-url origin git@github.com:erik-fryscok/ai-systems-lab.git
git remote -v
git ls-remote origin HEAD
```

Expected: both fetch and push use `git@github.com:erik-fryscok/ai-systems-lab.git`, and `git ls-remote` resolves `HEAD` over SSH.

- [ ] **Step 5: Push the implementation branch through SSH**

Review `git status` and the intended branch once more, then run:

```bash
git push -u origin HEAD
```

Expected: the current branch is published to the renamed repository over SSH.

- [ ] **Step 6: Rename the local checkout after ending processes rooted in it**

From the parent directory, after closing shells, test runners, and editor tasks that use the old absolute path:

```bash
cd /Users/erik/Developer/personal
mv local-ai-lab ai-systems-lab
cd ai-systems-lab
git status --short --branch
```

Expected: the checkout opens at `/Users/erik/Developer/personal/ai-systems-lab`, Git history and worktree state are unchanged, and the branch still tracks the renamed SSH origin. Perform this as the last action because the active Codex workspace cannot safely change its own root mid-task.

- [ ] **Step 7: Verify the public repository identity**

Run:

```bash
gh repo view erik-fryscok/ai-systems-lab --json name,nameWithOwner,url
```

Expected: `name` is `ai-systems-lab`, `nameWithOwner` is `erik-fryscok/ai-systems-lab`, and the URL uses the new slug.

---

## Final Acceptance Checklist

- [ ] `make test` passes.
- [ ] `./scripts/lab catalog --format json` reports provider identity for every runnable model.
- [ ] Local catalog, pull, gateway, service, verify, and benchmark tests still pass.
- [ ] A mocked OpenAI-compatible cloud model can run through chat, server benchmark, and quality candidate paths without local model residency calls.
- [ ] Skill evaluations resolve new `catalog:ALIAS` targets through the same provider registry and reject providers without Responses capability.
- [ ] Manual judging remains the default and no committed workflow incurs cloud cost.
- [ ] Provider URLs and credential environment names live in provider configuration, not routing/evaluation branches.
- [ ] README and focused docs describe both local and cloud scope and explicitly disclaim production readiness.
- [ ] Every old-name search result is explained by migration compatibility, history, or this plan.
- [ ] GitHub repository, SSH origin, package metadata, display name, and local checkout all use the new identity.
