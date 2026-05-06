# ADR-002: Per-stage model selection via aliases

**Status**: Accepted
**Date**: 2026-05-06

## Context

Each man-kit stage has different cost/capability requirements:

| Stage | Workload | Reasoning depth |
|-------|----------|-----------------|
| Plan | Architecture, risk analysis, codebase scan | Deep |
| Code | Implement task per plan | Moderate |
| Test | Mechanical edge-case generation | Shallow |
| Review | Cross-file analysis, severity discipline | Moderate |

Running every stage on Opus is wasteful — test generation is a high-volume, low-complexity task that Haiku handles well. Running every stage on Haiku produces low-fidelity plans and shallow reviews.

We also can't pin specific model versions in agent files; model IDs change (`claude-opus-4-6` → `claude-opus-4-7`) and a plugin shouldn't need updating each time.

## Decision

Each agent's frontmatter declares a model **alias**, not a full ID:

```yaml
# agents/planner.md
model: opus

# agents/coder.md
model: sonnet

# agents/tester.md
model: haiku

# agents/reviewer.md
model: sonnet
```

The alias resolves through Claude Code's environment variables:

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | What `opus` resolves to |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | What `sonnet` resolves to |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | What `haiku` resolves to |

Users pin specific versions in their personal `~/.claude/settings.json`:

```json
{
  "env": {
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-4-7",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-6",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-4-5-20251001"
  }
}
```

If unset, aliases fall back to whatever Claude Code's default is.

## Consequences

**Pros**

- Plugin updates don't churn: a new opus version means user changes one env var, not every agent file.
- Cost discipline: each stage runs on the cheapest model that meets its bar.
- Personal calibration: a user who wants Sonnet for everything sets all three aliases to Sonnet.

**Cons**

- Self-reporting agents (when asked "what model are you?") often answer wrong. Verifying actual model in use requires the API/billing dashboard, not asking the agent.
- The alias resolution is opaque to plugin users — if they don't read this ADR or the README, they may wonder why the planner is sometimes "smarter" than expected.
- A user with `ANTHROPIC_DEFAULT_OPUS_MODEL=claude-haiku-4-5-...` (intentionally or accidentally) will silently demote the planner. Hard to detect from inside the plugin.

## Alternatives considered

**A. Hard-code full model IDs in agent frontmatter.** Rejected: requires plugin update on every model release, and doesn't let individual users override (e.g., "I want Sonnet for everything because I'm cost-constrained").

**B. Single shared model across all stages.** Rejected per the cost/quality argument above.

**C. Let users configure model per agent via `.man-kit/config.json`.** Considered for v2. v1 piggybacks on Claude Code's existing alias mechanism rather than introducing a parallel one.

## Operational notes

When this plugin ships, the README should remind users to set `ANTHROPIC_DEFAULT_*_MODEL` for predictable behavior. Without setting them, the user gets Claude Code's defaults — usually fine, but the planner may run on Sonnet rather than Opus, with no obvious signal.
