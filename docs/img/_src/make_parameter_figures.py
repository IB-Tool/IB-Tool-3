"""Generate the parameter schematics (F13-F15) for docs/parameterization.md.

Run from anywhere:  python docs/img/_src/make_parameter_figures.py

Pure standard library; reuses the SVG and geometry helpers of
make_schematics.py. Writes SVG files to docs/img/parameterization/.

As in make_schematics.py, every number printed in a figure (areas, contact
shares) is computed from the drawn geometry and checked with an assertion
against the thresholds in the code:

- GapClose.py: BOUNDARY_OVERLAP_THRESHOLD_PCT = 70,
  BOUNDARY_OVERLAP_STRICT_PCT = 90, MAX_NARROW_GAP_EXTENT_M = 70,
  default max_gap_size = 4,900 m2, default max_hole_size = 10,000 m2
- ImportFilter.input_hu_filter: groups of touching buildings with
  Area > min_area are kept, then single buildings with
  Area > _MIN_BUILDING_AREA (35 m2)
"""
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_schematics import (  # noqa: E402  pylint: disable=wrong-import-position
    BUILDING, DASHED, LIGHT, MUTED, ORANGE, TEAL, WHITE,
    area, bbox, distance_to_poly, inside, line, panel_title, perimeter,
    polygon, poly_gap, rect_points, rotated_rect, along, settlement, text, write,
)

OUT_DIR = Path(__file__).resolve().parents[1] / "parameterization"

MAX_GAP_SIZE = 4900          # m2, default
MAX_HOLE_SIZE = 10000        # m2, default
CONTACT_PCT = 70             # BOUNDARY_OVERLAP_THRESHOLD_PCT
CONTACT_STRICT_PCT = 90      # BOUNDARY_OVERLAP_STRICT_PCT
NARROW_EXTENT_M = 70         # MAX_NARROW_GAP_EXTENT_M
MIN_AREA = 56.8              # m2, default min_area
MIN_BUILDING_AREA = 35       # m2, ImportFilter._MIN_BUILDING_AREA

FILTERED = 'fill-opacity="0.5"'


def fill_houses(ok, x0, y0, x1, y1, scale, seed, row_m=24):
    """Houses in rows along an east-west street, true scale, each rotated 5-10 deg.

    ok(p) decides whether a corner point (px) may be covered by a building.
    """
    rng = random.Random(seed)
    placed = []
    y = y0 + row_m * scale / 2
    while y < y1:
        x = x0 + rng.uniform(2, 8) * scale
        while x < x1:
            large = rng.random() < 0.07
            w, d = (rng.uniform(22, 30), rng.uniform(14, 18)) if large else \
                   (rng.uniform(9, 14), rng.uniform(7, 10))
            ang = rng.uniform(5, 10) * rng.choice((-1, 1))
            poly = rotated_rect(x + w * scale / 2, y + rng.uniform(-3, 3) * scale,
                                w * scale, d * scale, ang)
            nx0, ny0, nx1, ny1 = bbox(poly)
            free = all(nx1 + 2 < ox0 or ox1 + 2 < nx0 or ny1 + 2 < oy0 or oy1 + 2 < ny0
                       for ox0, oy0, ox1, oy1 in map(bbox, placed))
            if all(ok(p) for p in poly) and free and rng.random() > 0.15:
                placed.append(poly)
            x += w * scale + rng.uniform(4, 14) * scale
        y += row_m * scale
    return [polygon(p, BUILDING) for p in placed]


def gap_share(gap, open_len):
    """Share (%) of the gap boundary that touches the settlement."""
    return (perimeter(gap) - open_len) / perimeter(gap) * 100


# ---------------------------------------------------------------------------
# F13 - max_gap_size
# ---------------------------------------------------------------------------

