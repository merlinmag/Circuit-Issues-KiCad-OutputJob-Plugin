"""Tests for BOM generation and how the pipeline records BOM failures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from . import _bootstrap  # noqa: F401  (python -m unittest discover -s tests -t .)
except ImportError:
    import _bootstrap  # noqa: F401  (python -m unittest discover -s tests)

from kicad_library_automation.modules.bom_generator import generate_bom_files
from kicad_library_automation.modules.command_runner import CommandResult
from kicad_library_automation.modules.config_manager import load_defaults
from kicad_library_automation.modules.pipeline import run_export_pipeline

BOM_RUN = "kicad_library_automation.modules.bom_generator.run_command"


def _failed(cmd, cwd, timeout=None):  # noqa: ANN001
    return CommandResult(ok=False, cmd=cmd, stdout="", stderr="Failed to load schematic", return_code=3)


def _writes_output(cmd, cwd, timeout=None):  # noqa: ANN001
    out = Path(cmd[cmd.index("--output") + 1])
    out.write_text('"Reference","Value"\n"R1","1k"\n', encoding="utf-8")
    return CommandResult(ok=True, cmd=cmd, stdout="", stderr="", return_code=0)


def _ok_without_output(cmd, cwd, timeout=None):  # noqa: ANN001
    return CommandResult(ok=True, cmd=cmd, stdout="", stderr="", return_code=0)


class BomGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.sch = self.root / "board.kicad_sch"
        self.sch.write_text("(kicad_sch)", encoding="utf-8")
        self.out_dir = self.root / "bom"

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_collapsed_groups_by_value_footprint_mpn_with_quantity(self) -> None:
        with patch(BOM_RUN, side_effect=_writes_output) as run:
            res = generate_bom_files(self.sch, "board", self.out_dir, collapsed=True, line_by_line=False)
        self.assertTrue(res["collapsed"].ok)
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[cmd.index("--group-by") + 1], "Value,Footprint,MPN")
        self.assertIn("${QUANTITY}", cmd[cmd.index("--fields") + 1])
        self.assertIn("Quantity", cmd[cmd.index("--labels") + 1])
        self.assertTrue((self.out_dir / "board_BOM_collapsed.csv").exists())

    def test_line_by_line_has_one_row_per_reference(self) -> None:
        with patch(BOM_RUN, side_effect=_writes_output) as run:
            generate_bom_files(self.sch, "board", self.out_dir, collapsed=False, line_by_line=True)
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[cmd.index("--group-by") + 1], "")
        self.assertEqual(cmd[cmd.index("--output") + 1], str(self.out_dir / "board_BOM.csv"))

    def test_failure_writes_no_file_and_removes_stale_output(self) -> None:
        self.out_dir.mkdir()
        stale = self.out_dir / "board_BOM.csv"
        stale.write_text("old run", encoding="utf-8")
        with patch(BOM_RUN, side_effect=_failed):
            res = generate_bom_files(self.sch, "board", self.out_dir, collapsed=True, line_by_line=True)
        self.assertFalse(res["line_by_line"].ok)
        self.assertFalse(res["collapsed"].ok)
        self.assertEqual(list(self.out_dir.iterdir()), [])

    def test_success_without_output_file_is_a_failure(self) -> None:
        with patch(BOM_RUN, side_effect=_ok_without_output):
            res = generate_bom_files(self.sch, "board", self.out_dir, collapsed=False, line_by_line=True)
        self.assertFalse(res["line_by_line"].ok)

    def test_pipeline_records_bom_failure(self) -> None:
        board = self.root / "board.kicad_pcb"
        board.write_text("(kicad_pcb)", encoding="utf-8")
        cfg = load_defaults()
        with patch(BOM_RUN, side_effect=_failed):
            results = run_export_pipeline(board, cfg, headless=True, only=["bom"], report_dir=self.root / "reports")
        self.assertIn("bom_line_by_line", results["failed"])
        self.assertIn("bom_collapsed", results["failed"])
        self.assertNotIn("bom", results["ok"])
        self.assertIn("Failed to load schematic", results["failed"]["bom_collapsed"])
        self.assertEqual(results["exit_code"], 1)
        statuses = {s["name"]: s["status"] for s in results["steps"]}
        self.assertEqual(statuses, {"bom_line_by_line": "failed", "bom_collapsed": "failed"})

    def test_pipeline_records_bom_ok_only_when_written(self) -> None:
        board = self.root / "board.kicad_pcb"
        board.write_text("(kicad_pcb)", encoding="utf-8")
        with patch(BOM_RUN, side_effect=_writes_output):
            results = run_export_pipeline(board, load_defaults(), headless=True, only=["bom"], report_dir=self.root / "r")
        self.assertEqual(results["exit_code"], 0)
        self.assertEqual(sorted(results["ok"]), ["bom_collapsed", "bom_line_by_line"])


if __name__ == "__main__":
    unittest.main()
