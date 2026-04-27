"""Schematic export operations."""

from __future__ import annotations

from pathlib import Path

from .command_runner import CommandResult, kicad_cli_executable, run_command


def generate_schematic_pdf(sch_file: Path, output_path: Path, include_all_pages: bool = True) -> CommandResult:
    """Generate schematic PDF from a .kicad_sch file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        kicad_cli_executable(),
        "sch",
        "export",
        "pdf",
        "--output",
        str(output_path),
    ]
    if not include_all_pages:
        cmd += ["--pages", "1"]
    cmd.append(str(sch_file))
    result = run_command(cmd, cwd=sch_file.parent)
    result.output_path = output_path
    return result
