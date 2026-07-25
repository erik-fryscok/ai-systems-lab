# Agent Client Configuration

All clients target:

```text
http://127.0.0.1:8080/v1
```

Compatibility evidence recorded on 2026-07-24 used llama.cpp build `b10090`,
Cline CLI `3.0.46`, OpenCode `1.18.4`, and Qwen Code `0.19.6`.

Switch the resident alias through `scripts/lab` before starting an agent:

```sh
./scripts/lab switch fast-9b
```

## Cline

The local provider can be configured from the CLI:

```sh
cline auth openai-compatible \
  --apikey local \
  --modelid fast-9b \
  --baseurl http://127.0.0.1:8080/v1
```

Use `openai-compatible` and the selected catalog alias. The API key is a
non-secret placeholder required by the client.

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