def figure_max_gap_size():
    s = 1.4                                   # px per metre
    x0, y0, x1, y1 = 205, 112, 680, 280       # settlement extent (px)
    # Two notches open to the north: (west edge, width m, depth m)
    a0, aw, ad = 270, 40, 50
    b0, bw, bd = 455, 90, 80
    a1, b1 = a0 + aw * s, b0 + bw * s
    ya, yb = y0 + ad * s, y0 + bd * s
    outline = [(x0, y0), (a0, y0), (a0, ya), (a1, ya), (a1, y0), (b0, y0), (b0, yb),
               (b1, yb), (b1, y0), (x1, y0), (x1, y1), (x0, y1)]
    gap_a = rect_points(0, 0, aw, ad)         # metres
    gap_b = rect_points(0, 0, bw, bd)
    area_a, area_b = area(gap_a), area(gap_b)
    share_a, share_b = gap_share(gap_a, aw), gap_share(gap_b, bw)
    # Gap A: closed by filter 1
    assert area_a < MAX_GAP_SIZE and share_a >= CONTACT_PCT
    # Gap B: too large for filter 1, too open for filter 2, and its tessellation
    # triangles (two halves of the rectangle) all span the 120 m diagonal
    assert area_b >= MAX_GAP_SIZE and CONTACT_PCT <= share_b < CONTACT_STRICT_PCT
    assert math.hypot(bw, bd) >= NARROW_EXTENT_M

    def ok(p):
        return inside(p, outline) and distance_to_poly(p, outline) > 4 * s

    width, height = 700, 300
    body = [text(20, 30, f"max_gap_size = {MAX_GAP_SIZE:,} m² (default)",
                 size=17, weight="bold"),
            text(20, 52, "A gap at the settlement edge is closed only if it is smaller "
                 "than max_gap_size.", size=14, fill=MUTED)]

    # Reference square
    sq = 70 * s
    body.append(polygon(rect_points(30, y0, 30 + sq, y0 + sq), LIGHT, MUTED, 1.5,
                        'stroke-dasharray="6 4"'))
    body.append(text(30 + sq / 2, y0 + sq + 22, "70 m × 70 m", size=14, anchor="middle"))
    body.append(text(30 + sq / 2, y0 + sq + 42, f"= {70 * 70:,} m²", size=14,
                     anchor="middle", weight="bold"))

    body.append(settlement(outline))
    body.extend(fill_houses(ok, x0, y0, x1, y1, s, seed=13))
    body.append(polygon(rect_points(a0, y0, a1, ya), ORANGE, ORANGE, 1.5))
    body.append(line((a0, y0), (a1, y0), BUILDING, 3, DASHED))
    body.append(polygon(rect_points(b0, y0, b1, yb), WHITE, WHITE, 1))
    body.append(line((b0, y0), (b1, y0), BUILDING, 3, DASHED))
    body.append(polygon(outline, stroke=ORANGE, width=2.5))

    ca, cb = (a0 + a1) / 2, (b0 + b1) / 2
    body.append(text(ca, 78, f"{area_a:,.0f} m², {share_a:.0f} % contact", size=14,
                     anchor="middle"))
    body.append(text(ca, 98, "→ closed", size=14, anchor="middle", weight="bold",
                     fill=ORANGE))
    body.append(text(cb, 78, f"{area_b:,.0f} m², {share_b:.0f} % contact", size=14,
                     anchor="middle"))
    body.append(text(cb, 98, "→ stays open", size=14, anchor="middle", weight="bold",
                     fill=BUILDING))
    write("02_max_gap_size.svg", width, height, body, OUT_DIR)


# ---------------------------------------------------------------------------
# F14 - hole vs. gap
# ---------------------------------------------------------------------------

