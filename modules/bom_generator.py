"""BOM generation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from .command_runner import CommandResult, kicad_cli_executable, run_command

BOM_FIELDS = "Reference,Value,Footprint,MPN,Manufacturer,${QUANTITY}"
BOM_LABELS = "Reference,Value,Footprint,MPN,Manufacturer,Quantity"
COLLAPSED_GROUP_BY = "Value,Footprint,MPN"


def _export_bom(sch_file: Path, output_path: Path, group_by: str) -> CommandResult:
    """Run `kicad-cli sch export bom`. An empty group_by gives one row per reference."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        # Never leave a stale BOM behind that could be mistaken for this run's output.
        output_path.unlink()
    cmd = [
        kicad_cli_executable(),
        "sch",
        "export",
        "bom",
        "--fields",
        BOM_FIELDS,
        "--labels",
        BOM_LABELS,
        "--group-by",
        group_by,
        "--ref-range-delimiter",
        "",
        "--output",
        str(output_path),
        str(sch_file),
    ]
    result = run_command(cmd, cwd=sch_file.parent)
    result.output_path = output_path
    if result.ok and not output_path.exists():
        result.ok = False
        result.stderr = (result.stderr + f"\nkicad-cli reported success but did not write {output_path}").strip()
    return result


def generate_bom_files(
    sch_file: Path, project_name: str, output_dir: Path, collapsed: bool, line_by_line: bool
) -> Dict[str, CommandResult]:
    """Generate requested BOM styles and return a command result per style.

    - line_by_line: ``<project>_BOM.csv``, one row per reference.
    - collapsed: ``<project>_BOM_collapsed.csv``, grouped by Value + Footprint + MPN with a quantity column.
    """
    outputs: Dict[str, CommandResult] = {}
    if line_by_line:
        outputs["line_by_line"] = _export_bom(sch_file, output_dir / f"{project_name}_BOM.csv", group_by="")
    if collapsed:
        outputs["collapsed"] = _export_bom(
            sch_file, output_dir / f"{project_name}_BOM_collapsed.csv", group_by=COLLAPSED_GROUP_BY
        )
    return outputs
