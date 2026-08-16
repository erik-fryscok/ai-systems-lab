# GitHub Public Readiness Benchmark Article Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a privacy-safe, reproducible Promptfoo A/B benchmark of the `github-public-readiness` Codex skill and publish an Astro article that renders only its sanitized aggregate evidence.

**Architecture:** AI Systems Lab stages one isolated control workspace without the skill and one treatment workspace with the validated skill for every `(case_id, repetition)` pair. A new `skill-benchmark` command runs both arms through Promptfoo, validates pairing and containment, emits a strict public aggregate artifact, and records provenance. The website imports that copied artifact and renders result-dependent prose and tables without raw prompts, answers, traces, paths, or canaries.

**Tech Stack:** Python 3.9+, `unittest`, PyYAML 6.0.2, Promptfoo 0.122.0, `@openai/codex-sdk` 0.147.0, Codex CLI 0.147.0+, Astro 7, TypeScript strict mode, Tailwind CSS, Node's built-in test runner.

## Global Constraints

- Execute all changes in linked worktrees; never make implementation commits on `main`.
- Test `erik-fryscok/skills` commit `4480393` and record the runtime-package digest; reject a different Git revision.
- Use `openai:gpt-5.6-terra` as the candidate and `gpt-5.6` as the distinct OpenAI Responses judge.
- Use only the nine committed synthetic fixtures; do not copy or inspect a real private repository.
- Run every case in a read-only sandbox with network and web search disabled, approval policy `never`, no cache, and a fresh workspace plus fresh `CODEX_HOME` for every arm/repetition.
- Release execution is exactly 9 cases × 2 arms × 5 repetitions = 90 candidate runs; smoke execution is exactly 9 cases × 2 arms × 1 repetition = 18 candidate runs.
- Public exports may contain only allowlisted aggregate fields. Reject absolute paths, home-directory fragments, environment values, canaries, credential-like strings, emails, non-public hostnames, session identifiers, raw prompts, raw answers, traces, and unknown fields.
- Publish a valid positive, neutral, or negative outcome. Do not publish an invalid, incomplete, or privacy-failing run.
- Do not claim production certification, universal skill benefit, model-independent results, Snyk approval, or marketplace-partner approval.
- Keep raw Promptfoo output, traces, workspaces, agent homes, and verifier evidence beneath ignored `.ai-systems-lab/skill-evals/` directories.
- Update durable documentation and the website changelog for the public article; do not create duplicate delivery-status trackers.

---

## File Structure

### AI Systems Lab repository

- Modify: `scripts/skill_eval.py` — arm-aware staging, Promptfoo configuration, deterministic pair aggregation, and strict result projection helpers.
- Modify: `scripts/lab` — `skill-benchmark` command, cloud-run orchestration, revision preflight, private run metadata, and public export dispatch.
- Modify: `tests/test_skill_eval.py` — unit coverage for both arms, pairing, aggregate metrics, bootstrap intervals, and privacy projection.
- Modify: `tests/test_lab.py` — parser, preflight, command orchestration, failure cleanup, and export tests.
- Create: `benchmarks/skills/github-public-readiness/cases.yaml` — version-1 contract for the nine public synthetic cases.
- Create: `benchmarks/skills/github-public-readiness/fixtures/*` — nine fabricated repository fixtures.
- Create: `docs/benchmark-results/github-public-readiness-benchmark.schema.json` — exact public-result schema.
- Create: `docs/benchmark-results/github-public-readiness-benchmark.json` — sanitized result produced only after the valid release run.
- Create: `docs/case-studies/github-public-readiness-skill-benchmark.md` — canonical methodology and findings report derived only from the sanitized result.
- Modify: `README.md` and `docs/benchmark-methodology.md` — paired command, privacy boundary, invalid-run rules, and reproduction steps.

### erikfryscok.com repository

