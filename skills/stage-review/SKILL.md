---
name: stage-review
description: Reference for the man-kit Review stage. Use when reading review reports, deciding whether to merge a feature, or judging a CONCERNS verdict. Do NOT use to write the review itself — that is the reviewer sub-agent's job (see agents/reviewer.md).
---

# Review Stage Reference

The Review stage is the last gate before DONE. It produces one of three verdicts — PASS, CONCERNS, FAIL — backed by specific findings. The reviewer agent does not block; the gate does.

## The three verdicts

| Verdict | What it means | What happens next |
|---------|---------------|-------------------|
| **PASS** | No HIGH severity, no MEDIUM. LOW findings listed but optional. | Gate `review_to_done` passes; user runs `/man done`. |
| **CONCERNS** | MEDIUM findings exist, no HIGH. | Gate FAILS by default. User must accept each MEDIUM with documented reason, or fix. (v1 requires fix; v2 will add override mechanism.) |
| **FAIL** | HIGH severity finding, OR plan tasks not delivered, OR test gate was bypassed. | Gate FAILS. User must loop back to Code (or Plan if plan was wrong) and fix. |

## Severity rubric — strict definitions

The reviewer agent must apply these exactly. Vague severity defeats the gate.

### HIGH (must fix — verdict FAIL)
- Security vulnerability (any OWASP Top 10 issue)
- Data loss risk (uncaught exception that drops state, missing transaction boundary)
- Breaking change to public contract not flagged in plan
- Regression: existing test fails on the new code
- Hard-coded secret / token / API key

### MEDIUM (should fix or document — verdict CONCERNS)
- Incorrect behavior in an edge case the plan called out
- Missing test for an important code path (gate already enforces minimum coverage; this is for paths that are critical but not measured)
- Documented contract not honored (e.g., API doc says X, code returns Y)
- Performance regression with measurable impact (>20% slower on a hot path)
- Unhandled error path that is reachable in normal operation

### LOW (optional — does not block)
- Style preference (when project doesn't have a stricter rule)
- Naming clarity ("could be more descriptive")
- Micro-performance ("could use a Map instead of Array")
- Comment-quality nit

If a finding doesn't cleanly fit one of these, the reviewer agent must downgrade rather than upgrade. **Erring toward FAIL is worse than erring toward PASS** — false alarms train users to ignore the gate.

## Reading an aggregated report

The reviewer agent dispatches to specialist sub-reviewers when available:

| Specialist | What it finds |
|-----------|---------------|
| `craftpowers:code-reviewer` (sonnet) | General code quality, design issues, plan adherence |
| `craftpowers:secure-reviewer` (sonnet) | OWASP Top 10, auth/authz issues |
| `code-review` plugin (Anthropic, official) | Multi-confidence-level review of changed files |
| `coderabbit` plugin (if installed) | AST-level checks, 40+ analyzers |
| `semgrep` plugin (if installed) | Security rules + custom patterns |
| `aikido` plugin (if installed) | SAST + secrets + IaC scan |

The aggregator (built into the reviewer agent's contract) MUST:

1. **Dedupe findings.** Two specialists pointing at the same issue → one finding, severity = max.
2. **Cite each finding's source.** "(coderabbit)" or "(secure-reviewer)" appended to the bullet.
3. **Reconcile severity disagreement.** If specialists disagree, defer to the stricter one but note the disagreement.
4. **Never invent findings.** If specialists are silent, the report says "no findings" — does not fabricate to look thorough.

## When to override a CONCERNS verdict

In v1, CONCERNS is treated as FAIL by the gate. To ship a feature with known MEDIUM concerns, the user must:

1. Address each MEDIUM (preferred), OR
2. Edit the review report's verdict line to PASS with a comment explaining why each MEDIUM is acceptable. The audit trail in the report is the override record.

Future v2 will add a structured override mechanism (`/man override <finding-id> --reason="<text>"`) that records overrides in `state.json` rather than the report.

## Plan adherence — the silent killer

Most reviews focus on code quality. The reviewer agent's contract requires an additional check: **does the diff match the plan?**

Two failure modes:

| Failure | Severity | Why it matters |
|---------|----------|----------------|
| File changed that no plan task references | MEDIUM (or HIGH if security-sensitive) | Scope creep; reverse and submit a new plan or document the addition |
| Plan task not delivered (file/function not present) | HIGH | Code stage was incomplete; loop back to Code |

The audit trail (state.json's `artifacts.code_files` + plan's `## Tasks`) is what makes this verifiable.

## Common mistakes

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| Reviewer marks everything HIGH | Severity discipline not applied | Re-prompt with the rubric inline |
| Reviewer says PASS but a security issue is obvious | secure-reviewer not dispatched | Verify orchestrator detected the plugin; check enabledPlugins |
| Same finding appears 5 times in the report | Aggregator didn't dedupe | Re-prompt: "dedupe findings, severity = max of duplicates" |
| Verdict is FAIL but no specific finding listed | Reviewer fabricated severity | Reject the report; require concrete `path:line` citations |
| User wants to ship despite CONCERNS | Need explicit override | Edit report verdict line + add comment, or fix the MEDIUMs |
