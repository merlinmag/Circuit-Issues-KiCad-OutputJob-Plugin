"""Make the repository importable as the ``kicad_library_automation`` package.

The tests import the plugin by that package name, whatever the checkout folder is
called. Importing it also executes ``__init__.py`` outside KiCad, which must work
without wx/pcbnew.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "kicad_library_automation"

if PACKAGE not in sys.modules:
    _spec = importlib.util.spec_from_file_location(PACKAGE, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    assert _spec is not None and _spec.loader is not None
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[PACKAGE] = _module
    _spec.loader.exec_module(_module)