def figure_hole_vs_gap():
    s = 1.2
    width, height = 700, 330
    py0, py1 = 105, 270

    # Panel 1: hole = interior ring, fully enclosed
    hx0, hx1 = 25, 325
    outer = rect_points(hx0, py0, hx1, py1)
    hole = [(125, 150), (200, 140), (232, 178), (215, 228), (150, 236), (115, 196)]
    hole_m2 = area(hole) / s ** 2
    assert hole_m2 <= MAX_HOLE_SIZE

    def ok_hole(p):
        return (inside(p, outer) and distance_to_poly(p, outer) > 4 * s
                and not inside(p, hole) and distance_to_poly(p, hole) > 4 * s)

    # Panel 2: gap = notch open to the north, partly enclosed
    gx0, gx1 = 375, 675
    nw, nd = 70, 58
    n0 = 480
    n1, ny = n0 + nw * s, py0 + nd * s
    notch = [(gx0, py0), (n0, py0), (n0, ny), (n1, ny), (n1, py0), (gx1, py0),
             (gx1, py1), (gx0, py1)]
    gap_m = rect_points(0, 0, nw, nd)
    gap_m2, share = area(gap_m), gap_share(gap_m, nw)
    assert gap_m2 < MAX_GAP_SIZE and share >= CONTACT_PCT

    def ok_gap(p):
        return inside(p, notch) and distance_to_poly(p, notch) > 4 * s

    hole_subs = ["inside the settlement, fully enclosed",
                 f"filled if ≤ max_hole_size ({MAX_HOLE_SIZE:,} m²)"]
    gap_subs = ["at the settlement edge, partly enclosed",
                f"closed if < max_gap_size and ≥ {CONTACT_PCT} % contact"]
    body = [panel_title(hx0, 30, "1", "Hole", hole_subs),
            panel_title(gx0, 30, "2", "Gap", gap_subs)]
    body.append(settlement(outer))
    body.extend(fill_houses(ok_hole, hx0, py0, hx1, py1, s, seed=14))
    body.append(polygon(hole, ORANGE, ORANGE, 1.5))
    body.append(polygon(outer, stroke=ORANGE, width=2.5))

    body.append(settlement(notch))
    body.extend(fill_houses(ok_gap, gx0, py0, gx1, py1, s, seed=41))
    body.append(polygon(rect_points(n0, py0, n1, ny), ORANGE, ORANGE, 1.5))
    body.append(line((n0, py0), (n1, py0), BUILDING, 3, DASHED))
    body.append(polygon(notch, stroke=ORANGE, width=2.5))

    body.append(text((hx0 + hx1) / 2, 298, f"{hole_m2:,.0f} m², 100 % contact → filled",
                     size=14, anchor="middle"))
    body.append(text((gx0 + gx1) / 2, 298, f"{gap_m2:,.0f} m², {share:.0f} % contact → closed",
                     size=14, anchor="middle"))
    body.append(polygon(rect_points(25, 309, 43, 321), ORANGE, ORANGE, 1.5))
    body.append(text(50, 320, "area added to the settlement", size=14))
    body.append(line((290, 315), (318, 315), BUILDING, 3, DASHED))
    body.append(text(325, 320, "boundary without settlement contact", size=14))
    write("03_hole_vs_gap.svg", width, height, body, OUT_DIR)


# ---------------------------------------------------------------------------
# F15 - min_area
# ---------------------------------------------------------------------------

def convex_hull(points):
    pts = sorted(set(points))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def min_area_filter(buildings, scale):
    """Port of input_hu_filter step 3 (dissolve touching -> Area > min_area,
    then single buildings Area > _MIN_BUILDING_AREA). Returns kept indices."""
    parent = list(range(len(buildings)))

    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i

    for i, bi in enumerate(buildings):
        for j in range(i):
            if poly_gap(bi, buildings[j]) < 1e-6:
                parent[root(i)] = root(j)
    group_area = {}
    for i, b in enumerate(buildings):
        group_area[root(i)] = group_area.get(root(i), 0) + area(b) / scale ** 2
    return [i for i, b in enumerate(buildings)
            if group_area[root(i)] > MIN_AREA and area(b) / scale ** 2 > MIN_BUILDING_AREA]


