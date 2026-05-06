# Stage Guide

A walkthrough of every subcommand: what to type, what to expect, and what to do when a gate blocks.

## `/man status` (or just `/man`)

Shows the active feature and current stage. Reads from `.man-kit/state.json`.

```
/man

[man-kit] state.json is valid. feature=oauth-login stage=code
Stages completed: ['plan']
Next gate: code_to_test
```

When there's no active feature:

```
[man-kit] No active feature in this project. Run `/man plan <description>` to start a build loop.
```

---

## `/man plan <feature description>`

Initialize a feature and produce `docs/PLAN-<slug>.md`.

### What you type

```
/man plan add OAuth login flow with Google provider
```

### What happens

1. The slug is derived from your description: `oauth-login` (or similar — 2-3 words, ≤30 chars).
2. The state machine initializes: `feature=oauth-login`, `current_stage=plan`.
3. The `planner` sub-agent (Opus) reads the codebase and writes `docs/PLAN-oauth-login.md` with:
   - Goal
   - Success criteria (measurable)
   - Technical risks
   - Existing patterns to follow
   - Tasks (each ≤1 day, sized S/M/L)
   - Out of scope
4. The `plan_to_code` gate runs. PASS or FAIL is reported.
5. Even on PASS, **state is not auto-advanced**. You explicitly run `/man code` after reviewing the plan.

### What can fail the gate

| Failure | Why | Fix |
|---------|-----|-----|
| `plan_file_exists` failed | Planner didn't write the file | Re-run `/man plan` |
| `plan_sections` failed: missing "## Technical risks" | Planner skipped a required heading | Edit the plan to add the section (even one line is fine) |
| `task_size_hints` failed | A task has no `Size: S/M/L` line | Add size hints to each task |

### When the plan is wrong later

If the Code stage reveals the plan was incorrect, run:

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/stage-tracker.py" --action=loop-back --to=plan --reason="<one-line>"
```

Then re-run `/man plan` to revise.

---

## `/man code`

Implement the next un-implemented task from the plan.

### Preconditions

- `plan_to_code` gate must pass.
- Plan file must exist at `docs/PLAN-<slug>.md`.

### What happens

1. `plan_to_code` gate re-runs. If anything changed in the plan that broke it (e.g., you removed a section), the gate blocks.
2. State advances: `current_stage=code`, `stages_completed += ["plan"]`.
3. The `coder` sub-agent (Sonnet) reads the plan, picks the next un-done task, implements it.
4. Files touched are appended to `state.artifacts.code_files`.

### What can fail the gate (`code_to_test`)

| Failure | Tool | Fix |
|---------|------|-----|
| `typecheck_typescript` failed | `tsc` | Fix the type errors |
| `typecheck_python` failed | `mypy` | Fix the type errors |
| `lint_eslint` failed | `eslint` | Run `eslint --fix` or fix manually |
| `no_todo_in_new_code` failed | regex scan | The task isn't done; remove TODO and finish, or split into a follow-up task |

### Forgiveness

If `tsc`/`mypy`/`eslint` aren't installed, those checks show `[OK] skipped - <tool> not on PATH`. The gate doesn't fail on missing tooling; it only fails on real, detected errors.

---

## `/man test`

Generate tests for the changes from the Code stage.

### Preconditions

- `code_to_test` gate must pass.

### What happens

1. State advances: `current_stage=test`.
2. The `tester` sub-agent (Haiku) reads `code_files` from state and writes tests covering:
   - Happy path
   - Edge cases (null, empty, boundary values)
   - Error paths (invalid input, dependency failures)
3. New test files are appended to `state.artifacts.test_files`.

### What can fail the gate (`test_to_review`)

| Failure | Why | Fix |
|---------|-----|-----|
| `tests_exist` failed | No test files found | Tester didn't write tests; re-run `/man test` |
| `no_skip_or_only` failed: `test_x.py` | `@pytest.mark.skip` / `it.only` / `xit` left in | Remove the skip; if legitimate, document it (v2 will allow `// SKIP-REASON: <text>`) |
| `tests_pass_pytest` failed | Test suite has failures | Read the truncated output; either tests are wrong (fix tests) or code is broken (loop back to `/man code`) |
| `coverage_threshold` failed: 67% < 80% | Coverage below threshold | Add tests for uncovered paths, or relax threshold in `.man-kit/config.json` |

