"""Tests for plugin discovery and the headless JLC / iBOM paths (with fake plugins)."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from . import _bootstrap  # noqa: F401  (python -m unittest discover -s tests -t .)
except ImportError:
    import _bootstrap  # noqa: F401  (python -m unittest discover -s tests)

from kicad_library_automation.modules import external_tools

FAKE_JLC = {
    "options.py": (
        "EXTRA_LAYERS = 'e'\nALL_ACTIVE_LAYERS_OPT = 'a'\nARCHIVE_NAME = 'n'\nEXTEND_EDGE_CUT_OPT = 'x'\n"
        "ALTERNATIVE_EDGE_CUT_OPT = 'y'\nAUTO_TRANSLATE_OPT = 't'\nAUTO_FILL_OPT = 'f'\nEXCLUDE_DNP_OPT = 'd'\n"
        "OPEN_BROWSER_OPT = 'b'\nNO_BACKUP_OPT = 'k'\n"
    ),
    "utils.py": "def load_user_options(defaults):\n    return dict(defaults)\n",
    "config.py": "outputFolder = 'production'\n",
    "thread.py": (
        "import os\n"
        "class ProcessThread:\n"
        "    def __init__(self, wx, options, cli, openBrowser, nonInteractive):\n"
        "        assert wx is None and openBrowser is False and nonInteractive is True and options['b'] is False\n"
        "        out = os.path.join(os.path.dirname(cli), 'production')\n"
        "        os.makedirs(out, exist_ok=True)\n"
        "        open(os.path.join(out, 'GERBER-board.zip'), 'w').write('zip')\n"
        "    def join(self):\n"
        "        pass\n"
    ),
    # Must never be executed: the plugin's __init__ would register a KiCad action.
    "__init__.py": "raise RuntimeError('plugin __init__ must not run')\n",
}


class ExternalToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.plugins = self.root / "plugins"
        self.plugins.mkdir()
        self.project = self.root / "project"
        self.project.mkdir()
        self.board = self.project / "board.kicad_pcb"
        self.board.write_text("(kicad_pcb)", encoding="utf-8")
        self.env = patch.dict(os.environ, {"KICAD_PLUGIN_DIRS": str(self.plugins)})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self._td.cleanup()

    def _install_fake_jlc(self) -> Path:
        pkg = self.plugins / "com_github_bennymeg_JLC-Plugin-for-KiCad"
        pkg.mkdir()
        for name, text in FAKE_JLC.items():
            (pkg / name).write_text(text, encoding="utf-8")
        return pkg

    def test_plugin_dirs_env_override_replaces_defaults(self) -> None:
        self.assertEqual(external_tools._plugin_search_dirs(), [self.plugins])

    def test_folder_name_matching_ignores_parent_path(self) -> None:
        (self.plugins / "unrelated_plugin").mkdir()
        with patch.dict(os.environ, {"KICAD_PLUGIN_DIRS": str(self.plugins)}):
            self.assertIsNone(external_tools._find_package_dir(("plugins",)))

    def test_jlc_not_installed(self) -> None:
        self.assertEqual(external_tools.run_jlcpcb_plugin(self.board, headless=True), (False, external_tools.JLC_NOT_INSTALLED))

    def test_jlc_headless_runs_plugin_thread_in_subprocess(self) -> None:
        self._install_fake_jlc()
        ok, message = external_tools.run_jlcpcb_plugin(self.board, headless=True)
        self.assertTrue(ok, message)
        self.assertIn("production", message)
        self.assertTrue((self.project / "production" / "GERBER-board.zip").exists())

    def test_jlc_missing_board_fails(self) -> None:
        self._install_fake_jlc()
        ok, message = external_tools.run_jlcpcb_plugin(self.project / "missing.kicad_pcb", headless=True)
        self.assertFalse(ok)
        self.assertIn("Board file not found", message)

    @unittest.skipIf(sys.platform.startswith("win"), "uses a POSIX shell script as fake CLI")
    def test_ibom_headless_uses_cli_with_gui_options(self) -> None:
        args_file = self.root / "args.txt"
        fake = self.root / "fake_ibom"
        fake.write_text(
            "#!/bin/sh\n"
            f'printf "%s\\n" "$@" > "{args_file}"\n'
            'while [ "$1" != "--dest-dir" ]; do shift; done\n'
            'mkdir -p "$2" && echo "<html/>" > "$2/ibom.html"\n',
            encoding="utf-8",
        )
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        dest = self.project / "bom"
        with patch.dict(os.environ, {"IBOM_CLI": str(fake)}):
            ok, message = external_tools.run_ibom_plugin(self.board, headless=True, dest_dir=dest)
        self.assertTrue(ok, message)
        self.assertTrue((dest / "ibom.html").exists())
        args = args_file.read_text(encoding="utf-8").splitlines()
        for flag in ("--no-browser", "--include-tracks", "--include-nets", "--blacklist-virtual", "--no-blacklist-empty-val"):
            self.assertIn(flag, args)
        self.assertEqual(args[args.index("--name-format") + 1], "ibom")
        self.assertEqual(args[args.index("--dest-dir") + 1], str(dest))
        self.assertEqual(args[-1], str(self.board))

    def test_ibom_headless_without_cli_fails_clearly(self) -> None:
        with patch.dict(os.environ, {"IBOM_CLI": ""}), patch.object(external_tools.shutil, "which", return_value=None):
            ok, message = external_tools.run_ibom_plugin(self.board, headless=True)
        self.assertFalse(ok)
        self.assertIn("generate_interactive_bom not found", message)


if __name__ == "__main__":
    unittest.main()
