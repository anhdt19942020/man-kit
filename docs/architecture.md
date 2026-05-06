# Architecture

man-kit has three concerns: **state**, **gates**, and **dispatch**. Each lives in its own module so the others can be swapped without rippling.

## Components at a glance

```
                                   ┌──────────────────────────────────┐
        user types /man <subcmd>   │  commands/man.md  (dispatcher)   │
                ───────────────▶   └──────────────┬───────────────────┘
                                                  │
                          ┌───────────────────────┼───────────────────────┐
                          ▼                       ▼                       ▼
                ┌──────────────────┐  ┌─────────────────────┐  ┌──────────────────┐
                │ stage-tracker.py │  │   quality-gate.py   │  │ orchestrator.py  │
                │  (state machine) │  │  (gate enforcement) │  │ (plugin lookup)  │
                └────────┬─────────┘  └──────────┬──────────┘  └────────┬─────────┘
                         │                       │                      │
                         ▼                       ▼                      ▼
                .man-kit/state.json      docs/PLAN-*.md            ~/.claude/
                                         tests/, src/                settings.json
                                         .man-kit/reviews/
                                                  │
                                                  ▼
                                  ┌─────────────────────────────────┐
                                  │       Agent dispatch via         │
                                  │  Agent(subagent_type=<role>)     │
                                  │  → planner / coder / tester /    │
                                  │    reviewer                      │
                                  └─────────────────────────────────┘
```

## state — `hooks/stage-tracker.py`

The state machine is intentionally a single file with no dependencies beyond the Python stdlib. It manages `.man-kit/state.json` and rejects illegal transitions.

### Allowed transitions

```
(no state) ──▶ plan ──▶ code ──▶ test ──▶ review ──▶ done
                  ▲         ▲          ▲              │
                  └─────────┴──────────┴──────────────┘ (loop-back from review)
```

Encoded in `TRANSITIONS`:

```python
TRANSITIONS = {
    None: ("plan",),
    "plan": ("code",),
    "code": ("test",),
    "test": ("review",),
    "review": ("done", "code", "plan"),
    "done": (),
}
```

Any other `--action=advance --to=X` returns exit 2.

### Why one file at a time?

A team-wide `state.json` checked into the repo introduces merge conflicts on any concurrent feature work. v1 holds one feature per project and archives the rest under `.man-kit/history/`. v2 will key state by branch name, so each branch carries its own state and merges to main only after `done`.

### Schema versioning

`schema_version: 1` is checked on load. When v2 ships, the loader runs a migration block before reading; misaligned schemas are reported via `--action=validate` rather than silently mangled.

## gates — `hooks/quality-gate.py`

Each transition has a corresponding gate function:

| Transition | Function | Checks |
|------------|----------|--------|
| `plan_to_code` | `gate_plan_to_code` | `plan_file_exists`, `plan_sections`, `task_size_hints` |
| `code_to_test` | `gate_code_to_test` | `typecheck_*`, `lint_*`, `no_todo_in_new_code` |
| `test_to_review` | `gate_test_to_review` | `tests_exist`, `no_skip_or_only`, `tests_pass_*`, `coverage_threshold` |
| `review_to_done` | `gate_review_to_done` | `review_report_exists`, `verdict_present`, `verdict_acceptable` |

### Forgiveness over false positives

Each language-specific check (typecheck, lint, coverage) records `passed: True, detail: "skipped - <tool> not installed"` when its tool is missing. This keeps the loop usable on stripped-down dev machines. **Tooling absent ≠ check failed.** Real failures (typecheck error, broken test, missing plan section) are still hard blocks.

### Gate output shape

Two streams:

- **Stdout** — human-readable report with `[OK]` / `[!! ]` markers and detail lines.
- **Stderr** — single JSON line for tooling: `{"check": "...", "passed": bool, "findings": [...]}`.

The slash command pipes stdout to the user and parses the stderr JSON when it needs the structured result.

### Why CLI, not PreToolUse hook?

Slash commands don't trigger `PreToolUse/Bash` hooks (they aren't bash commands). Wiring quality-gate as a hook would catch `git commit` but miss `/man test`. We invoke the gate inline from the slash command, which executes deterministically before the agent dispatch.

## dispatch — `hooks/orchestrator.py`

A pure-detection module. Reads `enabledPlugins` from settings.json files (user, project, local) and reports what's installed.

```python
KNOWN = {
    "context-mode": [...],
    "context7": [...],
    "code-review": [...],
    ...
}
STAGE_PREFERENCE = {
    "plan":   ["superpowers", "context7", "craftpowers"],
    "code":   ["context-mode", "context7", "frontend-design", ...],
    "test":   ["craftpowers"],
    "review": ["code-review", "coderabbit", "semgrep", "aikido", "craftpowers"],
}
```

The orchestrator has zero side effects. It does not install, configure, or talk to plugins. It only reports which one is the best fit per stage so the slash command (and the agent it dispatches) can compose with whatever the user has.

When nothing is installed for a stage, `--best-for=<stage>` returns `builtin`. The man.md dispatcher treats this as "use the built-in agent without trying to delegate."

## Hook timing

| Event | Script | Purpose |
|-------|--------|---------|
| `SessionStart` (startup, resume) | `stage-tracker.py --action=load` | Inject "Active feature: X, stage: Y" reminder into model context |
| `UserPromptSubmit` | `stage-tracker.py --action=announce` | Silent in v1; reserved for future nudges (e.g., "you're in code stage but no plan task is selected") |

There is **no** PreToolUse or PostToolUse hook in v1. Quality gates are explicit, called by the slash command. This keeps the cost ledger predictable: hooks cost tokens whenever the matched event fires, even when there's nothing to do.

## File-layout rationale

| Folder | Why it exists separately |
|--------|--------------------------|
| `commands/` | Slash command surface; one file per user-facing entry point |
| `agents/` | Sub-agent definitions; loaded by Claude Code and dispatched via `Agent` tool |
| `skills/` | Long-form behavioral references; auto-included when descriptions match context |
| `hooks/` | Python scripts called by the harness or by slash commands; no Claude Code-specific format |
| `lib/` | Documentation that other parts of the plugin reference (state schema, review template) |
| `docs/` | Long-form docs and ADRs for human readers |

A skill file describing review behavior lives in `skills/stage-review/SKILL.md`. A user-facing doc explaining how to run review lives in `docs/stages.md`. They are intentionally distinct: skills shape agent behavior, docs explain to humans how to drive the system.

## Extension points

When v2 happens, the changes are likely:

- `STAGE_PREFERENCE` gets new entries when new plugins ship in the ecosystem.
- `quality-gate.py` grows new `gate_*` functions for added stages (`scaffold`, `security`, `ship`, `monitor`).
- `stage-tracker.py` adds branch-keyed state to lift the one-feature-at-a-time limit.
- `commands/man.md` adds new subcommands but the dispatch shape stays unchanged.

The state file's `schema_version` field is the seam that lets v2 read v1 state without breaking existing in-flight features.
