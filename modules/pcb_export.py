"""PCB export operations via kicad-cli."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from .command_runner import CommandResult, kicad_cli_executable, run_command


def _cli_render_quality(quality: str) -> str:
    """Map UI quality labels to valid kicad-cli render quality values."""
    normalized = str(quality).strip().lower()
    return {
        "low": "basic",
        "basic": "basic",
        "medium": "user",
        "user": "user",
        "high": "high",
        "job_settings": "job_settings",
    }.get(normalized, "user")


def generate_step(board_file: Path, output_path: Path) -> CommandResult:
    """Generate STEP model from a .kicad_pcb file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        kicad_cli_executable(),
        "pcb",
        "export",
        "step",
        "--subst-models",
        "--force",
        "--output",
        str(output_path),
        str(board_file),
    ]
    result = run_command(cmd, cwd=board_file.parent)
    result.output_path = output_path
    return result


def generate_gerbers(board_file: Path, output_dir: Path, layer_list: Optional[str] = None) -> CommandResult:
    """Generate gerber files to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        kicad_cli_executable(),
        "pcb",
        "export",
        "gerbers",
        "--output",
        str(output_dir),
    ]
    if layer_list:
        cmd += ["--layers", layer_list]
    cmd.append(str(board_file))
    result = run_command(cmd, cwd=board_file.parent)
    result.output_path = output_dir
    return result


def generate_drill_files(board_file: Path, output_dir: Path) -> CommandResult:
    """Generate drill files to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        kicad_cli_executable(),
        "pcb",
        "export",
        "drill",
        "--output",
        str(output_dir),
        str(board_file),
    ]
    result = run_command(cmd, cwd=board_file.parent)
    result.output_path = output_dir
    return result


def generate_position_files(board_file: Path, output_path: Path) -> CommandResult:
    """Generate position/PNP CSV output file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        kicad_cli_executable(),
        "pcb",
        "export",
        "pos",
        "--format",
        "csv",
        "--output",
        str(output_path),
        str(board_file),
    ]
    result = run_command(cmd, cwd=board_file.parent)
    result.output_path = output_path
    return result


def generate_render(
    board_file: Path,
    output_path: Path,
    side: str,
    azimuth: Optional[int] = None,
    elevation: Optional[int] = None,
    quality: str = "high",
    width: int = 3840,
    height: int = 2160,
) -> CommandResult:
    """Render 3D board image to PNG."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cli_quality = _cli_render_quality(quality)
    width = max(1, int(width))
    height = max(1, int(height))
    cmd = [
        kicad_cli_executable(),
        "pcb",
        "render",
        "--output",
        str(output_path),
        "--side",
        side,
        "--quality",
        cli_quality,
        "--width",
        str(width),
        "--height",
        str(height),
        "--background",
        "opaque",
    ]
    if azimuth is not None and elevation is not None:
        cmd += ["--rotate", f"{int(elevation)},0,{int(azimuth)}"]
    cmd.append(str(board_file))
    result = run_command(cmd, cwd=board_file.parent)
    result.output_path = output_path
    return result


def default_render_map(project_name: str, cfg: Dict[str, object]) -> Dict[str, List[object]]:
    """Build render config map from plugin settings."""
    return {
        "top": ["top", None, None, f"{project_name}_PCBA_TOP.png"],
        "bottom": ["bottom", None, None, f"{project_name}_PCBA_BOTTOM.png"],
        "left": ["left", None, None, f"{project_name}_PCBA_LEFT.png"],
        "right": ["right", None, None, f"{project_name}_PCBA_RIGHT.png"],
        "iso1": ["top", int(cfg.get("iso1_az", 45)), int(cfg.get("iso1_el", 35)), f"{project_name}_PCBA_ISO1.png"],
        "iso2": ["top", int(cfg.get("iso2_az", 225)), int(cfg.get("iso2_el", 35)), f"{project_name}_PCBA_ISO2.png"],
    }