def figure_min_area():
    s = 3.6
    street_y = 256
    plot_w = 25                                        # metres

    def plot_buildings(px0):
        """Three plots along a street; returns (polygons, labels)."""
        def at(x_m, y_m):
            return (px0 + x_m * s, street_y - y_m * s)

        out = []
        # Plot 1: house + attached garage (18 m2), garden shed (12 m2)
        a = 6
        c = at(10, 15)
        house = rotated_rect(*c, 12 * s, 9 * s, a)
        garage_c = along(c, a, (12 + 3) / 2 * s, (-9 / 2 + 6 / 2) * s)
        out += [house, rotated_rect(*garage_c, 3 * s, 6 * s, a),
                rotated_rect(*at(18, 36), 3 * s, 4 * s, -8)]
        # Plot 2: house, detached workshop (42 m2) in the rear
        out += [rotated_rect(*at(plot_w + 12, 16), 11 * s, 10 * s, -7),
                rotated_rect(*at(plot_w + 9, 33), 7 * s, 6 * s, -9)]
        # Plot 3: house + attached annex (42 m2), small shed (7.5 m2)
        a = 8
        c = at(2 * plot_w + 11, 14)
        annex_c = along(c, a, 0, (8 / 2 + 6 / 2) * s)
        out += [rotated_rect(*c, 13 * s, 8 * s, a), rotated_rect(*annex_c, 7 * s, 6 * s, a),
                rotated_rect(*at(2 * plot_w + 19, 37), 2.5 * s, 3 * s, 6)]
        return out

    def outline(polys):
        m = 3 * s
        pts = [(x + dx, y + dy) for p in polys for x, y in p for dx in (-m, m) for dy in (-m, m)]
        return convex_hull(pts)

    width, height = 600, 300
    body = []
    for panel, px0 in enumerate((22, 312)):
        buildings = plot_buildings(px0)
        kept = min_area_filter(buildings, s)
        assert kept == [0, 3, 5, 6], kept       # houses and the 42 m2 annex
        removed = [i for i in range(len(buildings)) if i not in kept]
        drawn = buildings if panel == 0 else [buildings[i] for i in kept]
        body.append(settlement(outline(drawn)))
        body.append(line((px0 - 25, street_y + 14), (px0 + 3 * plot_w * s + 25, street_y + 14),
                         TEAL, 6))
        for k in range(1, 3):
            x = px0 + k * plot_w * s
            body.append(line((x, street_y + 6), (x, street_y - 46 * s), MUTED, 1,
                             'stroke-dasharray="3 4"'))
        for i, b in enumerate(buildings):
            if panel == 0 or i in kept:
                body.append(polygon(b, BUILDING))
            else:
                body.append(polygon(b, "#BDBDBD", extra=FILTERED))
        if panel == 1:
            for i in removed:
                bx0, by0, bx1, by1 = bbox(buildings[i])
                # Labels outside the boundary: front yard or above rear buildings
                ty = street_y - 6 if by1 > street_y - 20 * s else by0 - 7
                body.append(text((bx0 + bx1) / 2, ty,
                                 f"{area(buildings[i]) / s ** 2:.0f} m²",
                                 size=14, anchor="middle", fill=MUTED))

    body.append(text(15, 30, "Before: all buildings", size=17, weight="bold"))
    body.append(text(15, 52, "boundary reaches the rear sheds", size=14, fill=MUTED))
    body.append(text(305, 30, f"After: min_area = {MIN_AREA} m²", size=17, weight="bold"))
    body.append(text(305, 52, "boundary follows the houses", size=14, fill=MUTED))
    body.append(text(15, 290, f"Removed: groups of touching buildings ≤ {MIN_AREA} m², then "
                     f"single buildings ≤ {MIN_BUILDING_AREA} m².", size=14, fill=MUTED))
    write("04_min_area.svg", width, height, body, OUT_DIR)


if __name__ == "__main__":
    figure_max_gap_size()
    figure_hole_vs_gap()
    figure_min_area()
