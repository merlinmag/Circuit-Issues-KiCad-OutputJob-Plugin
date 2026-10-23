"""Tests for the schematic vs. PCB DNP / BOM / position attribute check."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from . import _bootstrap  # noqa: F401  (python -m unittest discover -s tests -t .)
except ImportError:
    import _bootstrap  # noqa: F401  (python -m unittest discover -s tests)

from kicad_library_automation.modules.config_manager import load_defaults
from kicad_library_automation.modules.dnp_check import collect_schematic_parts, parse_sexpr, run_dnp_check
from kicad_library_automation.modules.pipeline import run_export_pipeline
from kicad_library_automation.ui.dialog import _build_summary_text

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ci_fixture"
R1_SYMBOL = '(symbol (lib_id "Device:R") (at 101.6 81.28 0) (unit 1) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)'
R1_FOOTPRINT = '(path "/ed22662c-d8d1-5e9c-8571-ead66a437b16/b7988e84-4ab9-589b-8158-8a7bb16e9e3b") (sheetname "/LEDs/") (sheetfile "leds.kicad_sch") (attr smd)'


class DnpCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.project = Path(self._td.name) / "ci_fixture"
        shutil.copytree(FIXTURE, self.project)
        self.sch = self.project / "ci_fixture.kicad_sch"
        self.pcb = self.project / "ci_fixture.kicad_pcb"

    def tearDown(self) -> None:
        self._td.cleanup()

    def _replace(self, path: Path, old: str, new: str) -> None:
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count(old), 1, old)
        path.write_text(text.replace(old, new), encoding="utf-8")

    def _depop_r1_in_schematic(self, pos_flag: bool = True) -> None:
        # Same state as a symbol with DNP + exclude from BOM + exclude from position files ticked.
        new = R1_SYMBOL.replace("(in_bom yes)", "(in_bom no)").replace("(dnp no)", "(dnp yes)")
        if pos_flag:
            new = new.replace("(on_board yes)", "(on_board yes) (in_pos_files no)")
        self._replace(self.project / "leds.kicad_sch", R1_SYMBOL, new)

    def test_fixture_matches(self) -> None:
        summary = run_dnp_check(self.sch, self.pcb)
        self.assertEqual(summary["errors"], 0)
        self.assertEqual(summary["compared"], 5)
        self.assertEqual(summary["dnp_parts"], 0)

    def test_hierarchy_is_walked_and_power_symbols_skipped(self) -> None:
        parts = collect_schematic_parts(self.sch)
        self.assertEqual(sorted(parts), ["D1", "D2", "J1", "R1", "R2"])
        self.assertEqual(parts["R1"]["sheet"], "leds.kicad_sch")

    def test_depopulated_in_schematic_but_not_on_pcb(self) -> None:
        self._depop_r1_in_schematic()
        summary = run_dnp_check(self.sch, self.pcb)
        self.assertEqual(summary["dnp_references"], ["R1"])
        self.assertEqual(summary["mismatched_parts"], 1)
        attrs = {v["attribute"]: v for v in summary["violations"]}
        self.assertEqual(sorted(attrs), ["dnp", "exclude_from_bom", "exclude_from_pos_files"])
        dnp = attrs["dnp"]
        self.assertEqual((dnp["schematic"], dnp["pcb"], dnp["severity"]), (True, False, "error"))
        self.assertIn("R1: 'Do not populate' is DNP in schematic but populated on PCB", dnp["description"])
        self.assertEqual(dnp["location"], "(112, 104)")

    def test_old_schematic_without_pos_flag_skips_pos_comparison(self) -> None:
        self._depop_r1_in_schematic(pos_flag=False)
        summary = run_dnp_check(self.sch, self.pcb)
        self.assertEqual(sorted(v["attribute"] for v in summary["violations"]), ["dnp", "exclude_from_bom"])

    def test_depopulated_on_pcb_only(self) -> None:
        self._replace(self.pcb, R1_FOOTPRINT, R1_FOOTPRINT.replace("(attr smd)", "(attr smd dnp)"))
        summary = run_dnp_check(self.sch, self.pcb)
        self.assertEqual([(v["reference"], v["attribute"], v["schematic"], v["pcb"]) for v in summary["violations"]],
                         [("R1", "dnp", False, True)])

    def test_synced_dnp_passes(self) -> None:
        self._depop_r1_in_schematic()
        self._replace(
            self.pcb, R1_FOOTPRINT,
            R1_FOOTPRINT.replace("(attr smd)", "(attr smd exclude_from_pos_files exclude_from_bom dnp)"),
        )
        summary = run_dnp_check(self.sch, self.pcb)
        self.assertEqual(summary["errors"], 0)
        self.assertEqual(summary["dnp_parts"], 1)

    def _pipeline(self, fail_on: str = "error") -> dict:
        cfg = load_defaults()
        cfg["checks"]["fail_on"] = fail_on
        results = run_export_pipeline(self.pcb, cfg, headless=True, only=["dnp"], report_dir=self.project / "reports")
        results["summary_md"] = (self.project / "reports" / "summary.md").read_text(encoding="utf-8")
        results["summary_json"] = json.loads((self.project / "reports" / "summary.json").read_text(encoding="utf-8"))
        return results

    def test_pipeline_mismatch_gives_exit_code_2(self) -> None:
        self._depop_r1_in_schematic()
        results = self._pipeline()
        self.assertEqual(results["exit_code"], 2)
        self.assertIn("R1", results["failed"]["dnp"])
        self.assertEqual(results["summary_json"]["checks"]["dnp"]["errors"], 3)
        self.assertIn("- DNP: 3 schematic/PCB mismatches in 1 parts", results["summary_md"])
        self.assertIn("is DNP in schematic but populated on PCB", results["summary_md"])
        self.assertIn("DNP mismatches", _build_summary_text(results))

    def test_pipeline_fail_on_never_reports_only(self) -> None:
        self._depop_r1_in_schematic()
        results = self._pipeline("never")
        self.assertEqual(results["exit_code"], 0)
        self.assertIn("dnp", results["ok"])

    def test_pipeline_clean_project_passes(self) -> None:
        results = self._pipeline()
        self.assertEqual(results["exit_code"], 0)
        self.assertIn("schematic and PCB match", results["ok"]["dnp"])


class SchematicReferenceTests(unittest.TestCase):
    def test_reused_sheet_gives_one_reference_per_instance(self) -> None:
        sch = (
            '(kicad_sch (version 20250114) (generator "eeschema")'
            ' (symbol (lib_id "Device:R") (in_bom yes) (on_board yes) (dnp yes)'
            '  (property "Reference" "R?" (at 0 0 0))'
            '  (instances'
            '   (project "other" (path "/x/y" (reference "R99") (unit 1)))'
            '   (project "board" (path "/a/b" (reference "R10") (unit 1)) (path "/a/c" (reference "R20") (unit 1))))))'
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "board.kicad_sch"
            path.write_text(sch, encoding="utf-8")
            parts = collect_schematic_parts(path)
        self.assertEqual(sorted(parts), ["R10", "R20"])
        self.assertTrue(parts["R10"]["dnp"])

    def test_parser_handles_escaped_quotes(self) -> None:
        tree = parse_sexpr('(a (property "Value" "10\\" \\\\ (x)") b)')
        self.assertEqual(tree, ["a", ["property", "Value", '10" \\ (x)'], "b"])


if __name__ == "__main__":
    unittest.main()
