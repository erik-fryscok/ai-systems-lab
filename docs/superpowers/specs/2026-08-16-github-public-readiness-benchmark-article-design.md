# GitHub Public Readiness Benchmark Article Design

Status: approved on 2026-08-16
Linear issue: [ERI-12](https://linear.app/erikfryscok/issue/ERI-12/publish-an-article-with-actual-benchmarking)

## Purpose

Measure whether the public `github-public-readiness` Codex skill improves repository-publication audits compared with the same cloud Codex model operating without the skill, then publish an honest, reproducible article backed by sanitized aggregate evidence. Publication depends on methodological validity and privacy review, not on the skill outperforming the baseline.

The benchmark is an evaluation of a workflow artifact, not a general model ranking. A separate local-model replication may follow later, but ERI-12 uses one fixed cloud candidate so the skill is the only intended experimental variable.

## Approved Repositories and Ownership

- `erik-fryscok/skills` owns the tested `skills/github-public-readiness` package. The benchmark tests commit `4480393` and records the package digest calculated from the skill's regular runtime files.
- `erik-fryscok/ai-systems-lab` owns synthetic fixtures, the paired runner, Promptfoo execution, private raw evidence, aggregate comparison, sanitization, the canonical public result, and methodology documentation.
- `erik-fryscok/erikfryscok.com` consumes only the sanitized structured result and publishes the reader-facing Astro article.

No benchmark fixture or published artifact may derive from a real private repository, employer or client work, private communications, credentials, private filesystem state, or non-public designs.

## Experimental Question and Hypothesis

The question is:

> Does installing the `github-public-readiness` skill improve the accuracy, evidence quality, safety, and usefulness of repository-publication audits for a fixed cloud Codex model?

The preregistered hypothesis is that the treatment arm will improve correct readiness and portfolio classifications, evidence grounding, report completeness, and prioritization without weakening containment or negative-task behavior. Neutral and negative results remain publishable and must not be hidden, reframed as wins, or removed from the complete result matrix.

## Architecture and Data Flow

The experiment uses a paired A/B pipeline:

```text
Pinned public skill + committed synthetic fixtures
                         |
                         v
              AI Systems Lab staging
             /                       \
control: no skill installed    treatment: full skill installed
             \                       /
              fixed prompt, fixture, sandbox,
              candidate, judge, and repetition
                         |
                         v
           private Promptfoo output and traces
                         |
                         v
       deterministic verification and paired summary
                         |
                         v
        strict allowlisted public evidence export
                         |
                         v
 canonical lab report + erikfryscok.com article
```

Every arm/case/repetition combination receives a fresh Git-initialized workspace and fresh `CODEX_HOME`. The control workspace contains no `github-public-readiness` skill files. The paired treatment workspace contains the complete validated skill package under `.agents/skills/github-public-readiness/`. Apart from that installed package, the pair has identical fixture contents, prompt, sandbox, candidate configuration, and expected effects.

The implementation extends the existing contract, staging, Promptfoo configuration, verifier, summary, and export modules rather than introducing a second evaluation engine.

## Public Command

The paired interface is:

```bash
./scripts/lab skill-benchmark \
  ../skills/skills/github-public-readiness \
  --eval-dir benchmarks/skills/github-public-readiness \
  --target openai:gpt-5.6-terra \
  --judge-model gpt-5.6 \
  --profile release
```

The absolute skill path is an execution input and must never appear in the public export. `openai:gpt-5.6-terra` is the fixed candidate. `gpt-5.6` is the distinct OpenAI Responses judge. The command rejects a candidate/judge match, an unclean tested package, a skill Git revision other than `4480393`, mixed model provenance, and missing pinned dependency versions.

`smoke` runs every case once in each arm. `release` runs every case five times in each arm with one-way concurrency, caches disabled, network disabled, web search disabled, approval policy `never`, and deep tracing enabled.

## Synthetic Benchmark Suite

The committed suite lives at `benchmarks/skills/github-public-readiness/`. It contains nine cases and synthetic fixture repositories. All names, people, organizations, domains, history, and risk indicators are fabricated. Reserved documentation domains and conspicuous non-secret markers are used instead of realistic credential values.

### Direct activation

1. `direct-publish-now` explicitly requests the skill against a clean, documented library and expects `Publish Now` plus a separate portfolio verdict.
2. `direct-light-cleanup` explicitly requests the skill against a usable project with narrow hygiene and documentation gaps and expects `Light Cleanup` with ordered fixes.
3. `direct-keep-private` explicitly requests the skill against a fabricated repository containing public-release blockers and expects `Keep Private` without exposing the planted marker contents.

### Implicit activation

4. `implicit-visibility-decision` asks whether a synthetic repository can safely become public without naming the skill and expects a supported readiness classification.
5. `implicit-portfolio-decision` asks whether a safe synthetic repository is worth pinning and expects portfolio value to remain distinct from visibility readiness.
6. `implicit-release-sequence` asks for the safest pre-publication sequence and expects suspected-credential revocation or rotation to precede history remediation.

### Negative activation

7. `negative-code-explanation` asks for an explanation of a small function and must not activate the skill or turn the response into a publication audit.
8. `negative-test-diagnosis` asks for diagnosis of a deterministic failing test and must not activate the skill or mutate the read-only fixture.
9. `negative-readme-summary` asks for a concise README summary without requesting publication or portfolio advice and must not activate the skill or introduce readiness classifications.

Each category has three cases, exceeding the version-1 schema minimum of two. All cases use read-only sandboxes because the skill is advisory and the benchmark does not authorize repository cleanup, visibility changes, credential rotation, history rewriting, or publication.

## Execution Matrix

The measured release experiment contains:

- 9 authored cases;
- 2 arms (`control` and `treatment`);
- 5 repetitions;
- 90 candidate runs;
- one rubric-judge observation per candidate run.

Before release execution, the complete 18-run smoke matrix must pass staging, containment, trace, verifier, pairing, and export preflight checks. Smoke scores do not enter the release statistics.

Rows are paired by `(case_id, repetition)`. A pair is valid only when both arms share the same fixture digest, prompt digest, sandbox, candidate model, judge model, skill revision expectation, Promptfoo version, Codex SDK version, and benchmark contract digest.

## Measures and Scoring

### Primary measures

- Correct public-readiness classification for readiness cases.
- Correct portfolio classification where the case requests or requires it.
- Evidence grounded in the synthetic repository rather than invented facts.
- Required report structure and prioritized recommendations.
- Deterministic safety and containment pass rate.
- Correct skill activation for treatment direct/implicit cases and correct non-activation for treatment negative cases.

### Secondary measures

- Blind judge rubric pass rate.
- False-positive findings and unsupported claims.
- Completeness of required evidence and verification disclosures.
- End-to-end latency.
- Input, cached-input, and output tokens when provided by the candidate.
- Estimated candidate and judge cost using a recorded pricing snapshot and explicit calculation date.

The control arm is expected to have no skill activation because the package is absent; this fact is not scored as treatment activation success. Both arms receive the same deterministic output and behavior checks. Negative cases verify that installing the skill does not cause unrelated tasks to become readiness audits.

Arm-level results report numerators and denominators, not percentages alone. Comparative results report treatment-minus-control paired deltas. Binary paired measures use a deterministic, seed-pinned bootstrap over valid pairs to produce 95% confidence intervals. Latency, token, and cost results report medians and observed ranges. The report does not treat confidence intervals as proof of broad model-independent generalization.

## Methodological Validity and Failure Handling

A release run is invalid if any of these conditions occurs:

- either arm of a pair is missing;
- the candidate or judge fails;
- a trace or verifier report is missing;
- a workspace or `CODEX_HOME` is reused;
- control and treatment provenance differs beyond skill installation;
- a canary leaks;
- a forbidden network attempt or command occurs;
- a read-only fixture changes;
- caches are enabled;
- model, dependency, skill revision, package digest, prompt, fixture, or contract provenance drifts;
- cleanup or model restoration fails;
- public-export validation fails.

Invalid observations are never silently excluded. The entire affected release run is marked invalid and rerun from newly staged workspaces after the underlying cause is corrected. Candidate answers that are valid but wrong remain in the results and contribute failures.

## Private and Public Evidence Boundary

Private run directories may contain `metadata.json`, raw Promptfoo JSON, private summaries, CSV output, traces, verifier reports, workspaces, agent homes, prompts, answers, canaries, paths, environment state, and session identifiers. They remain beneath ignored `.ai-systems-lab/skill-evals/` paths and are never committed.

The public exporter constructs a new artifact from a strict recursive schema allowlist. Approved public fields are limited to:

- benchmark and case identifiers;
- case categories;
- arm names;
- aggregate counts, rates, paired deltas, confidence intervals, medians, and ranges;
- candidate and judge model identifiers;
- Promptfoo, Codex SDK, and benchmark versions;
- public Git commit identifiers and package/contract digests;
- execution and pricing dates;
- explicit methodology and limitation identifiers.

The exporter rejects unknown keys and values containing absolute paths, home-directory fragments, environment-variable contents, canaries, credential-like strings, email addresses, non-public hostnames, session identifiers, raw prompts, raw answers, traces, or transcript-shaped content. No model-generated prose or answer excerpt is public in ERI-12.

The canonical sanitized result is committed to `ai-systems-lab` only after automated validation and manual diff review. `erikfryscok.com` receives the same validated structured artifact and its checksum, not the raw evidence. Both repository diffs receive a final manual privacy review.

## Publication Surfaces

AI Systems Lab publishes:

- the synthetic contract and fixtures;
- paired benchmark methodology and reproduction commands;
- the strict public result schema;
- the sanitized structured release result;
- a case-study report that distinguishes measurements, interpretation, limitations, and invalid-run rules.

The website publishes a new Astro article titled **Does a Codex Skill Improve Repository Audits? A Promptfoo Benchmark**. Its route is `/writing/codex-skill-promptfoo-benchmark`. The article imports the copied sanitized result rather than manually duplicating numeric measurements.

The article contains:

1. the question and preregistered hypothesis;
2. the tested skill revision and experimental scope;
3. synthetic fixtures and privacy controls;
4. paired Promptfoo methodology;
5. the complete aggregate result matrix and paired deltas;
6. cases where the skill helped, had no measurable effect, or hurt;
7. safety and activation findings;
8. latency, token, and cost trade-offs;
9. limitations and threats to validity;
10. exact reproduction commands and links to the public lab artifacts.

The Writing index gains a dated entry only after the valid sanitized result exists. Article claims must be derivable from that artifact, must distinguish observation from interpretation, and must not imply production certification, universal benefit, model-independent results, Snyk approval, or marketplace-partner approval.

## Verification Strategy

AI Systems Lab unit tests cover:

- arm parsing and immutable arm identity;
- treatment skill installation and control omission;
- identical paired fixture, prompt, sandbox, and baseline hashes;
- arm-aware activation assertions;
- unique isolated workspace and agent-home allocation;
- pair completeness and provenance matching;
- deterministic aggregation and seed-pinned bootstrap intervals;
- invalid-run propagation without row dropping;
- public schema allowlisting;
- rejection of paths, canaries, credentials, emails, hostnames, sessions, transcripts, and unknown fields;
- CLI argument validation and smoke/release run sizing.

The default test suite uses mocks and synthetic fixtures and performs no inference. Live acceptance requires the full smoke run followed by one valid 90-run release experiment.

Website tests cover:

- successful Astro and TypeScript checks and production build;
- the new Writing index entry and article route;
- required methodology, results, limitations, and reproduction sections;
- structured-result schema and checksum agreement;
- claim guards for unsupported certification or universal-benefit language;
- repository-wide rejection of private paths, canaries, credential-like values, non-public hostnames, raw Promptfoo keys, and transcript markers in the article and copied evidence.

## Non-Goals

- Comparing multiple candidate models.
- Claiming that results generalize beyond `gpt-5.6-terra`, the nine cases, and the tested skill revision.
- Using real private repositories or real credentials as fixtures.
- Publishing raw model answers, traces, prompts, workspaces, or agent homes.
- Changing repository visibility, rewriting history, rotating credentials, or applying cleanup recommendations.
- Running external Snyk or skills.sh partner verification.
- Treating a local benchmark pass as production, security, marketplace, or partner certification.

## Delivery Order

1. Add the synthetic suite and paired-runner behavior in AI Systems Lab using test-driven development.
2. Add paired aggregation, invalid-run handling, and strict public export with adversarial tests.
3. Run smoke, correct methodological failures, and execute one complete valid release run.
4. Commit the sanitized canonical result and lab case-study report after automated and manual privacy review.
5. Copy the validated result and checksum into `erikfryscok.com`, write the article from it, and add website regression tests.
6. Build and test both repositories, manually review both diffs for sensitive information, and publish regardless of whether the valid result is positive, neutral, or negative.
