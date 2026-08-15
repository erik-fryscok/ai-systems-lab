# local-ai-lab

Local llama.cpp lab for running one persistent gateway endpoint with
workload-specific model aliases, repeatable Hugging Face pulls, and benchmark
output you can compare over time. Cline sends an alias in each request; the
gateway JIT-loads it, evicts the previous generation model, then forwards the
original request.

The default setup is:

| Use case | Default alias | Purpose |
| --- | --- | --- |
| `coder` | `qwen3.6-35b-a3b` | Qwen3.6 35B-A3B Q5_K_M, loaded at startup |
| `reason` | `reason-27b` | Qwen3.6 27B Q5_K_M, loaded on demand |
| `review` | `gpt-oss-120b` | Flagship reasoning and skeptical review |
| `fast` | `fast-9b` | Qwen3.5 9B Q5_K_M, loaded on demand |
| `vision` | `gemma-4-12b` | Multimodal UI and screenshot analysis candidate |
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

Use one endpoint and send the desired catalog alias directly in each request.
No manual switch is required:

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
- `watchlist`: models that are intentionally not pullable until admitted to the
  runnable fleet.

Machine-specific model paths belong in the ignored `config/lab.local.json`
overlay. Copy [config/lab.local.example.json](config/lab.local.example.json)
and override only the fields that differ locally. The committed catalog never
contains a user-specific absolute path. The current machine uses this mechanism
to point `gpt-oss-120b` at existing LM Studio shards instead of duplicating
roughly 63 GB of weights.

Inspect the curated fleet without exposing local paths:

```sh
./scripts/lab catalog
./scripts/lab catalog --role coding
./scripts/lab catalog --status candidate --format json
```

Each catalog entry records release identity, architecture, total and active
parameters, quantization, license, roles, lifecycle, disk expectation, context,
source, last verification, and agent compatibility. See
[docs/model-fleet.md](docs/model-fleet.md) for lifecycle and admission rules.

By default, `server.models_autoload` is `false` and `server.models_max` is
`null`. The gateway listens on port 8080 and runs llama.cpp privately on port
8081 with enough capacity for one non-embedding model plus configured embedding
models. It serializes unload/load transitions, holds requests until the alias is
ready, and unloads idle generation models after 15 minutes.

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

Do not use `pull all` for fleet expansion. Download in small, medium, and
flagship waves so disk usage, license review, and runtime compatibility are
checked before the next wave. The installed core plus active-candidate weight
budget is 400 GiB.

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

Normal operation is `cline` mode: JIT loading and idle unload are enabled. For
reproducible experiments, explicitly pin a model before the run:

```sh
./scripts/lab mode benchmark fast-9b
./scripts/lab bench-server fast
./scripts/lab mode cline
```

Benchmark mode rejects automatic switching to any alias other than its pin.

Quick smoke chat:

```sh
./scripts/lab chat coder "Write a small TypeScript debounce function."
```

Run the compatibility gate for a candidate:

```sh
./scripts/lab verify fast-9b
```

`verify` checks every configured GGUF file, load, visible completion,
non-streaming structured tool calls, streaming `delta.tool_calls`, one-model
residency, and clean unload or restoration of the previous state. A model is
not promoted to `core` until it also completes real tool loops in Cline and
OpenCode. Qwen Code and Aider are recorded as additional scaffold evidence.

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

Quality and correctness benchmark with manual review by default:

```sh
./scripts/lab bench-quality coder --all-candidates
./scripts/lab bench-quality reason --all-candidates
./scripts/lab bench-quality fast --all-candidates
```

`bench-quality` runs the same local router path, saves each model answer, and
creates `manual-review.json`. This keeps paid inference out of the baseline and
keeps automated acceptance criteria plus blind human review above model judging.
The default 4096-token output budget leaves room for reasoning-capable models
to produce a visible answer; an empty visible completion is recorded as a
failed result rather than sent for review.
The default is configured in [config/lab.json](config/lab.json):

```json
"judge": {
  "provider": "manual"
}
```

Use another local fleet model as secondary evidence:

```sh
./scripts/lab bench-quality coder \
  --all-candidates \
  --judge-provider local \
  --judge-model gpt-oss-120b
```

Paid OpenAI judging remains an explicit opt-in:

```sh
export OPENAI_API_KEY=...
./scripts/lab bench-quality coder \
  --judge-provider openai \
  --judge-model gpt-5.5
```

Quality results are written under:

```text
benchmarks/results/<timestamp>-quality-<selector>/
```

Each raw result row includes the local model answer and performance data.
Manual runs create a review template for correctness, completeness, instruction
following, clarity, an overall 1-5 score, pass/fail, and rationale. Local or
OpenAI judge runs populate those fields automatically as secondary evidence.
Server and quality runs sample the selected llama.cpp model worker's resident
set size and report its observed peak in GiB; this is a comparable process-level
measurement, not total system or GPU energy telemetry.
Prompt-specific rubrics live alongside the prompt rows in
[benchmarks/prompts](benchmarks/prompts).

Before publishing any result, create a sanitized artifact:

```sh
./scripts/lab export-public benchmarks/results/<result-dir> \
  --output /tmp/public-result.json
```

The export omits raw answers, evaluation payloads, commands, local paths, host
details, response identifiers, and credentials. Raw results remain locally
ignored under `benchmarks/results/`. Export and publish only reviewed,
sanitized summaries.

The comparison contract, result hierarchy, publication fields, and scenario
matrix are documented in
[docs/benchmark-methodology.md](docs/benchmark-methodology.md).

## Upstream Notes

llama.cpp router mode is documented in the
[server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md):
it supports `--models-dir`, `--models-preset`, model routing by the request
`model` field, `GET /models`, `POST /models/load`, and `POST /models/unload`.

Hugging Face documents the current CLI as
[`hf`](https://huggingface.co/docs/huggingface_hub/guides/cli); this wrapper
uses `hf download` with `--local-dir` and falls back to `huggingface-cli` if
needed.

The optional paid quality judge uses OpenAI's
[Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses)
and [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
for schema-constrained judge responses.

## License

This project is licensed under the [MIT License](LICENSE).
