"""Run summary reports (summary.json / summary.md)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TOP_VIOLATIONS = 10


def git_short_sha(path: Path) -> Optional[str]:
    """Return the short HEAD SHA of the git repo containing ``path``, if any."""
    try:
        proc = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(path),
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = (proc.stdout or "").strip()
    return sha if proc.returncode == 0 and sha else None


def _md_escape(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def _short(text: Any, limit: int = 160) -> str:
    text = _md_escape(text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def build_summary(results: Dict[str, Any]) -> Dict[str, Any]:
    """Build the JSON-serialisable summary payload from pipeline results."""
    return {
        "project": results.get("project"),
        "board": results.get("board"),
        "git_sha": results.get("git_sha"),
        "timestamp": results.get("timestamp"),
        "duration_s": results.get("duration_s"),
        "headless": results.get("headless", False),
        "exit_code": results.get("exit_code", 0),
        "status": {0: "ok", 1: "failed", 2: "checks_failed"}.get(results.get("exit_code", 0), "failed"),
        "fail_on": results.get("fail_on"),
        "steps": results.get("steps", []),
        "checks": {
            kind: {
                **{k: v for k, v in data.items() if k != "violations"},
                "top_violations": (data.get("violations") or [])[:TOP_VIOLATIONS],
            }
            for kind, data in (results.get("checks") or {}).items()
        },
        "notes": results.get("notes", []),
    }


def _violation_lines(kind: str, data: Dict[str, Any]) -> List[str]:
    violations = data.get("violations", []) or []
    if not violations:
        return []
    lines = [f"**{kind.upper()}** (top {min(len(violations), TOP_VIOLATIONS)} of {len(violations)})", ""]
    lines.append("| Severity | Type | Description | Location |")
    lines.append("|---|---|---|---|")
    for v in violations[:TOP_VIOLATIONS]:
        items = "; ".join(v.get("items", [])[:2])
        description = v.get("description", "")
        if items:
            description = f"{description} ({items})"
        location = v.get("location", "")
        # ERC JSON positions use a different internal scale than the stated units, so only
        # DRC locations get a unit suffix.
        if location and data.get("units") and kind == "drc":
            location = f"{location} {data['units']}"
        lines.append(
            f"| {_md_escape(v.get('severity', ''))} | `{_md_escape(v.get('type', ''))}` | {_short(description)} | {_md_escape(location)} |"
        )
    lines.append("")
    return lines


def build_markdown(results: Dict[str, Any]) -> str:
    summary = build_summary(results)
    status_text = {
        "ok": "OK",
        "failed": "FAILED (some exports failed)",
        "checks_failed": "CHECKS FAILED (ERC/DRC)",
    }[summary["status"]]
    lines = [
        f"KiCad outputs for {summary['project']}: {status_text}",
        "",
        f"- Commit: {summary['git_sha'] or 'n/a'}",
        f"- Generated: {summary['timestamp']}",
        f"- Duration: {summary['duration_s']}s",
        f"- Exit code: {summary['exit_code']}",
    ]
    checks = results.get("checks") or {}
    for kind in ("erc", "drc"):
        data = checks.get(kind)
        if not data:
            continue
        text = f"- {kind.upper()}: {data.get('errors', 0)} errors, {data.get('warnings', 0)} warnings, {data.get('excluded', 0)} excluded"
        if kind == "drc":
            text += f" ({data.get('unconnected', 0)} unconnected, {data.get('parity', 0)} schematic parity)"
        lines.append(text)
    lines += ["", "| Step | Status | Duration | Detail |", "|---|---|---|---|"]
    for step in summary["steps"]:
        lines.append(
            f"| {_md_escape(step['name'])} | {step['status']} | {step.get('duration_s', 0)}s | {_short(step.get('detail', ''))} |"
        )
    lines.append("")

    violation_lines: List[str] = []
    for kind in ("erc", "drc"):
        if checks.get(kind):
            violation_lines += _violation_lines(kind, checks[kind])
    if violation_lines:
        lines += ["### Top violations", ""] + violation_lines

    if summary["notes"]:
        lines += ["### Notes", ""] + [f"- {_md_escape(n)}" for n in summary["notes"]] + [""]
    return "\n".join(lines).rstrip() + "\n"


def write_summary(results: Dict[str, Any], report_dir: Path) -> Tuple[Path, Path]:
    """Write summary.json and summary.md into ``report_dir``."""
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "summary.json"
    md_path = report_dir / "summary.md"
    json_path.write_text(json.dumps(build_summary(results), indent=2) + "\n", encoding="utf-8")
    md_path.write_text(build_markdown(results), encoding="utf-8")
    return json_path, md_path