### Mutation discipline

The tester agent is required to manually verify 1-2 random tests by breaking the corresponding code, confirming the test fails, then restoring. This isn't enforced by the gate; it's enforced by the agent's contract.

---

## `/man review`

Aggregate findings from specialist reviewers and produce a single verdict.

### Preconditions

- `test_to_review` gate must pass.

### What happens

1. State advances: `current_stage=review`.
2. The `reviewer` sub-agent (Sonnet) dispatches to specialist plugins as available:
   - `craftpowers:code-reviewer` — general quality
   - `craftpowers:secure-reviewer` — OWASP Top 10
   - `code-review` (Anthropic official) — multi-confidence review
   - `coderabbit` / `semgrep` / `aikido` — if installed
3. Findings are deduped and assigned severities.
4. A report is written to `.man-kit/reviews/<slug>.md` with `**Verdict**: PASS|CONCERNS|FAIL`.

### Verdicts

| Verdict | Meaning | What to do |
|---------|---------|------------|
| **PASS** | No HIGH, no MEDIUM. | Run `/man done`. |
| **CONCERNS** | MEDIUM exists, no HIGH. | Fix each MEDIUM (preferred) or add a documented override line (v2 will support structured override; v1 requires fix or manual verdict edit). |
| **FAIL** | HIGH severity, plan task missing, or test gate bypassed. | Loop back. Usually `/man code` to fix; sometimes `/man plan` if the plan was wrong. |

### Severity rubric (strict)

- **HIGH**: security vuln, data loss, breaking API change, regression, hard-coded secret.
- **MEDIUM**: incorrect edge case, missing test for important path, contract not honored, measurable perf regression.
- **LOW**: style, naming, micro-perf.

If a finding doesn't cleanly fit, the reviewer is required to **downgrade**, not upgrade. Erring toward FAIL trains users to ignore the gate.

---

## `/man done`

Mark the feature complete.

### Preconditions

- `review_to_done` gate passes (verdict = PASS).

### What happens

1. Gate re-runs to confirm the report still says PASS.
2. State advances: `current_stage=done`, `stages_completed=['plan', 'code', 'test', 'review']`.
3. The dispatcher tells you the feature is complete and suggests next steps (commit, push, PR) but does NOT run them. Those belong to a future "ship" stage.

### Starting another feature

You can now run `/man plan <new-feature>`. The previous state is auto-archived to `.man-kit/history/<slug>-<timestamp>.json`.

---

## Recovery

| Situation | Command |
|-----------|---------|
| Forgot what stage you're at | `/man status` |
| state.json got corrupted | `python "${CLAUDE_PLUGIN_ROOT}/hooks/stage-tracker.py" --action=recover` |
| Want to start over on the same feature | `python "${CLAUDE_PLUGIN_ROOT}/hooks/stage-tracker.py" --action=init --feature=<slug>` (will refuse if active feature isn't `done`) |
| Need to override a gate | Edit `.man-kit/state.json` directly (no obfuscation; just plain JSON) |

---

## Tips

- **Don't fight the gate.** If `code_to_test` fails on a typecheck error, fix the type. Don't disable the check.
- **Use `/man status` liberally.** It's read-only and reminds you what gate runs next.
- **Loop back is fine.** The state machine records loop-backs with reasons. A clean loop-back is healthier than silently expanding scope.
- **Compose with other plugins.** man-kit gets stronger as you add context-mode, context7, code-review, semgrep. Without them it works; with them it's faster and sharper.
