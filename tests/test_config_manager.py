"""Tests for config manager."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from . import _bootstrap  # noqa: F401  (python -m unittest discover -s tests -t .)
except ImportError:
    import _bootstrap  # noqa: F401  (python -m unittest discover -s tests)

import json

from kicad_library_automation.modules.config_manager import (
    config_file_path,
    deep_merge,
    load_config,
    load_config_file,
    load_defaults,
    resolve_relative_output,
    save_config,
)


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

    def test_defaults_include_checks_and_visual(self) -> None:
        defaults = load_defaults()
        self.assertEqual(defaults["checks"], {"erc": True, "drc": True, "fail_on": "error"})
        self.assertIn("visual", defaults["exports"])
        self.assertEqual(defaults["paths"]["visual"], "doc/visual")

    def test_old_saved_config_gets_new_sections_from_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # A v1.0.0 config: no "checks" section, no visual export/path.
            old = load_defaults()
            del old["checks"]
            del old["exports"]["visual"]
            del old["paths"]["visual"]
            old["exports"]["drill"] = True
            config_file_path(root).write_text(json.dumps(old), encoding="utf-8")

            cfg = load_config(root)
            self.assertTrue(cfg["exports"]["drill"])
            self.assertEqual(cfg["checks"]["fail_on"], "error")
            self.assertTrue(cfg["checks"]["erc"])
            self.assertFalse(cfg["exports"]["visual"])
            self.assertEqual(cfg["paths"]["visual"], "doc/visual")

    def test_partial_checks_section_merges_with_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config_file_path(root).write_text(json.dumps({"checks": {"fail_on": "warning"}}), encoding="utf-8")
            cfg = load_config(root)
            self.assertEqual(cfg["checks"], {"erc": True, "drc": True, "fail_on": "warning"})

    def test_invalid_fail_on_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config_file_path(root).write_text(json.dumps({"checks": {"fail_on": "sometimes"}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(root)

    def test_load_config_file_explicit_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            other = root / "ci.json"
            other.write_text(json.dumps({"exports": {"visual": True}, "checks": {"drc": False}}), encoding="utf-8")
            cfg = load_config_file(other, root)
            self.assertTrue(cfg["exports"]["visual"])
            self.assertFalse(cfg["checks"]["drc"])
            self.assertTrue(cfg["checks"]["erc"])
            self.assertTrue(cfg["exports"]["gerbers"])

    def test_absolute_visual_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = load_config(root)
            cfg["paths"]["visual"] = "/abs/visual"
            with self.assertRaises(ValueError):
                save_config(root, cfg)


if __name__ == "__main__":
    unittest.main()