- Create: `src/data/github-public-readiness-benchmark.json` — byte-for-byte copy of the canonical sanitized lab result.
- Create: `src/pages/writing/codex-skill-promptfoo-benchmark.astro` — result-driven article at `/writing/codex-skill-promptfoo-benchmark`.
- Modify: `src/pages/writing.astro` — dated article entry and summary.
- Modify: `tests/launch-readiness.test.mjs` — metadata, sitemap, and internal-link coverage for the new article route.
- Create: `tests/codex-skill-promptfoo-benchmark.test.mjs` — structured-evidence, required-section, claim-guard, and privacy-regression coverage.
- Modify: `docs/README.md`, `docs/strategy/decisions.md`, and `CHANGELOG.md` — durable design link, evidence-publication decision, and user-visible release note.

## Public Result Shape

All consumers use this schema-compatible object; no consumer reads raw Promptfoo JSON:

```json
{
  "schema_version": 1,
  "benchmark_id": "github-public-readiness-paired-v1",
  "provenance": {
    "candidate": "openai:gpt-5.6-terra",
    "judge": "gpt-5.6",
    "skill_git_revision": "4480393",
    "skill_digest": "[a-f0-9]{64}",
    "contract_digest": "[a-f0-9]{64}",
    "promptfoo_version": "0.122.0",
    "codex_sdk_version": "0.147.0"
  },
  "run": {"profile": "release", "cases": 9, "arms": 2, "repetitions": 5, "valid_pairs": 45},
  "metrics": {
    "control": {"task_pass_rate": 0, "safety_pass_rate": 0, "median_latency_seconds": 0, "latency_range_seconds": [0, 0], "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0},
    "treatment": {"task_pass_rate": 0, "safety_pass_rate": 0, "activation_accuracy": 0, "median_latency_seconds": 0, "latency_range_seconds": [0, 0], "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0},
    "paired_deltas": {"task_pass_rate": {"value": 0, "ci95": [0, 0]}, "safety_pass_rate": {"value": 0, "ci95": [0, 0]}}
  },
  "case_results": [{"case_id": "direct-publish-now", "category": "direct_activation", "control_pass_rate": 0, "treatment_pass_rate": 0, "delta": 0}],
  "limitations": ["Synthetic repositories bound the result to the authored cases."],
  "privacy_review": {"automated_export_validation": true, "manual_review": true}
}
```

The two digest strings must match the regular expression `[a-f0-9]{64}` after the release run computes them. They are provenance values, never secrets or local paths. The schema requires exactly the listed keys at every level and rejects any additional property.

### Task 1: Add Arm-Aware Isolated Staging

**Files:**
- Modify: `scripts/skill_eval.py`
- Modify: `tests/test_skill_eval.py`

**Interfaces:**
- Consumes: existing `SkillContract`, `SkillPackage`, `SkillCase`, and `stage_cases(contract, package, repetitions, run_root, keep_workspaces_on_error=False)` behavior.
- Produces: `BenchmarkArm`, `BenchmarkRow`, and `stage_benchmark_cases(contract, package, repetitions, run_root, keep_workspaces_on_error=False) -> list[BenchmarkRow]` for Task 2.

- [ ] **Step 1: Write failing staging tests**

Add tests that require exactly two rows for one authored case and one repetition, one with `arm == "control"` and one with `arm == "treatment"`; require different workspace and agent-home directories, equal fixture baseline hashes, equal prompt/case/sandbox data, no installed skill in the control, and the complete package under `.agents/skills/github-public-readiness/` in treatment.

```python
rows = skill_eval.stage_benchmark_cases(contract, package, 1, run_root)
control, treatment = rows
self.assertEqual((control.arm, treatment.arm), ("control", "treatment"))
self.assertEqual(control.case_id, treatment.case_id)
self.assertEqual(control.baseline_hashes, treatment.baseline_hashes)
self.assertFalse((control.workspace_dir / ".agents" / "skills" / contract.skill_name).exists())
self.assertTrue((treatment.workspace_dir / ".agents" / "skills" / contract.skill_name / "SKILL.md").is_file())
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run: `python3 -m unittest tests.test_skill_eval.SkillWorkspaceTests -v`

Expected: FAIL because `stage_benchmark_cases` and `BenchmarkRow` do not exist.

- [ ] **Step 3: Implement immutable arm and paired-row staging**

Add a frozen `BenchmarkArm` enum with `CONTROL = "control"` and `TREATMENT = "treatment"`; add frozen `BenchmarkRow` with `arm`, `case_id`, `repetition`, `workspace_dir`, `codex_home`, `case`, `baseline_hashes`, and `skill_name`. Extract common fixture copying, Git initialization, canary generation, and verifier creation from `stage_cases`. For every authored case/repetition, stage the control without `_install_runtime_skill` and stage treatment with it. Write each verifier JSON with its arm, package digest for treatment, and `null` package digest for control.

```python
def stage_benchmark_cases(contract, package, repetitions, run_root, keep_workspaces_on_error=False):
    rows = []
    for case in contract.cases:
        for repetition in range(1, repetitions + 1):
            rows.append(_stage_benchmark_row(BenchmarkArm.CONTROL, case, repetition, contract, package, run_root))
            rows.append(_stage_benchmark_row(BenchmarkArm.TREATMENT, case, repetition, contract, package, run_root))
    return rows
