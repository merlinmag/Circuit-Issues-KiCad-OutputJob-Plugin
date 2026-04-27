"""Third-party integration hooks for KiCad plugins."""

from __future__ import annotations

import importlib
import os
import re
import sys
import types
from pathlib import Path
from typing import List, Optional, Tuple


def _plugin_search_dirs() -> List[Path]:
    """Return likely KiCad plugin directories for KiCad 9/10 on Windows."""
    appdata = os.environ.get("APPDATA", "")
    home = Path.home()
    candidates = [
        Path(appdata) / "kicad" / "9.0" / "scripting" / "plugins",
        Path(appdata) / "kicad" / "10.0" / "scripting" / "plugins",
        Path(appdata) / "kicad" / "9.0" / "3rdparty" / "plugins",
        Path(appdata) / "kicad" / "10.0" / "3rdparty" / "plugins",
        Path(appdata) / "kicad" / "scripting" / "plugins",
        home / "Documents" / "KiCad" / "9.0" / "scripting" / "plugins",
        home / "Documents" / "KiCad" / "10.0" / "scripting" / "plugins",
        home / "Documents" / "KiCad" / "9.0" / "3rdparty" / "plugins",
        home / "Documents" / "KiCad" / "10.0" / "3rdparty" / "plugins",
    ]
    return [p for p in candidates if p.exists()]


def _looks_like_target(path: Path, aliases: Tuple[str, ...]) -> bool:
    txt = str(path).lower()
    return any(alias in txt for alias in aliases)


def _candidate_package_dirs(aliases: Tuple[str, ...]) -> List[Path]:
    """Find plugin package directories by name heuristics."""
    found: List[Path] = []
    for root in _plugin_search_dirs():
        for child in root.iterdir():
            if child.is_dir() and _looks_like_target(child, aliases):
                found.append(child)
    # Keep order stable while removing duplicates.
    return list(dict.fromkeys(found))


def _module_name_from_path(path: Path) -> str:
    """Build a valid synthetic module name from a path."""
    base = path.name
    safe = re.sub(r"[^0-9a-zA-Z_]", "_", base)
    if safe and safe[0].isdigit():
        safe = f"m_{safe}"
    return f"kicad_ext_{safe}_{abs(hash(str(path))) % 100000}"


def _ensure_package(package_dir: Path) -> str:
    """Register a synthetic package name for a plugin directory without running __init__.py."""
    package_name = _module_name_from_path(package_dir)
    if package_name in sys.modules:
        return package_name
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_dir)]
    package.__file__ = str(package_dir / "__init__.py")
    package.__package__ = package_name
    sys.modules[package_name] = package
    return package_name


def _find_package_dir(aliases: Tuple[str, ...]) -> Optional[Path]:
    candidates = _candidate_package_dirs(aliases)
    if not candidates:
        return None
    for candidate in candidates:
        if "10.0" in str(candidate):
            return candidate
    return candidates[0]


def _current_board_path() -> Path:
    try:
        import pcbnew  # type: ignore
    except ImportError:
        raise RuntimeError("pcbnew module unavailable")
    board = pcbnew.GetBoard()
    if board is None:
        raise RuntimeError("No active KiCad board")
    board_path = Path(board.GetFileName())
    if not board_path.exists():
        raise RuntimeError(f"Active board path not found: {board_path}")
    return board_path


def _import_plugin_submodule(package_dir: Path, relative_name: str):
    package_name = _ensure_package(package_dir)
    return importlib.import_module(f"{package_name}.{relative_name}")


def _snapshot_latest(path: Path) -> Tuple[float, int]:
    if not path.exists():
        return (0.0, 0)
    latest = 0.0
    count = 0
    for child in path.rglob("*"):
        if child.is_file():
            count += 1
            latest = max(latest, child.stat().st_mtime)
    return latest, count


