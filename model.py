"""
Parametric storage tray with divider grid and lip lid.

All dimensions in millimetres. Every value is a design input; nothing is
hard-coded inside the geometry functions.

Defaults assume a 0.4 mm nozzle at 0.2 mm layer height in PLA:
    WALL  2.4 mm = 6 perimeters
    FLOOR 1.2 mm = 6 layers
    CLEARANCE 0.25 mm per face  (mating printed parts, 0.2-0.3 mm)
"""

import cadquery as cq

DEFAULTS = {
    "length": 120.0,        # X, outer
    "width": 80.0,          # Y, outer
    "height": 40.0,         # Z, outer
    "wall": 2.4,            # side wall, 6 x 0.4 mm nozzle
    "floor": 1.2,           # base thickness, 6 x 0.2 mm layers
    "corner": 3.0,          # vertical edge fillet radius, 0 = square
    "cols": 3,              # divider cells along X
    "rows": 2,              # divider cells along Y
    "divider": 1.6,         # divider thickness, 4 x 0.4 mm
    "divider_drop": 0.0,    # dividers stop this far below the rim
    "lid": True,
    "lid_thickness": 2.0,   # lid plate
    "lip_height": 6.0,      # how far the lip drops into the tray
    "lip_wall": 1.6,        # lip is a ring, not a plug - clears dividers
    "clearance": 0.25,      # per face, lip to inner wall
}


def _cavity_dims(p):
    inner_l = p["length"] - 2 * p["wall"]
    inner_w = p["width"] - 2 * p["wall"]
    cav_h = p["height"] - p["floor"]
    return inner_l, inner_w, cav_h


def validate(p):
    """Return a list of human-readable problems. Empty list means buildable."""
    errs = []
    inner_l, inner_w, cav_h = _cavity_dims(p)

    if inner_l <= 1 or inner_w <= 1:
        errs.append("Wall too thick for these outer dimensions - no cavity left.")
    if cav_h <= 1:
        errs.append("Floor thickness leaves no usable depth.")
    if p["corner"] >= min(p["length"], p["width"]) / 2:
        errs.append("Corner radius too large for the footprint.")

    # dividers must leave a usable cell
    if p["cols"] > 1:
        cell = (inner_l - (p["cols"] - 1) * p["divider"]) / p["cols"]
        if cell <= 2:
            errs.append(f"{p['cols']} columns leaves cells under 2 mm wide.")
    if p["rows"] > 1:
        cell = (inner_w - (p["rows"] - 1) * p["divider"]) / p["rows"]
        if cell <= 2:
            errs.append(f"{p['rows']} rows leaves cells under 2 mm deep.")

    if p["lid"]:
        lip_l = inner_l - 2 * p["clearance"]
        lip_w = inner_w - 2 * p["clearance"]
        if lip_l - 2 * p["lip_wall"] <= 1 or lip_w - 2 * p["lip_wall"] <= 1:
            errs.append("Lip wall too thick for the cavity.")
        if p["lip_height"] >= cav_h:
            errs.append("Lip is deeper than the tray cavity.")
    return errs


def build_tray(p):
    inner_l, inner_w, cav_h = _cavity_dims(p)

    solid = cq.Workplane("XY").box(
        p["length"], p["width"], p["height"], centered=(True, True, False)
    )
    if p["corner"] > 0:
        solid = solid.edges("|Z").fillet(p["corner"])

    cavity = cq.Workplane("XY").workplane(offset=p["floor"]).box(
        inner_l, inner_w, cav_h + 1, centered=(True, True, False)
    )
    inner_r = p["corner"] - p["wall"]
    if inner_r > 0.15:
        cavity = cavity.edges("|Z").fillet(inner_r)

    solid = solid.cut(cavity)

    # --- divider grid -------------------------------------------------
    div_h = cav_h - p["divider_drop"]
    if div_h > 0.2 and p["divider"] > 0:
        # columns: walls running across Y, spaced along X
        for i in range(1, int(p["cols"])):
            x = -inner_l / 2 + i * inner_l / p["cols"]
            blade = (
                cq.Workplane("XY")
                .workplane(offset=p["floor"])
                .center(x, 0)
                .box(p["divider"], inner_w, div_h, centered=(True, True, False))
            )
            solid = solid.union(blade)
        # rows: walls running across X, spaced along Y
        for j in range(1, int(p["rows"])):
            y = -inner_w / 2 + j * inner_w / p["rows"]
            blade = (
                cq.Workplane("XY")
                .workplane(offset=p["floor"])
                .center(0, y)
                .box(inner_l, p["divider"], div_h, centered=(True, True, False))
            )
            solid = solid.union(blade)

    return solid


def build_lid(p):
    """Lid sits plate-down at z=0, lip pointing up, ready to print as-is."""
    inner_l, inner_w, _ = _cavity_dims(p)
    lip_l = inner_l - 2 * p["clearance"]
    lip_w = inner_w - 2 * p["clearance"]

    plate = cq.Workplane("XY").box(
        p["length"], p["width"], p["lid_thickness"], centered=(True, True, False)
    )
    if p["corner"] > 0:
        plate = plate.edges("|Z").fillet(p["corner"])

    ring = cq.Workplane("XY").workplane(offset=p["lid_thickness"]).box(
        lip_l, lip_w, p["lip_height"], centered=(True, True, False)
    )
    lip_r = p["corner"] - p["wall"] - p["clearance"]
    if lip_r > 0.15:
        ring = ring.edges("|Z").fillet(lip_r)

    void = cq.Workplane("XY").workplane(offset=p["lid_thickness"] - 0.5).box(
        lip_l - 2 * p["lip_wall"],
        lip_w - 2 * p["lip_wall"],
        p["lip_height"] + 1,
        centered=(True, True, False),
    )
    lid = plate.union(ring.cut(void))
    return lid


def build_all(p):
    """Return (tray, lid_or_None)."""
    tray = build_tray(p)
    lid = build_lid(p) if p["lid"] else None
    return tray, lid


def preview_assembly(p, gap=10.0):
    """Both parts side by side in Y, as a single compound for preview."""
    tray, lid = build_all(p)
    if lid is None:
        return tray
    offset = p["width"] + gap
    return tray.union(lid.translate((0, offset, 0)))


def merge_params(raw):
    """Coerce incoming strings into typed params, filling gaps from DEFAULTS."""
    p = dict(DEFAULTS)
    for k, v in raw.items():
        if k not in p:
            continue
        if isinstance(p[k], bool):
            p[k] = str(v).lower() in ("1", "true", "yes", "on")
        elif isinstance(p[k], int) and not isinstance(p[k], bool):
            p[k] = max(1, int(float(v)))
        else:
            p[k] = float(v)
    return p
