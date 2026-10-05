"""Subprocess helpers for invoking kicad-cli commands."""

from __future__ import annotations

import os
import subprocess
import shutil
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple


NEEDS_DISPLAY_MESSAGE = "needs display/xvfb"


@dataclass
class CommandResult:
    ok: bool
    cmd: List[str]
    stdout: str
    stderr: str
    return_code: int
    output_path: Optional[Path] = None


def kicad_cli_executable() -> str:
    """Return kicad-cli path.

    Lookup order: env ``KICAD_CLI``, ``PATH``, Windows install paths, ``/usr/bin/kicad-cli``.
    """
    from_env = os.environ.get("KICAD_CLI", "").strip()
    if from_env:
        return from_env

    from_path = shutil.which("kicad-cli")
    if from_path:
        return from_path

    candidates = [
        Path("C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"),
        Path("C:/Program Files/KiCad/9.0/bin/kicad-cli.exe"),
        Path("/usr/bin/kicad-cli"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return "kicad-cli"


def display_prefix() -> Tuple[List[str], Optional[str]]:
    """Return (command prefix, problem) for tools that need an X display (3D renders).

    On Linux without ``DISPLAY``/``WAYLAND_DISPLAY`` the command is wrapped in
    ``xvfb-run -a`` when available. If neither is available the prefix is empty and
    ``problem`` explains why the command may fail.
    """
    if not sys.platform.startswith("linux"):
        return [], None
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return [], None
    xvfb = shutil.which("xvfb-run")
    if xvfb:
        return [xvfb, "-a"], None
    return [], NEEDS_DISPLAY_MESSAGE


def run_command(cmd: List[str], cwd: Path, timeout: Optional[float] = None) -> CommandResult:
    """Run command and capture full output without raising."""
    creationflags = 0
    startupinfo = None
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        # Avoid opening transient console windows when called from KiCad GUI.
        creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0

    try:
        proc = subprocess.run(  # noqa: S603
            cmd,
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
            startupinfo=startupinfo,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        return CommandResult(ok=False, cmd=cmd, stdout="", stderr=f"Executable not found: {exc.filename or cmd[0]}", return_code=127)
    except subprocess.TimeoutExpired:
        return CommandResult(ok=False, cmd=cmd, stdout="", stderr=f"Timed out after {timeout}s", return_code=124)
    except OSError as exc:
        return CommandResult(ok=False, cmd=cmd, stdout="", stderr=f"{type(exc).__name__}: {exc}", return_code=126)

    return CommandResult(
        ok=proc.returncode == 0,
        cmd=cmd,
        stdout=(proc.stdout or "").strip(),
        stderr=(proc.stderr or "").strip(),
        return_code=proc.returncode,
    )