```

- [ ] **Step 4: Run focused staging tests to verify pass**

Run: `python3 -m unittest tests.test_skill_eval.SkillWorkspaceTests -v`

Expected: PASS, including existing single-arm staging tests.

- [ ] **Step 5: Commit the reviewed staging unit**

```bash
git add scripts/skill_eval.py tests/test_skill_eval.py
git commit -m "feat: stage paired skill benchmark arms"
```

### Task 2: Compile and Run the Paired Promptfoo Benchmark

**Files:**
- Modify: `scripts/skill_eval.py`
- Modify: `scripts/lab`
- Modify: `tests/test_skill_eval.py`
- Modify: `tests/test_lab.py`

**Interfaces:**
- Consumes: `stage_benchmark_cases` and `BenchmarkRow` from Task 1.
- Produces: `build_benchmark_promptfoo_config(target, judge_model, rows, profile, output_path) -> dict` and `cmd_skill_benchmark(args, cfg)` for Task 3.

- [ ] **Step 1: Write failing configuration and parser tests**

Add tests requiring `skill-benchmark` to accept `skill_dir`, `--target`, `--judge-model`, `--eval-dir`, `--profile smoke|release`, `--timeout`, and `--keep-workspaces`; assert its smoke/release row counts are 18/90. Assert control configurations use `not-skill-used`, treatment direct/implicit rows use `skill-used`, and treatment negative rows use `not-skill-used`.

```python
args = lab.build_parser().parse_args([
    "skill-benchmark", "skill-dir", "--target", "openai:gpt-5.6-terra",
    "--judge-model", "gpt-5.6", "--profile", "release",
])
self.assertEqual(args.profile, "release")
self.assertEqual(skill_eval.benchmark_repetitions("release"), 5)
self.assertEqual(len(config["tests"]), 90)
```

- [ ] **Step 2: Run focused configuration and command tests to verify failure**

Run: `python3 -m unittest tests.test_skill_eval.PromptfooConfigTests tests.test_lab.SkillEvalCommandTests -v`

Expected: FAIL because `skill-benchmark` and `build_benchmark_promptfoo_config` do not exist.

- [ ] **Step 3: Implement the public command and arm-aware assertions**

Add the parser entry and `COMMANDS` mapping. In `cmd_skill_benchmark`, validate target and judge, require Promptfoo/Codex SDK dependency versions, verify the skill repository's `HEAD` equals `4480393`, load the contract and package, stage paired rows, build one no-cache Promptfoo configuration, invoke `run_promptfoo`, and clean staged directories unless explicitly retained. Preserve existing `skill-eval` and `skill-redteam` behavior unchanged.

```python
def _benchmark_assertions(row, judge_model):
    activation = "not-skill-used" if row.arm is BenchmarkArm.CONTROL else (
        "skill-used" if row.case.expected.skill_used else "not-skill-used"
    )
    return [*row.case.expected.output, {"type": activation, "value": row.skill_name}, {
        "type": "llm-rubric", "value": row.case.rubric,
        "provider": f"openai:responses:{judge_model}",
    }]
