# Local Model Fleet

The fleet provides role-oriented local inference for real software work on one
128 GB Apple Silicon Mac. llama.cpp is the comparable primary runtime and the
router remains bound to `127.0.0.1`.

The current catalog is the source of truth:

```sh
./scripts/lab catalog
```

## Lifecycle

- `core`: installed, runtime-verified, and proven to complete tool loops in both
  Cline and OpenCode.
- `candidate`: selected for testing but not yet admitted.
- `retired`: superseded and no longer used for new comparisons.
- `watch`: intentionally not pullable until its role, license, runtime support,
  and hardware fit justify admission.

Qwen Code and Aider results are additional scaffold-specific evidence. They do
not block core admission because agent implementations can expose materially
different tool inventories and parsing behavior.

## Admission Gate

A candidate must pass:

1. Every configured GGUF and multimodal projector exists.
2. llama.cpp loads the alias at the catalog context limit.
3. A normal completion returns visible output.
4. Non-streaming chat returns a structured function call.
5. Streaming chat emits `delta.tool_calls`.
6. Exactly one non-embedding model remains resident.
7. The tested model cleanly unloads and the previous state is restored.
8. Cline executes a real tool loop.
9. OpenCode executes a real tool loop.

Use:

```sh
./scripts/lab verify MODEL
```

Promotion is deliberate; the verifier writes evidence but never edits lifecycle
or compatibility fields automatically.

## Quantization and Context

- Through 35B, start with Q5-class GGUFs.
- At roughly 120B, start with Q4 or native MXFP4.
- Start large models at 32K context.
- Raise context only after measuring memory headroom and confirming that the
  server and agent report the same limit.

The installed core plus active-candidate weight budget is 400 GiB. Download
small, medium, and flagship waves separately. Existing weights remain until a
replacement passes admission; then move the superseded files to Trash instead
of deleting them directly.

## Role Aliases

- `fast`: summaries, documentation, exploration, and bounded mechanical work.
- `coder`: normal implementation and agent loops.
- `reason`: planning, debugging, and ambiguous implementation.
- `review`: skeptical correctness and security review.
- `vision`: screenshot and UI analysis.
- `embedding`: retrieval.

Escalate by measured failure: a missed acceptance criterion, malformed tool
call, repeated repair, insufficient context, or an observed quality gap. Model
size and wall-clock speed matter only after the result is accepted.

## Client Endpoint

Cline, OpenCode, and Qwen Code use:

```text
http://127.0.0.1:8080/v1
```

The machine-specific client setup is documented in
[client-configuration.md](client-configuration.md). Keep local provider tokens
as non-secret placeholders; never add public exposure or real credentials for
the localhost runtime.

## Watchlist Policy

Devstral 2 123B requires a license review, memory dry-run, load test, and tool
verification before becoming runnable. Oversized frontier families remain on
the watchlist when their complete weight footprint is not reliable within
128 GB unified memory. Nemotron 3 Nano/Super and Trinity Mini remain deferred
because they duplicate active roles under custom licenses. Gemma 4 MTP
assistants remain deferred until mainline llama.cpp support is complete.
