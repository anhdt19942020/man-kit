# ADR-003: Quality gates are hard blocks, not warnings

**Status**: Accepted
**Date**: 2026-05-06

## Context

A common pattern in dev workflows is to run quality checks but allow override (`--no-verify`, "skip and proceed", "I'll fix it later"). The argument is usability: a strict gate blocks legitimate edge cases and trains users to disable the check entirely.

man-kit could have followed this pattern. Each stage transition would print warnings but allow `/man code --force` to proceed.

We rejected this for v1.

## Decision

Quality gates are **hard blocks**:

- A failing typecheck halts the loop. You fix the typecheck or you do not advance.
- A failing test halts the loop. You fix the test (or the code) or you do not advance.
- A non-PASS review verdict halts the loop. You address the findings or you do not mark the feature done.

There is no `--force` or `--skip-gate` flag in v1. The only escape hatch is editing `.man-kit/state.json` by hand, and the schema is plain JSON specifically so users CAN do that when truly needed.

## Why

man-kit's philosophy is **Smart > Safe > Fast** (see README). The gates are how that philosophy gets enforced. A workflow that warns but doesn't block fails to enforce anything — it merely surfaces information the user could already get from running `tsc` and `pytest` themselves.

Concretely:

- **Friction is the point.** `/man test` is annoying when tests fail. That annoyance is the user discovering, in the loop, that the work isn't done. Allowing override deletes the signal.
- **Loops are cheap.** Looping back from `review` → `code` is one command and the state machine logs the reason. The cost of "redo a stage" is much lower than the cost of "ship a feature with a known bug because the gate was warning-only."
- **Hard blocks make the contract clear.** Users learn quickly that the gates mean what they say. Soft gates produce ambiguity ("did the warning matter? Should I have stopped?").

## Consequences

**Pros**

- The loop's outcome is high-confidence by construction. If a feature reaches `done`, every gate signed off.
- No `--force` button to be pressed reflexively. Real overrides require deliberate action (hand-editing state).
- Aligns with the `Smart > Safe > Fast` priority order: speed yields when quality is at stake.

**Cons**

- Genuine edge cases (a single legitimately-skipped test, a known-acceptable lint rule) require workarounds: reconfigure the linter, document the skip, or hand-edit state.
- New users may be frustrated if they don't read the docs first and discover the loop refuses to advance.
- The "gates are forgiving when tooling is missing" exception (see ADR not yet written for forgiveness rule) creates a small inconsistency: missing `mypy` is forgiven, but `mypy` reporting an error is not.

## Alternatives considered

**A. Soft gates with `/man code --force`.** Rejected per the Decision rationale.

**B. Tiered gates: HIGH blocks, MEDIUM warns.** Considered for v2 (specifically for the review stage where CONCERNS verdict already implies MEDIUM-only). v1 keeps the model uniform: any gate failure is a block.

**C. Per-project configurable strictness.** Rejected for v1 to keep the contract obvious. v2 may allow `.man-kit/config.json` to relax specific checks (e.g., `coverage_threshold: 0.0` to disable coverage), but the override is per-check, not blanket.

## Operational notes

When users complain that the gate is too strict for their case, the right response is usually one of:

1. **Fix the underlying problem.** Most "this is too strict" gates are surfacing real issues.
2. **Configure the project's tooling.** A noisy lint rule should be silenced in `eslint.config.js`, not man-kit.
3. **Loop back.** A failing review verdict means returning to `code` is the correct move, not bypassing review.

If someone needs an override for a legitimately exceptional case, they edit `state.json` and document why in the commit message. v2 will add structured overrides for the `review` stage's CONCERNS verdict; other gates remain hard blocks.
