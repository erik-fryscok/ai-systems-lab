# local-ai-lab

Local llama.cpp lab for running one router endpoint with workload-specific model
aliases, repeatable Hugging Face pulls, and benchmark output you can compare over
time.

The default setup is:

| Use case | Default alias | Purpose |
| --- | --- | --- |
| `coder` | `coder-30b` | Qwen3-Coder 30B-A3B Q5_K_M, loaded at startup |
| `reason` | `reason-27b` | Qwen3.6 27B Q5_K_M, loaded on demand |
| `fast` | `fast-9b` | Qwen3.5 9B Q5_K_M, loaded on demand |
| `embedding` | `embed-4b` | Qwen3 Embedding 4B Q5_K_M |

## Requirements

This repo expects these tools on `PATH`:

- `llama-server`
- `llama-bench`
- `hf` from `huggingface_hub` (`huggingface-cli` also works as a fallback)
- Python 3

Check the current machine:

```sh
make doctor
```

## Quick Start

Pull the default coding model into the common model directory:

```sh
./scripts/lab pull coder
```

Render the llama.cpp router preset:

```sh
make presets
```

Start the router:

```sh
make start
```

The local OpenAI-compatible endpoint is:

```text
http://127.0.0.1:8080/v1
```

List router models and load state:

```sh
make models
```

Switch workloads:

```sh
./scripts/lab pull reason
./scripts/lab switch reason

./scripts/lab pull fast
./scripts/lab switch fast
```

`switch`, `load`, `chat`, and server benchmarks enforce the residency policy:
keep at most one non-embedding model loaded, while allowing embedding models to
stay loaded alongside it.

Stop the router:

```sh
make stop
```

## Client Usage

Use one endpoint. Before changing to a different non-embedding model, switch the
resident model through the lab control plane:

```sh
./scripts/lab switch coder
```

```js
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "local",
  baseURL: "http://127.0.0.1:8080/v1",
});

await client.chat.completions.create({
  model: "coder-30b",
  messages: [{ role: "user", content: "Review this function." }],
});
```

For another non-embedding model, switch first, then use that alias:

```sh
./scripts/lab switch reason
```

```js
await client.chat.completions.create({
  model: "reason-27b",
  messages: [{ role: "user", content: "Compare these designs." }],
});
```

Embedding models are exempt from the single non-embedding model rule and can
remain loaded alongside the active chat/reasoning/coding model.

## Configuration

Edit [config/lab.json](config/lab.json).

Important sections:

- `paths.models_dir`: common GGUF directory. Defaults to `~/Models/local-ai-lab`.
- `server`: router host, port, `models_max`, autoload, metrics, and extra args.
- `preset_defaults`: llama.cpp args applied to every model preset.
- `use_cases`: workload names, defaults, candidate models, and prompt files.
- `models`: stable aliases, Hugging Face source files, local dirs, and per-model preset args.

By default, `server.models_autoload` is `false` and `server.models_max` is
`null`. The wrapper then starts llama.cpp with enough capacity for one
non-embedding model plus all configured embedding models, and the wrapper does
the unload-then-load switch before requests. That avoids direct router autoloads
leaving multiple chat/reasoning/coding models resident.

Render the generated llama.cpp preset after changes:

```sh
./scripts/lab presets
```

The generated file is ignored by git:

```text
config/generated/models.ini
```

Add a local fine-tuned GGUF by using a direct path:

```json
"coder-my-ft": {
  "description": "My fine-tuned coding model.",
  "path": "~/Models/local-ai-lab/my-ft/model.gguf",
  "preset": {
    "ctx-size": 16384,
    "load-on-startup": false
  }
}
```

Then add that alias to a `candidate_models` list and benchmark it.

## Model Pulls

Pull one use case default:

```sh
./scripts/lab pull coder
```

Pull all candidates for a use case:

```sh
./scripts/lab pull coder --all-candidates
```

Run `./scripts/lab models-config` to see which configured aliases already have
local GGUF files.

Dry run a large download:

```sh
./scripts/lab pull reason --dry-run
```

Pull every configured model:

```sh
make pull-all
```

The configured defaults currently resolve to these approximate download sizes:

| Alias | File | Size |
| --- | --- | --- |
| `coder-30b` | `Qwen3-Coder-30B-A3B-Instruct-Q5_K_M.gguf` | 21.7 GB |
| `reason-27b` | `Qwen_Qwen3.6-27B-Q5_K_M.gguf` | 21.0 GB |
| `fast-9b` | `Qwen_Qwen3.5-9B-Q5_K_M.gguf` | 7.1 GB |
| `embed-4b` | `Qwen3-Embedding-4B-Q5_K_M.gguf` | 2.9 GB |

