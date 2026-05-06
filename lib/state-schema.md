# State Schema — `.man-kit/state.json`

man-kit persists per-project state at `.man-kit/state.json` in the project root (the directory where Claude Code was opened). The state machine in `hooks/stage-tracker.py` reads/writes this file. Quality gates in `hooks/quality-gate.py` use it to enforce stage transitions.

## File location

```
<project-root>/.man-kit/state.json
```

`.man-kit/` is intended to be checked into version control if the team wants stage state shared, or `.gitignore`d for personal-only use. man-kit does not enforce either choice.

## Schema (v1)

```json
{
  "schema_version": 1,
  "feature": "<slug>",
  "current_stage": "plan | code | test | review | done",
  "stages_completed": ["plan", "code"],
  "artifacts": {
    "plan": "docs/PLAN-<slug>.md",
    "code_files": ["src/auth/login.ts"],
    "test_files": ["src/auth/login.test.ts"],
    "review_report": ".man-kit/reviews/<slug>.md"
  },
  "gate_results": {
    "plan_to_code": {"passed": true, "checked_at": "ISO-8601", "failures": []},
    "code_to_test": {"passed": false, "checked_at": "ISO-8601", "failures": ["lint"]},
    "test_to_review": null,
    "review_to_done": null
  },
  "user_overrides": {
    "skip_gate_lint": {"reason": "legacy file, lint disabled by maintainer", "at": "ISO-8601"}
  },
  "started_at": "ISO-8601",
  "last_updated": "ISO-8601"
}
```

## Field definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | int | yes | Bump when schema changes incompatibly. Migrations live in `stage-tracker.py`. |
| `feature` | string | yes | The slug used in plan filename. Lowercase, hyphenated, ≤30 chars. |
| `current_stage` | enum | yes | One of `plan`, `code`, `test`, `review`, `done`. |
| `stages_completed` | array | yes | Stages whose gate passed. Append-only during a feature. |
| `artifacts.plan` | string | after Stage 1 | Path to the plan markdown file. |
| `artifacts.code_files` | array | after Stage 2 | Files touched in Stage 2. |
| `artifacts.test_files` | array | after Stage 3 | Test files added/modified. |
| `artifacts.review_report` | string | after Stage 4 | Path to the review report. |
| `gate_results.<transition>` | object \| null | yes | Last gate-check result for each transition. `null` if not yet attempted. |
| `gate_results.<transition>.passed` | bool | yes | Whether the gate passed last time. |
| `gate_results.<transition>.failures` | array | yes | Failed check names (for diagnostics). |
| `user_overrides` | object | optional | Explicit gate skips. Keyed by `skip_gate_<check>`. Each must include a `reason`. |
| `started_at` | ISO-8601 | yes | When state was first created for this feature. |
| `last_updated` | ISO-8601 | yes | Last write to this file. |

## Valid transitions

```
(no state) ──▶ plan ──▶ code ──▶ test ──▶ review ──▶ done
                ▲           ▲          ▲           │
                └───────────┴──────────┴───────────┘  (loop back on FAIL)
```

Allowed transitions:

| From | To | Gate |
|------|-----|------|
| (none) | plan | none — `/man plan` initializes state |
| plan | code | `plan_to_code` |
| code | test | `code_to_test` |
| test | review | `test_to_review` |
| review | done | `review_to_done` (only on PASS) |
| review | code | loop back on review FAIL — gate auto-passed, `code_files` is preserved |
| review | plan | loop back on review FAIL when plan was wrong |

Disallowed transitions (state machine rejects):

- Skipping stages (e.g., plan → test directly)
- Going backward without a FAIL signal
- Moving to `done` without `review` PASS

## Recovery

If `state.json` is corrupted or schema is from a future version:

1. `stage-tracker.py --action=validate` reports diagnostics without modifying.
2. `stage-tracker.py --action=recover` creates `.man-kit/state.json.bak`, then writes a minimal new state asking the user to confirm `feature` and `current_stage`.
3. User can edit `.man-kit/state.json` by hand. The schema is plain JSON; no obfuscation.

## Multiple features

v1 supports **one active feature at a time** per project. `.man-kit/history/` archives completed features as `<slug>-<timestamp>.json`. Starting a new `/man plan` while another feature is mid-flight prompts the user: archive current state, or discard.

v2 will support parallel features keyed by branch name.

## What state.json is NOT

- Not a build cache. man-kit does not store compile/test artifacts here.
- Not a secret store. Never write tokens, credentials, or PII.
- Not authoritative truth about the codebase. The codebase is. State is bookkeeping.
