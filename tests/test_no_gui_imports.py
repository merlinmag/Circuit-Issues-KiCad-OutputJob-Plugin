"""The package and modules/ must be usable without wx / pcbnew (headless CLI)."""

from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class NoGuiImportTests(unittest.TestCase):
    def test_modules_never_import_wx_or_pcbnew(self) -> None:
        for path in sorted((ROOT / "modules").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                for name in names:
                    self.assertNotIn(name.split(".")[0], ("wx", "pcbnew"), f"{path.name} imports {name}")

    def test_importing_package_and_cli_loads_no_gui_modules(self) -> None:
        code = (
            "import sys, importlib.util\n"
            f"root = {str(ROOT)!r}\n"
            "spec = importlib.util.spec_from_file_location('plugin_pkg', root + '/__init__.py', submodule_search_locations=[root])\n"
            "mod = importlib.util.module_from_spec(spec); sys.modules['plugin_pkg'] = mod; spec.loader.exec_module(mod)\n"
            "import plugin_pkg.cli, plugin_pkg.modules.headless, plugin_pkg.modules.pipeline\n"
            "assert hasattr(mod, 'run_export_pipeline')\n"
            "bad = sorted(m for m in sys.modules if m.split('.')[0] in ('wx', 'pcbnew') or m.startswith('plugin_pkg.ui'))\n"
            "print(','.join(bad))\n"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")

    def test_cli_script_help_runs(self) -> None:
        proc = subprocess.run([sys.executable, str(ROOT / "cli.py"), "--help"], capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--report-dir", proc.stdout)


if __name__ == "__main__":
    unittest.main()
