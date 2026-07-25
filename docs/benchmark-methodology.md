# Benchmark and Publication Method

The public question is:

> Can local AI ship it?

A faster failing result never outranks a slower passing result.

## Controlled Comparison

For a model comparison, hold these constant:

- agent and agent version;
- prompt and fresh conversation;
- Git baseline and isolated worktree;
- quantization class;
- runtime and runtime version;
- context limit;
- issue acceptance contract;
- validation commands.

Use separate branches or worktrees for implementation attempts. Do not let one
model see another model's implementation unless the experiment explicitly tests
review or repair.

## Scenario Matrix

1. Repository exploration and implementation planning.
2. Bounded feature implementation.
3. Bug fix beginning with a failing test.
4. Behavior-preserving refactor.
5. Test generation and edge-case discovery.
6. Security and correctness review.
7. Documentation update.
8. Structured tool-call recovery after a failed command.
9. Multimodal screenshot or UI analysis.

## Result Hierarchy

Evaluate in this order:

1. Automated acceptance criteria and repository tests.
2. First-attempt completion and required human repair.
3. Blind human review against the issue contract.
4. Wall-clock time, tool calls, tokens, throughput, peak memory, and optional
   energy measurement.
5. Local cross-model judging as secondary evidence only.

Role winners are selected by accepted-task count, then fewer interventions,
then shorter elapsed time and lower peak memory.

## Required Publication Fields

Every published experiment records:

- exact model, quantization, runtime, context, and agent;
- model release and verification dates;
- public prompt and Git base;
- attempts and human interventions;
- validation commands and outcomes;
- elapsed time and peak memory;
- marginal API spend as `$0`, with hardware and electricity acknowledged
  separately;
- accepted, repairable, or failed outcome;
- known runtime and tooling limitations.

The harness reports peak memory as the selected llama.cpp model worker's
observed resident set size (`peak_model_worker_rss_gib`). It excludes unrelated
processes and should not be interpreted as total system energy use or a complete
breakdown of Apple unified memory.

Raw results remain in this private repository. Export only sanitized summaries:

```sh
./scripts/lab export-public RESULT_DIR --output FILE
```

Review the generated file before copying it to a public repository. Accepted
diffs and prompts intended for release can be published separately after the
same privacy review.

## Initial Case Study

The first comparison is gpt-oss 120B versus 20B on website issue #2:

- 120B: 4 minutes 32 seconds;
- 20B: 2 minutes 56 seconds;
- 120B was approximately 55% slower;
- only the 120B implementation met the acceptance bar.

This establishes the series rule: speed and size are tie-breakers after usable
software, not substitutes for it.

The preserved evidence and historical metadata gaps are recorded in
[case-studies/gpt-oss-issue-2.md](case-studies/gpt-oss-issue-2.md).
