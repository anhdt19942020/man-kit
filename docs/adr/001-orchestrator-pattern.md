# ADR-001: Orchestrator pattern over re-implementation

**Status**: Accepted
**Date**: 2026-05-06

## Context

The Claude Code plugin ecosystem already covers most quality checks man-kit cares about:

- `code-review` (Anthropic) and `coderabbit` for general code review
- `semgrep`, `aikido`, `secure-reviewer` for security
- `context-mode` for context-window optimization
- `context7` for live framework docs
- `craftpowers` for `code-reviewer`, `secure-reviewer`, `test-engineer` agents

A naive design would re-implement these inside man-kit so it works standalone. This was rejected.

## Decision

man-kit is an **orchestrator**. It does not re-implement code review, security scanning, or context optimization. Instead, it:

1. Detects which complementary plugins are installed (`hooks/orchestrator.py`)
2. Dispatches each stage to the best available plugin per `STAGE_PREFERENCE`
3. Falls back to a built-in sub-agent (`planner`/`coder`/`tester`/`reviewer`) when nothing better is installed

The result the user sees is identical regardless of installed plugins; only fidelity and token cost change.

## Consequences

**Pros**

- Composability: man-kit gets stronger as the ecosystem grows. New review plugins automatically slot in via `STAGE_PREFERENCE` updates.
- Smaller surface area: less code to maintain, less opportunity for our review logic to disagree with the official `code-review` plugin.
- Honest scope: we focus on the workflow (state machine + gates) where competing plugins don't exist, not on solving review/security ourselves.

**Cons**

- Built-in fallbacks are intentionally less capable than dedicated plugins. A user with no plugins installed gets a workable but lower-fidelity experience.
- We depend on stable plugin contracts. If `craftpowers` renames `code-reviewer`, we must update `KNOWN`.
- Detecting "best" plugin per stage is opinionated. The order in `STAGE_PREFERENCE` reflects current judgment and will need revision over time.

## Alternatives considered

**A. Re-implement everything internally.** Rejected: duplicates work, drifts in quality vs ecosystem, and forces man-kit to maintain reviews/security expertise it shouldn't own.

**B. Hard-require specific plugins.** Rejected: makes man-kit unusable on a clean install; punishes users who haven't yet adopted the ecosystem.

**C. Detect-only, no fallback.** Rejected: leaves users stranded the first time they run `/man review` without any review plugin installed.

The chosen approach (detect → dispatch → fallback) keeps the floor reasonable and lets the ceiling rise as the ecosystem matures.
