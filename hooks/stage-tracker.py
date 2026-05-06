#!/usr/bin/env python3
"""
man-kit stage tracker — manages .man-kit/state.json state machine.

Actions:
  --action=load       Read state, emit hookSpecificOutput.additionalContext for the model.
                      Used as SessionStart hook.
  --action=announce   Read state, return a short systemMessage to remind user of stage.
                      Used as UserPromptSubmit hook (low-noise).
  --action=init       Initialize a new feature. Args: --feature=<slug>.
  --action=advance    Move current_stage -> next stage. Records gate result.
                      Args: --to=<stage> --gate-passed=true|false [--failures=a,b]
  --action=loop-back  Move review -> code or review -> plan (after FAIL).
                      Args: --to=code|plan --reason=<text>
  --action=validate   Print diagnostics about state.json without modifying.
  --action=recover    Backup corrupt state, write a minimal fresh state.

Exit codes:
  0 — success
  1 — soft error (e.g. state file missing for actions that read it)
  2 — hard error (e.g. invalid transition, corrupt state on action that requires intact state)

This script is intentionally dependency-free (stdlib only).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
STAGES = ("plan", "code", "test", "review", "done")
TRANSITIONS = {
    None: ("plan",),
    "plan": ("code",),
    "code": ("test",),
    "test": ("review",),
    "review": ("done", "code", "plan"),  # loop-back allowed
    "done": (),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def state_path() -> Path:
    return Path.cwd() / ".man-kit" / "state.json"


def load_state() -> dict[str, Any] | None:
    p = state_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"__corrupt__": True}


def write_state(state: dict[str, Any]) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    state["last_updated"] = now_iso()
    p.write_text(json.dumps(state, indent=2), encoding="utf-8")


def fresh_state(feature: str) -> dict[str, Any]:
    ts = now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "feature": feature,
        "current_stage": "plan",
        "stages_completed": [],
        "artifacts": {"plan": None, "code_files": [], "test_files": [], "review_report": None},
        "gate_results": {
            "plan_to_code": None,
            "code_to_test": None,
            "test_to_review": None,
            "review_to_done": None,
        },
        "user_overrides": {},
        "started_at": ts,
        "last_updated": ts,
    }


# ---------- Actions ----------


def action_load() -> int:
    state = load_state()
    if not state:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "[man-kit] No active feature in this project. Run `/man plan <description>` to start a build loop."
        }}))
        return 0
    if state.get("__corrupt__"):
        print(json.dumps({"systemMessage": "[man-kit] state.json is corrupt. Run `python hooks/stage-tracker.py --action=recover`."}))
        return 0
    feat = state.get("feature", "?")
    stage = state.get("current_stage", "?")
    done = ", ".join(state.get("stages_completed", [])) or "none"
    msg = (
        f"[man-kit] Active feature: **{feat}** | current stage: **{stage}** | completed: {done}. "
        "Use `/man <stage>` to continue."
    )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": msg}}))
    return 0


def action_announce() -> int:
    """UserPromptSubmit hook — quiet by default, only speaks when state exists."""
    state = load_state()
    if not state or state.get("__corrupt__"):
        return 0
    if state.get("current_stage") == "done":
        return 0
    # Stay silent unless something actionable. Future: nudge if user is editing code in `code` stage but coverage gate is failing.
    return 0


def action_init(feature: str) -> int:
    if not feature:
        sys.stderr.write("--feature=<slug> is required\n")
        return 2
    if not feature.replace("-", "").isalnum() or len(feature) > 30:
        sys.stderr.write(f"Invalid slug '{feature}': must be alphanumeric + hyphens, ≤30 chars\n")
        return 2
    existing = load_state()
    if existing and not existing.get("__corrupt__") and existing.get("current_stage") != "done":
        sys.stderr.write(
            f"Active feature '{existing.get('feature')}' is mid-flight (stage={existing.get('current_stage')}). "
            "Archive or finish it before starting a new one.\n"
        )
        return 2
    if existing and existing.get("current_stage") == "done":
        archive_completed(existing)
    write_state(fresh_state(feature))
    print(f"[man-kit] Initialized feature '{feature}'. Current stage: plan.")
    return 0


def archive_completed(state: dict[str, Any]) -> None:
    archive_dir = Path.cwd() / ".man-kit" / "history"
    archive_dir.mkdir(parents=True, exist_ok=True)
    feat = state.get("feature", "unknown")
    ts = state.get("last_updated", now_iso()).replace(":", "-")
    (archive_dir / f"{feat}-{ts}.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


def action_advance(to_stage: str, gate_passed: bool, failures: list[str]) -> int:
    state = load_state()
    if not state or state.get("__corrupt__"):
        sys.stderr.write("No valid state. Run `--action=init --feature=<slug>` first.\n")
        return 2
    current = state.get("current_stage")
    allowed = TRANSITIONS.get(current, ())
    if to_stage not in allowed:
        sys.stderr.write(f"Invalid transition: {current} -> {to_stage}. Allowed: {allowed}\n")
        return 2
    transition_key = f"{current}_to_{to_stage}"
    state.setdefault("gate_results", {})[transition_key] = {
        "passed": bool(gate_passed),
        "checked_at": now_iso(),
        "failures": failures,
    }
    if not gate_passed:
        sys.stderr.write(f"Gate {transition_key} FAILED: {failures}. Stage NOT advanced.\n")
        write_state(state)
        return 2
    if current and current not in state.get("stages_completed", []):
        state.setdefault("stages_completed", []).append(current)
    state["current_stage"] = to_stage
    write_state(state)
    print(f"[man-kit] Advanced {current} -> {to_stage}.")
    return 0


def action_loop_back(to_stage: str, reason: str) -> int:
    state = load_state()
    if not state or state.get("__corrupt__"):
        sys.stderr.write("No valid state.\n")
        return 2
    if state.get("current_stage") != "review":
        sys.stderr.write("Loop-back is only allowed from `review` stage.\n")
        return 2
    if to_stage not in ("code", "plan"):
        sys.stderr.write("Loop-back target must be `code` or `plan`.\n")
        return 2
    state["current_stage"] = to_stage
    state.setdefault("user_overrides", {})[f"loopback_{now_iso()}"] = {
        "from": "review",
        "to": to_stage,
        "reason": reason,
    }
    write_state(state)
    print(f"[man-kit] Looped back review -> {to_stage}. Reason logged.")
    return 0


def action_validate() -> int:
    state = load_state()
    if not state:
        print("[man-kit] No state file at .man-kit/state.json (this is fine for a fresh project).")
        return 0
    if state.get("__corrupt__"):
        print("[man-kit] state.json is CORRUPT (not valid JSON). Run --action=recover.")
        return 1
    issues: list[str] = []
    if state.get("schema_version") != SCHEMA_VERSION:
        issues.append(f"schema_version {state.get('schema_version')} != current {SCHEMA_VERSION}")
    if state.get("current_stage") not in STAGES:
        issues.append(f"current_stage {state.get('current_stage')!r} not in {STAGES}")
    if not state.get("feature"):
        issues.append("feature is empty")
    if issues:
        print("[man-kit] state.json has issues:\n  - " + "\n  - ".join(issues))
        return 1
    print(f"[man-kit] state.json is valid. feature={state['feature']} stage={state['current_stage']}")
    return 0


def action_recover() -> int:
    p = state_path()
    if p.exists():
        backup = p.with_suffix(".json.bak")
        backup.write_bytes(p.read_bytes())
        print(f"[man-kit] Backed up corrupt state to {backup}")
    sys.stderr.write(
        "Recovery: run `--action=init --feature=<slug>` to start fresh, "
        f"or hand-edit {p} to match the schema in lib/state-schema.md.\n"
    )
    return 0


# ---------- Entrypoint ----------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True, choices=[
        "load", "announce", "init", "advance", "loop-back", "validate", "recover"
    ])
    parser.add_argument("--feature", default="")
    parser.add_argument("--to", default="")
    parser.add_argument("--gate-passed", default="false")
    parser.add_argument("--failures", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()

    if args.action == "load":
        return action_load()
    if args.action == "announce":
        return action_announce()
    if args.action == "init":
        return action_init(args.feature)
    if args.action == "advance":
        gate_passed = args.gate_passed.lower() == "true"
        failures = [s for s in args.failures.split(",") if s]
        return action_advance(args.to, gate_passed, failures)
    if args.action == "loop-back":
        return action_loop_back(args.to, args.reason)
    if args.action == "validate":
        return action_validate()
    if args.action == "recover":
        return action_recover()
    return 2


if __name__ == "__main__":
    sys.exit(main())
