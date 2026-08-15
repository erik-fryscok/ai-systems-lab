# Skill Audit Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit Snyk preflight evidence and authenticated skills.sh verification without presenting local checks as guarantees of partner approval.

**Architecture:** `scripts/skill_audit.py` contains scanner, marketplace, digest, readiness, and private-report behavior. `scripts/lab` supplies CLI dispatch and public-export sanitization. Typed result dataclasses distinguish fail from unverified.

**Tech Stack:** Python 3.9+ standard library HTTP/process APIs, unittest, installed Snyk Agent Scan, authenticated skills.sh API.

## Global Constraints

- Never auto-download or execute a scanner during a release run.
- Never pass secrets on command lines or store them in reports.
- Snyk’s scan uploads skill content; disclose this before execution.
- Use `VERCEL_OIDC_TOKEN` for skills.sh authentication.
- Partner readiness requires matching published content plus normalized `pass` from Gen Agent Trust Hub, Socket, and Snyk.
- Raw scanner payloads, skill content, tokens, and local paths remain private.

---

## File Structure

- `scripts/skill_audit.py`: Snyk process adapter, authenticated skills.sh adapter, exact-content digest, gates, reports.
- `scripts/lab`: `skill-audit` parser/dispatch and sanitized public-export list.
- `tests/test_skill_audit.py`: mocked scanner, HTTP, digest, gate, and report tests.
- `tests/test_lab.py`: parser/export regression tests.
- `README.md` and `docs/benchmark-methodology.md`: consent, credentials, and status meaning.

### Task 1: Add the explicit Snyk preflight

**Files:**
- Create: `scripts/skill_audit.py`
- Create: `tests/test_skill_audit.py`
- Modify: `scripts/lab:3000-3166`

**Interfaces:**
- Produces: `run_snyk_scan(skill_dir: Path, scanner_bin: str, timeout: int) -> ScannerResult`
- Produces: `ScannerResult(status, version, exit_code, findings, raw_output_path, error)`

- [ ] **Step 1: Write failing scanner tests**

```python
def test_missing_scanner_is_unverified(self):
    result = skill_audit.run_snyk_scan(self.skill_dir, "not-installed", 5)
    self.assertEqual(result.status, "unverified")

def test_nonzero_json_scan_is_a_failure(self):
    completed = subprocess.CompletedProcess(["snyk-agent-scan"], 1, '{"findings":[{"id":"x"}]}', "")
    with mock.patch("subprocess.run", return_value=completed):
        result = skill_audit.run_snyk_scan(self.skill_dir, "snyk-agent-scan", 5)
    self.assertEqual(result.status, "fail")
    self.assertEqual(result.exit_code, 1)
```

Add missing `--snyk` consent, successful JSON/zero exit, malformed JSON, timeout, and secret-redaction tests.

- [ ] **Step 2: Run the tests**

Run: `python3 -m unittest tests.test_skill_audit.SnykScannerTests -v`
Expected: FAIL with import or missing-function errors.

- [ ] **Step 3: Implement the scanner adapter**

Only the `--snyk` code path calls this function. Resolve an existing binary with `shutil.which`, run its documented noninteractive JSON mode against `SKILL.md` using list-form `subprocess.run`, and write raw output only to the private run directory. Obtain version separately. Map exit zero to `pass`, nonzero to `fail`, and missing/timeout/malformed output to `unverified`; redact bearer tokens, `sk-` values, and local paths in returned errors.

- [ ] **Step 4: Verify**

Run: `python3 -m unittest tests.test_skill_audit.SnykScannerTests -v`
Expected: PASS without a live scanner.

- [ ] **Step 5: Commit**

```bash
git add scripts/skill_audit.py scripts/lab tests/test_skill_audit.py
git commit -m "feat: add explicit Snyk skill preflight"
```

### Task 2: Verify the skills.sh snapshot and partner audits

**Files:**
- Modify: `scripts/skill_audit.py`
- Modify: `tests/test_skill_audit.py`

**Interfaces:**
- Produces: `canonical_skill_digest(files: Mapping[str, str]) -> str`
- Produces: `fetch_skills_sh_snapshot(skill_id: str, token: str, timeout: int) -> MarketplaceSnapshot`
- Produces: `fetch_skills_sh_audits(skill_id: str, token: str, timeout: int) -> list[PartnerAudit]`
- Produces: `MarketplaceSnapshot(files, api_hash, digest)`, `PartnerAudit(partner, status, summary, detail_url)`.

- [ ] **Step 1: Write failing API/digest tests**

```python
def test_canonical_digest_is_order_independent(self):
    self.assertEqual(
        skill_audit.canonical_skill_digest({"b.txt": "two", "a.txt": "one"}),
        skill_audit.canonical_skill_digest({"a.txt": "one", "b.txt": "two"}),
    )

def test_missing_oidc_token_blocks_request(self):
    with self.assertRaisesRegex(skill_audit.SkillAuditError, "VERCEL_OIDC_TOKEN"):
        skill_audit.fetch_skills_sh_snapshot("owner/repo/skill", "", 10)
```

