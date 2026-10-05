"""ERC / DRC checks via kicad-cli with JSON report parsing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .command_runner import CommandResult, kicad_cli_executable, run_command
from .config_manager import FAIL_ON_CHOICES  # noqa: F401  (re-exported)


def run_erc(sch_file: Path, output_path: Path) -> CommandResult:
    """Run ERC and write a JSON report (all severities, saved exclusions flagged)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    cmd = [
        kicad_cli_executable(),
        "sch",
        "erc",
        "--format",
        "json",
        "--severity-all",
        "--output",
        str(output_path),
        str(sch_file),
    ]
    result = run_command(cmd, cwd=sch_file.parent)
    result.output_path = output_path
    return result


def run_drc(board_file: Path, output_path: Path) -> CommandResult:
    """Run DRC including schematic parity and write a JSON report."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    cmd = [
        kicad_cli_executable(),
        "pcb",
        "drc",
        "--schematic-parity",
        "--format",
        "json",
        "--severity-all",
        "--output",
        str(output_path),
        str(board_file),
    ]
    result = run_command(cmd, cwd=board_file.parent)
    result.output_path = output_path
    return result


def _location(item: Dict[str, Any], sheet: str = "") -> str:
    pos = item.get("pos") if isinstance(item, dict) else None
    parts = []
    if sheet:
        parts.append(sheet)
    if isinstance(pos, dict) and "x" in pos and "y" in pos:
        parts.append(f"({pos['x']}, {pos['y']})")
    return " ".join(parts)


def _summarize(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Count errors/warnings and keep the non-excluded violations ordered by severity."""
    counts = {"errors": 0, "warnings": 0, "excluded": 0}
    kept: List[Dict[str, Any]] = []
    for entry in entries:
        severity = str(entry.get("severity", "")).lower()
        # Violations excluded in the project are reported with --severity-all but flagged;
        # they must not count against the design.
        if entry.get("excluded") is True or severity == "exclusion":
            counts["excluded"] += 1
            continue
        if severity == "error":
            counts["errors"] += 1
        elif severity == "warning":
            counts["warnings"] += 1
        else:
            continue
        kept.append(entry)
    kept.sort(key=lambda e: 0 if str(e.get("severity", "")).lower() == "error" else 1)
    return {**counts, "violations": kept}


def _entry(raw: Dict[str, Any], category: str, sheet: str = "") -> Dict[str, Any]:
    items = raw.get("items") if isinstance(raw.get("items"), list) else []
    first = items[0] if items else {}
    return {
        "category": category,
        "type": str(raw.get("type", "")),
        "severity": str(raw.get("severity", "")),
        "excluded": bool(raw.get("excluded", False)),
        "description": str(raw.get("description", "")),
        "items": [str(i.get("description", "")) for i in items if isinstance(i, dict)],
        "location": _location(first, sheet),
    }


def parse_erc_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a kicad-cli ERC JSON report into counts and violations."""
    entries: List[Dict[str, Any]] = []
    for sheet in report.get("sheets", []) or []:
        if not isinstance(sheet, dict):
            continue
        sheet_path = str(sheet.get("path", ""))
        for raw in sheet.get("violations", []) or []:
            if isinstance(raw, dict):
                entries.append(_entry(raw, "violation", sheet_path))
    summary = _summarize(entries)
    summary["units"] = report.get("coordinate_units", "")
    return summary


def parse_drc_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a kicad-cli DRC JSON report (violations, unconnected items, parity)."""
    entries: List[Dict[str, Any]] = []
    per_category: Dict[str, int] = {}
    for key, category in (("violations", "violation"), ("unconnected_items", "unconnected"), ("schematic_parity", "parity")):
        raws = [r for r in (report.get(key, []) or []) if isinstance(r, dict)]
        parsed = [_entry(r, category) for r in raws]
        per_category[category] = sum(1 for p in parsed if not p["excluded"])
        entries.extend(parsed)
    summary = _summarize(entries)
    summary["unconnected"] = per_category["unconnected"]
    summary["parity"] = per_category["parity"]
    summary["units"] = report.get("coordinate_units", "")
    return summary


def load_report(path: Path, kind: str) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        report = json.load(f)
    if kind == "erc":
        return parse_erc_report(report)
    return parse_drc_report(report)


def check_fails(summary: Optional[Dict[str, Any]], fail_on: str) -> bool:
    """Return True when the check result violates the configured threshold."""
    if not summary:
        return False
    fail_on = str(fail_on).lower()
    if fail_on == "never":
        return False
    if fail_on == "warning":
        return summary.get("errors", 0) + summary.get("warnings", 0) > 0
    return summary.get("errors", 0) > 0


def describe_counts(kind: str, summary: Dict[str, Any]) -> str:
    text = f"{summary.get('errors', 0)} errors, {summary.get('warnings', 0)} warnings, {summary.get('excluded', 0)} excluded"
    if kind == "drc":
        text += f" ({summary.get('unconnected', 0)} unconnected, {summary.get('parity', 0)} parity)"
    return text
