"""Integration test: run cli.py on the KiCad fixture project twice (needs kicad-cli)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "ci_fixture"


def _kicad_cli() -> str:
    env = os.environ.get("KICAD_CLI")
    if env and Path(env).exists():
        return env
    return shutil.which("kicad-cli") or ("/usr/bin/kicad-cli" if Path("/usr/bin/kicad-cli").exists() else "")


EXPECTED_FILES = [
    "doc/schematics/ci_fixture_SCH.pdf",
    "3d/ci_fixture_STEP.step",
    "manufacturing/gerbers/ci_fixture-F_Cu.gtl",
    "manufacturing/gerbers/ci_fixture-B_Cu.gbl",
    "manufacturing/gerbers/ci_fixture-Edge_Cuts.gm1",
    "manufacturing/gerbers/ci_fixture-job.gbrjob",
    "manufacturing/drills/ci_fixture.drl",
    "manufacturing/placement/ci_fixture_POS.csv",
    "manufacturing/bom/ci_fixture_BOM.csv",
    "manufacturing/bom/ci_fixture_BOM_collapsed.csv",
    "doc/visual/schematic/ci_fixture.svg",
    "doc/visual/schematic/ci_fixture-LEDs.svg",
    "doc/visual/pcb/ci_fixture-pcb-F_Cu.svg",
    "doc/visual/pcb/ci_fixture-pcb-B_Cu.svg",
    "doc/visual/pcb/ci_fixture-pcb-F_Silkscreen.svg",
    "doc/visual/pcb/ci_fixture-pcb-F_Fab.svg",
    "doc/visual/pcb/ci_fixture-pcb-top.svg",
    "doc/visual/pcb/ci_fixture-pcb-bottom.svg",
    "renders/ci_fixture_PCBA_TOP.png",
    "reports/summary.json",
    "reports/summary.md",
    "reports/erc.json",
    "reports/drc.json",
    "reports/export.log",
]
# Files whose content legitimately changes between runs.
NOT_REPRODUCIBLE = {
    "reports/summary.json",
    "reports/summary.md",
    "reports/erc.json",
    "reports/drc.json",
    "reports/export.log",
    # OpenCascade orders STEP style entities differently between runs; only the
    # header timestamp can be normalized (checked separately below).
    "3d/ci_fixture_STEP.step",
}


def _ibom_available() -> bool:
    return bool(os.environ.get("IBOM_CLI") or shutil.which("generate_interactive_bom"))


@unittest.skipUnless(_kicad_cli(), "kicad-cli not installed")
class CliIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._td = tempfile.TemporaryDirectory()
        cls.project = Path(cls._td.name) / "ci_fixture"
        shutil.copytree(FIXTURE, cls.project, ignore=shutil.ignore_patterns("reports", "doc", "3d", "manufacturing", "renders", "bom"))
        cfg_path = cls.project / ".kicad_plugin_config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cls.ibom = _ibom_available() and bool(cfg["integrations"].get("ibom"))
        cfg["integrations"]["ibom"] = cls.ibom
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

        cls.runs = []
        for _ in range(2):
            proc = subprocess.run(
                [sys.executable, str(ROOT / "cli.py"), str(cls.project)],
                capture_output=True,
                text=True,
                check=False,
                timeout=900,
            )
            snapshot = {
                p.relative_to(cls.project).as_posix(): p.read_bytes()
                for p in sorted(cls.project.rglob("*"))
                if p.is_file() and not p.name.startswith(("ci_fixture.kicad_", "leds.kicad_", ".kicad_plugin", "fp-info-cache"))
            }
            cls.runs.append((proc, snapshot))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._td.cleanup()

    def test_exit_code_is_zero(self) -> None:
        for proc, _ in self.runs:
            self.assertEqual(proc.returncode, 0, proc.stdout[-4000:] + proc.stderr[-4000:])

    def test_summary_json(self) -> None:
        summary = json.loads(self.runs[-1][1]["reports/summary.json"])
        self.assertEqual(summary["exit_code"], 0)
        self.assertEqual(summary["status"], "ok")
        steps = {s["name"]: s["status"] for s in summary["steps"]}
        expected = {
            "erc", "drc", "schematic_pdf", "step", "gerbers", "drill", "position",
            "bom_line_by_line", "bom_collapsed", "visual", "render_top",
        }
        if self.ibom:
            expected.add("ibom")
        self.assertEqual(set(steps), expected)
        self.assertTrue(all(status == "ok" for status in steps.values()), steps)
        self.assertEqual(list(steps)[:2], ["erc", "drc"])
        self.assertEqual(summary["checks"]["erc"]["errors"], 0)
        self.assertEqual(summary["checks"]["drc"]["errors"], 0)
        self.assertEqual(summary["checks"]["drc"]["parity"], 0)

    def test_expected_files_exist(self) -> None:
        files = self.runs[-1][1]
        expected = EXPECTED_FILES + (["bom/ibom.html"] if self.ibom else [])
        missing = [f for f in expected if f not in files]
        self.assertEqual(missing, [])
        self.assertFalse((self.project / "kicad_postdesign_export.log").exists())

    def test_collapsed_bom_groups_parts(self) -> None:
        text = self.runs[-1][1]["manufacturing/bom/ci_fixture_BOM_collapsed.csv"].decode("utf-8")
        self.assertIn('"Quantity"', text.splitlines()[0])
        self.assertIn('"R1,R2","1k"', text)
        line = self.runs[-1][1]["manufacturing/bom/ci_fixture_BOM.csv"].decode("utf-8")
        self.assertEqual(len(line.strip().splitlines()), 1 + 5)

    def test_rerun_is_byte_identical(self) -> None:
        first, second = self.runs[0][1], self.runs[1][1]
        self.assertEqual(sorted(first), sorted(second))
        changed = [name for name in first if name not in NOT_REPRODUCIBLE and first[name] != second[name]]
        self.assertEqual(changed, [])
        for snap in (first, second):
            self.assertNotIn(b"CreationDate", snap["manufacturing/gerbers/ci_fixture-F_Cu.gtl"])
            self.assertIn(b"FILE_NAME('ci_fixture_STEP.step','1970-01-01T00:00:00'", snap["3d/ci_fixture_STEP.step"])


if __name__ == "__main__":
    unittest.main()
