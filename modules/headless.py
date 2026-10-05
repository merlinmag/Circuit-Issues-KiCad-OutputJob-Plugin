"""Headless command line entry point (see ``cli.py``)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .config_manager import config_file_path, load_config, load_config_file
from .pipeline import EXIT_EXPORT_FAILED, STEP_CONFIG, STEP_GROUPS, expand_only, run_export_pipeline


class _ArgumentParser(argparse.ArgumentParser):
    """Usage errors exit with 1, because exit code 2 is reserved for ERC/DRC failures."""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(EXIT_EXPORT_FAILED, f"{self.prog}: error: {message}\n")


def resolve_board(target: Path) -> Path:
    """Return the .kicad_pcb for a project directory, .kicad_pro or .kicad_pcb path."""
    target = target.expanduser().resolve()
    if target.is_file():
        if target.suffix == ".kicad_pcb":
            return target
        if target.suffix == ".kicad_pro":
            board = target.with_suffix(".kicad_pcb")
            if board.exists():
                return board
        raise ValueError(f"Not a KiCad board or project file: {target}")
    if not target.is_dir():
        raise ValueError(f"Path not found: {target}")

    projects = sorted(target.glob("*.kicad_pro"))
    for pro in projects:
        board = pro.with_suffix(".kicad_pcb")
        if board.exists():
            if len(projects) > 1:
                raise ValueError(f"Several projects in {target}; pass the .kicad_pcb file explicitly")
            return board
    boards = sorted(target.glob("*.kicad_pcb"))
    if len(boards) == 1:
        return boards[0]
    if not boards:
        raise ValueError(f"No .kicad_pcb file found in {target}")
    raise ValueError(f"Several .kicad_pcb files in {target}; pass one explicitly")


def build_parser() -> argparse.ArgumentParser:
    steps = ", ".join(list(STEP_CONFIG) + list(STEP_GROUPS))
    parser = _ArgumentParser(
        prog="cli.py",
        description="Run the Circuit-Issues KiCad OutputJob exports headless (CI).",
        epilog=(
            "Exit codes: 0 = all OK, 1 = an export failed (or bad usage), 2 = ERC/DRC failed per checks.fail_on. "
            f"Steps for --only: {steps}"
        ),
    )
    parser.add_argument("project", type=Path, help="project directory, .kicad_pro or .kicad_pcb file")
    parser.add_argument(
        "--config",
        type=Path,
        help="config JSON (default: <project>/.kicad_plugin_config.json, else bundled defaults)",
    )
    parser.add_argument("--only", help="comma separated steps to run, ignoring the config enable flags")
    parser.add_argument("--report-dir", type=Path, help="reports and export.log directory (default: <project>/reports)")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        board = resolve_board(args.project)
        project_root = board.parent
        if args.config is not None:
            cfg = load_config_file(args.config, project_root)
            config_source = str(args.config)
        else:
            cfg = load_config(project_root)
            saved = config_file_path(project_root)
            config_source = str(saved) if saved.exists() else "bundled defaults"
        only = [s for s in args.only.split(",") if s.strip()] if args.only else None
        expand_only(only, cfg)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
        return EXIT_EXPORT_FAILED  # pragma: no cover - parser.error exits

    print(f"Board: {board}", flush=True)
    print(f"Config: {config_source}", flush=True)
    results = run_export_pipeline(board, cfg, headless=True, only=only, report_dir=args.report_dir)
    for path in results.get("summary_files", []):
        print(f"Report: {path}", flush=True)
    return int(results.get("exit_code", EXIT_EXPORT_FAILED))
