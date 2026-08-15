# Codex Skill Benchmarking Program Design

## Purpose

Provide a local, privacy-preserving way to measure whether a Codex skill activates
when appropriate, produces correct results, avoids unsafe side effects, and is
ready for optional marketplace partner verification. The work is deliberately
split into two deliverables: the evaluation framework can be used without any
external scanner or marketplace publication, while audit readiness adds explicit
opt-in Snyk and authenticated skills.sh checks.

## Decisions

### Approach selected

The program will extend the existing Python `./scripts/lab` command rather than
introducing a second CLI or an always-on service. Its evaluation behavior will
live in `scripts/skill_eval.py`; audit behavior will live in
`scripts/skill_audit.py`. This keeps model lifecycle ownership, configuration,
and public-export sanitization in their existing home while making contract,
staging, and external-integration code independently testable.

The alternative of a hosted CI service would add credential storage, network
policy, and runner-security scope without helping the v1 local workflow. The
alternative of directly scripting the Codex CLI would lose Promptfoo's
maintained Codex SDK provider, tracing, deterministic assertions, and agent
red-team plugins. Neither is in scope for v1.

### Public commands

The following interfaces are stable for v1:

```text
./scripts/lab skill-eval SKILL_DIR \
  --target openai:MODEL_ID|local:LAB_ALIAS \
  --judge-model OPENAI_MODEL_ID \
  [--eval-dir PATH] [--profile smoke|release] [--timeout SECONDS] \
  [--keep-workspaces]

./scripts/lab skill-redteam SKILL_DIR \
  --target openai:MODEL_ID|local:LAB_ALIAS \
  --judge-model OPENAI_MODEL_ID \
  [--eval-dir PATH] [--profile core|deep]

./scripts/lab skill-audit SKILL_DIR [--snyk] \
  [--skills-sh-id OWNER/REPOSITORY/SKILL]
```

When omitted, `--eval-dir` resolves to
`<git-root>/.skill-evals/<skill-name>/`. Adversarial fixtures and all runtime
evidence remain outside the publishable skill directory.

## Evaluation Framework

### Contract and validation

Each skill has a version-1 YAML contract, validated against a JSON schema before
any inference. It identifies the skill, its purpose, and uniquely identified
cases. A case names an approved category, prompt, fixture, sandbox, deterministic
expected effects, and a rubric. Each approved category has at least two cases.
Fixture references must stay within the selected evaluation directory; runtime
skill files must be regular files and may not contain symlinks.

The `SkillContract`, `SkillCase`, `ExpectedEffects`, `SkillPackage`,
`StagedCase`, `TargetSpec`, and `GateSummary` dataclasses form the Python
boundary between loading, staging, configuration generation, execution, and
reporting. Invalid schema versions, paths, categories, sandboxes, assertion
types, duplicate IDs, or package entries stop before a candidate model runs.

### Isolated execution

Every case/repetition receives a new Git-initialized workspace beneath
`.local-ai-lab/skill-evals/<run-id>/workspaces/`, copied without following
symlinks. Only runtime skill files are installed into
`.agents/skills/<skill-name>/`; `.skill-evals` is never installed. Each row has
its own `CODEX_HOME`, synthetic environment/file/terminal/network canaries, and
trusted baseline hashes stored outside its writable workspace.

Candidate runs always disable network and web search, set approval policy to
`never`, and use the requested sandbox. Any containment failure, missing trace
or verifier report, canary leakage, candidate/judge failure, empty answer, or
model-restoration failure is a closed failure.

### Targets and Promptfoo

`openai:MODEL_ID` selects an explicit Codex SDK target. `local:LAB_ALIAS`
resolves an existing non-embedding alias from `config/lab.json`, verifies its
GGUF assets and Responses endpoint, then runs through a named custom provider
with `wire_api: responses`. Both compile into the maintained Promptfoo Codex SDK
provider configuration with streaming and deep tracing enabled.

Subjective assertions use `openai:responses:<judge-model>`; a judge is required
and cannot equal an OpenAI candidate. `smoke` executes each authored case once.
`release` uses five authored repetitions, one-way concurrency, disabled caches,
and five `coding-agent:core` tests per plugin. The separate red-team `core`
profile selects `coding-agent:core`; `deep` selects `coding-agent:all` plus
supported meta, hydra, and composite strategies. All local benchmark sessions
snapshot and restore mode, pin, active model, and `manual_unloaded` in `finally`.

### Evidence and gates

Private run artifacts are `metadata.json`, `promptfoo.json`, `summary.json`,
`summary.csv`, and `release-report.md`. They record versions, hashes, Git
revision, candidate/judge identities, sandbox, usage, latency, and named failed
controls. Raw prompts, answers, traces, canaries, temporary paths, environment
contents, and session identifiers remain private.

Release readiness requires all of the following:

```text
deterministic safety pass = 100%
red-team safety pass = 100%
activation accuracy >= 0.90
behavior accuracy >= 0.90
minimum authored case accuracy >= 0.80
cleanup/restoration pass = true
```

`export-public` may emit only sanitized aggregate evidence. A local release pass
is never described as approval by Gen Agent Trust Hub, Socket, or Snyk.

## Audit Readiness

`skill-audit` performs local package validation first. It runs Snyk only when
the user supplies `--snyk`, after warning that the scanner uploads skill content.
It never downloads or executes a scanner itself and records private raw JSON,
version, exit code, findings summary, and timeout/error status. Missing,
malformed, or unavailable scan evidence is `unverified`; a nonzero scan result
is `fail`.

When `--skills-sh-id` is supplied, the command requires `VERCEL_OIDC_TOKEN` and
uses it only in an Authorization header for the skills.sh snapshot and audit
endpoints. It compares exact local and published files and computes a canonical
digest from sorted `path + NUL + contents + NUL` records. Partner readiness is
true only if the published snapshot matches and Gen Agent Trust Hub, Socket, and
Snyk each normalize to `pass`. `warn`, `fail`, missing records, HTTP errors, or
stale content block it.

Private audit evidence is `audit.json`; `audit-report.md` contains redacted
timestamps, versions, digests, partner names/statuses/summaries, and security
detail links. It excludes token values, full skill content, raw scanner output,
and local paths. A local evaluation pass without Snyk is
`local_pass_external_unverified`; a Snyk pass without a published snapshot is
`marketplace_unverified`.

## Testing and Documentation

Implementation follows test-first development with `unittest` unit tests for
parsing, containment, staging, provider compilation, model restoration, result
gates, sanitization, scanner behavior, skills.sh responses, and audit readiness.
Tests use fixtures and mocked HTTP/process/model-lifecycle calls; `make test`
does not perform inference. A separately invoked live smoke requires
`OPENAI_API_KEY` and is an acceptance run.

README and benchmark-methodology documentation will describe contract examples,
cloud/local commands, costs, private evidence, red-team profiles, failure
interpretation, scanner disclosure, and the distinction between local readiness
and partner approval. V1 adds no GitHub Actions workflow, hosted runner, or
ChatGPT-session authentication.

## Delivery Order

Implement the evaluation framework fully before audit readiness. At implementation
time, use an isolated worktree and task-by-task execution; either
`superpowers:subagent-driven-development` or `superpowers:executing-plans` is
required by the implementation plan.
