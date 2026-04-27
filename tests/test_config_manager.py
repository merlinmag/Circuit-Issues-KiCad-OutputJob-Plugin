"""Tests for config manager."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kicad_library_automation.modules.config_manager import deep_merge, load_config, resolve_relative_output, save_config


class ConfigManagerTests(unittest.TestCase):
    def test_deep_merge_overrides_nested(self) -> None:
        base = {"a": 1, "b": {"x": 1, "y": 2}}
        over = {"b": {"y": 99}, "c": 3}
        got = deep_merge(base, over)
        self.assertEqual(got["a"], 1)
        self.assertEqual(got["b"]["x"], 1)
        self.assertEqual(got["b"]["y"], 99)
        self.assertEqual(got["c"], 3)

    def test_resolve_relative_output_allows_parent_relative(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            outside = resolve_relative_output(root, "../outside")
            self.assertTrue(str(outside).endswith("outside"))

    def test_save_and_load_config_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = load_config(root)
            cfg["paths"]["sch_pdf"] = "docs/sch"
            save_config(root, cfg)

            loaded = load_config(root)
            self.assertEqual(loaded["paths"]["sch_pdf"], "docs/sch")


if __name__ == "__main__":
    unittest.main()
