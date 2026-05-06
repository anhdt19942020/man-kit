---
name: stage-code
description: Reference for the man-kit Code stage. Use when implementing tasks from a plan file, deciding whether a code change is in scope, or judging whether to loop back to /man plan. Do NOT use this to write the code itself — that is the coder sub-agent's job (see agents/coder.md).
---

# Code Stage Reference

The Code stage implements one task at a time from `docs/PLAN-<slug>.md`. The plan is the contract. The coder agent's job is to satisfy the contract — nothing more, nothing less.

## In scope vs out of scope

The plan's "Tasks" section lists what is in scope. Everything else is out of scope, even if the coder spots an opportunity to improve the codebase.

| Situation | In scope? | What to do |
|-----------|-----------|------------|
| Task says "add config" — there's a typo in an unrelated config file | No | Note it for a later plan; do not fix |
| Task says "implement callback" — the callback handler needs a helper function | Yes | Add the helper, it's part of the task |
| While reading code, you spot a security bug elsewhere | No | Tell the user; they decide whether to file a separate task |
| The plan says "use existing X pattern" but X doesn't exist | Loop back | Stop coding; run `--action=loop-back --to=plan` |
| A library version is incompatible with the task | Ask | Surface to the user before installing/upgrading |

## When to loop back to plan

Some signals mean the plan was wrong, not the code:

- A task assumes a file/module that doesn't exist and isn't being created by an earlier task.
- The chosen library/pattern can't satisfy the success criteria after honest attempt.
- Implementing the task reveals a hidden dependency the plan missed (e.g., needing a DB migration nobody mentioned).

In those cases, do NOT silently expand the task. Run:

```bash
python "${CLAUDE_PLUGIN_ROOT}/hooks/stage-tracker.py" --action=loop-back --to=plan --reason="<one-line>"
```

Then re-run `/man plan` to revise the affected section. The state machine records the loop-back so the audit trail explains why the plan changed.

## Discipline rules (enforced by the agent contract)

The `coder` agent is bound by these rules. Violation = bug:

1. **One task at a time.** Don't bundle. Finish, mark done, await go-ahead.
2. **No comments explaining WHAT.** Names do that. Comments only for non-obvious WHY.
3. **No error handling for impossible cases.** Trust framework guarantees. Validate at boundaries only.
4. **No premature abstractions.** Three similar lines is better than a wrong abstraction.
5. **No "while I'm here" refactors.** Save those for a future plan.
6. **Mirror existing patterns.** The plan tells you which file/module sets the pattern. Copy that style.

## Quality gate (`code_to_test`)

Before `/man test` runs, the gate verifies:

- **Typecheck passes** — auto-detected per project (tsc, mypy, cargo check)
- **Lint passes** — auto-detected per project (eslint, ruff, clippy)
- **No TODO/FIXME in newly-changed files** — these are a smell that the task is incomplete
- **Every changed file is justified by a plan task** (verified at review stage, not here)

Skipped checks (e.g. typecheck when `tsc` not on PATH) are reported as `[OK] skipped — <reason>` rather than failing. The gate is forgiving about missing tooling, strict about real failures.

## When to leverage context-mode

If `context-mode` is installed (the orchestrator reports it via `--best-for=code`), prefer its sandboxed read tools when scanning large files. It returns only the relevant slices, saving ~98% of tokens vs reading the full file. The coder agent's system prompt already nudges this; this skill is the long-form rationale.

When `context-mode` is NOT installed, fall back to standard `Read`. Performance is just slightly worse — correctness is the same.

## Common mistakes

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| Gate fails with "typecheck: 50 errors" but only 1 was added | The previous baseline already had errors | Loop back to plan: add a "fix prior typecheck errors" task or accept the regression |
| Coder agent edits files not in any plan task | Scope creep | Revert the unwarranted changes; re-prompt the agent emphasizing the task scope |
| TODOs left in new code | Task was actually larger than estimated | Loop back to plan and split the task |
| Tests already exist for a task that hasn't been coded | Earlier feature shipped tests but coder reverted code | Run gate on the test files to identify what's missing |
