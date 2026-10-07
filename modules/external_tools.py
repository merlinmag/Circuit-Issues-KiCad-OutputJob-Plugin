"""Third-party integration hooks for KiCad plugins."""

from __future__ import annotations

import importlib
import os
import re
import shutil
import subprocess
import sys
import types
from pathlib import Path
from typing import List, Optional, Tuple


def _plugin_search_dirs() -> List[Path]:
    """Return likely KiCad plugin directories for KiCad 9/10 (Windows, Linux, macOS).

    ``KICAD_PLUGIN_DIRS`` (os.pathsep separated) replaces the built-in list when set.
    """
    override = os.environ.get("KICAD_PLUGIN_DIRS", "").strip()
    if override:
        return [Path(p).expanduser() for p in override.split(os.pathsep) if p.strip() and Path(p).expanduser().exists()]

    appdata = os.environ.get("APPDATA", "")
    home = Path.home()
    candidates: List[Path] = []
    if appdata:
        candidates += [
            Path(appdata) / "kicad" / "9.0" / "scripting" / "plugins",
            Path(appdata) / "kicad" / "10.0" / "scripting" / "plugins",
            Path(appdata) / "kicad" / "9.0" / "3rdparty" / "plugins",
            Path(appdata) / "kicad" / "10.0" / "3rdparty" / "plugins",
            Path(appdata) / "kicad" / "scripting" / "plugins",
        ]
    candidates += [
        home / "Documents" / "KiCad" / "9.0" / "scripting" / "plugins",
        home / "Documents" / "KiCad" / "10.0" / "scripting" / "plugins",
        home / "Documents" / "KiCad" / "9.0" / "3rdparty" / "plugins",
        home / "Documents" / "KiCad" / "10.0" / "3rdparty" / "plugins",
    ]
    for version in ("9.0", "10.0"):
        for kind in ("3rdparty", "scripting"):
            candidates.append(home / ".local" / "share" / "kicad" / version / kind / "plugins")
    return [p for p in candidates if p.exists()]


def _looks_like_target(path: Path, aliases: Tuple[str, ...]) -> bool:
    # Match the folder name only, so a search root like /opt/jlc-tools does not match every child.
    txt = path.name.lower()
    return any(alias in txt for alias in aliases)


def _candidate_package_dirs(aliases: Tuple[str, ...]) -> List[Path]:
    """Find plugin package directories by name heuristics."""
    found: List[Path] = []
    for root in _plugin_search_dirs():
        for child in sorted(root.iterdir()):
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


def _check_board_path(board_path: Path) -> Path:
    board_path = Path(board_path)
    if not board_path.exists():
        raise RuntimeError(f"Board file not found: {board_path}")
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


JLC_ALIASES = (
    "jlc",
    "fabrication_toolkit",
    "com_github_bennymeg_jlc-plugin-for-kicad",
    "jlcpcb_plugin",
)
IBOM_ALIASES = (
    "ibom",
    "interactivehtmlbom",
    "org_openscopeproject_interactivehtmlbom",
)
JLC_NOT_INSTALLED = "JLCPCB: plugin not installed"
IBOM_NOT_INSTALLED = "iBOM: plugin not installed"


def _tail(text: str, limit: int = 600) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else "..." + text[-limit:]


def _run_jlc_in_process(package_dir: Path, board_path: Path) -> Tuple[bool, str]:
    """Drive the JLC plugin's own non-interactive processing thread (no form, no browser)."""
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
    }
    # JLC 5.3.0 renamed NO_BACKUP_OPT to BACKUP_OPT; use the plugin's own default for either name.
    if hasattr(options_mod, "BACKUP_OPT"):
        default_options[options_mod.BACKUP_OPT] = True
    else:
        default_options[options_mod.NO_BACKUP_OPT] = False
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


