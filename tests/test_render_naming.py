"""Tests for render naming map."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from kicad_library_automation.modules.pcb_export import _cli_render_quality, default_render_map, generate_render


class RenderNamingTests(unittest.TestCase):
    def test_render_quality_mapping_uses_valid_cli_values(self) -> None:
        self.assertEqual(_cli_render_quality("low"), "basic")
        self.assertEqual(_cli_render_quality("medium"), "user")
        self.assertEqual(_cli_render_quality("high"), "high")

    def test_default_render_map_uses_expected_suffixes(self) -> None:
        m = default_render_map("myboard", {"iso1_az": 45, "iso1_el": 35, "iso2_az": 225, "iso2_el": 35})
        self.assertEqual(m["top"][3], "myboard_PCBA_TOP.png")
        self.assertEqual(m["bottom"][3], "myboard_PCBA_BOTTOM.png")
        self.assertEqual(m["left"][3], "myboard_PCBA_LEFT.png")
        self.assertEqual(m["right"][3], "myboard_PCBA_RIGHT.png")
        self.assertEqual(m["iso1"][3], "myboard_PCBA_ISO1.png")
        self.assertEqual(m["iso2"][3], "myboard_PCBA_ISO2.png")

    def test_generate_render_uses_board_stackup_colors(self) -> None:
        board_file = Path("C:/tmp/example.kicad_pcb")
        output_path = Path("C:/tmp/example.png")

        with patch("kicad_library_automation.modules.pcb_export.kicad_cli_executable", return_value="kicad-cli"), patch(
            "kicad_library_automation.modules.pcb_export.run_command"
        ) as run_command:
            run_command.return_value.ok = True
            run_command.return_value.return_code = 0
            run_command.return_value.stdout = ""
            run_command.return_value.stderr = ""

            generate_render(board_file, output_path, side="top")

        cmd = run_command.call_args.args[0]
        self.assertIn("--use-board-stackup-colors", cmd)


if __name__ == "__main__":
    unittest.main()