Mock exact match, changed/missing/extra remote files, `pass`/`warn`/`fail`, absent required partners, and HTTP 401/404/429/timeout.

- [ ] **Step 2: Run the tests**

Run: `python3 -m unittest tests.test_skill_audit.SkillsShTests -v`
Expected: FAIL with missing API helpers.

- [ ] **Step 3: Implement authenticated snapshot checks**

Accept only three nonempty `OWNER/REPOSITORY/SKILL` segments. Send `Authorization: Bearer <token>` using `urllib.request.Request` to:

```text
GET https://skills.sh/api/v1/skills/OWNER/REPOSITORY/SKILL
GET https://skills.sh/api/v1/skills/audit/OWNER/REPOSITORY/SKILL
```

SHA-256 the sorted UTF-8 records `path + NUL + contents + NUL`. Retain the API hash but use exact relative-file comparison and canonical digest as the freshness gate. Normalize partner names to the three required names and unknown/missing status to `unverified`.

- [ ] **Step 4: Verify**

Run: `python3 -m unittest tests.test_skill_audit.SkillsShTests -v`
Expected: PASS without network access.

- [ ] **Step 5: Commit**

```bash
git add scripts/skill_audit.py tests/test_skill_audit.py
git commit -m "feat: verify skills.sh partner audits"
```

### Task 3: Combine evidence into readiness reports

**Files:**
- Modify: `scripts/skill_audit.py`
- Modify: `scripts/lab:2920-3166`
- Modify: `README.md`
- Modify: `docs/benchmark-methodology.md`
- Modify: `tests/test_skill_audit.py`
- Modify: `tests/test_lab.py`

**Interfaces:**
- Produces: `evaluate_audit_readiness(local_package, snyk_preflight, marketplace_snapshot, partner_audits) -> AuditReadiness`
- Produces: `AuditReadiness(local_package, snyk_preflight, marketplace_snapshot, partner_audits, partner_ready, reasons)`

- [ ] **Step 1: Write failing gate tests**

```python
def test_local_pass_without_snyk_is_external_unverified(self):
    result = skill_audit.evaluate_audit_readiness(self.local_files, None, None, [])
    self.assertFalse(result.partner_ready)
    self.assertIn("local_pass_external_unverified", result.reasons)

def test_matching_snapshot_and_three_passes_is_partner_ready(self):
    result = skill_audit.evaluate_audit_readiness(self.local_files, self.snyk_pass, self.matching_snapshot, self.required_passes)
    self.assertTrue(result.partner_ready)

def test_stale_snapshot_blocks_partner_readiness(self):
    result = skill_audit.evaluate_audit_readiness(self.local_files, self.snyk_pass, self.changed_snapshot, self.required_passes)
    self.assertFalse(result.partner_ready)
```

Add cases for partner warn/fail/missing and public export excluding raw scan payload, skill contents, tokens, and local paths.

- [ ] **Step 2: Run the tests**

Run: `python3 -m unittest tests.test_skill_audit tests.test_lab.PublicExportTests -v`
Expected: FAIL because readiness/report behavior is absent.

- [ ] **Step 3: Implement reports, CLI, and documentation**

Register `skill-audit SKILL_DIR [--snyk] [--skills-sh-id ID]`; print the upload disclosure before a Snyk call. Write private `audit.json` and redacted `audit-report.md` containing timestamp, scanner version/status, canonical/API digests, partner statuses/summaries, and detail links. Exclude raw content/payloads, tokens, and local paths. Return `local_pass_external_unverified` without Snyk and `marketplace_unverified` without a matching snapshot. Set `partner_ready` only when local/remote content matches, the Snyk preflight passes, and each Gen Agent Trust Hub, Socket, and Snyk marketplace audit is `pass`. Extend the public-export sanitizer and document that local readiness never guarantees partner approval.

- [ ] **Step 4: Verify**

Run:

```bash
make test
./scripts/lab doctor
./scripts/lab skill-audit /absolute/path/to/skill --snyk --skills-sh-id owner/repository/skill
```

Expected: tests and doctor pass; run the final command only for a published skill with an installed scanner and `VERCEL_OIDC_TOKEN`.

- [ ] **Step 5: Commit**

```bash
git add scripts/skill_audit.py scripts/lab README.md docs/benchmark-methodology.md tests/test_skill_audit.py tests/test_lab.py
git commit -m "feat: report skill audit readiness"
```

## Coverage Review

This plan covers consented Snyk scanning, authenticated snapshot/audit retrieval, exact-content freshness, named-partner gates, private evidence, public sanitization, and accurate readiness language. Implement it only after the evaluation-framework plan.
