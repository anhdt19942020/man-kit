---
name: stage-plan
description: Reference for the man-kit Plan stage. Use when interpreting docs/PLAN-*.md files, deciding whether a plan is ready for the Code stage, or troubleshooting why /man plan rejected a draft. Do NOT use this to write the plan itself — that is the planner sub-agent's job (see agents/planner.md).
---

# Plan Stage Reference

The Plan stage turns a vague feature request into an executable specification. The plan file is the single source of truth that all later stages reference.

## What a good plan looks like

A plan that passes the `plan_to_code` gate has these properties:

1. **Goal section** — 1–2 sentences naming the user-visible change. Not a list of tasks. Not architecture.
2. **Success criteria** — measurable outcomes, not adjectives. "User can log in with Google and the session persists for 7 days" beats "Login works well".
3. **Technical risks** — at minimum, one risk named with mitigation. If the author truly believes there are no risks, the section reads `- None significant. Reasoning: <one sentence>.`
4. **Existing patterns** — references to real files/modules in this repo. The plan must show the planner read the codebase.
5. **Tasks** — each ≤1 day of dev work, sized **S** (hours), **M** (half day), or **L** (full day). Larger than L → split.
6. **Out of scope** — explicit list. Prevents scope creep in the Code stage.

## When a plan is NOT ready

Reject the plan and ask for revision when:

- A task description starts with "Refactor X" with no concrete change defined.
- Success criteria contain words like "good", "clean", "fast" without a number.
- Technical risks section is missing or contains the literal phrase "no risks" with no reasoning.
- Tasks reference files that don't exist in this repo (and aren't being created by an earlier task).
- The plan has > 10 tasks of size L. That is a multi-week project, not a v1 plan — break into multiple smaller plans.

## Plan file location & naming

Always `docs/PLAN-<slug>.md` where slug is 2-3 lowercase hyphenated words from the feature description, ≤30 chars.

| Request | Slug | File |
|---------|------|------|
| `add OAuth login` | `oauth-login` | `docs/PLAN-oauth-login.md` |
| `make the dashboard load faster` | `dashboard-perf` | `docs/PLAN-dashboard-perf.md` |
| `fix race condition in cart sync` | `cart-sync-race` | `docs/PLAN-cart-sync-race.md` |

## Common mistakes (caught by the gate)

| Mistake | What the gate sees | Fix |
|---------|--------------------|-----|
| Forgot a section | `plan_sections` fails with the missing names | Add the section, even if short |
| Tasks have no Size hints | `task_size_hints` fails | Append `Size: S` / `M` / `L` to each task |
| Plan file in wrong place | `plan_file_exists` fails | Move/rename to `docs/PLAN-<slug>.md` |

## When the plan stage is wrong

Sometimes the Code stage reveals the plan was wrong (a task is impossible as described, an assumed pattern doesn't exist). Do NOT ad-hoc edit the plan during Code. Instead:

1. Stop the Code work.
2. Loop back: `python hooks/stage-tracker.py --action=loop-back --to=plan --reason="<one line>"`.
3. Re-run `/man plan` to revise the affected section.

The state machine records the loop-back so future you (or your reviewer) can see the plan evolved with reason.