```

- [ ] **Step 4: Run focused command tests to verify pass**

Run: `python3 -m unittest tests.test_skill_eval.PromptfooConfigTests tests.test_lab.SkillEvalCommandTests -v`

Expected: PASS; cloud tests must not invoke local-model preflight or lifecycle management.

- [ ] **Step 5: Commit the command unit**

```bash
git add scripts/skill_eval.py scripts/lab tests/test_skill_eval.py tests/test_lab.py
git commit -m "feat: add paired skill benchmark command"
```

### Task 3: Validate Pairs and Produce a Strict Aggregate Export

**Files:**
- Modify: `scripts/skill_eval.py`
- Modify: `scripts/lab`
- Modify: `tests/test_skill_eval.py`
- Modify: `tests/test_lab.py`
- Create: `docs/benchmark-results/github-public-readiness-benchmark.schema.json`

**Interfaces:**
- Consumes: Promptfoo raw result path and `BenchmarkRow` provenance from Tasks 1–2.
- Produces: `summarize_benchmark(rows, raw_result, provenance) -> dict`, `validate_benchmark_public_result(payload) -> None`, and `export-benchmark-public` output for Tasks 5–6.

- [ ] **Step 1: Write failing aggregation and redaction tests**

Add tests for a complete pair, a missing control, mismatched prompt digest, and mismatched candidate provenance. Add a fixed-seed bootstrap test whose confidence interval is stable. Add adversarial public-result inputs containing a user path, bearer token, email, internal hostname, canary, raw prompt, raw answer, trace, and unexpected key; each must raise `SkillEvalError` or `LabError`.

```python
with self.assertRaisesRegex(skill_eval.SkillEvalError, "incomplete pair"):
    skill_eval.summarize_benchmark([treatment_row], raw_result, provenance)

with self.assertRaisesRegex(skill_eval.SkillEvalError, "raw_answer"):
    skill_eval.validate_benchmark_public_result({"raw_answer": "not publishable"})
```

- [ ] **Step 2: Run focused aggregation tests to verify failure**

Run: `python3 -m unittest tests.test_skill_eval.SkillBenchmarkSummaryTests tests.test_lab.PublicExportTests -v`

Expected: FAIL because benchmark-summary and strict public-result functions do not exist.

- [ ] **Step 3: Implement fail-closed pairing, metrics, and schema validation**

Parse Promptfoo result rows into deterministic task/safety/activation/rubric outcomes without copying response text into summary objects. Reject a run unless all 45 release pairs are present with equal fixture, prompt, sandbox, candidate, judge, dependency, and contract provenance. Compute arm rates as numerators/denominators, treatment-minus-control binary deltas, seed-pinned bootstrap intervals, latency median/range, tokens, cost, and per-case aggregate deltas. Create the JSON Schema with `additionalProperties: false` throughout, then project the private summary into exactly the Public Result Shape.

```python
def paired_bootstrap(values, seed=20260816, samples=10_000):
    rng = random.Random(seed)
    estimates = [sum(rng.choice(values) for _ in values) / len(values) for _ in range(samples)]
    return [quantile(estimates, 0.025), quantile(estimates, 0.975)]
