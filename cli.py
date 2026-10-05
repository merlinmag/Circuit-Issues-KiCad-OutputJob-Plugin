"""Headless entry point for CI.

Usage:
    python3 cli.py <project_dir | board.kicad_pcb> [--config PATH] [--only step1,step2] [--report-dir DIR]
    python3 -m <package>.cli ...   (when the plugin folder is importable as a package)

Exit codes: 0 = all OK, 1 = some export failed, 2 = ERC/DRC failed per checks.fail_on.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

_STANDALONE_PACKAGE = "circuit_issues_outputjob"


def _load_main():
    if __package__:
        from .modules.headless import main

        return main

    # Run as a plain script: expose this folder as a package without executing the
    # KiCad ActionPlugin code in __init__.py, then import the CLI module from it.
    root = Path(__file__).resolve().parent
    if _STANDALONE_PACKAGE not in sys.modules:
        package = types.ModuleType(_STANDALONE_PACKAGE)
        package.__path__ = [str(root)]  # type: ignore[attr-defined]
        package.__file__ = str(root / "__init__.py")
        sys.modules[_STANDALONE_PACKAGE] = package
    return importlib.import_module(f"{_STANDALONE_PACKAGE}.modules.headless").main


if __name__ == "__main__":
    sys.exit(_load_main()())
