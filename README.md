# man-kit

A quality-first build loop for [Claude Code](https://claude.com/claude-code):
**`/man plan` → `/man code` → `/man test` → `/man review` → `/man done`**

Each transition is gated. You cannot reach `done` without earning it.

## Philosophy

> **Smart > Safe > Fast** — quality first, ship later.

man-kit is an **orchestrator**, not a re-implementation. It dispatches each stage to the best installed plugin (context-mode for context-window savings, craftpowers for review/test agents, code-review for official Anthropic review, etc.) and aggregates results behind one state machine. When no plugin is available, built-in sub-agents take over.

Five design rules:

1. **The state machine cannot be skipped.** No `/man test` until `/man code` passes its gate.
2. **Gates are hard blocks, not warnings.** A failing typecheck stops the loop until fixed.
3. **The plan is the contract.** Code, tests, and review all derive from `docs/PLAN-<slug>.md`.
4. **One feature at a time.** Parallel features arrive in v2, keyed by branch.
5. **Resumable across sessions.** State persists in `.man-kit/state.json`; the SessionStart hook reminds you where you left off.

## Quick start

### Minimal (man-kit only)

```sh
/plugin marketplace add anhdt19942020/man-kit
/plugin install man-kit@man-kit
```

### Recommended (man-kit + community plugins, one marketplace)

The `man-kit` marketplace lists man-kit plus three community plugins it composes with. After adding the marketplace once, install whichever you want:

```sh
/plugin marketplace add anhdt19942020/man-kit

/plugin install man-kit@man-kit
/plugin install context-mode@man-kit    # ~98% context-window savings (mksglu/context-mode)
/plugin install caveman@man-kit         # ~75% output token compression (JuliusBrussee/caveman)
/plugin install craftpowers@man-kit     # test/review/security sub-agents (anhdt19942020/craftpowers)
```

Each is independent. man-kit detects what's installed and dispatches accordingly; without these, built-in fallbacks run.

### Discover more plugins per stage

After install, ask man-kit which extra plugins (Anthropic-official + others) would help:

```sh
/man setup
```

It prints copy-pasteable `/plugin install` commands for missing recommended plugins, grouped by stage. Nothing auto-installs.

### Daily workflow

```sh
# 1. Start a feature
/man plan add OAuth login flow

# 2. After reviewing the generated docs/PLAN-oauth-login.md, build it
/man code     # implement one task at a time
/man test     # generate tests, run suite, gate on coverage
/man review   # aggregated quality + security verdict
/man done     # only allowed when review verdict = PASS

# At any point
/man status   # show current stage and what gate runs next
```

## What each stage does

| Stage | Agent | Model | Output | Gate |
|-------|-------|-------|--------|------|
| `plan` | `planner` | opus | `docs/PLAN-<slug>.md` | Required sections + size hints |
| `code` | `coder` | sonnet | Code files matching plan tasks | Typecheck + lint + no-TODO |
| `test` | `tester` | haiku | Test files | Tests pass + no skip/only + coverage |
| `review` | `reviewer` | sonnet | `.man-kit/reviews/<slug>.md` | Verdict = PASS |

Models are referenced by alias (`opus`, `sonnet`, `haiku`). To pin specific versions, set `ANTHROPIC_DEFAULT_*_MODEL` environment variables in your Claude Code settings.

## How the orchestrator works

When you run `/man review`, man-kit consults `hooks/orchestrator.py --best-for=review` to pick the best aggregator from what's installed:

```
review preference order: code-review → coderabbit → semgrep → aikido → craftpowers → builtin
```

It dispatches the matching agent/plugin, collects findings, dedupes across sources, applies a strict severity rubric, and writes a unified report. If none of those plugins are installed, the built-in `reviewer` agent runs solo.

## Quality gates

Each gate runs as a CLI script invoked inline by the slash command:

```sh
python "${CLAUDE_PLUGIN_ROOT}/hooks/quality-gate.py" --check=plan_to_code
```

| Gate | Checks |
|------|--------|
| `plan_to_code` | Plan file exists, has Goal/Success criteria/Risks/Tasks sections, every task has a Size hint |
| `code_to_test` | Typecheck passes (tsc/mypy/cargo check/go vet), Lint passes (eslint/ruff/clippy/golangci-lint), no TODO/FIXME in new files |
| `test_to_review` | Tests exist, no `.skip`/`.only`/`xit`/`@pytest.mark.skip`/`#[ignore]`, test suite passes, coverage ≥ threshold (best effort) |
| `review_to_done` | Review report exists at the path in state, contains `**Verdict**: PASS` |

When tooling isn't installed (no mypy, no eslint), the corresponding check is **skipped, not failed** — keeping the loop unblocked while still surfacing real issues when the tools are available.

## State machine

State persists in `.man-kit/state.json` per project. Schema in [`lib/state-schema.md`](lib/state-schema.md).

```
            (no state) ──▶ plan ──▶ code ──▶ test ──▶ review ──▶ done
                            ▲          ▲          ▲           │
                            └──────────┴──────────┴───────────┘
                                      loop back on FAIL
```

- Hyou cannot skip stages.
- You cannot move to `done` without `review` PASS.
- Loop-back from `review` → `code` (or → `plan`) is allowed and recorded in `user_overrides`.

## Configuration

Optional per-project overrides at `.man-kit/config.json`:

```json
{
  "coverage_threshold": 0.85
}
```

## Composes well with

man-kit detects which complementary plugins are installed and dispatches each stage to the best available. None are required — built-in fallbacks always work.

### Stage-aligned (auto-dispatched)

| Stage | Plugins man-kit will leverage if installed |
|-------|--------------------------------------------|
| `plan` | [feature-dev](https://claude.com/plugins/feature-dev), [superpowers](https://claude.com/plugins/superpowers), [sourcegraph](https://claude.com/plugins/sourcegraph), [context7](https://claude.com/plugins/context7), [craftpowers](https://github.com/anhdt19942020/craftpowers) |
| `code` | [context-mode](https://github.com/mksglu/context-mode), [sourcegraph](https://claude.com/plugins/sourcegraph), [context7](https://claude.com/plugins/context7), [frontend-design](https://claude.com/plugins/frontend-design), [code-simplifier](https://claude.com/plugins/code-simplifier), [craftpowers](https://github.com/anhdt19942020/craftpowers) |
| `test` | [craftpowers](https://github.com/anhdt19942020/craftpowers) (test-engineer agent) |
| `review` | [code-review](https://claude.com/plugins/code-review), [pr-review-toolkit](https://claude.com/plugins/pr-review-toolkit), [coderabbit](https://claude.com/plugins/coderabbit), [optibot](https://claude.com/plugins/optibot-code-review), [semgrep](https://claude.com/plugins/semgrep), [aikido](https://claude.com/plugins/aikido-security), [craftpowers](https://github.com/anhdt19942020/craftpowers) |

Order within each row reflects dispatch preference (most thorough first). The first installed wins; built-in agent runs if none are installed.

### Meta / adjacent (surfaced via `orchestrator --meta`, not auto-dispatched)

| Plugin | Role |
|--------|------|
| [sentry](https://claude.com/plugins/sentry) | Post-ship error monitoring (future `monitor` stage in v2) |
| [skill-creator](https://claude.com/plugins/skill-creator) | Author/improve skills outside the loop |
| [claude-md-management](https://claude.com/plugins/claude-md-management) | Post-`done` housekeeping for CLAUDE.md hygiene |
| [hookify](https://claude.com/plugins/hookify) | Generate custom hooks |
| [session-report](https://claude.com/plugins/session-report) | Token/cache analytics |
| [plugin-developer-toolkit](https://claude.com/plugins/plugin-developer-toolkit) | Plugin development tooling |

### Output compressors (cross-stage benefit)

| Plugin | Effect |
|--------|--------|
| [caveman](https://github.com/JuliusBrussee/caveman) | ~75% reduction in agent output tokens |
| [context-mode](https://github.com/mksglu/context-mode) | 98% reduction in code-reading tokens |

## Documentation

- [Architecture](docs/architecture.md) — state machine, orchestrator, hooks
- [Stage guide](docs/stages.md) — what to expect at each stage as a user
- [State schema](lib/state-schema.md) — `.man-kit/state.json` field reference
- [Review template](lib/review-template.md) — canonical review report shape
- [ADRs](docs/adr/) — major design decisions

## License

[MIT](LICENSE)
