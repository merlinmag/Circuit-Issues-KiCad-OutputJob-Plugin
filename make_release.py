"""Package the plugin into a KiCad PCM zip and print the metadata.json values.

Cross-platform replacement for make_release.ps1.

Usage:
    python3 make_release.py --version 1.2.0 [--source DIR] [--out dist]

Archive layout (KiCad PCM): plugin files under ``plugins/``, ``metadata.json`` at the root.
The packaged metadata.json lists only the packaged version, without the download fields
(KiCad requires that); the repository metadata.json keeps all versions.
Timestamps are fixed, so the same sources always give the same zip and SHA256.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import zipfile
from pathlib import Path

INCLUDE = ("__init__.py", "cli.py", "LICENSE", "config", "modules", "ui")
DOWNLOAD_KEYS = ("download_url", "download_sha256", "download_size", "install_size")
ZIP_DATE = (2026, 1, 1, 0, 0, 0)
REPO_URL = "https://github.com/merlinmag/Circuit-Issues-KiCad-OutputJob-Plugin"


def _files(source: Path):
    for item in INCLUDE:
        path = source / item
        if path.is_file():
            yield path
        elif path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and "__pycache__" not in child.parts and child.suffix not in (".pyc", ".pyo"):
                    yield child
        else:
            print(f"warning: skipping missing item {item}", file=sys.stderr)


def package_metadata(source: Path, version: str) -> dict:
    meta = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    entries = [v for v in meta.get("versions", []) if v.get("version") == version]
    entry = copy.deepcopy(entries[0]) if entries else {"version": version, "status": "stable", "kicad_version": "9.0"}
    for key in DOWNLOAD_KEYS:
        entry.pop(key, None)
    meta["versions"] = [entry]
    return meta


def _add(zf: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, ZIP_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zf.writestr(info, data)


def build(source: Path, version: str, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_name = f"circuit-issues-outputjob-v{version}.zip"
    zip_path = out_dir / zip_name
    install_size = 0
    with zipfile.ZipFile(zip_path, "w") as zf:
        meta = (json.dumps(package_metadata(source, version), indent=4) + "\n").encode("utf-8")
        _add(zf, "metadata.json", meta)
        install_size += len(meta)
        for path in _files(source):
            data = path.read_bytes()
            _add(zf, "plugins/" + path.relative_to(source).as_posix(), data)
            install_size += len(data)
    data = zip_path.read_bytes()
    return {
        "path": str(zip_path),
        "version": version,
        "download_url": f"{REPO_URL}/releases/download/v{version}/{zip_name}",
        "download_sha256": hashlib.sha256(data).hexdigest(),
        "download_size": len(data),
        "install_size": install_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "dist")
    args = parser.parse_args()
    info = build(args.source.resolve(), args.version, args.out.resolve())
    print(f"Created {info.pop('path')}")
    print("metadata.json versions entry values:")
    print(json.dumps(info, indent=4))
    return 0


if __name__ == "__main__":
    sys.exit(main())
