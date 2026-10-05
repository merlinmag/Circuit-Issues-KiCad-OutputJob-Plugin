"""Strip creation timestamps from generated files so reruns are byte-identical.

KiCad stamps most outputs with the time of export (Gerber X2 attributes, drill
headers, SVG titles, PDF info dictionary, STEP header). Committing outputs to git
then produces noise diffs on every run. These helpers remove or pin those stamps.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, List, Union

FIXED_STEP_TIMESTAMP = b"1970-01-01T00:00:00"

# Line-level rules applied to text outputs (Gerber, drill, SVG, STEP, position files).
_REMOVE_LINE_PATTERNS = [
    re.compile(rb"^%TF\.CreationDate,[^\n]*\*%\r?\n", re.MULTILINE),  # Gerber X2 attribute
    re.compile(rb"^G04 #@! TF\.CreationDate,[^\n]*\r?\n", re.MULTILINE),  # Gerber X1 comment form
    re.compile(rb"^; #@! TF\.CreationDate,[^\n]*\r?\n", re.MULTILINE),  # Excellon drill
]
_SUBSTITUTIONS = [
    # "G04 Created by KiCad (PCBNEW 9.0.1) date 2025-03-01 10:00:00*"
    (re.compile(rb"^(G04 Created by KiCad[^\n]*?) date [^\n*]*\*", re.MULTILINE), rb"\1*"),
    # "; DRILL file {KiCad 9.0.1} date 2025-03-01T10:00:00" / "; DRILL file KiCad 10.0 date ..."
    (re.compile(rb"^(; DRILL file [^\n]*?) date [^\r\n]*", re.MULTILINE), rb"\1"),
    # "<title>SVG Image created as foo.svg date 2025-03-01T10:00:00 </title>"
    (re.compile(rb"(<title>SVG Image created as [^<]*?) date [^<]*</title>"), rb"\1</title>"),
    # STEP header: FILE_NAME('board.step','2025-03-01T10:00:00',...
    (re.compile(rb"(FILE_NAME\('[^']*',')[^']*(')"), rb"\g<1>" + FIXED_STEP_TIMESTAMP + rb"\2"),
    # Position files (ascii): "## Created on 2025-03-01 10:00:00" / "### ... - created on ..."
    (re.compile(rb"^(#+[^\n]*?)[Cc]reated on [^\r\n]*", re.MULTILINE), rb"\1"),
]

# PDF info dictionary dates. Replaced with a same-length value so xref offsets stay valid.
_PDF_DATE = re.compile(rb"/(CreationDate|ModDate)\s*\(([^)]*)\)")

TEXT_SUFFIXES = {".drl", ".exc", ".xln", ".svg", ".step", ".stp", ".pos", ".gbr", ".gbrjob"}
_GERBER_SUFFIX = re.compile(r"^\.g[a-z0-9]{1,3}$", re.IGNORECASE)  # .gtl .gbl .gm1 .g2 ...


def _normalize_text(data: bytes) -> bytes:
    for pattern in _REMOVE_LINE_PATTERNS:
        data = pattern.sub(b"", data)
    for pattern, repl in _SUBSTITUTIONS:
        data = pattern.sub(repl, data)
    return data


def _normalize_gbrjob(data: bytes) -> bytes:
    try:
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _normalize_text(data)
    header = doc.get("Header") if isinstance(doc, dict) else None
    if isinstance(header, dict) and "CreationDate" in header:
        del header["CreationDate"]
        return (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return data


def _normalize_pdf(data: bytes) -> bytes:
    def _pin(match: "re.Match[bytes]") -> bytes:
        value = match.group(2)
        pinned = re.sub(rb"\d", b"0", value)
        return b"/" + match.group(1) + b" (" + pinned + b")"

    return _PDF_DATE.sub(_pin, data)


def normalize_file(path: Path) -> bool:
    """Normalize one file in place. Returns True when the file was changed."""
    if not path.is_file():
        return False
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        handler = _normalize_pdf
    elif suffix == ".gbrjob":
        handler = _normalize_gbrjob
    elif suffix in TEXT_SUFFIXES or _GERBER_SUFFIX.match(suffix):
        handler = _normalize_text
    else:
        return False

    original = path.read_bytes()
    updated = handler(original)
    if updated == original:
        return False
    path.write_bytes(updated)
    return True


def normalize_outputs(paths: Union[Path, Iterable[Path]]) -> List[Path]:
    """Normalize files and directory trees in place. Returns the files that changed."""
    items = [paths] if isinstance(paths, Path) else list(paths)
    changed: List[Path] = []
    for item in items:
        if item.is_dir():
            files = sorted(p for p in item.rglob("*") if p.is_file())
        else:
            files = [item]
        for file_path in files:
            if normalize_file(file_path):
                changed.append(file_path)
    return changed
