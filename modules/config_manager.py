"""Configuration loader and validator for the KiCad plugin."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


CONFIG_FILENAME = ".kicad_plugin_config.json"
_DEFAULTS_PATH = Path(__file__).resolve().parent.parent / "config" / "config_defaults.json"


def load_defaults() -> Dict[str, Any]:
    """Load default settings bundled with the plugin."""
    with _DEFAULTS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge nested dictionaries recursively."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def config_file_path(project_root: Path) -> Path:
    """Return the persisted config path for a KiCad project."""
    return project_root / CONFIG_FILENAME


def _reject_absolute_path(path_text: str) -> None:
    p = Path(path_text)
    if p.is_absolute():
        raise ValueError(f"Absolute path is not allowed: {path_text}")
    if path_text.startswith("\\") or path_text.startswith("/"):
        raise ValueError(f"Absolute path is not allowed: {path_text}")
    if len(path_text) >= 2 and path_text[1] == ":":
        raise ValueError(f"Absolute path is not allowed: {path_text}")


def resolve_relative_output(project_root: Path, rel_path: str) -> Path:
    """Resolve relative output path; '..' is allowed, absolute paths are not."""
    _reject_absolute_path(rel_path)
    return (project_root / rel_path).resolve()


def validate_config(cfg: Dict[str, Any], project_root: Path) -> None:
    """Validate required keys and path constraints."""
    for top_key in ("paths", "exports", "integrations", "renders"):
        if top_key not in cfg or not isinstance(cfg[top_key], dict):
            raise ValueError(f"Missing or invalid config section: {top_key}")

    for path_key in ("sch_pdf", "step", "manufacturing", "renders"):
        if path_key not in cfg["paths"] or not isinstance(cfg["paths"][path_key], str):
            raise ValueError(f"Missing or invalid path setting: {path_key}")
        resolve_relative_output(project_root, cfg["paths"][path_key])


def load_config(project_root: Path) -> Dict[str, Any]:
    """Load defaults, then overlay saved project config when present."""
    defaults = load_defaults()
    cfg_path = config_file_path(project_root)
    if not cfg_path.exists():
        return defaults

    with cfg_path.open("r", encoding="utf-8") as f:
        saved = json.load(f)
    merged = deep_merge(defaults, saved)
    validate_config(merged, project_root)
    return merged


def save_config(project_root: Path, cfg: Dict[str, Any]) -> Path:
    """Validate and write config to project-local json file."""
    validate_config(cfg, project_root)
    cfg_path = config_file_path(project_root)
    with cfg_path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return cfg_path
