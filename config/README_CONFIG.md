# Plugin Configuration

Users configure the plugin through the popup dialog. The headless CLI (`cli.py`) reads the
same file, or another one passed with `--config`.

The plugin persists settings into `.kicad_plugin_config.json` in the project root.
That file is internal state and should not be edited manually.

Key rules:
- All output paths are relative to the `.kicad_pro` directory.
- Absolute paths are rejected.
- Paths and checkbox states are restored on next run.
- `checks` (`erc`, `drc`, `fail_on`: `error` | `warning` | `never`) controls the ERC/DRC step that runs first.
- `exports.visual` + `paths.visual` control the SVG export for visual diffs.
- Settings missing from a saved file are taken from `config_defaults.json`.
