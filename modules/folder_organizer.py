"""Output organization helpers."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Union


PathLikeList = Union[Path, Iterable[Path]]


def organize_outputs(export_results: Dict[str, PathLikeList], destination_root: Path) -> Dict[str, List[Path]]:
    """Copy output files into destination root, preserving timestamps."""
    destination_root.mkdir(parents=True, exist_ok=True)
    organized: Dict[str, List[Path]] = {}

    for key, value in export_results.items():
        paths = list(value) if not isinstance(value, Path) else [value]
        organized[key] = []
        for src in paths:
            if not src.exists():
                continue
            dst = destination_root / src.name
            shutil.copy2(src, dst)
            organized[key].append(dst)

    return organized
