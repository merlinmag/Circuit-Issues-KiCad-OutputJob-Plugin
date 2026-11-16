"""The plugin version shown in the dialog title matches the newest metadata.json release."""

from __future__ import annotations

import json
import unittest

from tests import _bootstrap  # noqa: F401
from tests._bootstrap import ROOT

from kicad_library_automation.modules import __version__


class VersionTest(unittest.TestCase):
    def test_matches_metadata(self) -> None:
        meta = json.loads((ROOT / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["versions"][0]["version"], __version__)


if __name__ == "__main__":
    unittest.main()
