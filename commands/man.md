---
description: |
  man-kit build loop dispatcher. Subcommands: plan, code, test, review, done, status.
  Examples: /man plan add OAuth login | /man code | /man test | /man review | /man status
argument-hint: <plan|code|test|review|done|status> [args]
---

# /man — man-kit Build Loop

The user invoked `/man $ARGUMENTS`. Parse the input and execute the matching subcommand. Be terse with the user — they already know the workflow.

## Step 1 — Parse subcommand

Take the first word of `$ARGUMENTS` as `<subcommand>`. The rest is `<rest>`.

If `$ARGUMENTS` is empty or `<subcommand>` is `status`, run **2A**. Otherwise jump to the matching step.

If `<subcommand>` is anything other than `plan|code|test|review|done|status`, reply with the valid list and STOP.

## 2A — `status`

Run:

```bash
python "${CLAUDE_PLUGIN_ROOT}/hooks/stage-tracker.py" --action=validate
```

If `.man-kit/state.json` exists and is valid, also `cat` the file and report:
- Active feature
- Current stage
- Stages completed
- Next gate to run (`<current_stage>_to_<next_stage>`)

Report concisely. Do not dispatch any agent.

## 2B — `plan <feature description>`

1. If `<rest>` is empty → ask the user for a one-line feature description and STOP.
2. Generate slug from `<rest>`: lowercase, 2–3 keywords, hyphenated, ≤30 chars. Example: `"add OAuth login"` → `oauth-login`.
3. Run:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/hooks/stage-tracker.py" --action=init --feature=<slug>
   ```
   - Exit 2 means a feature is mid-flight. Tell the user, list it, STOP.
4. Dispatch the **planner** sub-agent (subagent_type=`planner`). Pass the user's request verbatim plus this guidance: "Produce `docs/PLAN-<slug>.md` per your contract. Do not modify any other files."
5. Run the gate:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/hooks/quality-gate.py" --check=plan_to_code
   ```
6. Report PASS / FAIL with the gate's findings.
7. **Do not auto-advance state.** Tell the user: "Plan ready. Review `docs/PLAN-<slug>.md`. Run `/man code` when ready."

## 2C — `code`

1. Run gate `plan_to_code`. If exit 2 → report findings, do NOT advance, STOP.
2. Run:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/hooks/stage-tracker.py" --action=advance --to=code --gate-passed=true
   ```
3. Read `.man-kit/state.json` to get the feature slug, then read `docs/PLAN-<slug>.md` to identify the next un-implemented task. (Track which tasks are done in the plan's checklist or via state's `code_files`.)
4. Dispatch the **coder** sub-agent with: "Plan: `docs/PLAN-<slug>.md`. Next task: `<task title>`. Implement only that task per your contract. Report changed files."
5. Append the changed files to state's `artifacts.code_files` (re-write `.man-kit/state.json`).
6. Tell the user the task is done and which task is next, or if all plan tasks are implemented prompt them to run `/man test`.

## 2D — `test`

1. Run gate `code_to_test`. Exit 2 → report findings, STOP.
2. Advance state: `--to=test --gate-passed=true`.
3. Dispatch the **tester** sub-agent with: "Cover the files listed in state.artifacts.code_files. Follow your contract: happy path + edge + error paths, no vacuous tests."
4. Append test files written to state's `artifacts.test_files`.
5. Tell user to run `/man review` when ready.

## 2E — `review`

1. Run gate `test_to_review`. Exit 2 → report findings, STOP.
2. Advance state: `--to=review --gate-passed=true`.
3. Make sure `.man-kit/reviews/` exists. Dispatch the **reviewer** sub-agent with: "Audit the feature per your contract. Write the report to `.man-kit/reviews/<slug>.md` with a `**Verdict**: PASS|CONCERNS|FAIL` line."
4. Update state's `artifacts.review_report` to the report path.
5. Show the user the verdict + summary. If FAIL, suggest `/man code` (loop back) and tell them which findings to address.

## 2F — `done`

1. Run gate `review_to_done`. Exit 2 → report verdict was not PASS, STOP.
2. Advance state: `--to=done --gate-passed=true`. (This appends `review` to stages_completed and sets current_stage=done.)
3. Tell the user the feature is complete. Suggest the next step (commit, push, open PR — but do NOT run those commands; they belong to a future stage).

## Notes

- Always report gate findings verbatim when a gate fails. The user needs to know what to fix.
- Never silently skip a gate. If the user wants to override, they must say so explicitly and you record the override in state.
- All agent dispatches use the `Agent` tool with the matching `subagent_type`.
- The orchestrator helper at `${CLAUDE_PLUGIN_ROOT}/hooks/orchestrator.py --best-for=<stage>` reports the best-installed plugin per stage — you may consult it inside the agent prompt to suggest which third-party plugin to leverage, but never make availability of a plugin a hard requirement (built-in agents are the fallback).