def run_jlcpcb_plugin() -> Tuple[bool, str]:
    """Run JLCPCB Fabrication Toolkit once without opening its form."""
    package_dir = _find_package_dir(
        (
            "jlc",
            "fabrication_toolkit",
            "com_github_bennymeg_jlc-plugin-for-kicad",
            "jlcpcb_plugin",
        )
    )
    if package_dir is None:
        return False, "JLCPCB: plugin not installed"

    try:
        board_path = _current_board_path()
        thread_mod = _import_plugin_submodule(package_dir, "thread")
        options_mod = _import_plugin_submodule(package_dir, "options")
        utils_mod = _import_plugin_submodule(package_dir, "utils")
        config_mod = _import_plugin_submodule(package_dir, "config")

        default_options = {
            options_mod.EXTRA_LAYERS: "",
            options_mod.ALL_ACTIVE_LAYERS_OPT: False,
            options_mod.ARCHIVE_NAME: "",
            options_mod.EXTEND_EDGE_CUT_OPT: False,
            options_mod.ALTERNATIVE_EDGE_CUT_OPT: False,
            options_mod.AUTO_TRANSLATE_OPT: True,
            options_mod.AUTO_FILL_OPT: True,
            options_mod.EXCLUDE_DNP_OPT: False,
            options_mod.OPEN_BROWSER_OPT: False,
            options_mod.NO_BACKUP_OPT: False,
        }
        options = utils_mod.load_user_options(default_options)
        options[options_mod.OPEN_BROWSER_OPT] = False

        output_dir = board_path.parent / config_mod.outputFolder
        before_latest, before_count = _snapshot_latest(output_dir)
        worker = thread_mod.ProcessThread(None, options, cli=str(board_path), openBrowser=False, nonInteractive=True)
        worker.join()
        after_latest, after_count = _snapshot_latest(output_dir)
        if after_count > before_count or after_latest > before_latest:
            return True, f"JLCPCB: generated output in {output_dir}"
        if output_dir.exists():
            return True, f"JLCPCB: output available in {output_dir}"
        return False, f"JLCPCB: no output generated in {output_dir}"
    except Exception as exc:  # noqa: BLE001
        return False, f"JLCPCB failed: {type(exc).__name__}: {exc}"


def run_ibom_plugin() -> Tuple[bool, str]:
    """Generate iBOM output directly without opening the settings dialog."""
    package_dir = _find_package_dir(
        (
            "ibom",
            "interactivehtmlbom",
            "org_openscopeproject_interactivehtmlbom",
        )
    )
    if package_dir is None:
        return False, "iBOM: plugin not installed"

    try:
        board_path = _current_board_path()
        ibom_mod = _import_plugin_submodule(package_dir, "core.ibom")
        config_mod = _import_plugin_submodule(package_dir, "core.config")
        ecad_mod = _import_plugin_submodule(package_dir, "ecad")
        version_mod = _import_plugin_submodule(package_dir, "version")

        logger = ibom_mod.Logger(cli=True)
        config = config_mod.Config(version_mod.version, str(board_path.parent))
        config.load_from_ini()
        config.include_tracks = True
        config.include_nets = True
        config.bom_name_format = "ibom"
        config.component_blacklist = []
        config.blacklist_virtual = True
        config.blacklist_empty_val = False
        config.open_browser = False
        parser = ecad_mod.get_parser_by_extension(str(board_path.resolve()), config, logger)

        output_dir = board_path.parent / config.bom_dest_dir
        before_latest, before_count = _snapshot_latest(output_dir)
        ibom_mod.main(parser, config, logger)
        after_latest, after_count = _snapshot_latest(output_dir)
        if after_count > before_count or after_latest > before_latest:
            return True, f"iBOM: generated output in {output_dir} (tracks and nets included, component filters disabled)"
        return False, f"iBOM: no output generated in {output_dir}"
    except Exception as exc:  # noqa: BLE001
        return False, f"iBOM failed: {type(exc).__name__}: {exc}"
