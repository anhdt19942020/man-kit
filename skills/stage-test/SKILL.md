---
name: stage-test
description: Reference for the man-kit Test stage. Use when judging whether a test suite is ready for review, identifying vacuous tests, or deciding when to push code back to the Code stage. Do NOT use to write tests directly — that is the tester sub-agent's job (see agents/tester.md).
---

# Test Stage Reference

The Test stage produces a suite that catches real bugs. A test that always passes is worse than no test — it lies about safety.

## What "good coverage" actually means

Line coverage is necessary but not sufficient. A 100%-line-covered codebase can still ship with broken behavior. Real coverage means:

| Layer | What gets tested |
|-------|------------------|
| **Happy path** | Expected input → expected output. The "obvious" case. |
| **Edge cases** | Null, undefined, empty array, empty string, boundary values (0, 1, max, max+1, negative, very large) |
| **Error paths** | Invalid input, dependency failure, timeout, partial state. The function must reject these correctly. |
| **State transitions** | Stateful units tested with realistic sequences, not isolated calls. |

Aim for **at least one edge case test per public function**. The gate enforces this through coverage % + skip detection, not by examining each test individually — but the tester agent's contract requires it.

## Vacuous tests — the cardinal sin

These shapes always pass and prove nothing. Reject any test that looks like:

```typescript
// ❌ Always passes
expect(true).toBe(true);

// ❌ Tests the mock, not the code
const mock = jest.fn().mockReturnValue(42);
expect(mock()).toBe(42);

// ❌ Snapshots the function's own output as the baseline
expect(myFn(input)).toMatchSnapshot();  // first run creates the snapshot — nothing was verified

// ❌ No assertion
it('does the thing', () => {
  myFn(input);  // if it throws the test fails, otherwise passes silently
});
```

If you see any of these in the suite, ask the tester agent to rewrite. Do not move to Review.

## Mutation discipline (the manual sample check)

For 1–2 tests in any newly-written batch, perform a mutation check:

1. Temporarily break the code the test claims to verify (flip a condition, return wrong value).
2. Run the test.
3. The test MUST fail. If it still passes, the test is wrong, not the code.
4. Restore the code.

This is not formal mutation testing (which requires tooling like Stryker / mutmut). It is a quick sanity check that the test actually exercises the behavior it claims to.

## Coverage threshold

Default: **80% line coverage** for new/changed files. Configurable via:

- `package.json` `jest`/`vitest` config `coverageThreshold`
- `pyproject.toml` `[tool.pytest]` `coverage` settings  
- A `.man-kit/config.json` file with `{"coverage_threshold": 0.85}` (overrides project config)

The gate is best-effort: if no coverage tool is detected, it skips the threshold check rather than failing. This keeps the loop unblocked when a project doesn't have coverage configured yet.

## When to push back to the Code stage

Sometimes writing tests reveals that the code is wrong, not just untested:

| Signal | Action |
|--------|--------|
| Function has unhandled `undefined` path | Push back: code needs a guard |
| Tests for the happy path can't be written without elaborate mocking | Push back: code has a hidden hard dependency that should be injectable |
| Edge cases break the implementation | Push back: code needs to handle them or contract explicitly forbids them |
| Cannot reach 80% without testing private internals | Discuss with user: private internals usually shouldn't be tested directly; surface might need exposure |

To loop back, the tester agent stops, reports findings, and tells the user to run `/man code` after fixing.

## Skip / only / xit detection

The gate fails on any of these in test files:

```typescript
it.skip(...)
describe.skip(...)
test.only(...)        // CI-poison: run only this test
xit(...)
xdescribe(...)
```

Reason: `.skip` hides a known-broken test (which is a lie about coverage). `.only` was committed accidentally and silently skips every other test in the file in CI.

If a test legitimately needs to be skipped (e.g., flaky on Windows, tracked in issue #X), document it via:

```typescript
// SKIP-REASON: flaky on Windows path separators, tracked in #234
it.skip('handles backslashes', ...)
```

The gate currently does not honor this comment in v1 — it always fails on `.skip`. v2 will allow opt-out via the comment marker.

## Integration with craftpowers:test-engineer

If the `craftpowers` plugin is installed (orchestrator reports it), prefer the `test-engineer` agent for coverage analysis and edge-case identification. It is tuned for this work. Otherwise the built-in `tester` agent (man-kit) does the same job at slightly lower fidelity.

## Common mistakes

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| Coverage drops after adding tests | Test infrastructure not configured to include new files | Update `coverageThreshold` paths / `pytest --cov` source |
| All tests pass but a real bug ships | Tests were vacuous | Run mutation sample on each new test |
| Gate fails on `.only` left in a single file | Forgot to clean up after debugging | Remove `.only`, run full suite |
| Tester agent generates 50 tests for a 10-line function | Coverage padding | Trim to meaningful tests; reject the rest |
