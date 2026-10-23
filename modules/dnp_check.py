"""DNP / assembly attribute check: schematic symbols vs. PCB footprints.

KiCad keeps "Do not populate", "Exclude from BOM" and "Exclude from position files" on both
the symbol and the footprint, and only syncs them on "Update PCB from Schematic". When the
board is not updated, a part marked DNP in the schematic is still placed by the assembler.
KiCad's own parity check reports this only as a (configurable) warning, so this check reads
the files directly and reports every difference as an error.

Pure file parsing, no kicad-cli, ``wx`` or ``pcbnew`` needed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')

# Attribute key -> human readable name (same wording as KiCad's properties dialogs).
ATTRIBUTES = {
    "dnp": "Do not populate",
    "exclude_from_bom": "Exclude from bill of materials",
    "exclude_from_pos_files": "Exclude from position files",
}


def parse_sexpr(text: str) -> List[Any]:
    """Parse a KiCad s-expression file into nested lists (atoms and strings are ``str``)."""
    stack: List[List[Any]] = [[]]
    for match in _TOKEN.finditer(text):
        token = match.group(0)
        if token == "(":
            stack.append([])
        elif token == ")":
            if len(stack) < 2:
                raise ValueError("Unbalanced ')' in s-expression")
            node = stack.pop()
            stack[-1].append(node)
        elif token.startswith('"'):
            stack[-1].append(re.sub(r"\\(.)", r"\1", token[1:-1]))
        else:
            stack[-1].append(token)
    if len(stack) != 1:
        raise ValueError("Unbalanced '(' in s-expression")
    return stack[0][0] if len(stack[0]) == 1 and isinstance(stack[0][0], list) else stack[0]


def _children(node: List[Any], name: str) -> List[List[Any]]:
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == name]


def _child(node: List[Any], name: str) -> Optional[List[Any]]:
    found = _children(node, name)
    return found[0] if found else None


def _flag(node: List[Any], name: str) -> Optional[bool]:
    """Read ``(name yes|no)``; ``None`` when the token is absent."""
    child = _child(node, name)
    if child is None or len(child) < 2:
        return None
    return str(child[1]).lower() == "yes"


def _property(node: List[Any], name: str) -> Optional[str]:
    for prop in _children(node, "property"):
        if len(prop) > 2 and prop[1] == name:
            return str(prop[2])
    return None


# --------------------------------------------------------------------------- schematic


def _symbol_references(symbol: List[Any], project: str) -> List[str]:
    """References of a placed symbol: one per sheet instance, else the Reference property."""
    refs: List[str] = []
    fallback: List[str] = []
    instances = _child(symbol, "instances")
    for proj in _children(instances, "project") if instances else []:
        bucket = refs if len(proj) > 1 and proj[1] == project else fallback
        for path in _children(proj, "path"):
            ref = _child(path, "reference")
            if ref is not None and len(ref) > 1:
                bucket.append(str(ref[1]))
    if not refs:
        refs = fallback
    if not refs:
        ref = _property(symbol, "Reference")
        if ref:
            refs = [ref]
    return refs


def collect_schematic_parts(sch_file: Path, project: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Walk the sheet hierarchy and return ``{reference: attributes}`` for every placed part.

    Attributes: ``dnp``, ``exclude_from_bom`` and ``exclude_from_pos_files`` (``None`` when the schematic format has no such flag).
    Power symbols / flags (references starting with ``#``) are skipped.
    """
    sch_file = Path(sch_file)
    project = project or sch_file.stem
    parts: Dict[str, Dict[str, Any]] = {}
    visited = set()
    pending = [sch_file.resolve()]
    while pending:
        current = pending.pop()
        if current in visited or not current.exists():
            continue
        visited.add(current)
        root = parse_sexpr(current.read_text(encoding="utf-8"))
        for sheet in _children(root, "sheet"):
            sheet_file = _property(sheet, "Sheetfile") or _property(sheet, "Sheet file")
            if sheet_file:
                pending.append((current.parent / sheet_file).resolve())
        for symbol in _children(root, "symbol"):
            if _child(symbol, "lib_id") is None:
                continue
            in_bom = _flag(symbol, "in_bom")
            in_pos = _flag(symbol, "in_pos_files")
            attrs = {
                "dnp": bool(_flag(symbol, "dnp")),
                "exclude_from_bom": in_bom is False,
                "exclude_from_pos_files": None if in_pos is None else not in_pos,
                "sheet": current.name,
            }
            for ref in _symbol_references(symbol, project):
                if not ref or ref.startswith("#"):
                    continue
                if ref in parts:  # another unit of a multi-unit part
                    prev = parts[ref]
                    for key in ATTRIBUTES:
                        if attrs[key] is not None:
                            prev[key] = bool(prev[key]) or attrs[key]
                    continue
                parts[ref] = dict(attrs)
    return parts


