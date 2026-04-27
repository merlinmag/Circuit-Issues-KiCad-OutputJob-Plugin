"""KiCad ActionPlugin entrypoint for Circuit-Issues-KiCad-OutputJob-Plugin."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from .modules.bom_generator import generate_bom_files
from .modules.config_manager import load_config, resolve_relative_output, save_config
from .modules.external_tools import run_ibom_plugin, run_jlcpcb_plugin
from .modules.logger import get_logger
from .modules.pcb_export import (
    default_render_map,
    generate_drill_files,
    generate_gerbers,
    generate_position_files,
    generate_render,
    generate_step,
)
from .modules.schematic_export import generate_schematic_pdf
from .ui.dialog import create_progress_reporter, prompt_for_config, show_summary_dialog

try:
    import pcbnew  # type: ignore
except ImportError:  # pragma: no cover
    pcbnew = None


GERBER_PRESET_LAYERS = {
    "2_layer_default": "F.Cu,B.Cu,F.Paste,B.Paste,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts",
    "all_enabled": "",
}


def _collect_project_files(board_file: Path) -> Tuple[Path, Path]:
    """Infer .kicad_sch and .kicad_pcb files from active board file."""
    project_root = board_file.parent
    name = board_file.stem
    sch_file = project_root / f"{name}.kicad_sch"
    if sch_file.exists():
        return sch_file, board_file

    pro_file = project_root / f"{name}.kicad_pro"
    if pro_file.exists():
        candidate = project_root / f"{pro_file.stem}.kicad_sch"
        if candidate.exists():
            return candidate, board_file

    all_sch = sorted(project_root.glob("*.kicad_sch"))
    if len(all_sch) == 1:
        return all_sch[0], board_file

    return sch_file, board_file


def _count_export_steps(cfg: Dict[str, Any]) -> int:
    """Count enabled steps for progress reporting."""
    exports = cfg.get("exports", {}) if isinstance(cfg.get("exports"), dict) else {}
    renders = cfg.get("renders", {}) if isinstance(cfg.get("renders"), dict) else {}
    integrations = cfg.get("integrations", {}) if isinstance(cfg.get("integrations"), dict) else {}

    total = 0
    for key in ("sch_pdf", "step", "gerbers", "drill", "position"):
        if exports.get(key):
            total += 1
    if exports.get("bom_collapsed") or exports.get("bom_line_by_line"):
        total += 1
    for key in ("top", "bottom", "left", "right", "iso1", "iso2"):
        if renders.get(key):
            total += 1
    for key in ("jlcpcb", "ibom"):
        if integrations.get(key):
            total += 1
    return total


def run_export_pipeline(
    board_file: Path,
    cfg: Dict[str, Any],
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """Run selected exports and return status payload for summary dialog."""
    project_root = board_file.parent
    project_name = board_file.stem
    sch_file, pcb_file = _collect_project_files(board_file)

    logger = get_logger(log_file=project_root / "kicad_postdesign_export.log")
    results: Dict[str, Any] = {"ok": {}, "failed": {}, "notes": []}
    total_steps = max(1, _count_export_steps(cfg))
    current_step = 0

    def _tick(message: str) -> None:
        nonlocal current_step
        current_step += 1
        if progress_cb is not None:
            progress_cb(current_step, total_steps, message)

    def _record(key: str, ok: bool, detail: str) -> None:
        if ok:
            results["ok"][key] = detail
        else:
            results["failed"][key] = detail

    def _cmd_detail(cmd_res: Any, fallback_path: Path) -> str:
        parts = []
        if getattr(cmd_res, "return_code", None) is not None:
            parts.append(f"rc={cmd_res.return_code}")
        stderr = (getattr(cmd_res, "stderr", "") or "").strip()
        stdout = (getattr(cmd_res, "stdout", "") or "").strip()
        if stderr:
            parts.append(stderr)
        elif stdout:
            parts.append(stdout)
        else:
            parts.append(str(fallback_path))
        return "; ".join(parts)

    if not sch_file.exists():
        _record("schematic_pdf", False, f"Schematic file not found near board: {sch_file}")

    if cfg["exports"].get("sch_pdf", False) and sch_file.exists():
        _tick("Exporting schematic PDF...")
        out = resolve_relative_output(project_root, cfg["paths"]["sch_pdf"]) / f"{project_name}_SCH.pdf"
        cmd_res = generate_schematic_pdf(sch_file, out)
        _record("schematic_pdf", cmd_res.ok, _cmd_detail(cmd_res, out))

    if cfg["exports"].get("step", False):
        _tick("Exporting STEP model...")
        out = resolve_relative_output(project_root, cfg["paths"]["step"]) / f"{project_name}_STEP.step"
        cmd_res = generate_step(pcb_file, out)
        _record("step", cmd_res.ok, _cmd_detail(cmd_res, out))

    mfg_root = resolve_relative_output(project_root, cfg["paths"]["manufacturing"])
    if cfg["exports"].get("gerbers", False):
        _tick("Exporting Gerbers...")
        preset_key = str(cfg.get("exports", {}).get("gerber_layer_preset", "2_layer_default"))
        layer_list = GERBER_PRESET_LAYERS.get(preset_key, GERBER_PRESET_LAYERS["2_layer_default"])
        cmd_res = generate_gerbers(pcb_file, mfg_root / "gerbers", layer_list=layer_list)
        _record("gerbers", cmd_res.ok, _cmd_detail(cmd_res, mfg_root / "gerbers"))

    if cfg["exports"].get("drill", False):
        _tick("Exporting drill files...")
        cmd_res = generate_drill_files(pcb_file, mfg_root / "drills")
        _record("drill", cmd_res.ok, _cmd_detail(cmd_res, mfg_root / "drills"))

    if cfg["exports"].get("position", False):
        _tick("Exporting position/PNP...")
        pos_file = mfg_root / "placement" / f"{project_name}_POS.csv"
        cmd_res = generate_position_files(pcb_file, pos_file)
        _record("position", cmd_res.ok, _cmd_detail(cmd_res, pos_file))

    if cfg["exports"].get("bom_collapsed", False) or cfg["exports"].get("bom_line_by_line", False):
        _tick("Generating BOM...")
        bom_paths = generate_bom_files(
            sch_file=sch_file,
            project_name=project_name,
            output_dir=mfg_root / "bom",
            collapsed=bool(cfg["exports"].get("bom_collapsed", False)),
            line_by_line=bool(cfg["exports"].get("bom_line_by_line", False)),
        )
        results["ok"]["bom"] = {k: str(v) for k, v in bom_paths.items()}

    render_root = resolve_relative_output(project_root, cfg["paths"]["renders"])
    render_map = default_render_map(project_name, cfg["renders"])
    enabled_renders = sum(1 for key in ("top", "bottom", "left", "right", "iso1", "iso2") if cfg["renders"].get(key, False))
    quality = str(cfg["renders"].get("quality", "medium")).lower()
    width = int(cfg["renders"].get("width", 1920))
    height = int(cfg["renders"].get("height", 1080))
    if enabled_renders >= 4 and quality == "high" and width >= 3840:
        results["notes"].append(
            "Render settings are heavy (4+ views at 4K high quality); long runtime is expected."
        )
    for key, data in render_map.items():
        if not cfg["renders"].get(key, False):
            continue
        _tick(f"Rendering {key} view...")
        side, az, el, filename = data
        out = render_root / str(filename)
        cmd_res = generate_render(
            pcb_file,
            out,
            side=str(side),
            azimuth=int(az) if az is not None else None,
            elevation=int(el) if el is not None else None,
            quality=quality,
            width=width,
            height=height,
        )
        _record(f"render_{key}", cmd_res.ok, _cmd_detail(cmd_res, out))

    if cfg["integrations"].get("jlcpcb", False):
        _tick("Running JLCPCB integration...")
        ok, message = run_jlcpcb_plugin()
        _record("jlcpcb", ok, message)
        if "not installed" in message.lower():
            results["notes"].append(message)
    if cfg["integrations"].get("ibom", False):
        _tick("Running iBOM integration...")
        ok, message = run_ibom_plugin()
        _record("ibom", ok, message)
        if "not installed" in message.lower():
            results["notes"].append(message)

    logger.info("Export run completed. Success=%s Failed=%s", len(results["ok"]), len(results["failed"]))
    return results


if pcbnew is not None:
    class PostDesignExportPlugin(pcbnew.ActionPlugin):
        """ActionPlugin hook shown in KiCad's Tools menu."""

        def defaults(self) -> None:  # pragma: no cover - KiCad runtime only
            self.name = "Circuit-Issues-KiCad-OutputJob-Plugin"
            self.category = "Circuit Issues"
            self.description = "Generate post-design outputs and run integrations (KiCad 9/10)"
            self.show_toolbar_button = True

        def Run(self) -> None:  # noqa: N802  # pragma: no cover - KiCad runtime only
            board = pcbnew.GetBoard()
            if board is None:
                return
            board_file = Path(board.GetFileName())
            if not board_file.exists():
                return

            project_root = board_file.parent
            config = load_config(project_root)
            selected = prompt_for_config(config, project_root=project_root)
            if selected is None:
                return

            save_config(project_root, selected)
            total_steps = max(1, _count_export_steps(selected))
            progress_update, progress_close = create_progress_reporter(total_steps)

            def _worker() -> None:
                results: Dict[str, Any] = {"ok": {}, "failed": {}, "notes": []}
                try:
                    results = run_export_pipeline(board_file, selected, progress_cb=progress_update)
                except Exception as exc:  # noqa: BLE001
                    results["failed"]["fatal"] = f"Unhandled exception: {type(exc).__name__}: {exc}"
                finally:
                    progress_close()
                if pcbnew is not None:
                    import wx  # type: ignore

                    wx.CallAfter(show_summary_dialog, results)

            threading.Thread(target=_worker, name="post_design_export_worker", daemon=True).start()


    PostDesignExportPlugin().register()
