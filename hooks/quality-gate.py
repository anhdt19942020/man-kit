#!/usr/bin/env python3
"""
man-kit quality gate — validates a stage transition.

Called inline from slash commands (`/man code`, `/man test`, etc.) BEFORE the
slash command does any real work. Returns exit code 0 if the gate passes, 2 if
it blocks the transition. Findings are printed to stdout as a human-readable
report and to stderr as a JSON line for tooling.

Usage:
  python quality-gate.py --check=plan_to_code
  python quality-gate.py --check=code_to_test
  python quality-gate.py --check=test_to_review
  python quality-gate.py --check=review_to_done
  python quality-gate.py --check=all          # Run the gate for the current stage's outgoing transition

The script is intentionally lenient: when the project type can't be determined
(no tsconfig, no pyproject, etc.) the gate logs a "skipped" check rather than
failing. v1 priority is a working flow; deeper enforcement comes in v2.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

GATES = ("plan_to_code", "code_to_test", "test_to_review", "review_to_done")


# ---------- Helpers ----------


def project_root() -> Path:
    return Path.cwd()


def state_file() -> Path:
    return project_root() / ".man-kit" / "state.json"


def load_state() -> dict[str, Any] | None:
    p = state_file()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def file_globs_exist(*globs: str) -> bool:
    return any(project_root().glob(g) for g in globs)


def run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    """Run a command; return (exit_code, combined_output). Never raise."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except FileNotFoundError:
        return 127, f"binary not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except Exception as e:  # broad catch — gates must never crash the slash command
        return 1, f"unexpected: {e}"


# ---------- Per-gate checks ----------