## Router Commands

```sh
make start
make status
make logs
make models
make stop
```

Manual model management:

```sh
./scripts/lab load coder
./scripts/lab unload coder
./scripts/lab switch reason
```

`load` and `switch` are equivalent for residency: if another non-embedding model
is active, it is unloaded before the requested non-embedding model is loaded.
Embedding models are exempt from that eviction rule and can stay loaded.

Quick smoke chat:

```sh
./scripts/lab chat coder "Write a small TypeScript debounce function."
```

## Always-on macOS Service

Install the router as a per-user LaunchAgent. It starts after login, restarts if
it crashes, and remains bound to `127.0.0.1`:

```sh
make service-install
make service-status
```

The LaunchAgent is installed at:

```text
~/Library/LaunchAgents/com.erik.local-ai-lab.plist
```

Service controls:

```sh
make service-start
make service-stop
make service-restart
make service-uninstall
```

Once installed, the normal `make start`, `make stop`, and `make status` commands
use the LaunchAgent. Logs remain available through `make logs`.

The default coding model starts hot and remains loaded. Enable automatic idle
sleep to release the model and KV-cache memory after 15 minutes without a task:

```sh
./scripts/lab auto-idle on
./scripts/lab auto-idle off
./scripts/lab auto-idle toggle
```

A sleeping model wakes automatically on its next request. Manual unload is
different: it persists across service restarts and requires an explicit load.
This is useful before switching to battery power:

```sh
./scripts/lab unload-active
./scripts/lab load coder
```

The active preferences live outside the repository at:

```text
~/Library/Application Support/com.erik.local-ai-lab/state.json
```

Status is available for terminals, Raycast, or automation:

```sh
./scripts/lab status --format text
./scripts/lab status --format raycast
./scripts/lab status --format json
```

The service does not prevent macOS from sleeping. While the Mac itself is
asleep, the endpoint is unavailable and resumes after wake.

## Benchmarking

Raw llama.cpp throughput with `llama-bench`:

```sh
./scripts/lab bench-llama coder
./scripts/lab bench-llama coder --all-candidates
```

This uses the configured GGUF paths and preset settings where `llama-bench`
supports the same flags. Results are written under:

```text
benchmarks/results/<timestamp>-llama-bench-<selector>/
```

End-to-end router benchmark through `/v1/chat/completions`:

```sh
make start
./scripts/lab bench-server coder --all-candidates --unload-after
```

`--all-candidates` requires every candidate GGUF for that use case to be present
locally. Pull them first with `./scripts/lab pull coder --all-candidates`, run
without `--all-candidates` to benchmark only the default model, or add
`--skip-missing` to benchmark the candidates that are already downloaded.

Prompt sets live in [benchmarks/prompts](benchmarks/prompts).
Each server benchmark writes JSONL records plus `summary.json` and `summary.csv`
under `benchmarks/results/`.

Use both benchmark modes:

- `bench-llama` isolates model/runtime throughput for prompt and generation token rates.
- `bench-server` measures the workload path your apps use, including router load behavior and request latency.

Quality and correctness benchmark with an OpenAI judge:

```sh
export OPENAI_API_KEY=...
./scripts/lab bench-quality coder --all-candidates
./scripts/lab bench-quality reason --all-candidates
./scripts/lab bench-quality fast --all-candidates
```

`bench-quality` runs the same local router path, saves each model answer, and
scores it with OpenAI's Responses API using structured JSON output. The default
judge is configured in [config/lab.json](config/lab.json):

```json
"judge": {
  "provider": "openai",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-5.5",
  "reasoning_effort": "low"
}
```

Override judge settings per run:

```sh
./scripts/lab bench-quality coder --all-candidates --judge-model gpt-5.5 --limit-prompts 1
```

Quality results are written under:

```text
benchmarks/results/<timestamp>-quality-<selector>/
```

Each row includes the local model answer, judge scores for correctness,
completeness, instruction following, clarity, an overall 1-5 score, pass/fail,
and the judge rationale. Prompt-specific rubrics live alongside the prompt rows
in [benchmarks/prompts](benchmarks/prompts).

## Upstream Notes

llama.cpp router mode is documented in the
[server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md):
it supports `--models-dir`, `--models-preset`, model routing by the request
`model` field, `GET /models`, `POST /models/load`, and `POST /models/unload`.

Hugging Face documents the current CLI as
[`hf`](https://huggingface.co/docs/huggingface_hub/guides/cli); this wrapper
uses `hf download` with `--local-dir` and falls back to `huggingface-cli` if
needed.

The quality benchmark uses OpenAI's
[Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses)
and [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
for schema-constrained judge responses.
