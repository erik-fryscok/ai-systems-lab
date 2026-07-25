# gpt-oss on Website Issue #2

Status: historical case study requiring a controlled rerun for full benchmark
metadata

## Recorded Outcome

| Model | Quantization | Elapsed | Review outcome |
| --- | --- | ---: | --- |
| gpt-oss-120b | MXFP4 | 4:32 | Usable; the only implementation that met the acceptance bar |
| gpt-oss-20b | MXFP4 | 2:56 | Failed; dependency claims did not produce an installable implementation |

The 120B run took 96 seconds longer, approximately 55% more time than the 20B
run. It still wins because accepted work is the first ranking criterion.

## Known Contract

- Public task:
  [erikfryscok.com issue #2](https://github.com/erik-fryscok/erikfryscok.com/issues/2)
- Work type: Astro, strict TypeScript, and Tailwind foundation.
- Primary acceptance: installable implementation, documented validation
  commands, and a successful repository validation path.

## Historical Limitations

The original run did not preserve every field now required by the benchmark
method:

- exact agent version;
- llama.cpp build;
- context limit;
- prompt artifact;
- Git commit SHA for the common base;
- token, throughput, and peak-memory measurements.

Do not reconstruct or invent these values. The first episode should distinguish
the evidence captured at the time from a future controlled rerun.

## Reproduction

A controlled rerun must use fresh isolated worktrees from the same Git base,
the same agent version and prompt, 32K context, the current llama.cpp build,
and the issue acceptance commands. Export only the sanitized summary; keep raw
agent transcripts and runtime state in this private repository.
