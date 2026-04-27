"""Subprocess helpers for invoking kicad-cli commands."""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CommandResult:
    ok: bool
    cmd: List[str]
    stdout: str
    stderr: str
    return_code: int
    output_path: Optional[Path] = None


def kicad_cli_executable() -> str:
    """Return kicad-cli path from PATH or common KiCad install locations."""
    from_path = shutil.which("kicad-cli")
    if from_path:
        return from_path

    candidates = [
        Path("C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"),
        Path("C:/Program Files/KiCad/9.0/bin/kicad-cli.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return "kicad-cli"


def run_command(cmd: List[str], cwd: Path) -> CommandResult:
    """Run command and capture full output without raising."""
    creationflags = 0
    startupinfo = None
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        # Avoid opening transient console windows when called from KiCad GUI.
        creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0

    proc = subprocess.run(  # noqa: S603
        cmd,
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        creationflags=creationflags,
        startupinfo=startupinfo,
    )
    return CommandResult(
        ok=proc.returncode == 0,
        cmd=cmd,
        stdout=proc.stdout.strip(),
        stderr=proc.stderr.strip(),
        return_code=proc.returncode,
    )
