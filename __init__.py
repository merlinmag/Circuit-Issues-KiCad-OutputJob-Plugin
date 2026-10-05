"""KiCad ActionPlugin entrypoint for Circuit-Issues-KiCad-OutputJob-Plugin.

The export logic lives in ``modules.pipeline`` and is shared with the headless CLI
(``cli.py``). ``wx``, ``pcbnew`` and ``ui.*`` are only imported when the plugin is
loaded by KiCad, so importing this package outside KiCad has no GUI dependencies.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any, Dict

from .modules.config_manager import load_config, save_config
from .modules.pipeline import (  # noqa: F401  (re-exported for backwards compatibility)
    GERBER_PRESET_LAYERS,
    _collect_project_files,
    _count_export_steps,
    run_export_pipeline,
)


def _register_action_plugin() -> None:  # pragma: no cover - KiCad runtime only
    import pcbnew  # type: ignore

    class PostDesignExportPlugin(pcbnew.ActionPlugin):
        """ActionPlugin hook shown in KiCad's Tools menu."""

        def defaults(self) -> None:
            self.name = "Circuit-Issues-KiCad-OutputJob-Plugin"
            self.category = "Circuit Issues"
            self.description = "Generate post-design outputs and run integrations (KiCad 9/10)"
            self.show_toolbar_button = True

        def Run(self) -> None:  # noqa: N802
            from .ui.dialog import create_progress_reporter, prompt_for_config, show_summary_dialog

            board = pcbnew.GetBoard()
            if board is None:
                return
            board_file = Path(board.GetFileName())
            if not board_file.exists():
                return

            project_root = board_file.parent
            config = load_config(project_root)
            selected = prompt_for_config(config, project_root=project_root)
            if selected is None:
                return

            save_config(project_root, selected)
            total_steps = max(1, _count_export_steps(selected))
            progress_update, progress_close = create_progress_reporter(total_steps)

            def _worker() -> None:
                results: Dict[str, Any] = {"ok": {}, "failed": {}, "notes": []}
                try:
                    results = run_export_pipeline(board_file, selected, progress_cb=progress_update)
                except Exception as exc:  # noqa: BLE001
                    results["failed"]["fatal"] = f"Unhandled exception: {type(exc).__name__}: {exc}"
                finally:
                    progress_close()
                import wx  # type: ignore

                wx.CallAfter(show_summary_dialog, results)

            threading.Thread(target=_worker, name="post_design_export_worker", daemon=True).start()

    PostDesignExportPlugin().register()


# KiCad imports pcbnew before it loads action plugins. Outside KiCad (CLI, tests) pcbnew
# is not loaded and nothing GUI related is imported or registered.
if "pcbnew" in sys.modules:
    _register_action_plugin()