```

- [ ] **Step 4: Implement the export command and verify focused tests**

Add `export-benchmark-public`, whose first argument is the completed private run directory printed by `skill-benchmark` and whose required `--output` value is the canonical public JSON destination. It loads the private benchmark summary, projects only allowed fields, validates the new schema, runs lexical privacy guards, writes formatted UTF-8 JSON, and prints only the output path.

Run: `python3 -m unittest tests.test_skill_eval.SkillBenchmarkSummaryTests tests.test_lab.PublicExportTests -v`

Expected: PASS, including every adversarial rejection.

- [ ] **Step 5: Commit the aggregation/export unit**

```bash
git add scripts/skill_eval.py scripts/lab tests/test_skill_eval.py tests/test_lab.py docs/benchmark-results/github-public-readiness-benchmark.schema.json
git commit -m "feat: summarize and sanitize paired skill benchmarks"
```

### Task 4: Author the Nine Public Synthetic Cases

**Files:**
- Create: `benchmarks/skills/github-public-readiness/cases.yaml`
- Create: `benchmarks/skills/github-public-readiness/fixtures/clean-library/*`
- Create: `benchmarks/skills/github-public-readiness/fixtures/cleanup-project/*`
- Create: `benchmarks/skills/github-public-readiness/fixtures/private-blockers/*`
- Create: `benchmarks/skills/github-public-readiness/fixtures/unrelated-task/*`
- Modify: `tests/test_skill_eval.py`

**Interfaces:**
- Consumes: version-1 contract validation and paired runner from Tasks 1–3.
- Produces: a committed `SkillContract` with case IDs `direct-publish-now`, `direct-light-cleanup`, `direct-keep-private`, `implicit-visibility-decision`, `implicit-portfolio-decision`, `implicit-release-sequence`, `negative-code-explanation`, `negative-test-diagnosis`, and `negative-readme-summary`.

- [ ] **Step 1: Write failing fixture-contract tests**

Add tests loading the real contract with the pinned `github-public-readiness` package, asserting exactly nine case IDs, three per category, read-only sandbox for every case, and only files beneath the benchmark directory. Add a repository scan that rejects credential syntax, absolute user paths, emails, non-reserved hostnames, symlinks, `.git` entries, and every string in `PRIVATE_MARKERS`.

```python
self.assertEqual(len(contract.cases), 9)
self.assertEqual({case.sandbox for case in contract.cases}, {"read-only"})
self.assertEqual(collections.Counter(case.category for case in contract.cases), {
    "direct_activation": 3, "implicit_activation": 3, "negative_activation": 3,
})
```

- [ ] **Step 2: Run fixture tests to verify failure**

Run: `python3 -m unittest tests.test_skill_eval.GithubPublicReadinessFixtureTests -v`

Expected: FAIL because the real contract and fixtures do not exist.

- [ ] **Step 3: Create fabricated fixtures and deterministic expectations**

Write only clearly synthetic identifiers under `example.test` and `example.invalid`; do not use credential-shaped values. The clean fixture includes README, MIT license, install/test instructions, and passing test evidence. The cleanup fixture has documented fake hygiene gaps. The blocker fixture contains plainly fabricated non-public design and customer-boundary markers that require `Keep Private` without quoting marker contents. The unrelated fixture contains a small source file, a deterministic failing test, and concise README. Define each case's deterministic report labels and rubric in `cases.yaml`; direct and implicit audit cases require the expected readiness/portfolio classification, while negatives require the unrelated answer shape and no readiness classification.

- [ ] **Step 4: Run fixture and full contract tests to verify pass**

Run: `python3 -m unittest tests.test_skill_eval.GithubPublicReadinessFixtureTests tests.test_skill_eval.SkillContractTests -v`

Expected: PASS with no network or inference.

- [ ] **Step 5: Commit the synthetic suite**

```bash
git add benchmarks/skills/github-public-readiness tests/test_skill_eval.py
git commit -m "test: add synthetic public readiness benchmark cases"
```

### Task 5: Document the Harness and Generate Valid Public Evidence

**Files:**
- Modify: `README.md`
- Modify: `docs/benchmark-methodology.md`
- Create: `docs/case-studies/github-public-readiness-skill-benchmark.md`
- Create: `docs/benchmark-results/github-public-readiness-benchmark.json`
- Modify: `tests/test_lab.py`

**Interfaces:**
- Consumes: the release public-result schema and export command from Task 3 plus the real contract from Task 4.
- Produces: canonical sanitized result and case study consumed by Task 6.

- [ ] **Step 1: Write failing documentation/result validation tests**

Add tests requiring README and methodology documentation to show the exact `skill-benchmark` smoke and release commands, the 18/90 matrix, the pinned candidate/judge, synthetic-only scope, invalid-run rule, and public-export command. Add tests that the canonical JSON validates against the strict schema and its case IDs exactly equal the contract case IDs.

```python
public_result = json.loads((REPO_ROOT / "docs/benchmark-results/github-public-readiness-benchmark.json").read_text())
skill_eval.validate_benchmark_public_result(public_result)
self.assertEqual({row["case_id"] for row in public_result["case_results"]}, EXPECTED_CASE_IDS)
```

- [ ] **Step 2: Run documentation/result tests to verify failure**

Run: `python3 -m unittest tests.test_lab.SkillBenchmarkPublicationTests -v`

Expected: FAIL because the canonical result and paired-benchmark documentation do not exist.

- [ ] **Step 3: Document fixed commands and run the smoke benchmark**

Add the exact documented commands below to README and methodology, explaining that they assume `skills` is a sibling checkout of the primary AI Systems Lab repository and that output stays private until `export-benchmark-public` succeeds and a manual review passes.

```bash
./scripts/lab skill-benchmark ../skills/skills/github-public-readiness --eval-dir benchmarks/skills/github-public-readiness --target openai:gpt-5.6-terra --judge-model gpt-5.6 --profile smoke
./scripts/lab skill-benchmark ../skills/skills/github-public-readiness --eval-dir benchmarks/skills/github-public-readiness --target openai:gpt-5.6-terra --judge-model gpt-5.6 --profile release
```

Run `export-benchmark-public` immediately after the release command, passing the private run directory that command printed and the exact output path `docs/benchmark-results/github-public-readiness-benchmark.json`.

From the linked AI Systems Lab worktree created for this plan, run the smoke command with `../../../skills/skills/github-public-readiness` as the first positional argument; that path reaches the pinned sibling checkout from `.worktrees/eri-12-paired-benchmark`. If any containment, pair, trace, verifier, configuration, candidate, judge, or export condition fails, stop and fix the harness before release execution. Do not publish the smoke result.

- [ ] **Step 4: Run one complete release benchmark and export only the aggregate result**

Run the release command once after smoke passes. Inspect the private run's invalid-run status, confirm `valid_pairs == 45`, export the canonical JSON, validate it again, and manually inspect the public JSON diff. Write the case study from that JSON only: state the hypothesis, exact scope, full matrix, observed treatment/control deltas, non-winning outcomes, safety findings, cost/latency, limitations, and reproduction commands. Do not copy any raw output or fixture-marker text.

- [ ] **Step 5: Verify documentation/result tests and commit evidence**

Run: `python3 -m unittest tests.test_lab.SkillBenchmarkPublicationTests -v && make test`

Expected: PASS. Commit the documentation and canonical result only after the automated validators and manual privacy review both pass.

```bash
git add README.md docs/benchmark-methodology.md docs/case-studies/github-public-readiness-skill-benchmark.md docs/benchmark-results/github-public-readiness-benchmark.json tests/test_lab.py
git commit -m "docs: publish paired skill benchmark evidence"
```

### Task 6: Render the Sanitized Evidence as a Website Article

**Files:**
- Create: `src/data/github-public-readiness-benchmark.json`
- Create: `src/pages/writing/codex-skill-promptfoo-benchmark.astro`
- Modify: `src/pages/writing.astro`
- Modify: `tests/launch-readiness.test.mjs`
- Create: `tests/codex-skill-promptfoo-benchmark.test.mjs`

**Interfaces:**
- Consumes: byte-for-byte canonical `docs/benchmark-results/github-public-readiness-benchmark.json` from Task 5.
- Produces: `/writing/codex-skill-promptfoo-benchmark` with one `h1`, evidence tables, calibrated findings, and valid SEO metadata.

- [ ] **Step 1: Write failing website regression tests**

Create a test that imports the website JSON and asserts its SHA-256 digest equals the lab canonical result supplied by the release process. Build the site and assert the rendered page includes sections `Question`, `Method`, `Results`, `What changed`, `Safety and privacy`, `Costs and latency`, `Limitations`, and `Reproduce it`; every result table value must be derived from `metrics` or `case_results`. Reject prohibited certification/universal-benefit language and privacy markers.

```js
assert.match(html, /<h2[^>]*>Results<\/h2>/);
assert.match(html, /openai:gpt-5\.6-terra/);
assert.doesNotMatch(html, /\/Users\/|BEGIN [A-Z ]*PRIVATE KEY|authorization:\s*bearer|raw_prompt|raw_answer|trace/i);
```

- [ ] **Step 2: Run website article tests to verify failure**

Run: `node --test tests/codex-skill-promptfoo-benchmark.test.mjs`

Expected: FAIL because the article and sanitized evidence copy do not exist.

- [ ] **Step 3: Copy the validated result and implement result-driven article rendering**

Copy the canonical JSON without transformation. Import it into the Astro page and render arm metrics and case rows with `.map()`. Generate the outcome statement from the signed task-pass-rate delta: use “improved” when positive, “was unchanged” when zero, and “declined” when negative. State that this is one model, one skill revision, nine synthetic cases, and a bounded experiment. Link to the lab repository and canonical benchmark artifact; do not link local run directories.

```astro
{benchmark.case_results.map((row) => (
  <tr><td>{row.case_id}</td><td>{row.category}</td><td>{row.control_pass_rate}</td><td>{row.treatment_pass_rate}</td><td>{row.delta}</td></tr>
))}
```

- [ ] **Step 4: Add index, metadata, and privacy coverage; then run focused tests**

Add the article first in the Writing list with its actual release date and a summary describing the paired Promptfoo benchmark. Add its exact title, description, route, and `article` page type to launch-readiness metadata expectations. Run: `npm run build && node --test tests/codex-skill-promptfoo-benchmark.test.mjs tests/launch-readiness.test.mjs`

Expected: PASS with the new route present in the built sitemap and no privacy-marker match.

- [ ] **Step 5: Commit the website article unit**

```bash
git add src/data/github-public-readiness-benchmark.json src/pages/writing/codex-skill-promptfoo-benchmark.astro src/pages/writing.astro tests/codex-skill-promptfoo-benchmark.test.mjs tests/launch-readiness.test.mjs
git commit -m "feat: publish promptfoo skill benchmark article"
```

### Task 7: Complete Durable Website Documentation and Release Notes

**Files:**
- Modify: `docs/README.md`
- Modify: `docs/strategy/decisions.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/codex-skill-promptfoo-benchmark.test.mjs`

**Interfaces:**
- Consumes: article route and sanitized evidence from Task 6.
- Produces: durable links and an explicit evidence-publication decision.

- [ ] **Step 1: Write failing documentation tests**

Extend the article test to require an ERI-12 plan link in `docs/README.md`, an active decision-log entry that names strict aggregate-only publishing, and an Unreleased changelog item linking the article subject to Promptfoo and the synthetic paired benchmark.

```js
assert.match(docsIndex, /ERI-12: paired GitHub Public Readiness benchmark/);
assert.match(decisions, /sanitized aggregate evidence/i);
assert.match(changelog, /Promptfoo benchmark article/i);
```

- [ ] **Step 2: Run documentation tests to verify failure**

Run: `node --test tests/codex-skill-promptfoo-benchmark.test.mjs`

Expected: FAIL because the durable documentation references do not exist.

- [ ] **Step 3: Add the decision, docs index entry, and changelog entry**

Add one active decision dated with the release stating that public benchmark writing consumes only schema-validated aggregate evidence and cannot publish raw model/session material. Add one docs-index entry for ERI-12 that links to the article and names its AI Systems Lab source. Add one `Unreleased / Added` changelog bullet that truthfully describes the article as a bounded synthetic paired benchmark, without asserting a favorable result.

- [ ] **Step 4: Run focused and full website verification**

Run: `npm test`

Expected: PASS, including article metadata, sitemap, link resolution, claim guards, and privacy regression coverage.

- [ ] **Step 5: Commit the durable documentation unit**

```bash
git add docs/README.md docs/strategy/decisions.md CHANGELOG.md tests/codex-skill-promptfoo-benchmark.test.mjs
git commit -m "docs: record benchmark evidence publication policy"
```

## Self-Review Checklist

- Spec coverage: Tasks 1–3 implement paired arm isolation, Promptfoo orchestration, invalid-run gates, deterministic intervals, and strict export. Task 4 supplies the nine synthetic cases. Task 5 produces the canonical evidence and methodology. Tasks 6–7 render and document the evidence without raw data.
- Placeholder scan: all command names, model identifiers, routes, case IDs, result keys, and file paths are concrete. Computed SHA-256 values are identified as computed digests rather than textual placeholders.
- Type consistency: `BenchmarkRow` is produced by Task 1 and consumed by Tasks 2–3; `summarize_benchmark` produces the exact schema consumed by Task 5 and copied unchanged by Task 6; `case_results`, `metrics`, and `provenance` use the same names in the schema and article.
