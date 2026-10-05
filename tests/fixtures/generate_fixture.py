"""Regenerate the tiny KiCad 9 fixture project in tests/fixtures/ci_fixture.

The files are written in KiCad 9 format (readable by KiCad 9 and 10) with
deterministic UUIDs, so rerunning this script produces identical files.

Design: root sheet with a 2-pin power connector (J1) and a sub-sheet "LEDs"
with two resistor + LED channels (R1/D1, R2/D2). 2-layer board, fully routed.

Usage: python3 tests/fixtures/generate_fixture.py
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

PROJECT = "ci_fixture"
OUT_DIR = Path(__file__).resolve().parent / PROJECT
NS = uuid.UUID("5b0e7c52-8f1e-4d43-9a39-6c3c1f0b9a10")


def uid(name: str) -> str:
    return str(uuid.uuid5(NS, name))


ROOT_UUID = uid("root")
SHEET_UUID = uid("sheet:LEDs")
TITLE_BLOCK = '\t(title_block\n\t\t(title "CI Fixture")\n\t\t(date "2026-01-01")\n\t\t(rev "A")\n\t)\n'

FONT = "(effects (font (size 1.27 1.27)))"
FONT_HIDE = "(effects (font (size 1.27 1.27)) (hide yes))"


def _pin(kind: str, x: float, y: float, rot: int, length: float, name: str, number: str) -> str:
    return (
        f'(pin {kind} line (at {x} {y} {rot}) (length {length}) '
        f'(name "{name}" {FONT}) (number "{number}" {FONT}))'
    )


def _lib_props(ref: str, value: str, desc: str, ref_hidden: bool = False) -> str:
    ref_fx = FONT_HIDE if ref_hidden else FONT
    return (
        f'(property "Reference" "{ref}" (at 0 2.54 0) {ref_fx})'
        f'(property "Value" "{value}" (at 0 -2.54 0) {FONT})'
        f'(property "Footprint" "" (at 0 0 0) {FONT_HIDE})'
        f'(property "Datasheet" "" (at 0 0 0) {FONT_HIDE})'
        f'(property "Description" "{desc}" (at 0 0 0) {FONT_HIDE})'
    )


def _line(points: str, width: float = 0) -> str:
    return f"(polyline (pts {points}) (stroke (width {width}) (type default)) (fill (type none)))"


LIB_SYMBOLS = {
    "Device:R": (
        '(symbol "Device:R" (pin_numbers (hide yes)) (pin_names (offset 0)) (exclude_from_sim no) (in_bom yes) (on_board yes)'
        + _lib_props("R", "R", "Resistor")
        + '(property "ki_fp_filters" "R_*" (at 0 0 0) ' + FONT_HIDE + ")"
        + '(symbol "R_0_1" (rectangle (start -1.016 -2.54) (end 1.016 2.54) (stroke (width 0.254) (type default)) (fill (type none))))'
        + '(symbol "R_1_1" '
        + _pin("passive", 0, 3.81, 270, 1.27, "", "1")
        + _pin("passive", 0, -3.81, 90, 1.27, "", "2")
        + ")(embedded_fonts no))"
    ),
    "Device:LED": (
        '(symbol "Device:LED" (pin_numbers (hide yes)) (pin_names (offset 1.016) (hide yes)) (exclude_from_sim no) (in_bom yes) (on_board yes)'
        + _lib_props("D", "LED", "Light emitting diode")
        + '(property "ki_fp_filters" "LED* LED_SMD:* LED_THT:*" (at 0 0 0) ' + FONT_HIDE + ")"
        + '(symbol "LED_0_1" '
        + _line("(xy -1.27 -1.27) (xy -1.27 1.27)", 0.254)
        + _line("(xy -1.27 0) (xy 1.27 0)")
        + _line("(xy 1.27 -1.27) (xy 1.27 1.27) (xy -1.27 0) (xy 1.27 -1.27)", 0.254)
        + ")"
        + '(symbol "LED_1_1" '
        + _pin("passive", -3.81, 0, 0, 2.54, "K", "1")
        + _pin("passive", 3.81, 0, 180, 2.54, "A", "2")
        + ")(embedded_fonts no))"
    ),
    "Connector_Generic:Conn_01x02": (
        '(symbol "Connector_Generic:Conn_01x02" (pin_names (offset 1.016) (hide yes)) (exclude_from_sim no) (in_bom yes) (on_board yes)'
        + _lib_props("J", "Conn_01x02", "Generic connector, single row, 01x02")
        + '(property "ki_fp_filters" "Connector*:*_1x??_*" (at 0 0 0) ' + FONT_HIDE + ")"
        + '(symbol "Conn_01x02_1_1" (rectangle (start -1.27 1.27) (end 1.27 -3.81) (stroke (width 0.254) (type default)) (fill (type background)))'
        + _pin("passive", -5.08, 0, 0, 3.81, "Pin_1", "1")
        + _pin("passive", -5.08, -2.54, 0, 3.81, "Pin_2", "2")
        + ")(embedded_fonts no))"
    ),
    "power:+5V": (
        '(symbol "power:+5V" (power) (pin_numbers (hide yes)) (pin_names (offset 0) (hide yes)) (exclude_from_sim no) (in_bom yes) (on_board yes)'
        + _lib_props("#PWR", "+5V", "Power symbol creates a global label with name +5V", ref_hidden=True)
        + '(symbol "+5V_0_1" '
        + _line("(xy -0.762 1.27) (xy 0 2.54) (xy 0.762 1.27)")
        + _line("(xy 0 0) (xy 0 2.54)")
        + ")"
        + '(symbol "+5V_1_1" ' + _pin("power_in", 0, 0, 90, 0, "", "1") + ")(embedded_fonts no))"
    ),
    "power:GND": (
        '(symbol "power:GND" (power) (pin_numbers (hide yes)) (pin_names (offset 0) (hide yes)) (exclude_from_sim no) (in_bom yes) (on_board yes)'
        + _lib_props("#PWR", "GND", "Power symbol creates a global label with name GND, ground", ref_hidden=True)
        + '(symbol "GND_0_1" '
        + _line("(xy 0 0) (xy 0 -1.27) (xy 1.27 -1.27) (xy 0 -2.54) (xy -1.27 -1.27) (xy 0 -1.27)")
        + ")"
        + '(symbol "GND_1_1" ' + _pin("power_in", 0, 0, 270, 0, "", "1") + ")(embedded_fonts no))"
    ),
    "power:PWR_FLAG": (
        '(symbol "power:PWR_FLAG" (power) (pin_numbers (hide yes)) (pin_names (offset 0) (hide yes)) (exclude_from_sim no) (in_bom yes) (on_board yes)'
        + _lib_props("#FLG", "PWR_FLAG", "Special symbol for telling ERC where power comes from", ref_hidden=True)
        + '(symbol "PWR_FLAG_0_0" ' + _pin("power_out", 0, 0, 90, 0, "", "1") + ")"
        + '(symbol "PWR_FLAG_0_1" '
        + _line("(xy 0 0) (xy 0 1.27) (xy -1.016 1.905) (xy 0 2.54) (xy 1.016 1.905) (xy 0 1.27)")
        + ")(embedded_fonts no))"
    ),
}

# Parts placed on the board: ref -> (lib_id, value, footprint, mpn, manufacturer, sheet)
PARTS = {
    "J1": ("Connector_Generic:Conn_01x02", "PWR_IN", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", "61300211121", "Wurth", "root"),
    "R1": ("Device:R", "1k", "Resistor_SMD:R_0805_2012Metric", "RC0805FR-071KL", "Yageo", "leds"),
    "R2": ("Device:R", "1k", "Resistor_SMD:R_0805_2012Metric", "RC0805FR-071KL", "Yageo", "leds"),
    "D1": ("Device:LED", "RED", "LED_SMD:LED_0805_2012Metric", "LTST-C171KRKT", "Lite-On", "leds"),
    "D2": ("Device:LED", "GREEN", "LED_SMD:LED_0805_2012Metric", "LTST-C171KGKT", "Lite-On", "leds"),
}


def _sch_symbol(ref: str, lib_id: str, x: float, y: float, rot: int, value: str, sheet_path: str,
                footprint: str = "", mpn: str = "", manufacturer: str = "", pins=("1", "2")) -> str:
    hidden_ref = ref.startswith("#")
    ref_fx = FONT_HIDE if hidden_ref else FONT
    extra = ""
    if mpn:
        extra += f'\t\t(property "MPN" "{mpn}" (at {x} {y} 0) {FONT_HIDE})\n'
    if manufacturer:
        extra += f'\t\t(property "Manufacturer" "{manufacturer}" (at {x} {y} 0) {FONT_HIDE})\n'
    pin_txt = "".join(f'\t\t(pin "{p}" (uuid "{uid(f"pin:{ref}:{p}")}"))\n' for p in pins)
    return (
        f'\t(symbol (lib_id "{lib_id}") (at {x} {y} {rot}) (unit 1) (exclude_from_sim no) (in_bom {"no" if hidden_ref else "yes"}) '
        f'(on_board {"no" if hidden_ref else "yes"}) (dnp no) (uuid "{uid(f"sym:{ref}")}")\n'
        f'\t\t(property "Reference" "{ref}" (at {x + 2.54} {y - 1.27} 0) {ref_fx})\n'
        f'\t\t(property "Value" "{value}" (at {x + 2.54} {y + 1.27} 0) {FONT})\n'
        f'\t\t(property "Footprint" "{footprint}" (at {x} {y} 0) {FONT_HIDE})\n'
        f'\t\t(property "Datasheet" "" (at {x} {y} 0) {FONT_HIDE})\n'
        f'\t\t(property "Description" "" (at {x} {y} 0) {FONT_HIDE})\n'
        f"{extra}{pin_txt}"
        f'\t\t(instances (project "{PROJECT}" (path "{sheet_path}" (reference "{ref}") (unit 1))))\n'
        "\t)\n"
    )


def _wire(x1: float, y1: float, x2: float, y2: float, name: str) -> str:
    return f'\t(wire (pts (xy {x1} {y1}) (xy {x2} {y2})) (stroke (width 0) (type default)) (uuid "{uid(name)}"))\n'


def _sch_file(body: str, file_uuid: str, libs, root: bool) -> str:
    lib_txt = "".join(f"\t\t{LIB_SYMBOLS[name]}\n" for name in libs)
    tail = '\t(sheet_instances (path "/" (page "1")))\n' if root else ""
    return (
        '(kicad_sch\n\t(version 20250114)\n\t(generator "eeschema")\n\t(generator_version "9.0")\n'
        f'\t(uuid "{file_uuid}")\n\t(paper "A4")\n{TITLE_BLOCK}'
        f"\t(lib_symbols\n{lib_txt}\t)\n{body}{tail}\t(embedded_fonts no)\n)\n"
    )


def build_root_sch() -> str:
    root_path = f"/{ROOT_UUID}"
    j = PARTS["J1"]
    body = _sch_symbol("J1", j[0], 76.2, 76.2, 0, j[1], root_path, j[2], j[3], j[4])
    body += _wire(71.12, 76.2, 63.5, 76.2, "w:j1p1")
    body += _wire(71.12, 78.74, 66.04, 78.74, "w:j1p2a")
    body += _wire(66.04, 78.74, 66.04, 83.82, "w:j1p2b")
    body += _sch_symbol("#PWR01", "power:+5V", 63.5, 76.2, 0, "+5V", root_path, pins=("1",))
    body += _sch_symbol("#FLG01", "power:PWR_FLAG", 63.5, 76.2, 0, "PWR_FLAG", root_path, pins=("1",))
    body += _sch_symbol("#PWR02", "power:GND", 66.04, 83.82, 0, "GND", root_path, pins=("1",))
    body += _sch_symbol("#FLG02", "power:PWR_FLAG", 66.04, 83.82, 0, "PWR_FLAG", root_path, pins=("1",))
    body += (
        f'\t(sheet (at 88.9 63.5) (size 20.32 10.16) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n'
        f'\t\t(stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0000)) (uuid "{SHEET_UUID}")\n'
        f'\t\t(property "Sheetname" "LEDs" (at 88.9 62.7884 0) (effects (font (size 1.27 1.27)) (justify left bottom)))\n'
        f'\t\t(property "Sheetfile" "leds.kicad_sch" (at 88.9 74.2446 0) (effects (font (size 1.27 1.27)) (justify left top)))\n'
        f'\t\t(instances (project "{PROJECT}" (path "/{ROOT_UUID}" (page "2"))))\n'
        "\t)\n"
    )
    libs = ["Connector_Generic:Conn_01x02", "power:+5V", "power:GND", "power:PWR_FLAG"]
    return _sch_file(body, ROOT_UUID, libs, root=True)


def build_leds_sch() -> str:
    sheet_path = f"/{ROOT_UUID}/{SHEET_UUID}"
    body = ""
    pwr = 3
    for idx, (r, d, dx) in enumerate((("R1", "D1", 0.0), ("R2", "D2", 25.4)), start=1):
        rx = round(101.6 + dx, 2)
        rp, dp = PARTS[r], PARTS[d]
        body += _sch_symbol(r, rp[0], rx, 81.28, 0, rp[1], sheet_path, rp[2], rp[3], rp[4])
        # LED rotated 180 degrees: anode at (rx + 3.81, 93.98), cathode at (rx + 11.43, 93.98).
        body += _sch_symbol(d, dp[0], round(rx + 7.62, 2), 93.98, 180, dp[1], sheet_path, dp[2], dp[3], dp[4])
        body += _sch_symbol(f"#PWR{pwr:02d}", "power:+5V", rx, 77.47, 0, "+5V", sheet_path, pins=("1",))
        body += _sch_symbol(f"#PWR{pwr + 1:02d}", "power:GND", round(rx + 11.43, 2), 93.98, 0, "GND", sheet_path, pins=("1",))
        pwr += 2
        body += _wire(rx, 85.09, rx, 93.98, f"w:{r}a")
        body += _wire(rx, 93.98, round(rx + 3.81, 2), 93.98, f"w:{r}b")
        body += (
            f'\t(label "LED{idx}_A" (at {rx} 93.98 0) (effects (font (size 1.27 1.27)) (justify left bottom)) '
            f'(uuid "{uid(f"label:{idx}")}"))\n'
        )
    libs = ["Device:LED", "Device:R", "power:+5V", "power:GND"]
    return _sch_file(body, uid("file:leds"), libs, root=False)


# ---------------------------------------------------------------- board

NETS = ["", "+5V", "GND", "/LEDs/LED1_A", "/LEDs/LED2_A"]


def _net(name: str) -> str:
    return f'(net {NETS.index(name)} "{name}")'


def _fp_text_props(ref: str, value: str, footprint: str, mpn: str, manufacturer: str, ref_y: float) -> str:
    fx = "(effects (font (size 1 1) (thickness 0.15)))"
    hidden = "(hide yes) (effects (font (size 1.27 1.27) (thickness 0.15)))"
    return (
        f'\t\t(property "Reference" "{ref}" (at 0 {ref_y} 0) (layer "F.SilkS") (uuid "{uid(f"fp:{ref}:ref")}") {fx})\n'
        f'\t\t(property "Value" "{value}" (at 0 {-ref_y} 0) (layer "F.Fab") (uuid "{uid(f"fp:{ref}:val")}") {fx})\n'
        f'\t\t(property "Footprint" "{footprint}" (at 0 0 0) (layer "F.Fab") (uuid "{uid(f"fp:{ref}:fp")}") {hidden})\n'
        f'\t\t(property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (uuid "{uid(f"fp:{ref}:ds")}") {hidden})\n'
        f'\t\t(property "Description" "" (at 0 0 0) (layer "F.Fab") (uuid "{uid(f"fp:{ref}:desc")}") {hidden})\n'
        f'\t\t(property "MPN" "{mpn}" (at 0 0 0) (layer "F.Fab") (uuid "{uid(f"fp:{ref}:mpn")}") {hidden})\n'
        f'\t\t(property "Manufacturer" "{manufacturer}" (at 0 0 0) (layer "F.Fab") (uuid "{uid(f"fp:{ref}:mfr")}") {hidden})\n'
    )


def _fp_rect(ref: str, layer: str, x1: float, y1: float, x2: float, y2: float, width: float, tag: str) -> str:
    return (
        f'\t\t(fp_rect (start {x1} {y1}) (end {x2} {y2}) (stroke (width {width}) (type solid)) (fill no) '
        f'(layer "{layer}") (uuid "{uid(f"fp:{ref}:{tag}")}"))\n'
    )


def _fp_line(ref: str, layer: str, x1: float, y1: float, x2: float, y2: float, tag: str) -> str:
    return (
        f'\t\t(fp_line (start {x1} {y1}) (end {x2} {y2}) (stroke (width 0.12) (type solid)) '
        f'(layer "{layer}") (uuid "{uid(f"fp:{ref}:{tag}")}"))\n'
    )


def _footprint(ref: str, x: float, y: float, rot: int, pad_nets, kind: str) -> str:
    lib_id, value, footprint, mpn, manufacturer, sheet = PARTS[ref]
    if sheet == "root":
        path, sheetname, sheetfile = f"/{uid(f'sym:{ref}')}", "/", f"{PROJECT}.kicad_sch"
    else:
        path, sheetname, sheetfile = f"/{SHEET_UUID}/{uid(f'sym:{ref}')}", "/LEDs/", "leds.kicad_sch"
    at = f"(at {x} {y} {rot})" if rot else f"(at {x} {y})"
    out = f'\t(footprint "{footprint}" (layer "F.Cu") (uuid "{uid(f"fp:{ref}")}") {at}\n'
    if kind == "smd":
        out += _fp_text_props(ref, value, footprint, mpn, manufacturer, -1.65)
        out += f'\t\t(path "{path}") (sheetname "{sheetname}") (sheetfile "{sheetfile}") (attr smd)\n'
        out += _fp_line(ref, "F.SilkS", -0.25, -0.9, 0.25, -0.9, "silk1")
        out += _fp_line(ref, "F.SilkS", -0.25, 0.9, 0.25, 0.9, "silk2")
        out += _fp_rect(ref, "F.CrtYd", -1.68, -0.95, 1.68, 0.95, 0.05, "crtyd")
        out += _fp_rect(ref, "F.Fab", -1, -0.625, 1, 0.625, 0.1, "fab")
        dx = 0.9125 if ref.startswith("R") else 0.9375
        w = 1.025 if ref.startswith("R") else 0.975
        for num, sign in (("1", -1), ("2", 1)):
            pin_type = "passive"
            out += (
                f'\t\t(pad "{num}" smd roundrect (at {sign * dx} 0{" " + str(rot) if rot else ""}) (size {w} 1.4) '
                f'(layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.243902) {_net(pad_nets[num])} '
                f'(pintype "{pin_type}") (uuid "{uid(f"pad:{ref}:{num}")}"))\n'
            )
    else:
        out += _fp_text_props(ref, value, footprint, mpn, manufacturer, -2.33)
        out += f'\t\t(path "{path}") (sheetname "{sheetname}") (sheetfile "{sheetfile}") (attr through_hole)\n'
        out += _fp_rect(ref, "F.SilkS", -1.33, -1.33, 1.33, 3.87, 0.12, "silk")
        out += _fp_rect(ref, "F.CrtYd", -1.8, -1.8, 1.8, 4.35, 0.05, "crtyd")
        out += _fp_rect(ref, "F.Fab", -1.27, -1.27, 1.27, 3.81, 0.1, "fab")
        out += (
            f'\t\t(pad "1" thru_hole rect (at 0 0) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask") '
            f'(remove_unused_layers no) {_net(pad_nets["1"])} (pinfunction "Pin_1") (pintype "passive") (uuid "{uid(f"pad:{ref}:1")}"))\n'
            f'\t\t(pad "2" thru_hole oval (at 0 2.54) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask") '
            f'(remove_unused_layers no) {_net(pad_nets["2"])} (pinfunction "Pin_2") (pintype "passive") (uuid "{uid(f"pad:{ref}:2")}"))\n'
        )
    out += "\t)\n"
    return out


def _segment(net: str, pts, tag: str) -> str:
    out = ""
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        out += (
            f'\t(segment (start {x1} {y1}) (end {x2} {y2}) (width 0.25) (layer "F.Cu") '
            f'(net {NETS.index(net)}) (uuid "{uid(f"seg:{tag}:{i}")}"))\n'
        )
    return out


def build_pcb() -> str:
    layers = (
        '\t(layers\n'
        '\t\t(0 "F.Cu" signal)\n\t\t(2 "B.Cu" signal)\n'
        '\t\t(9 "F.Adhes" user "F.Adhesive")\n\t\t(11 "B.Adhes" user "B.Adhesive")\n'
        '\t\t(13 "F.Paste" user)\n\t\t(15 "B.Paste" user)\n'
        '\t\t(5 "F.SilkS" user "F.Silkscreen")\n\t\t(7 "B.SilkS" user "B.Silkscreen")\n'
        '\t\t(1 "F.Mask" user)\n\t\t(3 "B.Mask" user)\n'
        '\t\t(17 "Dwgs.User" user "User.Drawings")\n\t\t(19 "Cmts.User" user "User.Comments")\n'
        '\t\t(21 "Eco1.User" user "User.Eco1")\n\t\t(23 "Eco2.User" user "User.Eco2")\n'
        '\t\t(25 "Edge.Cuts" user)\n\t\t(27 "Margin" user)\n'
        '\t\t(31 "F.CrtYd" user "F.Courtyard")\n\t\t(29 "B.CrtYd" user "B.Courtyard")\n'
        '\t\t(35 "F.Fab" user)\n\t\t(33 "B.Fab" user)\n'
        "\t)\n"
    )
    out = (
        '(kicad_pcb\n\t(version 20241229)\n\t(generator "pcbnew")\n\t(generator_version "9.0")\n'
        "\t(general (thickness 1.6) (legacy_teardrops no))\n"
        f'\t(paper "A4")\n{TITLE_BLOCK}{layers}'
        "\t(setup (pad_to_mask_clearance 0) (allow_soldermask_bridges_in_footprints no) (tenting front back))\n"
    )
    out += "".join(f'\t(net {i} "{name}")\n' for i, name in enumerate(NETS))
    out += _footprint("J1", 104, 106, 0, {"1": "+5V", "2": "GND"}, "tht")
    out += _footprint("R1", 112, 104, 0, {"1": "+5V", "2": "/LEDs/LED1_A"}, "smd")
    out += _footprint("D1", 118, 104, 180, {"1": "GND", "2": "/LEDs/LED1_A"}, "smd")
    out += _footprint("R2", 112, 112, 0, {"1": "+5V", "2": "/LEDs/LED2_A"}, "smd")
    out += _footprint("D2", 118, 112, 180, {"1": "GND", "2": "/LEDs/LED2_A"}, "smd")
    out += (
        f'\t(gr_rect (start 100 100) (end 126 119) (stroke (width 0.05) (type default)) (fill no) '
        f'(layer "Edge.Cuts") (uuid "{uid("edge")}"))\n'
    )
    out += _segment("+5V", [(104, 106), (108, 106), (108, 104), (111.0875, 104)], "p5a")
    out += _segment("+5V", [(108, 106), (108, 112), (111.0875, 112)], "p5b")
    out += _segment("/LEDs/LED1_A", [(112.9125, 104), (117.0625, 104)], "l1")
    out += _segment("/LEDs/LED2_A", [(112.9125, 112), (117.0625, 112)], "l2")
    out += _segment("GND", [(118.9375, 104), (122, 104), (122, 116), (104, 116), (104, 108.54)], "g1")
    out += _segment("GND", [(118.9375, 112), (122, 112)], "g2")
    out += "\t(embedded_fonts no)\n)\n"
    return out


def build_pro() -> str:
    pro = {
        "board": {"design_settings": {"drc_exclusions": []}},
        "erc": {"erc_exclusions": []},
        "meta": {"filename": f"{PROJECT}.kicad_pro", "version": 3},
        "sheets": [[ROOT_UUID, "Root"], [SHEET_UUID, "LEDs"]],
    }
    return json.dumps(pro, indent=2) + "\n"


def build_plugin_config() -> str:
    cfg = {
        "paths": {
            "sch_pdf": "doc/schematics",
            "step": "3d",
            "manufacturing": "manufacturing",
            "renders": "renders",
            "visual": "doc/visual",
        },
        "exports": {
            "sch_pdf": True,
            "step": True,
            "gerbers": True,
            "gerber_layer_preset": "2_layer_default",
            "drill": True,
            "position": True,
            "bom_collapsed": True,
            "bom_line_by_line": True,
            "visual": True,
        },
        "checks": {"erc": True, "drc": True, "fail_on": "error"},
        "integrations": {"jlcpcb": False, "ibom": True},
        "renders": {
            "top": True,
            "bottom": False,
            "left": False,
            "right": False,
            "iso1": False,
            "iso2": False,
            "quality": "low",
            "width": 640,
            "height": 360,
        },
    }
    return json.dumps(cfg, indent=2) + "\n"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = {
        f"{PROJECT}.kicad_sch": build_root_sch(),
        "leds.kicad_sch": build_leds_sch(),
        f"{PROJECT}.kicad_pcb": build_pcb(),
        f"{PROJECT}.kicad_pro": build_pro(),
        ".kicad_plugin_config.json": build_plugin_config(),
    }
    for name, text in files.items():
        (OUT_DIR / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {OUT_DIR / name}")


if __name__ == "__main__":
    main()
