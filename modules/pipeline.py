"""Export pipeline shared by the KiCad GUI plugin and the headless CLI.

Nothing in here may import ``wx`` or ``pcbnew``.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from .bom_generator import generate_bom_files
from .checks import check_fails, describe_counts, load_report, run_drc, run_erc
from .command_runner import NEEDS_DISPLAY_MESSAGE, display_prefix
from .config_manager import resolve_relative_output
from .external_tools import JLC_NOT_INSTALLED, _plugin_search_dirs, run_ibom_plugin, run_jlcpcb_plugin
from .logger import close_file_handlers, get_logger
from .pcb_export import (
    default_render_map,
    generate_drill_files,
    generate_gerbers,
    generate_position_files,
    generate_render,
    generate_step,
)
from .report import git_short_sha, write_summary
from .reproducible import normalize_outputs
from .schematic_export import generate_schematic_pdf
from .visual import export_pcb_svgs, export_schematic_svgs


GERBER_PRESET_LAYERS = {
    "2_layer_default": "F.Cu,B.Cu,F.Paste,B.Paste,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts",
    "4_layer": "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts",
    "6_layer": "F.Cu,In1.Cu,In2.Cu,In3.Cu,In4.Cu,B.Cu,F.Paste,B.Paste,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts",
    "8_layer": "F.Cu,In1.Cu,In2.Cu,In3.Cu,In4.Cu,In5.Cu,In6.Cu,B.Cu,F.Paste,B.Paste,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts",
    "all_enabled": "",
}

RENDER_VIEWS = ("top", "bottom", "left", "right", "iso1", "iso2")

# Step name -> (config section, config key). Order is execution order; checks run first.
STEP_CONFIG: Dict[str, Tuple[str, str]] = {
    "erc": ("checks", "erc"),
    "drc": ("checks", "drc"),
    "schematic_pdf": ("exports", "sch_pdf"),
    "step": ("exports", "step"),
    "gerbers": ("exports", "gerbers"),
    "drill": ("exports", "drill"),
    "position": ("exports", "position"),
    "bom_line_by_line": ("exports", "bom_line_by_line"),
    "bom_collapsed": ("exports", "bom_collapsed"),
    "visual": ("exports", "visual"),
    **{f"render_{view}": ("renders", view) for view in RENDER_VIEWS},
    "jlcpcb": ("integrations", "jlcpcb"),
    "ibom": ("integrations", "ibom"),
}
STEP_GROUPS: Dict[str, List[str]] = {
    "checks": ["erc", "drc"],
    "sch_pdf": ["schematic_pdf"],
    "bom": ["bom_line_by_line", "bom_collapsed"],
    "renders": [],  # expanded from config, see expand_only()
}

EXIT_OK = 0
EXIT_EXPORT_FAILED = 1
EXIT_CHECKS_FAILED = 2


def _section(cfg: Dict[str, Any], name: str) -> Dict[str, Any]:
    value = cfg.get(name, {})
    return value if isinstance(value, dict) else {}


def expand_only(only: Optional[Iterable[str]], cfg: Dict[str, Any]) -> Optional[Set[str]]:
    """Expand ``--only`` names (steps or groups) into step names. Raises ValueError on unknown names."""
    if only is None:
        return None
    selected: Set[str] = set()
    for raw in only:
        name = raw.strip().lower()
        if not name:
            continue
        if name in STEP_CONFIG:
            selected.add(name)
        elif name in ("render", "renders"):
            views = [v for v in RENDER_VIEWS if _section(cfg, "renders").get(v)] or ["top"]
            selected.update(f"render_{v}" for v in views)
        elif name in STEP_GROUPS:
            selected.update(STEP_GROUPS[name])
        else:
            valid = sorted(set(STEP_CONFIG) | set(STEP_GROUPS))
            raise ValueError(f"Unknown step '{raw}'. Valid steps: {', '.join(valid)}")
    return selected


def planned_steps(cfg: Dict[str, Any], only: Optional[Iterable[str]] = None) -> List[str]:
    """Return the ordered step names that will run.

    Without ``only`` the config enable flags decide. With ``only`` exactly the listed
    steps run, regardless of their enable flags.
    """
    selected = expand_only(only, cfg)
    steps = []
    for name, (section, key) in STEP_CONFIG.items():
        enabled = bool(_section(cfg, section).get(key, False)) if selected is None else name in selected
        if enabled:
            steps.append(name)
    return steps


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


def _count_export_steps(cfg: Dict[str, Any], only: Optional[Iterable[str]] = None) -> int:
    """Count enabled steps for progress reporting."""
    return len(planned_steps(cfg, only))


def compute_exit_code(results: Dict[str, Any]) -> int:
    """0 = all OK, 1 = some step failed to run, 2 = ERC/DRC violations exceed ``fail_on``.

    A failed export takes precedence over failed checks: its outputs are incomplete.
    """
    steps = results.get("steps", [])
    if any(s["status"] == "failed" and not s.get("check_violation") for s in steps):
        return EXIT_EXPORT_FAILED
    if any(s.get("check_violation") for s in steps):
        return EXIT_CHECKS_FAILED
    return EXIT_OK


def run_export_pipeline(
    board_file: Path,
    cfg: Dict[str, Any],
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    *,
    headless: bool = False,
    only: Optional[Iterable[str]] = None,
    report_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run selected checks/exports and return a status payload.

    The payload keeps the legacy ``ok``/``failed``/``notes`` maps used by the GUI summary
    and adds ``skipped``, ordered ``steps`` records, ``checks`` and ``exit_code``.
    Reports (summary.json/.md, erc.json, drc.json, export.log) go to ``report_dir``
    (default ``<project>/reports``).
    """
    board_file = Path(board_file).resolve()
    project_root = board_file.parent
    project_name = board_file.stem
    sch_file, pcb_file = _collect_project_files(board_file)
    report_dir = Path(report_dir).resolve() if report_dir is not None else project_root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    logger = get_logger(log_file=report_dir / "export.log")
    started = time.monotonic()
    checks_cfg = _section(cfg, "checks")
    fail_on = str(checks_cfg.get("fail_on", "error")).lower()
    results: Dict[str, Any] = {
        "ok": {},
        "failed": {},
        "skipped": {},
        "notes": [],
        "steps": [],
        "checks": {},
        "project": project_name,
        "board": str(pcb_file),
        "headless": headless,
        "fail_on": fail_on,
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "git_sha": git_short_sha(project_root),
    }
    steps = planned_steps(cfg, only)
    total_steps = max(1, len(steps))
    current_step = 0
    logger.info("Project %s (%s), %d step(s): %s", project_name, pcb_file, len(steps), ", ".join(steps) or "-")

    def rel(path: Path) -> str:
        try:
            return os.path.relpath(str(path), str(project_root)).replace("\\", "/")
        except ValueError:  # different drive on Windows
            return str(path)

    def _cmd_detail(cmd_res: Any, fallback_path: Path) -> str:
        if getattr(cmd_res, "ok", False):
            return rel(fallback_path)
        parts = []
        if getattr(cmd_res, "return_code", None) is not None:
            parts.append(f"rc={cmd_res.return_code}")
        stderr = (getattr(cmd_res, "stderr", "") or "").strip()
        stdout = (getattr(cmd_res, "stdout", "") or "").strip()
        parts.append(stderr or stdout or rel(fallback_path))
        return "; ".join(parts)

    def _record(name: str, status: str, detail: Any, duration: float, check_violation: bool = False) -> None:
        bucket = {"ok": "ok", "failed": "failed", "skipped": "skipped"}[status]
        results[bucket][name] = detail
        record = {"name": name, "status": status, "detail": str(detail), "duration_s": round(duration, 2)}
        if check_violation:
            record["check_violation"] = True
        results["steps"].append(record)
        log = logger.error if status == "failed" else logger.info
        log("[%s] %s (%.1fs): %s", status.upper(), name, duration, detail)

    def _run(name: str, message: str, fn: Callable[[], Tuple[str, Any]]) -> None:
        """Run one step; fn returns (status, detail) or (status, detail, check_violation)."""
        nonlocal current_step
        if name not in steps:
            return
        current_step += 1
        logger.info("(%d/%d) %s", current_step, total_steps, message)
        if progress_cb is not None:
            progress_cb(current_step, total_steps, message)
        t0 = time.monotonic()
        try:
            outcome = fn()
        except Exception as exc:  # noqa: BLE001
            outcome = ("failed", f"Unhandled exception: {type(exc).__name__}: {exc}")
        status, detail = outcome[0], outcome[1]
        violation = bool(outcome[2]) if len(outcome) > 2 else False
        _record(name, status, detail, time.monotonic() - t0, check_violation=violation)

    def _cmd_step(cmd_res: Any, out: Path, normalize: Optional[Path] = None) -> Tuple[str, str]:
        if cmd_res.ok and not out.exists():
            cmd_res.ok = False
            cmd_res.stderr = f"Expected output not written: {out}"
        if cmd_res.ok:
            normalize_outputs(normalize or out)
        return ("ok" if cmd_res.ok else "failed"), _cmd_detail(cmd_res, out)

    missing_sch = f"Schematic file not found near board: {sch_file}"

    # ------------------------------------------------------------------ checks
    def _check(kind: str) -> Tuple[str, str, bool]:
        if kind == "erc" and not sch_file.exists():
            return "failed", missing_sch, False
        out = report_dir / f"{kind}.json"
        cmd_res = run_erc(sch_file, out) if kind == "erc" else run_drc(pcb_file, out)
        if not cmd_res.ok or not out.exists():
            return "failed", _cmd_detail(cmd_res, out) if not cmd_res.ok else f"No report written: {out}", False
        summary = load_report(out, kind)
        results["checks"][kind] = summary
        counts = describe_counts(kind, summary)
        if check_fails(summary, fail_on):
            return "failed", f"{counts} (fail_on={fail_on})", True
        return "ok", counts, False

    _run("erc", "Running ERC...", lambda: _check("erc"))
    _run("drc", "Running DRC (with schematic parity)...", lambda: _check("drc"))

    # ------------------------------------------------------------------ exports
    paths = _section(cfg, "paths")
    exports = _section(cfg, "exports")

    def _sch_pdf() -> Tuple[str, str]:
        if not sch_file.exists():
            return "failed", missing_sch
        out = resolve_relative_output(project_root, paths["sch_pdf"]) / f"{project_name}_SCH.pdf"
        return _cmd_step(generate_schematic_pdf(sch_file, out), out)

    def _step() -> Tuple[str, str]:
        out = resolve_relative_output(project_root, paths["step"]) / f"{project_name}_STEP.step"
        return _cmd_step(generate_step(pcb_file, out), out)

    mfg_root = resolve_relative_output(project_root, paths["manufacturing"])

    def _gerbers() -> Tuple[str, str]:
        preset_key = str(exports.get("gerber_layer_preset", "2_layer_default"))
        layer_list = GERBER_PRESET_LAYERS.get(preset_key, GERBER_PRESET_LAYERS["2_layer_default"])
        out = mfg_root / "gerbers"
        return _cmd_step(generate_gerbers(pcb_file, out, layer_list=layer_list), out)

    def _drill() -> Tuple[str, str]:
        out = mfg_root / "drills"
        return _cmd_step(generate_drill_files(pcb_file, out), out)

    def _position() -> Tuple[str, str]:
        out = mfg_root / "placement" / f"{project_name}_POS.csv"
        return _cmd_step(generate_position_files(pcb_file, out), out)

    def _bom(style: str) -> Tuple[str, str]:
        if not sch_file.exists():
            return "failed", missing_sch
        bom = generate_bom_files(
            sch_file=sch_file,
            project_name=project_name,
            output_dir=mfg_root / "bom",
            collapsed=style == "collapsed",
            line_by_line=style == "line_by_line",
        )
        cmd_res = bom[style]
        return ("ok" if cmd_res.ok else "failed"), _cmd_detail(cmd_res, cmd_res.output_path)

    def _visual() -> Tuple[str, str]:
        visual_root = resolve_relative_output(project_root, str(paths.get("visual", "doc/visual")))
        problems: List[str] = []
        count = 0
        if sch_file.exists():
            sch_res = export_schematic_svgs(sch_file, visual_root / "schematic")
            if not sch_res.ok:
                problems.append(f"schematic: {_cmd_detail(sch_res, visual_root / 'schematic')}")
        else:
            problems.append(missing_sch)
        for out, res in export_pcb_svgs(pcb_file, project_name, visual_root / "pcb"):
            if not res.ok:
                problems.append(f"{out.name}: {_cmd_detail(res, out)}")
        normalize_outputs(visual_root)
        count = sum(1 for _ in visual_root.rglob("*.svg"))
        if problems:
            return "failed", "; ".join(problems)
        return "ok", f"{count} SVG files in {rel(visual_root)}"

    _run("schematic_pdf", "Exporting schematic PDF...", _sch_pdf)
    _run("step", "Exporting STEP model...", _step)
    _run("gerbers", "Exporting Gerbers...", _gerbers)
    _run("drill", "Exporting drill files...", _drill)
    _run("position", "Exporting position/PNP...", _position)
    _run("bom_line_by_line", "Generating BOM (line-by-line)...", lambda: _bom("line_by_line"))
    _run("bom_collapsed", "Generating BOM (collapsed)...", lambda: _bom("collapsed"))
    _run("visual", "Exporting SVGs for visual diff...", _visual)

    # ------------------------------------------------------------------ renders
    renders_cfg = _section(cfg, "renders")
    render_root = resolve_relative_output(project_root, paths["renders"])
    render_map = default_render_map(project_name, renders_cfg)
    render_steps = [s for s in steps if s.startswith("render_")]
    quality = str(renders_cfg.get("quality", "medium")).lower()
    width = int(renders_cfg.get("width", 1920))
    height = int(renders_cfg.get("height", 1080))
    if len(render_steps) >= 4 and quality == "high" and width >= 3840:
        results["notes"].append(
            "Render settings are heavy (4+ views at 4K high quality); long runtime is expected."
        )
    prefix, display_problem = display_prefix()

    def _render(key: str) -> Tuple[str, str]:
        side, az, el, filename = render_map[key]
        out = render_root / str(filename)
        if out.exists():
            out.unlink()
        cmd_res = generate_render(
            pcb_file,
            out,
            side=str(side),
            azimuth=int(az) if az is not None else None,
            elevation=int(el) if el is not None else None,
            quality=quality,
            width=width,
            height=height,
            cmd_prefix=prefix,
        )
        status, detail = _cmd_step(cmd_res, out)
        if status == "failed" and display_problem:
            detail = f"{NEEDS_DISPLAY_MESSAGE}: {detail}"
        return status, detail

    for view in RENDER_VIEWS:
        _run(f"render_{view}", f"Rendering {view} view...", lambda v=view: _render(v))

    # ------------------------------------------------------------------ integrations
    def _jlc() -> Tuple[str, str]:
        ok, message = run_jlcpcb_plugin(pcb_file, headless=headless)
        if message == JLC_NOT_INSTALLED:
            if headless:
                searched = ", ".join(str(p) for p in _plugin_search_dirs()) or "no plugin directories found"
                return "skipped", f"JLC plugin for KiCad not installed (searched: {searched}; set KICAD_PLUGIN_DIRS)"
            results["notes"].append(message)
        return ("ok" if ok else "failed"), message

    def _ibom() -> Tuple[str, str]:
        dest = project_root / "bom" if headless else None
        ok, message = run_ibom_plugin(pcb_file, headless=headless, dest_dir=dest)
        if "not installed" in message.lower():
            results["notes"].append(message)
        return ("ok" if ok else "failed"), message

    _run("jlcpcb", "Running JLCPCB integration...", _jlc)
    _run("ibom", "Running iBOM integration...", _ibom)

    # ------------------------------------------------------------------ summary
    results["exit_code"] = compute_exit_code(results)
    results["duration_s"] = round(time.monotonic() - started, 1)
    try:
        json_path, md_path = write_summary(results, report_dir)
        results["summary_files"] = [str(json_path), str(md_path)]
    except OSError as exc:
        results["notes"].append(f"Could not write summary report: {exc}")
    logger.info(
        "Export run completed in %.1fs. ok=%d failed=%d skipped=%d exit_code=%d",
        results["duration_s"],
        len(results["ok"]),
        len(results["failed"]),
        len(results["skipped"]),
        results["exit_code"],
    )
    close_file_handlers(logger)
    return results