def run_jlcpcb_plugin(board_path: Path, headless: bool = False) -> Tuple[bool, str]:
    """Run JLCPCB Fabrication Toolkit once without opening its form.

    In GUI mode the plugin runs inside KiCad's Python. In headless mode it runs in a
    separate Python process (``KICAD_PYTHON`` or the current interpreter, which must be
    able to import ``pcbnew``) so a crash in the plugin cannot take the CLI down.
    Returns ``(False, JLC_NOT_INSTALLED)`` when the plugin cannot be found.
    """
    package_dir = _find_package_dir(JLC_ALIASES)
    if package_dir is None:
        return False, JLC_NOT_INSTALLED

    try:
        board_path = _check_board_path(board_path)
        if not headless:
            return _run_jlc_in_process(package_dir, board_path)

        python = os.environ.get("KICAD_PYTHON", "").strip() or sys.executable
        cmd = [python, str(Path(__file__).resolve()), "jlc", str(package_dir), str(board_path)]
        proc = subprocess.run(cmd, cwd=str(board_path.parent), capture_output=True, text=True, check=False)  # noqa: S603
        lines = [ln for ln in (proc.stdout or "").splitlines() if ln.startswith("JLCPCB")]
        message = lines[-1] if lines else f"JLCPCB failed: rc={proc.returncode}; {_tail(proc.stderr or proc.stdout)}"
        return proc.returncode == 0, message
    except Exception as exc:  # noqa: BLE001
        return False, f"JLCPCB failed: {type(exc).__name__}: {exc}"


def ibom_cli_command() -> Optional[List[str]]:
    """Locate the InteractiveHtmlBom CLI: env ``IBOM_CLI``, ``generate_interactive_bom`` on PATH, or the plugin dir."""
    from_env = os.environ.get("IBOM_CLI", "").strip()
    if from_env:
        return [from_env]
    from_path = shutil.which("generate_interactive_bom")
    if from_path:
        return [from_path]
    package_dir = _find_package_dir(IBOM_ALIASES)
    if package_dir is not None:
        script = package_dir / "generate_interactive_bom.py"
        if script.exists():
            python = os.environ.get("KICAD_PYTHON", "").strip() or sys.executable
            return [python, str(script)]
    return None


def _run_ibom_cli(board_path: Path, dest_dir: Path) -> Tuple[bool, str]:
    base = ibom_cli_command()
    if base is None:
        return False, f"{IBOM_NOT_INSTALLED} (generate_interactive_bom not found; set IBOM_CLI)"
    dest_dir.mkdir(parents=True, exist_ok=True)
    cmd = base + [
        "--no-browser",
        "--dest-dir",
        str(dest_dir),
        "--name-format",
        "ibom",
        "--include-tracks",
        "--include-nets",
        "--blacklist-virtual",
        "--no-blacklist-empty-val",
        "--blacklist",
        "",
        str(board_path),
    ]
    before_latest, before_count = _snapshot_latest(dest_dir)
    proc = subprocess.run(cmd, cwd=str(board_path.parent), capture_output=True, text=True, check=False)  # noqa: S603
    after_latest, after_count = _snapshot_latest(dest_dir)
    if proc.returncode == 0 and (after_count > before_count or after_latest > before_latest):
        return True, f"iBOM: generated output in {dest_dir} (tracks and nets included, component filters disabled)"
    return False, f"iBOM failed: rc={proc.returncode}; {_tail(proc.stderr or proc.stdout) or 'no output generated'}"


def run_ibom_plugin(board_path: Path, headless: bool = False, dest_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """Generate iBOM output directly without opening the settings dialog.

    GUI mode imports the installed plugin in-process. Headless mode calls the
    ``generate_interactive_bom`` CLI with the same options and an explicit ``dest_dir``.
    """
    try:
        board_path = _check_board_path(board_path)
        if headless:
            return _run_ibom_cli(board_path, dest_dir or (board_path.parent / "bom"))

        package_dir = _find_package_dir(IBOM_ALIASES)
        if package_dir is None:
            return False, IBOM_NOT_INSTALLED

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
        if dest_dir is not None:
            config.bom_dest_dir = str(dest_dir)
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


def _main(argv: List[str]) -> int:
    """Worker entry used by headless JLC runs: ``external_tools.py jlc <package_dir> <board>``."""
    if len(argv) != 3 or argv[0] != "jlc":
        print("usage: external_tools.py jlc <package_dir> <board.kicad_pcb>", file=sys.stderr)
        return 2
    try:
        ok, message = _run_jlc_in_process(Path(argv[1]), _check_board_path(Path(argv[2])))
    except Exception as exc:  # noqa: BLE001
        ok, message = False, f"JLCPCB failed: {type(exc).__name__}: {exc}"
    print(message, flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
