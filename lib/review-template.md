# Review report template

The `reviewer` agent must produce a file at `.man-kit/reviews/<slug>.md` matching this exact structure. The `review_to_done` gate parses the `**Verdict**:` line — keep that string literal.

```markdown
# Review — <feature slug>

**Verdict**: PASS | CONCERNS | FAIL

## Summary
<1–2 sentences. Plain English. No hedge words.>

## HIGH severity (must fix)
- `path/to/file.ext:LINE` — <finding>. Why it matters: <impact>. (source: <specialist or "inline">)

## MEDIUM severity (should fix or document)
- `path/to/file.ext:LINE` — <finding>. Why it matters: <impact>. (source: <specialist>)

## LOW severity (optional)
- `path/to/file.ext:LINE` — <finding>. (source: <specialist>)

## Plan adherence

| Check | Result |
|-------|--------|
| Tasks delivered | N of M |
| Files changed not in plan | <list, or "none"> |
| Plan tasks not implemented | <list, or "none"> |

## Specialist reviews

| Specialist | Verdict | Notes |
|-----------|---------|-------|
| code-reviewer (craftpowers) | PASS / CONCERNS / FAIL / not available | <one line> |
| secure-reviewer (craftpowers) | PASS / CONCERNS / FAIL / not available | <one line> |
| code-review (Anthropic) | PASS / CONCERNS / FAIL / not available | <one line> |
| <other if installed> | … | … |

## Override (only if Verdict was CONCERNS but is being shipped)

Each MEDIUM finding above must have a corresponding line here with a reason:

- `path/file.ext:LINE` — accepted because <reason>. Tracked in <issue-link or "none">.

If this section is empty and Verdict is not PASS, the gate will FAIL.
```

## Filling in the template — rules for the reviewer agent

1. **Section presence is mandatory.** Even when empty, write the heading and one of: `- (none)`, `<list, or "none">`, `not available`. Empty sections without a placeholder will be flagged as malformed.
2. **One finding per bullet.** Do not bundle multiple issues. Severity must be unambiguous per bullet.
3. **Citations are mandatory.** `path:line` for every code finding. If line number is meaningless (e.g., architectural concern), use `path::function-or-class-name`.
4. **Never invent severity to look thorough.** If everything is fine, the only filled section is "Summary" + "Specialist reviews" with all PASS. The other severity sections each show `- (none)`.
5. **Dedupe across specialists.** If `secure-reviewer` and `coderabbit` both flag the same line, write one bullet citing both: `(source: secure-reviewer, coderabbit)`.

## What the gate enforces

`hooks/quality-gate.py --check=review_to_done` parses the file and checks:

- File exists at the path stored in `state.artifacts.review_report`
- Contains a `**Verdict**:` line with one of `PASS|CONCERNS|FAIL`
- Verdict is `PASS` (the only verdict the gate accepts in v1)

It does not validate severity counts, citations, or section completeness — those are the reviewer agent's contract, not the gate's. The agent gets the high-fidelity validation via its own self-check rules; the gate is a coarse safety net.
