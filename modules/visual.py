"""SVG exports with stable file names for visual diffs (e.g. on GitHub)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from .command_runner import CommandResult, kicad_cli_executable, run_command

_COPPER_LAYER = re.compile(r'\(\s*\d+\s+"([^"]+\.Cu)"\s+(?:signal|power|mixed|jumper)\b')
_EXTRA_LAYERS = ("F.Silkscreen", "F.Fab")
# Combined views: (name, layers, mirror)
_COMBINED_VIEWS = (
    ("top", "F.Cu,F.Silkscreen,Edge.Cuts", False),
    ("bottom", "B.Cu,B.Silkscreen,Edge.Cuts", True),
)


def board_copper_layers(board_file: Path) -> List[str]:
    """Return copper layer names declared in a .kicad_pcb file, front to back."""
    text = board_file.read_text(encoding="utf-8", errors="replace")
    start = text.find("(layers")
    if start < 0:
        return ["F.Cu", "B.Cu"]
    layers = list(dict.fromkeys(_COPPER_LAYER.findall(text[start:start + 20000])))

    def _order(name: str) -> Tuple[int, int]:
        if name == "F.Cu":
            return (0, 0)
        if name == "B.Cu":
            return (2, 0)
        digits = re.findall(r"\d+", name)
        return (1, int(digits[0]) if digits else 0)

    return sorted(layers, key=_order) or ["F.Cu", "B.Cu"]


def _safe(layer: str) -> str:
    return layer.replace(".", "_")


def _clean_svgs(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for stale in directory.glob("*.svg"):
        stale.unlink()


def export_schematic_svgs(sch_file: Path, output_dir: Path) -> CommandResult:
    """Export one SVG per schematic sheet (KiCad names them after the sheet path)."""
    _clean_svgs(output_dir)
    cmd = [kicad_cli_executable(), "sch", "export", "svg", "--output", str(output_dir), str(sch_file)]
    result = run_command(cmd, cwd=sch_file.parent)
    result.output_path = output_dir
    if result.ok and not any(output_dir.glob("*.svg")):
        result.ok = False
        result.stderr = (result.stderr + "\nNo schematic SVG files were written").strip()
    return result


def _export_pcb_svg(board_file: Path, output_path: Path, layers: str, mirror: bool) -> CommandResult:
    base = [kicad_cli_executable(), "pcb", "export", "svg", "--output", str(output_path), "--layers", layers]
    tail = ["--exclude-drawing-sheet", "--page-size-mode", "2"]
    if mirror:
        tail.append("--mirror")
    tail.append(str(board_file))

    result = run_command(base + ["--mode-single"] + tail, cwd=board_file.parent)
    if not result.ok and "mode-single" in f"{result.stderr} {result.stdout}":
        # Older kicad-cli builds always write a single file and reject the flag.
        result = run_command(base + tail, cwd=board_file.parent)
    result.output_path = output_path
    if result.ok and not output_path.exists():
        result.ok = False
        result.stderr = (result.stderr + f"\nExpected output not written: {output_path}").strip()
    return result


def export_pcb_svgs(board_file: Path, project_name: str, output_dir: Path) -> List[Tuple[Path, CommandResult]]:
    """Export per-layer SVGs (copper + F.Silkscreen/F.Fab) and combined top/bottom views."""
    _clean_svgs(output_dir)
    results: List[Tuple[Path, CommandResult]] = []
    for layer in board_copper_layers(board_file) + list(_EXTRA_LAYERS):
        out = output_dir / f"{project_name}-pcb-{_safe(layer)}.svg"
        results.append((out, _export_pcb_svg(board_file, out, f"{layer},Edge.Cuts", mirror=False)))
    for name, layers, mirror in _COMBINED_VIEWS:
        out = output_dir / f"{project_name}-pcb-{name}.svg"
        results.append((out, _export_pcb_svg(board_file, out, layers, mirror=mirror)))
    return results