# --------------------------------------------------------------------------- board


def collect_board_parts(pcb_file: Path) -> Dict[str, Dict[str, Any]]:
    """Return ``{reference: attributes}`` for every footprint on the board."""
    root = parse_sexpr(Path(pcb_file).read_text(encoding="utf-8"))
    parts: Dict[str, Dict[str, Any]] = {}
    for fp in _children(root, "footprint"):
        ref = _property(fp, "Reference")
        if ref is None:  # KiCad 7 and older
            for text in _children(fp, "fp_text"):
                if len(text) > 2 and text[1] == "reference":
                    ref = str(text[2])
                    break
        if not ref:
            continue
        attr = _child(fp, "attr")
        flags = {str(a) for a in attr[1:]} if attr else set()
        at = _child(fp, "at")
        parts[ref] = {
            "dnp": "dnp" in flags,
            "exclude_from_bom": "exclude_from_bom" in flags,
            "exclude_from_pos_files": "exclude_from_pos_files" in flags,
            "pos": (float(at[1]), float(at[2])) if at and len(at) > 2 else None,
            "side": "bottom" if (_child(fp, "layer") or [None, ""])[1] == "B.Cu" else "top",
        }
    return parts


# --------------------------------------------------------------------------- compare


def _state(name: str, value: bool) -> str:
    if name == "dnp":
        return "DNP" if value else "populated"
    return "set" if value else "not set"


def _ref_key(ref: str) -> Tuple[str, int, str]:
    m = re.match(r"^(\D*)(\d*)(.*)$", ref)
    prefix, num, rest = m.groups() if m else (ref, "", "")
    return prefix, int(num) if num else -1, rest


def compare_parts(sch_parts: Dict[str, Dict[str, Any]], pcb_parts: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return one violation per reference/attribute that differs between schematic and board.

    Parts missing on either side are left to KiCad's schematic parity check (DRC).
    """
    violations: List[Dict[str, Any]] = []
    for ref in sorted(set(sch_parts) & set(pcb_parts), key=_ref_key):
        sch, pcb = sch_parts[ref], pcb_parts[ref]
        for key, label in ATTRIBUTES.items():
            if sch.get(key) is None or bool(sch[key]) == bool(pcb.get(key)):
                continue
            pos = pcb.get("pos")
            violations.append(
                {
                    "category": "dnp",
                    "type": f"{key}_mismatch",
                    "severity": "error",
                    "excluded": False,
                    "reference": ref,
                    "attribute": key,
                    "schematic": bool(sch[key]),
                    "pcb": bool(pcb.get(key)),
                    "description": f"{ref}: '{label}' is {_state(key, sch[key])} in schematic "
                    f"but {_state(key, bool(pcb.get(key)))} on PCB",
                    "items": [f"Symbol {ref} ({sch.get('sheet', '')})", f"Footprint {ref} ({pcb.get('side', 'top')})"],
                    "location": f"({pos[0]:g}, {pos[1]:g})" if pos else "",
                }
            )
    return violations


def run_dnp_check(sch_file: Path, pcb_file: Path) -> Dict[str, Any]:
    """Compare DNP/BOM/position attributes and return a summary like the ERC/DRC parsers."""
    sch_parts = collect_schematic_parts(sch_file, Path(pcb_file).stem)
    pcb_parts = collect_board_parts(pcb_file)
    violations = compare_parts(sch_parts, pcb_parts)
    dnp_refs = sorted((r for r, a in sch_parts.items() if a["dnp"]), key=_ref_key)
    return {
        "errors": len(violations),
        "warnings": 0,
        "excluded": 0,
        "mismatched_parts": len({v["reference"] for v in violations}),
        "dnp_parts": len(dnp_refs),
        "dnp_references": dnp_refs,
        "compared": len(set(sch_parts) & set(pcb_parts)),
        "units": "mm",
        "violations": violations,
    }


def describe_dnp(summary: Dict[str, Any]) -> str:
    text = f"{summary.get('compared', 0)} parts compared, {summary.get('dnp_parts', 0)} DNP"
    if summary.get("errors"):
        refs = sorted({v["reference"] for v in summary.get("violations", [])}, key=_ref_key)
        shown = ", ".join(refs[:10]) + (", ..." if len(refs) > 10 else "")
        text += f", {summary['errors']} mismatches in {len(refs)} parts: {shown}"
    else:
        text += ", schematic and PCB match"
    return text
