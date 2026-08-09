# Agent Client Configuration

All clients target:

```text
http://127.0.0.1:8080/v1
```

Compatibility evidence recorded on 2026-07-24 used llama.cpp build `b10090`,
Cline CLI `3.0.46`, OpenCode `1.18.4`, and Qwen Code `0.19.6`.

`local-ai-lab` is a persistent JIT gateway. Select the catalog alias in the
agent configuration; the gateway validates files, serializes any necessary
unload/load transition, waits for readiness, and forwards the original request.
It keeps one generation model resident for later requests and unloads it after
roughly 15 minutes of idle time. `/v1/models` exposes catalog aliases rather
than GGUF filenames.

## Cline

The local provider can be configured from the CLI:

```sh
cline auth openai-compatible \
  --apikey local \
  --modelid fast-9b \
  --baseurl http://127.0.0.1:8080/v1
```

Use `openai-compatible` and the selected catalog alias. The API key is a
non-secret placeholder required by the client. Configure Cline's context limit
to the alias's `context_tokens` value in `config/lab.json` (currently 32,768 for
the active Cline aliases); the gateway renders the same value into llama.cpp.

Large aliases such as `gpt-oss-120b` may take tens of seconds for their first
request. Keep the client request timeout generous; the gateway uses a 15-minute
load timeout and a 30-minute forwarded-request timeout by default.

## Benchmark Mode

For reproducible measurements, pin a model before invoking benchmark commands:

```sh
./scripts/lab mode benchmark qwen3.6-35b-a3b
./scripts/lab bench-server coder
./scripts/lab mode cline
```

Benchmark mode disables automatic alias changes: requests for a different model
return a conflict instead of altering clean residency.

## OpenCode

Use a `llama.cpp` provider with `@ai-sdk/openai-compatible`, the localhost base
URL, and model IDs that exactly match catalog aliases. Keep context limits
aligned with `config/lab.json`.

Run a selected model:

```sh
opencode run \
  --model llama.cpp/fast-9b \
  --dir /path/to/project \
  "Inspect the repository and report the validation commands."
```

## Qwen Code

Define the aliases under the `openai` `modelProviders` list in
`~/.qwen/settings.json`. Each provider entry must include its complete
`generationConfig`, including `contextWindowSize`, because provider settings
replace rather than inherit lower configuration layers.

Run:

```sh
qwen --model fast-9b
```

Record the actual tool inventory in compatibility notes. A correct answer is
not proof of a tool loop when the requested shell tool was not exposed.

## Compatibility Check

Use a bounded, non-mutating task:

```text
Use the shell tool to run pwd. Do not edit files. Report only the final
directory basename.
```

Passing evidence must show a structured tool call, successful result, and final
answer. Do not infer execution from an answer the model could obtain from
existing context.

The 2026-07-24 Qwen Code check did not expose a shell tool in its advertised
tool inventory. It returned the expected directory from existing context
without executing the requested command, so that result is recorded as
`partial`, not a passing tool loop.