def gate_plan_to_code(state: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    feature = state.get("feature", "")
    plan_path = project_root() / "docs" / f"PLAN-{feature}.md"

    if not plan_path.exists():
        findings.append({"check": "plan_file_exists", "passed": False,
                         "detail": f"Expected {plan_path.relative_to(project_root())} to exist."})
        return False, findings

    text = plan_path.read_text(encoding="utf-8")
    required = ["## Goal", "## Success criteria", "## Technical risks", "## Tasks"]
    missing = [s for s in required if s not in text]
    if missing:
        findings.append({"check": "plan_sections", "passed": False,
                         "detail": f"Missing required sections: {missing}"})
    else:
        findings.append({"check": "plan_sections", "passed": True})

    # Tasks must each carry a size hint (S/M/L) per the planner agent's contract.
    tasks_block = text.split("## Tasks", 1)[-1]
    has_size = bool(re.search(r"Size:\s*[SML]", tasks_block))
    findings.append({
        "check": "task_size_hints",
        "passed": has_size,
        "detail": "Each task should declare Size: S/M/L (per planner contract)" if not has_size else "",
    })

    passed = all(f["passed"] for f in findings)
    return passed, findings


def _detect_project_type(root: Path) -> str:
    if (root / "tsconfig.json").exists() or (root / "package.json").exists():
        return "ts"
    if (root / "pyproject.toml").exists() or list(root.glob("*.py")):
        return "py"
    if (root / "Cargo.toml").exists():
        return "rust"
    if (root / "go.mod").exists():
        return "go"
    return "unknown"


def _typecheck(root: Path, kind: str) -> dict[str, Any]:
    if kind == "ts":
        if shutil.which("tsc") or (root / "node_modules" / ".bin" / "tsc").exists():
            tsc = "tsc" if shutil.which("tsc") else str(root / "node_modules" / ".bin" / "tsc")
            code, out = run([tsc, "--noEmit"], timeout=120)
            return {"check": "typecheck_typescript", "passed": code == 0,
                    "detail": "" if code == 0 else _truncate(out, 600)}
        return {"check": "typecheck_typescript", "passed": True, "detail": "skipped - tsc not on PATH"}
    if kind == "py":
        if shutil.which("mypy"):
            code, out = run(["mypy", str(root)], timeout=120)
            return {"check": "typecheck_python", "passed": code == 0,
                    "detail": "" if code == 0 else _truncate(out, 600)}
        return {"check": "typecheck_python", "passed": True, "detail": "skipped - mypy not installed"}
    if kind == "rust":
        code, out = run(["cargo", "check"], timeout=180)
        return {"check": "typecheck_rust", "passed": code == 0,
                "detail": "" if code == 0 else _truncate(out, 600)}
    if kind == "go":
        code, out = run(["go", "vet", "./..."], timeout=120)
        return {"check": "typecheck_go", "passed": code == 0,
                "detail": "" if code == 0 else _truncate(out, 600)}
    return {"check": "typecheck", "passed": True, "detail": "skipped - project type not detected"}


def _lint(root: Path, kind: str) -> dict[str, Any]:
    if kind == "ts":
        if shutil.which("eslint") or (root / "node_modules" / ".bin" / "eslint").exists():
            eslint = "eslint" if shutil.which("eslint") else str(root / "node_modules" / ".bin" / "eslint")
            code, out = run([eslint, ".", "--max-warnings=0"], timeout=120)
            return {"check": "lint_eslint", "passed": code == 0,
                    "detail": "" if code == 0 else _truncate(out, 600)}
        return {"check": "lint_eslint", "passed": True, "detail": "skipped - eslint not on PATH"}
    if kind == "py":
        if shutil.which("ruff"):
            code, out = run(["ruff", "check", str(root)], timeout=60)
            return {"check": "lint_ruff", "passed": code == 0,
                    "detail": "" if code == 0 else _truncate(out, 600)}
        return {"check": "lint_ruff", "passed": True, "detail": "skipped - ruff not installed"}
    if kind == "rust":
        code, out = run(["cargo", "clippy", "--", "-D", "warnings"], timeout=180)
        return {"check": "lint_clippy", "passed": code == 0,
                "detail": "" if code == 0 else _truncate(out, 600)}
    if kind == "go":
        if shutil.which("golangci-lint"):
            code, out = run(["golangci-lint", "run"], timeout=120)
            return {"check": "lint_golangci", "passed": code == 0,
                    "detail": "" if code == 0 else _truncate(out, 600)}
        return {"check": "lint_golangci", "passed": True, "detail": "skipped - golangci-lint not installed"}
    return {"check": "lint", "passed": True, "detail": "skipped - project type not detected"}


def gate_code_to_test(state: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    root = project_root()

    kind = _detect_project_type(root)
    findings.append(_typecheck(root, kind))
    findings.append(_lint(root, kind))

    # Forbid TODO/FIXME in newly added code (best effort: search code_files from state).
    new_files = state.get("artifacts", {}).get("code_files") or []
    todo_offenders = []
    for f in new_files:
        p = root / f
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if re.search(r"\b(TODO|FIXME)\b", line):
                todo_offenders.append(f"{f}:{i}")
    findings.append({
        "check": "no_todo_in_new_code",
        "passed": not todo_offenders,
        "detail": ", ".join(todo_offenders[:5]) if todo_offenders else "",
    })

    passed = all(f["passed"] for f in findings)
    return passed, findings


def _run_tests(root: Path, kind: str) -> dict[str, Any]:
    """Run the project's test command. Returns a finding dict."""
    if kind == "ts":
        # Prefer package.json's test script if available
        pkg_json = root / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
                if (pkg.get("scripts") or {}).get("test"):
                    code, out = run(["npm", "test", "--", "--silent"], timeout=300)
                    return {"check": "tests_pass_npm", "passed": code == 0,
                            "detail": "" if code == 0 else _truncate(out, 800)}
            except Exception:
                pass
        # Try common runners directly
        for runner in ("vitest", "jest"):
            if shutil.which(runner) or (root / "node_modules" / ".bin" / runner).exists():
                cmd = runner if shutil.which(runner) else str(root / "node_modules" / ".bin" / runner)
                code, out = run([cmd, "run", "--passWithNoTests"], timeout=300)
                return {"check": f"tests_pass_{runner}", "passed": code == 0,
                        "detail": "" if code == 0 else _truncate(out, 800)}
        return {"check": "tests_pass", "passed": True, "detail": "skipped - no JS test runner found"}
    if kind == "py":
        if shutil.which("pytest"):
            code, out = run(["pytest", "-q"], timeout=300)
            return {"check": "tests_pass_pytest", "passed": code == 0,
                    "detail": "" if code == 0 else _truncate(out, 800)}
        return {"check": "tests_pass_pytest", "passed": True, "detail": "skipped - pytest not installed"}
    if kind == "rust":
        code, out = run(["cargo", "test"], timeout=600)
        return {"check": "tests_pass_cargo", "passed": code == 0,
                "detail": "" if code == 0 else _truncate(out, 800)}
    if kind == "go":
        code, out = run(["go", "test", "./..."], timeout=300)
        return {"check": "tests_pass_go", "passed": code == 0,
                "detail": "" if code == 0 else _truncate(out, 800)}
    return {"check": "tests_pass", "passed": True, "detail": "skipped - project type not detected"}


def _read_coverage_threshold(root: Path) -> float:
    """Read user-configured coverage threshold; default 0.80."""
    cfg = root / ".man-kit" / "config.json"
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            t = float(data.get("coverage_threshold", 0.80))
            if 0.0 <= t <= 1.0:
                return t
        except Exception:
            pass
    return 0.80


def _coverage_check(root: Path, kind: str) -> dict[str, Any]:
    """Best-effort coverage check. Skips silently when tooling/config missing."""
    threshold = _read_coverage_threshold(root)
    threshold_pct = int(threshold * 100)

    if kind == "py":
        if not shutil.which("pytest"):
            return {"check": "coverage_threshold", "passed": True, "detail": "skipped - pytest not installed"}
        code, out = run(["pytest", "--cov", "--cov-report=term", "-q"], timeout=300)
        # Look for "TOTAL ... 87%" in pytest-cov output
        m = re.search(r"^TOTAL\s+.*?(\d+)%\s*$", out, re.MULTILINE)
        if not m:
            return {"check": "coverage_threshold", "passed": True,
                    "detail": "skipped - pytest-cov not installed or no coverage config"}
        pct = int(m.group(1))
        return {"check": "coverage_threshold", "passed": pct >= threshold_pct,
                "detail": f"{pct}% (threshold {threshold_pct}%)"}
    if kind == "ts":
        # Many TS projects gate coverage via jest/vitest config; we don't second-guess.
        # If the test runner was invoked with coverage, the runner itself would have failed.
        return {"check": "coverage_threshold", "passed": True,
                "detail": "skipped - rely on jest/vitest coverageThreshold in project config"}
    if kind == "go":
        code, out = run(["go", "test", "-cover", "./..."], timeout=300)
        # Aggregate % from "coverage: NN.N% of statements" lines (best of all packages)
        pcts = [float(m.group(1)) for m in re.finditer(r"coverage:\s+(\d+(?:\.\d+)?)%", out)]
        if not pcts:
            return {"check": "coverage_threshold", "passed": True,
                    "detail": "skipped - no coverage reported"}
        avg = sum(pcts) / len(pcts)
        return {"check": "coverage_threshold", "passed": avg >= threshold_pct,
                "detail": f"avg {avg:.1f}% (threshold {threshold_pct}%)"}
    return {"check": "coverage_threshold", "passed": True, "detail": "skipped - project type not handled"}


def gate_test_to_review(state: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    root = project_root()
    test_files = state.get("artifacts", {}).get("test_files") or []
    candidates: list[Path] = []

    if not test_files:
        # Best effort: look for any test file in the repo.
        candidates = list(root.rglob("*.test.*")) + list(root.rglob("*_test.py")) + list(root.rglob("test_*.py"))
        if not candidates:
            findings.append({"check": "tests_exist", "passed": False,
                             "detail": "No test files found and state.artifacts.test_files is empty"})
            return False, findings
        findings.append({"check": "tests_exist", "passed": True, "detail": f"{len(candidates)} test files detected"})
    else:
        findings.append({"check": "tests_exist", "passed": True, "detail": f"{len(test_files)} tests in state"})

    # Forbid skipped/focused tests across JS, Python, Rust (vacuous-test guard).
    # JS:    it.skip, describe.only, test.skip, xit, xdescribe
    # Py:    @pytest.mark.skip (unconditional only — skipif with condition is allowed),
    #        pytest.skip(...) call, @unittest.skip
    # Rust:  #[ignore] attribute
    skip_pattern = re.compile(
        r"\b(?:it|describe|test)\.(?:skip|only)\b"
        r"|\bxit\b|\bxdescribe\b"
        r"|@pytest\.mark\.skip\s*(?:\(\s*\))?\s*$"
        r"|@unittest\.skip\b"
        r"|\bpytest\.skip\s*\("
        r"|#\[ignore\]",
        re.MULTILINE,
    )
    skip_offenders = []
    targets = test_files or [str(c.relative_to(root)) for c in candidates[:50]]
    for tf in targets:
        p = root / tf
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if skip_pattern.search(text):
            skip_offenders.append(tf)
    findings.append({
        "check": "no_skip_or_only",
        "passed": not skip_offenders,
        "detail": ", ".join(skip_offenders[:5]) if skip_offenders else "",
    })

    # Run the project's test suite — must pass.
    kind = _detect_project_type(root)
    findings.append(_run_tests(root, kind))

    # Coverage threshold (best effort).
    findings.append(_coverage_check(root, kind))

    passed = all(f["passed"] for f in findings)
    return passed, findings


def gate_review_to_done(state: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    report_path_str = state.get("artifacts", {}).get("review_report")
    if not report_path_str:
        findings.append({"check": "review_report_exists", "passed": False,
                         "detail": "state.artifacts.review_report is empty"})
        return False, findings

    p = project_root() / report_path_str
    if not p.exists():
        findings.append({"check": "review_report_exists", "passed": False,
                         "detail": f"{report_path_str} does not exist"})
        return False, findings

    text = p.read_text(encoding="utf-8")
    m = re.search(r"\*\*Verdict\*\*:\s*(PASS|CONCERNS|FAIL)", text)
    verdict = m.group(1) if m else None
    if not verdict:
        findings.append({"check": "verdict_present", "passed": False,
                         "detail": "No `**Verdict**: PASS|CONCERNS|FAIL` line found"})
        return False, findings

    findings.append({"check": "verdict_present", "passed": True, "detail": verdict})
    findings.append({
        "check": "verdict_acceptable",
        "passed": verdict == "PASS",  # CONCERNS requires explicit override (not yet wired in v1)
        "detail": "" if verdict == "PASS" else f"Verdict={verdict}; PASS required to mark DONE",
    })

    passed = all(f["passed"] for f in findings)
    return passed, findings


GATE_FUNCS: dict[str, Callable[[dict[str, Any]], tuple[bool, list[dict[str, Any]]]]] = {
    "plan_to_code": gate_plan_to_code,
    "code_to_test": gate_code_to_test,
    "test_to_review": gate_test_to_review,
    "review_to_done": gate_review_to_done,
}


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + "...[truncated]"


# ---------- Reporting ----------


def emit(report: dict[str, Any]) -> None:
    print("===== man-kit quality gate =====")
    print(f"check: {report['check']}")
    print(f"verdict: {'PASS' if report['passed'] else 'FAIL'}")
    print()
    for f in report["findings"]:
        mark = "[OK]" if f["passed"] else "[!! ]"
        print(f"  {mark} {f['check']}")
        if f.get("detail"):
            for line in str(f["detail"]).splitlines():
                print(f"      {line}")
    print()
    sys.stderr.write(json.dumps(report) + "\n")


# ---------- Entrypoint ----------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", required=True,
                        help=f"Gate to run. One of: {', '.join(GATES)}, or 'all' for current stage.")
    args = parser.parse_args()

    state = load_state()
    if not state:
        sys.stderr.write("[man-kit] No state file. Run `/man plan` first.\n")
        return 2

    check = args.check
    if check == "all":
        current = state.get("current_stage")
        # Map current stage to its outgoing transition.
        outgoing = {"plan": "plan_to_code", "code": "code_to_test",
                    "test": "test_to_review", "review": "review_to_done"}.get(current)
        if not outgoing:
            print(f"[man-kit] No outgoing gate for stage '{current}'.")
            return 0
        check = outgoing

    if check not in GATE_FUNCS:
        sys.stderr.write(f"Unknown gate: {check}\n")
        return 2

    passed, findings = GATE_FUNCS[check](state)
    emit({"check": check, "passed": passed, "findings": findings})
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())
