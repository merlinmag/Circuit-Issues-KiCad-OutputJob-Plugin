"""Tests for run summary formatting."""

from __future__ import annotations

import unittest

from kicad_library_automation.ui.dialog import _build_summary_text


class SummaryDialogTests(unittest.TestCase):
    def test_summary_text_includes_success_and_fail_sections(self) -> None:
        text = _build_summary_text(
            {
                "ok": {"schematic_pdf": "doc/schematics/board_SCH.pdf"},
                "failed": {"ibom": "plugin not found"},
                "notes": ["KiCad 10 mode"],
            }
        )
        self.assertIn("Successful steps: 1", text)
        self.assertIn("Failed steps: 1", text)
        self.assertIn("Success:", text)
        self.assertIn("Failed:", text)
        self.assertIn("Notes:", text)


if __name__ == "__main__":
    unittest.main()
