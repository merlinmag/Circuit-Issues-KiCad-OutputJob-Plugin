"""Tests for ERC/DRC parsing, fail_on thresholds, exit codes and the CLI front end."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

try:
    from . import _bootstrap  # noqa: F401  (python -m unittest discover -s tests -t .)
except ImportError:
    import _bootstrap  # noqa: F401  (python -m unittest discover -s tests)

from kicad_library_automation.modules import headless
from kicad_library_automation.modules.checks import check_fails, parse_drc_report, parse_erc_report
from kicad_library_automation.modules.command_runner import CommandResult
from kicad_library_automation.modules.config_manager import load_defaults
from kicad_library_automation.modules.pipeline import compute_exit_code, planned_steps, run_export_pipeline

CHECKS_RUN = "kicad_library_automation.modules.checks.run_command"


def _violation(severity: str, vtype: str = "clearance", excluded: bool = False) -> dict:
    v = {
        "type": vtype,
        "severity": severity,
        "description": f"{vtype} problem",
        "items": [{"description": "Track on F.Cu", "pos": {"x": 1.0, "y": 2.0}, "uuid": "x"}],
    }
    if excluded:
        v["excluded"] = True
    return v


def _drc_report(violations=(), unconnected=(), parity=()) -> dict:
    return {
        "coordinate_units": "mm",
        "violations": list(violations),
        "unconnected_items": list(unconnected),
        "schematic_parity": list(parity),
    }


def _erc_report(violations=()) -> dict:
    return {"coordinate_units": "mm", "sheets": [{"path": "/", "violations": list(violations)}]}


class CheckParsingTests(unittest.TestCase):
    def test_drc_counts_respect_exclusions(self) -> None:
        summary = parse_drc_report(
            _drc_report(
                violations=[_violation("error"), _violation("warning"), _violation("error", excluded=True)],
                unconnected=[_violation("error", "unconnected_items")],
                parity=[_violation("warning", "missing_footprint")],
            )
        )
        self.assertEqual(summary["errors"], 2)
        self.assertEqual(summary["warnings"], 2)
        self.assertEqual(summary["excluded"], 1)
        self.assertEqual(summary["unconnected"], 1)
        self.assertEqual(summary["parity"], 1)
        self.assertEqual(summary["violations"][0]["severity"], "error")
        self.assertTrue(all(not v["excluded"] for v in summary["violations"]))

    def test_erc_counts_and_location(self) -> None:
        summary = parse_erc_report(_erc_report([_violation("warning", "pin_not_connected"), _violation("exclusion")]))
        self.assertEqual((summary["errors"], summary["warnings"], summary["excluded"]), (0, 1, 1))
        self.assertEqual(summary["violations"][0]["location"], "/ (1.0, 2.0)")

    def test_fail_on_thresholds(self) -> None:
        only_warn = {"errors": 0, "warnings": 3}
        with_err = {"errors": 1, "warnings": 0}
        self.assertFalse(check_fails(only_warn, "error"))
        self.assertTrue(check_fails(with_err, "error"))
        self.assertTrue(check_fails(only_warn, "warning"))
        self.assertFalse(check_fails(with_err, "never"))


class ExitCodeTests(unittest.TestCase):
    def test_compute_exit_code(self) -> None:
        ok = {"name": "gerbers", "status": "ok"}
        failed = {"name": "gerbers", "status": "failed"}
        skipped = {"name": "jlcpcb", "status": "skipped"}
        check = {"name": "drc", "status": "failed", "check_violation": True}
        self.assertEqual(compute_exit_code({"steps": [ok, skipped]}), 0)
        self.assertEqual(compute_exit_code({"steps": [ok, failed]}), 1)
        self.assertEqual(compute_exit_code({"steps": [ok, check]}), 2)
        self.assertEqual(compute_exit_code({"steps": [check, failed]}), 1)

    def _run_drc(self, report: dict, fail_on: str) -> dict:
        def fake_run(cmd, cwd, timeout=None):  # noqa: ANN001
            out = Path(cmd[cmd.index("--output") + 1])
            out.write_text(json.dumps(report), encoding="utf-8")
            return CommandResult(ok=True, cmd=cmd, stdout="", stderr="", return_code=0)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            board = root / "b.kicad_pcb"
            board.write_text("(kicad_pcb)", encoding="utf-8")
            cfg = load_defaults()
            cfg["checks"]["fail_on"] = fail_on
            with patch(CHECKS_RUN, side_effect=fake_run):
                results = run_export_pipeline(board, cfg, headless=True, only=["drc"], report_dir=root / "reports")
            results["summary_md"] = (root / "reports" / "summary.md").read_text(encoding="utf-8")
            results["summary_json"] = json.loads((root / "reports" / "summary.json").read_text(encoding="utf-8"))
            return results

    def test_drc_errors_give_exit_code_2(self) -> None:
        results = self._run_drc(_drc_report([_violation("error")]), "error")
        self.assertEqual(results["exit_code"], 2)
        self.assertEqual(results["summary_json"]["status"], "checks_failed")
        self.assertIn("clearance problem", results["summary_md"])
        self.assertIn("Top violations", results["summary_md"])

    def test_warnings_only_pass_with_fail_on_error(self) -> None:
        results = self._run_drc(_drc_report([_violation("warning")]), "error")
        self.assertEqual(results["exit_code"], 0)
        self.assertEqual(results["summary_json"]["checks"]["drc"]["warnings"], 1)

    def test_warnings_fail_with_fail_on_warning(self) -> None:
        self.assertEqual(self._run_drc(_drc_report([_violation("warning")]), "warning")["exit_code"], 2)

    def test_excluded_errors_do_not_fail(self) -> None:
        self.assertEqual(self._run_drc(_drc_report([_violation("error", excluded=True)]), "error")["exit_code"], 0)

    def test_drc_tool_failure_is_exit_code_1(self) -> None:
        def broken(cmd, cwd, timeout=None):  # noqa: ANN001
            return CommandResult(ok=False, cmd=cmd, stdout="", stderr="Failed to load board", return_code=3)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            board = root / "b.kicad_pcb"
            board.write_text("(kicad_pcb)", encoding="utf-8")
            with patch(CHECKS_RUN, side_effect=broken):
                results = run_export_pipeline(board, load_defaults(), headless=True, only=["drc"], report_dir=root / "r")
        self.assertEqual(results["exit_code"], 1)

    def test_jlc_missing_is_skipped_headless(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            board = root / "b.kicad_pcb"
            board.write_text("(kicad_pcb)", encoding="utf-8")
            with patch.dict("os.environ", {"KICAD_PLUGIN_DIRS": str(root / "nowhere")}):
                results = run_export_pipeline(board, load_defaults(), headless=True, only=["jlcpcb"], report_dir=root / "r")
        self.assertIn("jlcpcb", results["skipped"])
        self.assertIn("not installed", results["skipped"]["jlcpcb"])
        self.assertEqual(results["exit_code"], 0)


class PlannedStepTests(unittest.TestCase):
    def test_checks_run_first_and_follow_config(self) -> None:
        cfg = load_defaults()
        self.assertEqual(planned_steps(cfg), ["erc", "drc", "gerbers"])

    def test_only_overrides_enable_flags_and_expands_groups(self) -> None:
        cfg = load_defaults()
        self.assertEqual(planned_steps(cfg, ["bom", "visual", "checks"]), ["erc", "drc", "bom_line_by_line", "bom_collapsed", "visual"])
        self.assertEqual(planned_steps(cfg, ["renders"]), ["render_top"])

    def test_unknown_only_step_raises(self) -> None:
        with self.assertRaises(ValueError):
            planned_steps(load_defaults(), ["gerberz"])


class CliTests(unittest.TestCase):
    def _project(self, root: Path) -> Path:
        (root / "demo.kicad_pro").write_text("{}", encoding="utf-8")
        board = root / "demo.kicad_pcb"
        board.write_text("(kicad_pcb)", encoding="utf-8")
        return board

    def test_cli_returns_pipeline_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            board = self._project(root)
            for code in (0, 1, 2):
                with patch.object(headless, "run_export_pipeline", return_value={"exit_code": code}) as run, redirect_stdout(io.StringIO()):
                    self.assertEqual(headless.main([str(root), "--only", "gerbers,drill"]), code)
                args, kwargs = run.call_args
                self.assertEqual(args[0], board.resolve())
                self.assertTrue(kwargs["headless"])
                self.assertEqual(kwargs["only"], ["gerbers", "drill"])

    def test_cli_usage_errors_exit_1(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._project(root)
            for argv in ([str(root / "missing")], [str(root), "--only", "nope"], [str(root), "--bogus"]):
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
                    headless.main(argv)
                self.assertEqual(ctx.exception.code, 1, argv)


if __name__ == "__main__":
    unittest.main()
