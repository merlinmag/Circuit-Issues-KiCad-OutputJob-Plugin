"""Main plugin configuration dialog."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import wx  # type: ignore
except ImportError:  # pragma: no cover - only in non-KiCad environments
    wx = None


class ConfigDialogUnavailable(RuntimeError):
    """Raised when dialog is requested without wxPython available."""


_SUMMARY_WINDOW = None
_PROGRESS_WINDOW = None


def _build_summary_text(results: Dict[str, Any]) -> str:
    """Build a multiline run summary for UI and logging fallback."""
    ok = results.get("ok", {}) if isinstance(results, dict) else {}
    failed = results.get("failed", {}) if isinstance(results, dict) else {}
    notes = results.get("notes", []) if isinstance(results, dict) else []

    lines = [
        f"Successful steps: {len(ok)}",
        f"Failed steps: {len(failed)}",
        "",
    ]

    if ok:
        lines.append("Success:")
        for key, detail in ok.items():
            lines.append(f"- {key}: {detail}")
        lines.append("")

    if failed:
        lines.append("Failed:")
        for key, detail in failed.items():
            lines.append(f"- {key}: {detail}")
        lines.append("")

    if notes:
        lines.append("Notes:")
        for note in notes:
            lines.append(f"- {note}")

    return "\n".join(lines).strip()


if wx is not None:
    class ConfigDialog(wx.Dialog):
        """Single popup for config + execution trigger."""

        def __init__(self, parent: Optional[object], config: Dict[str, Any], project_root: Optional[Path] = None) -> None:
            super().__init__(parent, title="Circuit-Issues-KiCad-OutputJob-Plugin", size=(760, 700))
            self._cfg = deepcopy(config)
            self._project_root = project_root
            self._path_ctrls: Dict[str, Any] = {}
            self._check_ctrls: Dict[str, Any] = {}
            self._choice_ctrls: Dict[str, Any] = {}
            self._angle_ctrls: Dict[str, Any] = {}
            self._build_ui()
            self.CentreOnParent()

        def _cfg_get(self, section: str, key: str, default: Any) -> Any:
            section_value = self._cfg.get(section, {})
            if not isinstance(section_value, dict):
                return default
            return section_value.get(key, default)

        def _build_ui(self) -> None:
            panel = wx.Panel(self)
            root = wx.BoxSizer(wx.VERTICAL)

            scrolled = wx.ScrolledWindow(panel, style=wx.VSCROLL)
            scrolled.SetScrollRate(12, 12)
            content = wx.BoxSizer(wx.VERTICAL)

            path_box = wx.StaticBoxSizer(wx.VERTICAL, scrolled, "Output Paths (relative to project)")
            for key, label in (
                ("sch_pdf", "Schematic PDF"),
                ("step", "STEP 3D"),
                ("manufacturing", "BOM / Gerbers"),
                ("renders", "3D Renders"),
            ):
                row = wx.BoxSizer(wx.HORIZONTAL)
                row.Add(wx.StaticText(scrolled, label=label), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
                ctrl = wx.TextCtrl(scrolled, value=str(self._cfg_get("paths", key, "")))
                self._path_ctrls[key] = ctrl
                row.Add(ctrl, 1, wx.ALL | wx.EXPAND, 4)
                browse_btn = wx.Button(scrolled, label="Browse", size=(88, -1))
                browse_btn.Bind(wx.EVT_BUTTON, lambda evt, path_key=key: self._on_browse_path(path_key))
                row.Add(browse_btn, 0, wx.ALL, 4)
                path_box.Add(row, 0, wx.EXPAND)
            content.Add(path_box, 0, wx.ALL | wx.EXPAND, 8)

            exports_box = wx.StaticBoxSizer(wx.VERTICAL, scrolled, "Exports")
            for key, label in (
                ("sch_pdf", "Schematic PDF"),
                ("step", "STEP 3D"),
                ("gerbers", "Gerbers"),
                ("drill", "Drill files"),
                ("position", "Position / PNP"),
                ("bom_collapsed", "BOM (collapsed)"),
                ("bom_line_by_line", "BOM (line-by-line)"),
            ):
                cb = wx.CheckBox(scrolled, label=label)
                cb.SetValue(bool(self._cfg_get("exports", key, False)))
                self._check_ctrls[f"exports.{key}"] = cb
                exports_box.Add(cb, 0, wx.ALL, 2)

            preset_row = wx.BoxSizer(wx.HORIZONTAL)
            preset_row.Add(wx.StaticText(scrolled, label="Gerber Layers"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
            preset_choices = [
                "2-layer default (F/B Cu+Paste+Mask+Silk+Edge)",
                "All enabled board layers",
            ]
            preset_choice = wx.Choice(scrolled, choices=preset_choices)
            preset_key = str(self._cfg_get("exports", "gerber_layer_preset", "2_layer_default"))
            preset_index = 0 if preset_key == "2_layer_default" else 1
            preset_choice.SetSelection(preset_index)
            self._choice_ctrls["exports.gerber_layer_preset"] = preset_choice
            preset_row.Add(preset_choice, 1, wx.ALL | wx.EXPAND, 4)
            exports_box.Add(preset_row, 0, wx.EXPAND)

            content.Add(exports_box, 0, wx.ALL | wx.EXPAND, 8)

            render_box = wx.StaticBoxSizer(wx.VERTICAL, scrolled, "3D Render Sides")
            hint = wx.StaticText(scrolled, label="Render time scales with number of views, quality, and resolution.")
            render_box.Add(hint, 0, wx.ALL, 2)
            for key, label in (("top", "Top"), ("bottom", "Bottom"), ("left", "Left"), ("right", "Right"), ("iso1", "ISO 1"), ("iso2", "ISO 2")):
                cb = wx.CheckBox(scrolled, label=label)
                cb.SetValue(bool(self._cfg_get("renders", key, False)))
                self._check_ctrls[f"renders.{key}"] = cb
                render_box.Add(cb, 0, wx.ALL, 2)

            quality_row = wx.BoxSizer(wx.HORIZONTAL)
            quality_row.Add(wx.StaticText(scrolled, label="Render Quality"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
            quality_choices = ["Low (fast)", "Medium", "High (slow)"]
            quality_choice = wx.Choice(scrolled, choices=quality_choices)
            quality_key = str(self._cfg_get("renders", "quality", "medium")).lower()
            quality_index = {"low": 0, "medium": 1, "high": 2}.get(quality_key, 1)
            quality_choice.SetSelection(quality_index)
            self._choice_ctrls["renders.quality"] = quality_choice
            quality_row.Add(quality_choice, 1, wx.ALL | wx.EXPAND, 4)
            render_box.Add(quality_row, 0, wx.EXPAND)

            size_row = wx.BoxSizer(wx.HORIZONTAL)
            size_row.Add(wx.StaticText(scrolled, label="Width"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
            width_ctrl = wx.TextCtrl(scrolled, value=str(self._cfg_get("renders", "width", 1920)), size=(90, -1))
            size_row.Add(width_ctrl, 0, wx.ALL, 4)
            size_row.Add(wx.StaticText(scrolled, label="Height"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
            height_ctrl = wx.TextCtrl(scrolled, value=str(self._cfg_get("renders", "height", 1080)), size=(90, -1))
            size_row.Add(height_ctrl, 0, wx.ALL, 4)
            self._angle_ctrls["width"] = width_ctrl
            self._angle_ctrls["height"] = height_ctrl
            render_box.Add(size_row, 0, wx.EXPAND)

            angle_row = wx.BoxSizer(wx.HORIZONTAL)
            angle_row.Add(wx.StaticText(scrolled, label="ISO1 Az"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
            iso1_az = wx.TextCtrl(scrolled, value=str(self._cfg_get("renders", "iso1_az", 45)), size=(60, -1))
            angle_row.Add(iso1_az, 0, wx.ALL, 4)
            angle_row.Add(wx.StaticText(scrolled, label="ISO1 El"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
            iso1_el = wx.TextCtrl(scrolled, value=str(self._cfg_get("renders", "iso1_el", 35)), size=(60, -1))
            angle_row.Add(iso1_el, 0, wx.ALL, 4)

            angle_row.Add(wx.StaticText(scrolled, label="ISO2 Az"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
            iso2_az = wx.TextCtrl(scrolled, value=str(self._cfg_get("renders", "iso2_az", 225)), size=(60, -1))
            angle_row.Add(iso2_az, 0, wx.ALL, 4)
            angle_row.Add(wx.StaticText(scrolled, label="ISO2 El"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
            iso2_el = wx.TextCtrl(scrolled, value=str(self._cfg_get("renders", "iso2_el", 35)), size=(60, -1))
            angle_row.Add(iso2_el, 0, wx.ALL, 4)

            self._angle_ctrls["iso1_az"] = iso1_az
            self._angle_ctrls["iso1_el"] = iso1_el
            self._angle_ctrls["iso2_az"] = iso2_az
            self._angle_ctrls["iso2_el"] = iso2_el
            render_box.Add(angle_row, 0, wx.EXPAND)

            content.Add(render_box, 0, wx.ALL | wx.EXPAND, 8)

            integrations_box = wx.StaticBoxSizer(wx.VERTICAL, scrolled, "Integrations")
            for key, label in (("jlcpcb", "Run JLCPCB plugin"), ("ibom", "Run iBOM plugin")):
                cb = wx.CheckBox(scrolled, label=label)
                cb.SetValue(bool(self._cfg_get("integrations", key, False)))
                self._check_ctrls[f"integrations.{key}"] = cb
                integrations_box.Add(cb, 0, wx.ALL, 2)
            content.Add(integrations_box, 0, wx.ALL | wx.EXPAND, 8)

            scrolled.SetSizer(content)
            content.Fit(scrolled)
            root.Add(scrolled, 1, wx.ALL | wx.EXPAND, 4)

            button_row = wx.BoxSizer(wx.HORIZONTAL)
            button_row.AddStretchSpacer(1)
            run_btn = wx.Button(panel, wx.ID_OK, label="Save && Run")
            cancel_btn = wx.Button(panel, wx.ID_CANCEL, label="Cancel")
            button_row.Add(run_btn, 0, wx.ALL, 6)
            button_row.Add(cancel_btn, 0, wx.ALL, 6)
            root.Add(button_row, 0, wx.ALL | wx.EXPAND, 2)

            panel.SetSizer(root)
            root.Fit(panel)

            dlg_root = wx.BoxSizer(wx.VERTICAL)
            dlg_root.Add(panel, 1, wx.EXPAND)
            self.SetSizer(dlg_root)
            self.Layout()

        def _on_browse_path(self, key: str) -> None:
            ctrl = self._path_ctrls.get(key)
            if ctrl is None:
                return

            start_dir = ""
            if self._project_root is not None:
                current_rel = ctrl.GetValue().strip()
                if current_rel:
                    candidate = (self._project_root / current_rel)
                    if candidate.exists():
                        start_dir = str(candidate)
                if not start_dir:
                    start_dir = str(self._project_root)

            dlg = wx.DirDialog(self, "Select output folder", defaultPath=start_dir or "")
            try:
                if dlg.ShowModal() != wx.ID_OK:
                    return
                selected = Path(dlg.GetPath())
                if self._project_root is not None:
                    project_root = self._project_root.resolve()
                    rel_text = os.path.relpath(str(selected.resolve()), str(project_root)).replace("\\", "/")
                    if rel_text == ".":
                        rel_text = ""
                    ctrl.SetValue(rel_text)
                else:
                    ctrl.SetValue(selected.as_posix())
            finally:
                dlg.Destroy()

        def get_config(self) -> Dict[str, Any]:
            cfg = deepcopy(self._cfg)
            for key, ctrl in self._path_ctrls.items():
                cfg["paths"][key] = ctrl.GetValue().strip()
            for key, ctrl in self._check_ctrls.items():
                section, item = key.split(".", 1)
                cfg[section][item] = bool(ctrl.GetValue())
            for key, ctrl in self._choice_ctrls.items():
                section, item = key.split(".", 1)
                selected = int(ctrl.GetSelection())
                if key == "exports.gerber_layer_preset":
                    cfg[section][item] = "2_layer_default" if selected <= 0 else "all_enabled"
                elif key == "renders.quality":
                    cfg[section][item] = {0: "low", 1: "medium", 2: "high"}.get(selected, "medium")
            for key, ctrl in self._angle_ctrls.items():
                cfg["renders"][key] = int(ctrl.GetValue().strip() or "0")
            return cfg


    def prompt_for_config(initial_config: Dict[str, Any], project_root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
        """Show modal dialog and return config if accepted."""
        app = wx.GetApp() or wx.App(False)
        _ = app
        dlg = ConfigDialog(None, initial_config, project_root=project_root)
        try:
            if dlg.ShowModal() == wx.ID_OK:
                return dlg.get_config()
            return None
        finally:
            dlg.Destroy()


    def show_summary_dialog(results: Dict[str, Any]) -> None:
        """Show non-blocking completion summary window."""
        global _SUMMARY_WINDOW
        text = _build_summary_text(results)

        if _SUMMARY_WINDOW is not None and _SUMMARY_WINDOW:
            try:
                _SUMMARY_WINDOW.Destroy()
            except Exception:  # noqa: BLE001
                pass

        frame = wx.Frame(
            None,
            title="Post-Design Export Summary",
            size=(760, 520),
            style=wx.DEFAULT_FRAME_STYLE | wx.RESIZE_BORDER,
        )
        panel = wx.Panel(frame)
        root = wx.BoxSizer(wx.VERTICAL)

        info = wx.StaticText(panel, label="Run finished. You can keep working in PCB Editor while this window stays open.")
        root.Add(info, 0, wx.ALL, 8)

        summary_ctrl = wx.TextCtrl(
            panel,
            value=text,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP | wx.HSCROLL,
        )
        root.Add(summary_ctrl, 1, wx.ALL | wx.EXPAND, 8)

        close_btn = wx.Button(panel, label="Close")
        close_btn.Bind(wx.EVT_BUTTON, lambda evt: frame.Close())
        root.Add(close_btn, 0, wx.ALL | wx.ALIGN_RIGHT, 8)

        panel.SetSizer(root)
        frame.Show()
        frame.Raise()
        _SUMMARY_WINDOW = frame


    def create_progress_reporter(total_steps: int):
        """Create modeless progress UI and return (update, close) callbacks."""
        global _PROGRESS_WINDOW

        if _PROGRESS_WINDOW is not None and _PROGRESS_WINDOW:
            try:
                _PROGRESS_WINDOW.Destroy()
            except Exception:  # noqa: BLE001
                pass

        total = max(1, int(total_steps))
        frame = wx.Frame(None, title="Post-Design Export Progress", size=(520, 140), style=wx.DEFAULT_FRAME_STYLE & ~wx.RESIZE_BORDER)
        panel = wx.Panel(frame)
        root = wx.BoxSizer(wx.VERTICAL)
        status = wx.StaticText(panel, label="Preparing...")
        gauge = wx.Gauge(panel, range=total)
        root.Add(status, 0, wx.ALL | wx.EXPAND, 8)
        root.Add(gauge, 0, wx.ALL | wx.EXPAND, 8)
        panel.SetSizer(root)
        frame.CenterOnScreen()
        frame.Show()
        frame.Raise()
        _PROGRESS_WINDOW = frame

        def _apply(current: int, message: str) -> None:
            status.SetLabel(message)
            gauge.SetValue(max(0, min(int(current), total)))

        def _update(current: int, total_current: int, message: str) -> None:
            _ = total_current
            wx.CallAfter(_apply, current, message)

        def _close() -> None:
            def _do_close() -> None:
                nonlocal frame
                try:
                    frame.Destroy()
                except Exception:  # noqa: BLE001
                    pass
                frame = None

            wx.CallAfter(_do_close)

        return _update, _close
else:
    def prompt_for_config(initial_config: Dict[str, Any], project_root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
        """Fallback for non-KiCad runtime contexts."""
        if initial_config is None:
            raise ConfigDialogUnavailable("Initial config is required")
        _ = project_root
        return initial_config


    def show_summary_dialog(results: Dict[str, Any]) -> None:
        """Fallback summary output for non-KiCad runtime contexts."""
        print(_build_summary_text(results))


    def create_progress_reporter(total_steps: int):
        """Fallback no-op progress reporter for non-KiCad runtime contexts."""
        _ = total_steps

        def _update(current: int, total_current: int, message: str) -> None:
            _ = (current, total_current, message)

        def _close() -> None:
            return

        return _update, _close
