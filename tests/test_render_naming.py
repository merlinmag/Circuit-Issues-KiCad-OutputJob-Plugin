"""Tests for render naming map."""

from __future__ import annotations

import unittest

from kicad_library_automation.modules.pcb_export import _cli_render_quality, default_render_map


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


if __name__ == "__main__":
    unittest.main()
