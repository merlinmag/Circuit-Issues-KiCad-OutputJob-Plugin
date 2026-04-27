# Plugin Configuration

Users configure the plugin through the popup dialog only.

The plugin persists settings into `.kicad_plugin_config.json` in the project root.
That file is internal state and should not be edited manually.

Key rules:
- All output paths are relative to the `.kicad_pro` directory.
- Absolute paths are rejected.
- Paths and checkbox states are restored on next run.
