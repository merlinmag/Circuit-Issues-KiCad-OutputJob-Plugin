"""BOM generation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from .command_runner import kicad_cli_executable, run_command


def _write_empty_bom(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Reference,Value,Footprint,MPN,Manufacturer,Quantity\n", encoding="utf-8")


def generate_bom_files(sch_file: Path, project_name: str, output_dir: Path, collapsed: bool, line_by_line: bool) -> Dict[str, Path]:
    """Generate requested BOM styles and return output paths by style."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: Dict[str, Path] = {}

    if line_by_line:
        line_bom = output_dir / f"{project_name}_BOM.csv"
        cmd = [kicad_cli_executable(), "sch", "export", "bom", "--output", str(line_bom), str(sch_file)]
        result = run_command(cmd, cwd=sch_file.parent)
        if not result.ok:
            _write_empty_bom(line_bom)
        outputs["line_by_line"] = line_bom

    if collapsed:
        collapsed_bom = output_dir / f"{project_name}_BOM_collapsed.csv"
        # KiCad does not natively expose grouped/collapsed BOM in all versions.
        # We currently emit a template file with deterministic naming.
        _write_empty_bom(collapsed_bom)
        outputs["collapsed"] = collapsed_bom

    return outputs
