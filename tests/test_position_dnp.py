"""Position/PNP export leaves DNP footprints out unless ``exports.position_include_dnp`` is set."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import _bootstrap  # noqa: F401
from tests.test_integration_cli import FIXTURE, _kicad_cli

from kicad_library_automation.modules import pcb_export
from kicad_library_automation.modules.command_runner import CommandResult
from kicad_library_automation.modules.config_manager import load_defaults, validate_config


class PositionCommandTest(unittest.TestCase):
    def _cmd(self, **kwargs) -> list:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(pcb_export, "run_command") as run:
            run.return_value = CommandResult(ok=True, cmd=[], stdout="", stderr="", return_code=0)
            pcb_export.generate_position_files(Path(tmp) / "b.kicad_pcb", Path(tmp) / "pos" / "b_POS.csv", **kwargs)
            return run.call_args[0][0]

    def test_excludes_dnp_by_default(self) -> None:
        self.assertIn("--exclude-dnp", self._cmd())

    def test_include_dnp(self) -> None:
        self.assertNotIn("--exclude-dnp", self._cmd(exclude_dnp=False))

    def test_default_config_excludes_dnp(self) -> None:
        self.assertIs(load_defaults()["exports"]["position_include_dnp"], False)

    def test_config_rejects_non_bool(self) -> None:
        cfg = load_defaults()
        cfg["exports"]["position_include_dnp"] = "yes"
        with self.assertRaises(ValueError):
            validate_config(cfg, Path("."))


@unittest.skipUnless(_kicad_cli(), "kicad-cli not found")
class PositionExportDnpTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.board = Path(self._tmp.name) / "ci_fixture.kicad_pcb"
        text = (FIXTURE / "ci_fixture.kicad_pcb").read_text(encoding="utf-8")
        # Mark R2 as "Do not populate" on the board.
        marker = '(sheetfile "leds.kicad_sch") (attr smd)'
        r2 = text.index('(property "Reference" "R2"')
        at = text.index(marker, r2)
        text = text[:at] + '(sheetfile "leds.kicad_sch") (attr smd dnp)' + text[at + len(marker):]
        self.board.write_text(text, encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _refs(self, exclude_dnp: bool) -> set:
        out = Path(self._tmp.name) / f"pos_{exclude_dnp}.csv"
        res = pcb_export.generate_position_files(self.board, out, exclude_dnp=exclude_dnp)
        self.assertTrue(res.ok, res.stderr)
        with out.open(encoding="utf-8") as f:
            return {row["Ref"] for row in csv.DictReader(f)}

    def test_dnp_excluded(self) -> None:
        refs = self._refs(exclude_dnp=True)
        self.assertNotIn("R2", refs)
        self.assertIn("R1", refs)

    def test_dnp_included(self) -> None:
        self.assertIn("R2", self._refs(exclude_dnp=False))


if __name__ == "__main__":
    unittest.main()
