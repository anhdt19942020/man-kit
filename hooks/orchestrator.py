#!/usr/bin/env python3
"""
man-kit orchestrator -- detect installed Claude Code plugins and recommend dispatch targets.

man-kit is a thin coordination layer; the heavy lifting (deep code review, security scans,
context-window optimization, etc.) belongs to specialist plugins. This module reports what is
installed so each stage's skill can pick the best available worker, and falls back to built-in
sub-agents when nothing better is around.

Detection sources, in priority order:
  1. ~/.claude/settings.json `enabledPlugins` (true/false flags)
  2. Plugin cache directories under ~/.claude/plugins/cache/
  3. Project-level .claude/settings.json `enabledPlugins`

Output: JSON object on stdout. Designed to be consumed by skills, not by humans.

Usage:
  python orchestrator.py                       # Print full detection report (JSON)
  python orchestrator.py --has=context-mode    # Exit 0 if installed, 1 otherwise
  python orchestrator.py --best-for=review     # Print best plugin for the named stage
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Plugins man-kit knows how to leverage. Keys are short canonical names; values describe
# which marketplace IDs to look for (any match counts as installed).
KNOWN = {
    # --- previously known ---
    "context-mode": ["context-mode@context-mode", "context-mode@context-mode-marketplace"],
    "context7": ["context7@context7", "context7@claude-plugins-official"],
    "caveman": ["caveman@caveman-marketplace", "caveman@caveman"],
    "superpowers": ["superpowers@claude-plugins-official", "superpowers@superpowers-marketplace"],
    "craftpowers": ["craftpowers@craftpowers-marketplace"],
    "code-review": ["code-review@claude-plugins-official"],
    "secure-reviewer": ["secure-reviewer"],  # may be a craftpowers agent, treat specially
    "frontend-design": ["frontend-design@claude-plugins-official"],
    "code-simplifier": ["code-simplifier@claude-plugins-official"],
    "playwright": ["playwright@claude-plugins-official"],
    "semgrep": ["semgrep@claude-plugins-official", "semgrep"],
    "aikido": ["aikido@aikido-marketplace", "aikido-security"],
    "coderabbit": ["coderabbit@coderabbit"],
    # --- expanded set: stage-aligned ---
    "feature-dev": ["feature-dev@claude-plugins-official"],
    "pr-review-toolkit": ["pr-review-toolkit@claude-plugins-official"],
    "optibot": ["optibot-code-review@optibot", "optibot@optibot"],
    "sourcegraph": ["sourcegraph@claude-plugins-official", "sourcegraph"],
    # --- expanded set: meta / future stages (not yet in STAGE_PREFERENCE) ---
    "sentry": ["sentry@claude-plugins-official"],
    "skill-creator": ["skill-creator@claude-plugins-official"],
    "claudemd-mgmt": ["claude-md-management@claude-plugins-official"],
    "hookify": ["hookify@claude-plugins-official"],
    "session-report": ["session-report@claude-plugins-official"],
    "plugin-dev-toolkit": ["plugin-developer-toolkit@claude-plugins-official"],
}

# Per-stage preference: try these in order; first installed wins. Built-in fallback at end.
# Order reflects fidelity (most thorough first), then breadth.
STAGE_PREFERENCE = {
    "plan":   ["feature-dev", "superpowers", "sourcegraph", "context7", "craftpowers"],
    "code":   ["context-mode", "sourcegraph", "context7", "frontend-design", "code-simplifier", "craftpowers"],
    "test":   ["craftpowers"],  # craftpowers ships test-engineer; expand when test-focused plugins emerge
    "review": ["code-review", "pr-review-toolkit", "coderabbit", "optibot", "semgrep", "aikido", "craftpowers"],
}

# Meta plugins that don't slot into current 4 stages but are useful adjacent to the loop.
# Surface them via `--meta` for slash-command discovery; not invoked automatically.
META_PLUGINS = {
    "sentry": "post-ship error monitoring (future `monitor` stage)",
    "skill-creator": "meta -- author/improve skills",
    "claudemd-mgmt": "post-`done` housekeeping for CLAUDE.md hygiene",
    "hookify": "meta -- generate custom hooks",
    "session-report": "meta -- token/cache analytics for the session",
    "plugin-dev-toolkit": "meta -- plugin development tooling",
}


def settings_paths() -> list[Path]:
    paths = []
    home = Path.home() / ".claude" / "settings.json"
    if home.exists():
        paths.append(home)
    proj = Path.cwd() / ".claude" / "settings.json"
    if proj.exists():
        paths.append(proj)
    proj_local = Path.cwd() / ".claude" / "settings.local.json"
    if proj_local.exists():
        paths.append(proj_local)
    return paths


def read_enabled_plugins() -> set[str]:
    enabled: set[str] = set()
    for p in settings_paths():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for plugin_id, flag in (data.get("enabledPlugins") or {}).items():
            if flag is True or (isinstance(flag, list) and flag):
                enabled.add(plugin_id)
    return enabled


def detect() -> dict[str, Any]:
    enabled = read_enabled_plugins()
    detected = {}
    for short_name, candidates in KNOWN.items():
        match = next((c for c in candidates if c in enabled), None)
        detected[short_name] = {"installed": bool(match), "id": match}
    return {
        "enabled_plugin_ids": sorted(enabled),
        "known_plugins": detected,
        "stage_preferences": STAGE_PREFERENCE,
    }


def best_for(stage: str, report: dict[str, Any]) -> str | None:
    prefs = STAGE_PREFERENCE.get(stage, [])
    for short_name in prefs:
        if report["known_plugins"].get(short_name, {}).get("installed"):
            return short_name
    return None


# Map short_name -> "/plugin install <plugin-id>@<marketplace>" command.
# Empty string means "no canonical install path" (community plugin not on a marketplace yet, etc.)
INSTALL_HINTS = {
    "context-mode":       "/plugin marketplace add mksglu/context-mode && /plugin install context-mode@context-mode",
    "context7":           "/plugin install context7@claude-plugins-official",
    "caveman":            "/plugin marketplace add JuliusBrussee/caveman && /plugin install caveman@caveman",
    "superpowers":        "/plugin install superpowers@claude-plugins-official",
    "craftpowers":        "/plugin marketplace add anhdt19942020/craftpowers && /plugin install craftpowers@craftpowers-marketplace",
    "code-review":        "/plugin install code-review@claude-plugins-official",
    "frontend-design":    "/plugin install frontend-design@claude-plugins-official",
    "code-simplifier":    "/plugin install code-simplifier@claude-plugins-official",
    "playwright":         "/plugin install playwright@claude-plugins-official",
    "semgrep":            "/plugin install semgrep@claude-plugins-official",
    "aikido":             "/plugin install aikido-security@claude-plugins-official",
    "coderabbit":         "/plugin install coderabbit@claude-plugins-official",
    "feature-dev":        "/plugin install feature-dev@claude-plugins-official",
    "pr-review-toolkit":  "/plugin install pr-review-toolkit@claude-plugins-official",
    "optibot":            "/plugin install optibot-code-review@claude-plugins-official",
    "sourcegraph":        "/plugin install sourcegraph@claude-plugins-official",
    "sentry":             "/plugin install sentry@claude-plugins-official",
    "skill-creator":      "/plugin install skill-creator@claude-plugins-official",
    "claudemd-mgmt":      "/plugin install claude-md-management@claude-plugins-official",
    "hookify":            "/plugin install hookify@claude-plugins-official",
    "session-report":     "/plugin install session-report@claude-plugins-official",
    "plugin-dev-toolkit": "/plugin install plugin-developer-toolkit@claude-plugins-official",
    "secure-reviewer":    "",  # built into craftpowers
}


def suggest_install(report: dict[str, Any]) -> int:
    """Print install commands for plugins missing across stages + meta.

    Output is plain text the user can copy-paste into the Claude Code prompt.
    Plugins already installed are skipped. Plugins without a known install path
    (INSTALL_HINTS empty) are skipped silently.
    """
    seen: set[str] = set()
    sections: list[tuple[str, list[str]]] = []

    for stage in ("plan", "code", "test", "review"):
        lines: list[str] = []
        for short in STAGE_PREFERENCE.get(stage, []):
            if short in seen:
                continue
            seen.add(short)
            installed = report["known_plugins"].get(short, {}).get("installed", False)
            if installed:
                continue
            cmd = INSTALL_HINTS.get(short, "")
            if cmd:
                lines.append(f"  {cmd}")
        if lines:
            sections.append((f"For `{stage}` stage:", lines))

    meta_lines: list[str] = []
    for short in META_PLUGINS:
        if short in seen:
            continue
        seen.add(short)
        installed = report["known_plugins"].get(short, {}).get("installed", False)
        if installed:
            continue
        cmd = INSTALL_HINTS.get(short, "")
        if cmd:
            meta_lines.append(f"  {cmd}  # {META_PLUGINS[short]}")
    if meta_lines:
        sections.append(("Meta / adjacent (optional):", meta_lines))

    if not sections:
        print("[man-kit] All known recommended plugins are installed. Nothing to add.")
        return 0

    print("[man-kit] Recommended but missing plugins.\n")
    print("Copy and paste these into Claude Code (one at a time). Each is independent;")
    print("install whichever fit your workflow. The built-in fallbacks work without any of them.\n")
    for title, lines in sections:
        print(title)
        for line in lines:
            print(line)
        print()
    print("After installing, run `/plugin reload` (or restart) and `/man setup` again to verify.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--has", help="Short name of a plugin. Exits 0 if installed, 1 otherwise.")
    parser.add_argument("--best-for", help="Stage name (plan|code|test|review). Prints best installed plugin or 'builtin'.")
    parser.add_argument("--meta", action="store_true", help="List meta plugins (skill-creator, hookify, etc.) and which are installed.")
    parser.add_argument("--suggest-install", action="store_true", help="Print copy-pasteable /plugin install commands for missing recommended plugins, grouped by stage.")
    args = parser.parse_args()

    report = detect()

    if args.has:
        installed = report["known_plugins"].get(args.has, {}).get("installed", False)
        return 0 if installed else 1

    if args.best_for:
        choice = best_for(args.best_for, report)
        print(choice or "builtin")
        return 0

    if args.meta:
        for name, purpose in META_PLUGINS.items():
            installed = report["known_plugins"].get(name, {}).get("installed", False)
            mark = "[installed]" if installed else "[ missing ]"
            print(f"{mark} {name:18s} -- {purpose}")
        return 0

    if args.suggest_install:
        return suggest_install(report)

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
