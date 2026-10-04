"""Generate the algorithm schematics (F10a-F10e) for docs/how-it-works.md.

Run from anywhere:  python docs/img/_src/make_schematics.py

Pure standard library. Writes SVG files to docs/img/how-it-works/.

The geometry is not just drawn - it is computed with ports of the plugin's
own logic (``_main_angle`` / ``calc_bounding_rect`` from MST_Clustering.py,
``apply_filter_rules`` from helpers/edge_catch_utils.py), and every number
printed in a figure (BCR, contact shares, distances) is checked with an
assertion. The pictures therefore show what the code would do with the drawn
input, and cannot drift from the thresholds they illustrate.

Only SVG Tiny features are used (no <marker>, no <pattern>) so the files
render identically in browsers, Qt and QGIS.
"""
import math
import random
from html import escape
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "how-it-works"

# Palette taken from the plugin icon (icon.png, IB-Tool_Icon_2HiRes.png)
TEAL = "#007D85"      # icon grid     -> road network, accepted steps, contact
ORANGE = "#F7561A"    # icon letters  -> settlement outline, added areas, current step
PINK = "#FFBCB0"      # icon fill     -> settlement area
# Neutral greys (not in the icon) for buildings, text and rejected elements
BUILDING = "#3C3C3C"
TEXT = "#212121"
MUTED = "#616161"
LIGHT = "#E4E4E4"
WHITE = "#FFFFFF"

DASHED = 'stroke-dasharray="7 5"'


# ---------------------------------------------------------------------------
# SVG helpers
# ---------------------------------------------------------------------------

def svg_document(width, height, body):
    """Wrap body elements in an SVG document with a white background."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" font-family="sans-serif">\n'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="{WHITE}"/>\n'
        + "".join(body)
        + '</svg>\n'
    )


def text(x, y, content, size=15, anchor="start", weight="normal", fill=TEXT):
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" '
        f'font-weight="{weight}" fill="{fill}">{escape(content)}</text>\n'
    )


def polygon(points, fill="none", stroke="none", width=1.0, extra=""):
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return (
        f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="{width}" stroke-linejoin="round" {extra}/>\n'
    )


def line(p, q, stroke=TEXT, width=1.5, extra=""):
    return (
        f'<line x1="{p[0]:.1f}" y1="{p[1]:.1f}" x2="{q[0]:.1f}" y2="{q[1]:.1f}" '
        f'stroke="{stroke}" stroke-width="{width}" stroke-linecap="round" {extra}/>\n'
    )


def settlement(points, width=2.5):
    return polygon(points, PINK, ORANGE, width)


def road(p, q):
    return line(p, q, TEAL, 6)


def arrow_head(start, end, colour, size=11):
    """Filled triangle at `end`, pointing away from `start`."""
    ang = math.atan2(end[1] - start[1], end[0] - start[0])
    left = (end[0] - size * math.cos(ang - 0.45), end[1] - size * math.sin(ang - 0.45))
    right = (end[0] - size * math.cos(ang + 0.45), end[1] - size * math.sin(ang + 0.45))
    return polygon([end, left, right], colour)


def panel_title(x, y, number, title, subtitle_lines=()):
    out = text(x, y, f"{number}  {title}", size=17, weight="bold")
    for i, sub in enumerate(subtitle_lines):
        out += text(x, y + 21 * (i + 1), sub, size=14, fill=MUTED)
    return out


def check_mark(x, y, ok):
    symbol, colour = ("✓", TEAL) if ok else ("✗", BUILDING)
    return text(x, y, symbol, size=20, weight="bold", fill=colour)


def write(name, width, height, body, out_dir=OUT_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    path.write_text(svg_document(width, height, body), encoding="utf-8")
    size_kb = path.stat().st_size / 1024
    assert size_kb < 50, f"{name} is {size_kb:.1f} KB (budget 50 KB)"
    print(f"wrote {path.name} ({size_kb:.1f} KB)")


# ---------------------------------------------------------------------------
# Geometry helpers (SVG coordinates: x right, y down; angles in map
# convention: counter-clockwise from east, y up)
# ---------------------------------------------------------------------------

def rect_points(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def rotated_rect(cx, cy, w, h, angle_deg):
    """Rectangle of size w x h centred at (cx, cy), long side at angle_deg (map)."""
    a = math.radians(angle_deg)
    out = []
    for lx, ly in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        out.append((cx + lx * math.cos(a) - ly * math.sin(a),
                    cy - (lx * math.sin(a) + ly * math.cos(a))))
    return out


def along(origin, angle_deg, s, t=0.0):
    """Point at distance s along direction angle_deg and t to its left (map)."""
    a = math.radians(angle_deg)
    return (origin[0] + s * math.cos(a) - t * math.sin(a),
            origin[1] - (s * math.sin(a) + t * math.cos(a)))


def edges(poly):
    return list(zip(poly, poly[1:] + poly[:1]))


def area(points):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in edges(points))) / 2


def perimeter(points):
    return sum(math.dist(a, b) for a, b in edges(points))


def bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def foot_on_segment(p, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    t = ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / (vx * vx + vy * vy)
    t = max(0.0, min(1.0, t))
    return (a[0] + t * vx, a[1] + t * vy)


def distance_to_poly(pt, poly):
    return min(math.dist(pt, foot_on_segment(pt, a, b)) for a, b in edges(poly))


def poly_gap(p1, p2):
    """Distance between two non-overlapping polygons (edge to edge)."""
    return min(min(distance_to_poly(v, p2) for v in p1),
               min(distance_to_poly(v, p1) for v in p2))


def inside(pt, poly):
    x, y = pt
    result = False
    for (x0, y0), (x1, y1) in edges(poly):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            result = not result
    return result


def line_intersection(p1, p2, p3, p4):
    d = (p1[0] - p2[0]) * (p3[1] - p4[1]) - (p1[1] - p2[1]) * (p3[0] - p4[0])
    a = p1[0] * p2[1] - p1[1] * p2[0]
    b = p3[0] * p4[1] - p3[1] * p4[0]
    return ((a * (p3[0] - p4[0]) - (p1[0] - p2[0]) * b) / d,
            (a * (p3[1] - p4[1]) - (p1[1] - p2[1]) * b) / d)


def map_angle(p, q):
    """Direction of p->q in degrees, map convention, folded to [0, 180)."""
    return round(math.degrees(math.atan2(-(q[1] - p[1]), q[0] - p[0])) % 180, 1)


# ---------------------------------------------------------------------------
# Ports of the plugin logic
# ---------------------------------------------------------------------------

def main_angle(angle_length_pairs, max_diff=10):
    """Literal port of MST_Clustering._main_angle (_MAIN_ANGLE_MAX_DIFF = 10)."""
    sorted_pairs = sorted(angle_length_pairs, key=lambda p: p[0])
    groups = [[sorted_pairs[0]]]
    for pair in sorted_pairs[1:]:
        if abs(pair[0] - groups[-1][-1][0]) < max_diff:
            groups[-1].append(pair)
        else:
            groups.append([pair])
    group_sums = [sum(entry[1] for entry in group) for group in groups]
    max_group = groups[group_sums.index(max(group_sums))]
    current_angle = max_group[0][0]
    current_sum = 0
    length_sums = []
    for entry in max_group:
        if current_angle == entry[0]:
            current_sum += entry[1]
        else:
            length_sums.append(current_sum)
            current_sum = entry[1]
        current_angle = entry[0]
    if not length_sums:
        length_sums.append(current_sum)
    return max_group[length_sums.index(max(length_sums))][0], groups, max_group


def building_edges(polys):
    """Edges per building, without edges < 20 % of the building's longest edge
    (MST_Clustering._filter_short_edges, _MIN_EDGE_LENGTH_RATIO = 0.20)."""
    out = []
    for poly in polys:
        rows = [(a, b, math.dist(a, b)) for a, b in edges(poly)]
        longest = max(r[2] for r in rows)
        kept = [r for r in rows if r[2] >= 0.2 * longest]
        out.extend(kept if len(kept) >= 2 else rows)
    return out


def oriented_mbr(polys, scale=1.0):
    """Rectangle along the dominant direction enclosing all vertices
    (equivalent to MST_Clustering.calc_bounding_rect). Lengths in metres
    = px / scale."""
    rows = building_edges(polys)
    pairs = [(map_angle(a, b), length / scale) for a, b, length in rows]
    dominant, groups, max_group = main_angle(pairs)
    a = math.radians(dominant)
    u = (math.cos(a), -math.sin(a))        # map direction in SVG coordinates
    v = (math.sin(a), math.cos(a))
    pts = [p for poly in polys for p in poly]
    us = [p[0] * u[0] + p[1] * u[1] for p in pts]
    vs = [p[0] * v[0] + p[1] * v[1] for p in pts]
    corners = [(s * u[0] + t * v[0], s * u[1] + t * v[1])
               for s, t in ((min(us), min(vs)), (max(us), min(vs)),
                            (max(us), max(vs)), (min(us), max(vs)))]
    return corners, dominant, groups, max_group, rows


def bcr(polys, scale=1.0):
    corners = oriented_mbr(polys, scale)[0]
    return sum(area(p) for p in polys) / area(corners) * 100


def edgecatch_filter(lines, min_keep=2):
    """Port of edge_catch_utils.apply_filter_rules for one group of 4 lines.

    Each line: dict(key, start, end, distance (m), angle (deg, 0-360))."""
    def rule_max_distance(ls):
        return [ln for ln in ls if ln["distance"] < 70]

    def rule_endpoint_in_rectangle(ls):
        xs = [ln["start"][0] for ln in ls]
        ys = [ln["start"][1] for ln in ls]
        keep, removed = [], []
        for ln in ls:
            x, y = ln["end"]
            if min(xs) - 1e-3 <= x <= max(xs) + 1e-3 and min(ys) - 1e-3 <= y <= max(ys) + 1e-3:
                removed.append(ln)
            else:
                keep.append(ln)
        if len(keep) >= min_keep:
            return keep
        removed.sort(key=lambda ln: ln["distance"])
        return keep + removed[:min_keep - len(keep)]

    def rule_parallel_close_endpoints(ls, scale):
        remove = set()
        for i in range(len(ls)):
            for j in range(i + 1, len(ls)):
                diff = abs(ls[i]["angle"] - ls[j]["angle"])
                diff = 360 - diff if diff > 180 else diff
                opp = abs(abs(ls[i]["angle"] - ls[j]["angle"]) - 180)
                opp = 360 - opp if opp > 180 else opp
                if min(diff, opp) <= 2 and math.dist(ls[i]["end"], ls[j]["end"]) / scale <= 5:
                    remove.add(i if ls[i]["distance"] > ls[j]["distance"] else j)
        if remove and len(ls) - len(remove) >= min_keep:
            return [ln for k, ln in enumerate(ls) if k not in remove]
        return ls

    scale = lines[0]["scale"]
    ls = rule_max_distance(lines)
    if len(ls) <= min_keep:
        return ls
    ls = rule_endpoint_in_rectangle(ls)
    if len(ls) <= min_keep:
        return ls
    ls = rule_parallel_close_endpoints(ls, scale)
    if len(ls) <= min_keep:
        return ls
    if len(ls) == 4:
        norm = [ln["angle"] % 180 for ln in ls]
        if max(norm) - min(norm) <= 5:
            return sorted(ls, key=lambda ln: ln["distance"])[:2]
    # Rule 4: with >= 3 direction groups (+-2 deg, _group_lines_by_angle), drop
    # the group whose mean length is > 2 x the next-longest group's mean
    if len(ls) <= 2:
        return ls
    ordered = sorted(ls, key=lambda ln: ln["angle"])
    groups = [[ordered[0]]]
    for ln in ordered[1:]:
        if abs(ln["angle"] - groups[-1][-1]["angle"]) <= 2:
            groups[-1].append(ln)
        else:
            groups.append([ln])
    if len(groups) <= 1:
        return ls
    stats = sorted(((sum(ln["distance"] for ln in g) / len(g), g) for g in groups),
                   key=lambda s: s[0], reverse=True)
    remaining = sum(len(g) for _, g in stats[1:])
    if remaining >= min_keep and stats[0][0] > 2.0 * stats[1][0] and len(groups) >= 3:
        return [ln for _, g in stats[1:] for ln in g]
    return ls


# ---------------------------------------------------------------------------
# F10a - Oriented minimum bounding rectangle (Algorithm 1)
# ---------------------------------------------------------------------------

def figure_mbr():
    """F10a: oriented MBR of a small group of houses along a street."""
    scale = 5.0
    street = 25                                   # street direction (map, deg)
    # (along-street, offset, width, depth, own angle) in metres / degrees
    houses = [(0, 0, 12, 9, 25), (15, 1.5, 10, 8, 21), (29, -0.5, 13, 10, 28),
              (6, -11, 6, 5, 33), (22, -13, 9, 7, 18)]

    def buildings_at(origin):
        out = []
        for s, t, w, h, ang in houses:
            c = along(origin, street, s * scale, t * scale)
            out.append(rotated_rect(c[0], c[1], w * scale, h * scale, ang))
        return out

    # Centre the group in each panel
    probe = buildings_at((0, 0))
    bx0, by0, bx1, by1 = bbox([p for b in probe for p in b])

    def placed(px_centre, py_centre):
        return buildings_at((px_centre - (bx0 + bx1) / 2, py_centre - (by0 + by1) / 2))

    width, height = 860, 440
    body = []
    panels = [20, 300, 580]
    cy = 225

    blds0 = placed(panels[0] + 120, cy)
    corners, dominant, groups, max_group, rows = oriented_mbr(blds0, scale)
    group_sum = sum(e[1] for e in max_group)
    other = [g for g in groups if g is not max_group]
    assert len(other) == 1
    other_sum = sum(e[1] for e in other[0])
    lo, hi = min(e[0] for e in max_group), max(e[0] for e in max_group)
    olo, ohi = min(e[0] for e in other[0]), max(e[0] for e in other[0])
    bld_area = sum(area(b) for b in blds0) / scale ** 2
    mbr_area = area(corners) / scale ** 2
    ratio = bld_area / mbr_area * 100

    titles = [
        ("1", "Collect building edges",
         ["edges < 20 % of a building's", "longest edge are ignored"]),
        ("2", "Find the dominant direction",
         ["group directions within ±10°;", "largest total length wins"]),
        ("3", "Oriented rectangle",
         [f"along {dominant:.0f}°, encloses all vertices",
          f"BCR = {bld_area:.0f} / {mbr_area:.0f} m² = {ratio:.0f} %"]),
    ]
    for i, px0 in enumerate(panels):
        number, title, subs = titles[i]
        body.append(panel_title(px0, 34, number, title, subs))
        blds = placed(px0 + 120, cy)

        if i == 2:
            corners_i = oriented_mbr(blds, scale)[0]
            ax0, ay0, ax1, ay1 = bbox([p for b in blds for p in b])
            body.append(polygon(rect_points(ax0, ay0, ax1, ay1), stroke=MUTED, width=1.5,
                                extra=DASHED))
            body.append(text(ax0, ay0 - 8, "axis-aligned box, for comparison",
                             size=13, fill=MUTED))
            body.append(settlement(corners_i))

        for b in blds:
            if i == 1:
                body.append(polygon(b, LIGHT))
                for a, c in edges(b):
                    in_group = lo <= map_angle(a, c) <= hi
                    body.append(line(a, c, ORANGE if in_group else TEAL, 4))
            else:
                body.append(polygon(b, BUILDING))

        if i == 1:
            # Direction arrow below the group, clear of the buildings
            lowest = max(p[1] for b in blds for p in b)
            start = (px0 + 95, lowest + 55)
            end = along(start, dominant, 130)
            body.append(line(start, end, ORANGE, 2.5))
            body.append(arrow_head(start, end, ORANGE))
            body.append(text(end[0] + 6, end[1] + 5, f"{dominant:.0f}°", size=14,
                             fill=ORANGE, weight="bold"))
            body.append(line((px0, 392), (px0 + 26, 392), ORANGE, 4))
            body.append(text(px0 + 34, 397, f"Σ {group_sum:.0f} m at {lo:.0f}–{hi:.0f}°"
                             " → dominant", size=14, fill=ORANGE, weight="bold"))
            body.append(line((px0, 416), (px0 + 26, 416), TEAL, 4))
            body.append(text(px0 + 34, 421, f"Σ {other_sum:.0f} m at {olo:.0f}–{ohi:.0f}°",
                             size=14, fill=TEAL))

    write("05a_mbr_algorithm.svg", width, height, body)


# ---------------------------------------------------------------------------
# F10b - MST-based aggregation (Algorithm 2)
# ---------------------------------------------------------------------------

def figure_mst_aggregation():
    """F10b: MST edges processed shortest-first, each merge validated by BCR.

    Code: MST_Clustering.mst_clustering (ratio = sum(areas) / MBR area * 100,
    accepted if ratio > overlap_ratio; overlap_ratio is the local BCR from
    calc_footprint_density). The threshold value here is an example.
    """
    threshold = 25
    scale = 2.6
    # name: (x, y, width, depth, angle) in metres / degrees; y grows downwards
    spec = {
        "A": (7, 6, 12, 9, 14),
        "B": (26, 5, 11, 8, 10),
        "C": (10, 22, 13, 9, 19),
        "D": (73, 21, 7, 5, 38),
    }

    def blds(px0, py0):
        return {n: rotated_rect(px0 + x * scale, py0 + y * scale, w * scale, h * scale, a)
                for n, (x, y, w, h, a) in spec.items()}

    ref = blds(0, 0)

    def gap(a, b):
        return poly_gap(ref[a], ref[b]) / scale

    def group_bcr(names):
        return bcr([ref[n] for n in names], scale)

    # The three edges must form the MST: check against every alternative
    pairs = {(a, b): gap(a, b) for a in "ABCD" for b in "ABCD" if a < b}
    mst = [("A", "C"), ("A", "B"), ("B", "D")]
    assert sorted(mst, key=lambda e: pairs[e]) == mst
    assert pairs[("B", "C")] > pairs[("A", "B")]
    assert pairs[("B", "D")] < min(pairs[("A", "D")], pairs[("C", "D")])

    bcr_ac = group_bcr("AC")
    bcr_abc = group_bcr("ABC")
    bcr_abcd = group_bcr("ABCD")
    bcr_bd = group_bcr("BD")
    assert bcr_ac > threshold and bcr_abc > threshold
    assert bcr_abcd < threshold and bcr_bd < threshold  # both attempts in the code fail

    width, height = 920, 400
    body = []
    panel_w = 225
    steps = [
        ("1", f"A–C ({pairs[('A', 'C')]:.0f} m)", "AC", ("A", "C"),
         [f"new group: BCR {bcr_ac:.0f} % > t"], True),
        ("2", f"A–B ({pairs[('A', 'B')]:.0f} m)", "ABC", ("A", "B"),
         [f"extend group: BCR {bcr_abc:.0f} % > t"], True),
        ("3", f"B–D ({pairs[('B', 'D')]:.0f} m)", "ABCD", ("B", "D"),
         ["rejected:", f"A+B+C+D: BCR {bcr_abcd:.0f} % < t",
          f"B+D alone: BCR {bcr_bd:.0f} % < t"], False),
        ("4", "Result", "ABC", None,
         ["one rectangle per group;", "D stays ungrouped"], True),
    ]

    for i, (number, title, mbr_names, edge, notes, ok) in enumerate(steps):
        px0 = 15 + i * panel_w
        body.append(panel_title(px0, 34, number, title))
        b = blds(px0 + 22, 105)
        group = mbr_names if ok else "ABC"
        body.append(settlement(oriented_mbr([b[n] for n in group], scale)[0]))
        if not ok:
            rejected = oriented_mbr([b[n] for n in mbr_names], scale)[0]
            body.append(polygon(rejected, stroke=BUILDING, width=2, extra=DASHED))

        def centroid(n):
            pts = b[n]
            return (sum(p[0] for p in pts) / 4, sum(p[1] for p in pts) / 4)

        for a, c in mst:
            current = edge == (a, c)
            if current:
                body.append(line(centroid(a), centroid(c), ORANGE if ok else BUILDING, 3,
                                 '' if ok else DASHED))
            else:
                body.append(line(centroid(a), centroid(c), MUTED, 1.2, 'stroke-dasharray="3 3"'))

        for name, pts in b.items():
            body.append(polygon(pts, BUILDING))
            cx, cy = centroid(name)
            body.append(text(cx, cy + 5, name, size=13, anchor="middle", weight="bold",
                             fill=WHITE))

        indent = 24 if edge is not None else 0
        if edge is not None:
            body.append(check_mark(px0, 272, ok))
        for k, note in enumerate(notes):
            body.append(text(px0 + indent, 270 + 22 * k, note, size=14,
                             weight="bold" if (not ok and k == 0) else "normal"))

    body.append(text(15, 355, "Edges are processed shortest first (distance between building "
                     f"edges). t = local BCR threshold, here {threshold} % as an example.",
                     size=14, fill=MUTED))
    body.append(text(15, 378, "BCR = sum of footprint areas / area of the oriented rectangle "
                     "(Algorithm 1).", size=14, fill=MUTED))
    write("05b_mst_aggregation.svg", width, height, body)


# ---------------------------------------------------------------------------
# F10c - EdgeCatch
# ---------------------------------------------------------------------------

def figure_edgecatch():
    """F10c: snapping a cluster rectangle to the road network.

    Code: helpers/edge_catch_utils.py - apply_filter_rules (ported above)
    and process_single_feature (AREA_FILTER_FACTOR = 2).
    """
    scale = 2.7
    cluster_angle = 8
    # Two rows of houses, slightly irregular (along, offset, w, d, angle)
    houses = [(6, 0, 12, 9, 8), (22, 0.5, 11, 9, 5), (38, -0.5, 13, 10, 10),
              (54, 0, 11, 8, 7), (9, 17, 10, 8, 12), (30, 18, 9, 7, 4), (48, 16.5, 12, 9, 9)]

    blds = []
    for s, t, w, h, a in houses:
        c = along((0, 0), cluster_angle, s * scale, t * scale)
        blds.append(rotated_rect(c[0], c[1], w * scale, h * scale, a))
    rect = oriented_mbr(blds, scale)[0]
    # Corner naming by position in the picture
    by_y = sorted(rect, key=lambda p: p[1])
    tl, tr = sorted(by_y[:2])
    bl, br = sorted(by_y[2:])
    corners = {"TL": tl, "TR": tr, "BR": br, "BL": bl}

    # Roads: bottom road almost parallel, right road almost perpendicular
    bottom = (along(bl, 5, -100, -16 * scale), along(bl, 5, 400, -16 * scale))
    right = (along(tr, 97, 100, -20 * scale), along(tr, 97, -300, -20 * scale))
    x_pt = line_intersection(*bottom, *right)

    lines = []
    for key, p in corners.items():
        q = min((foot_on_segment(p, *bottom), foot_on_segment(p, *right)),
                key=lambda f: math.dist(p, f))
        ang = math.degrees(math.atan2(-(q[1] - p[1]), q[0] - p[0])) % 360
        lines.append(dict(key=key, start=p, end=q, distance=math.dist(p, q) / scale,
                          angle=ang, scale=scale))
    kept = {ln["key"] for ln in edgecatch_filter(lines)}
    assert kept == {"BL", "BR", "TR"}, kept
    ends = {ln["key"]: ln["end"] for ln in lines}
    dist = {ln["key"]: ln["distance"] for ln in lines}

    piece_bottom = [bl, br, ends["BR"], ends["BL"]]
    piece_right = [br, tr, ends["TR"], x_pt, ends["BR"]]
    for piece in (piece_bottom, piece_right):
        assert area(piece) < 2 * area(rect)                  # AREA_FILTER_FACTOR
    result = [tl, tr, ends["TR"], x_pt, ends["BL"], bl]

    road_bottom = (along(ends["BL"], 5, -30), along(x_pt, 5, 25))
    road_right = (along(ends["TR"], 97, 30), along(x_pt, 97, -25))
    content = rect + list(road_bottom) + list(road_right)
    cx0, cy0, cx1, cy1 = bbox(content)

    width, panel_w = 990, 325
    height = int(cy1 - cy0) + 110 + 80
    body = []
    titles = [
        ("1", "Shortest lines corner \u2192 road", ["filtered by rules 1\u20134"]),
        ("2", "Polygonise, keep small pieces",
         ["lines + road + rectangle edges;", "pieces < 2 \u00d7 rectangle area"]),
        ("3", "Result", ["rectangle reaches the road"]),
    ]
    for i, (number, title, subs) in enumerate(titles):
        px0 = 15 + i * panel_w
        body.append(panel_title(px0, 34, number, title, subs))
        body.append(f'<g transform="translate({px0 + 58 - cx0:.1f},{100 - cy0:.1f})">\n')
        if i == 0:
            body.append(settlement(rect))
        elif i == 1:
            body.append(polygon(piece_bottom, ORANGE, ORANGE, 1.5))
            body.append(polygon(piece_right, ORANGE, ORANGE, 1.5))
            body.append(settlement(rect))
        else:
            body.append(settlement(result))
        body.append(road(*road_bottom))
        body.append(road(*road_right))
        for b in blds:
            body.append(polygon(b, BUILDING))
        if i == 0:
            for ln in lines:
                p, q = ln["start"], ln["end"]
                mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
                if ln["key"] in kept:
                    body.append(line(p, q, TEXT, 2.5))
                    horizontal = abs(q[0] - p[0]) > abs(q[1] - p[1])
                    dx, dy = (-10, -9) if horizontal else (7, 5)
                    body.append(text(mx + dx, my + dy, f"{ln['distance']:.0f} m", size=13,
                                     weight="bold"))
                else:
                    body.append(line(p, q, BUILDING, 2.5, DASHED))
                    body.append(text(mx - 8, my - 4, f"{ln['distance']:.0f} m,", size=13,
                                     anchor="end", fill=BUILDING, weight="bold"))
                    body.append(text(mx - 8, my + 13, "removed", size=13, anchor="end",
                                     fill=BUILDING, weight="bold"))
        body.append('</g>\n')

    body.append(text(15, height - 45, "TL line removed by rule 3a: parallel to the BL line, end "
                     f"points \u2264 5 m apart, longer ({dist['TL']:.0f} m vs {dist['BL']:.0f} m). "
                     "Lines \u2265 70 m are removed by rule 1.", size=14, fill=MUTED))
    body.append(text(15, height - 22, "Before this step, roads are split into 20 m segments; "
                     "only segments within 25 m of a building are used.", size=14, fill=MUTED))
    write("07_edgecatch_schematic.svg", width, height, body)


# ---------------------------------------------------------------------------
# F10d - GapClose double buffer and gap filters
# ---------------------------------------------------------------------------

def figure_gapclose():
    """F10d: inter-cluster gap detection and the three gap filters.

    Code: GapClose._close_buffer_gaps (gap_dist = 15 m,
    BOUNDARY_OVERLAP_THRESHOLD_PCT = 70, BOUNDARY_OVERLAP_STRICT_PCT = 90,
    MAX_NARROW_GAP_EXTENT_M = 70, default max_gap_size = 4,900 m2).
    """
    gap_dist = 15
    max_gap_size = 4900
    s1 = (15, 30, 85, 140)
    s2 = (105, 30, 175, 140)
    assert s2[0] - s1[2] < 2 * gap_dist                     # bridged by the buffer
    gap_poly = rect_points(s1[2], s1[1], s2[0], s1[3])
    gap_area = area(gap_poly)
    contact = 2 * (s1[3] - s1[1]) / perimeter(gap_poly) * 100
    assert gap_area < max_gap_size and contact >= 70         # closed by filter 1

    width, height = 920, 720
    body = []
    titles = [
        ("1", "Settlement", ["two clusters, 20 m apart"]),
        ("2", f"Buffer +{gap_dist} m", ["dissolved: the gap disappears"]),
        ("3", f"Remove outer {gap_dist} m", ["outline shrinks back,", "bridge remains"]),
        ("4", "Minus settlement", ["= gap candidate",
                                   f"{gap_area:,.0f} m², {contact:.0f} % contact"]),
    ]
    for i, (number, title, subs) in enumerate(titles):
        px0 = 15 + i * 228
        body.append(panel_title(px0, 34, number, title, subs))
        body.append(f'<g transform="translate({px0 + 10},110)">\n')
        if i == 1:
            for s in (s1, s2):
                # Buffer of a rectangle = rectangle grown by d with corner radius d
                body.append(f'<rect x="{s[0] - gap_dist}" y="{s[1] - gap_dist}" '
                            f'width="{s[2] - s[0] + 2 * gap_dist}" '
                            f'height="{s[3] - s[1] + 2 * gap_dist}" rx="{gap_dist}" '
                            f'fill="{PINK}" fill-opacity="0.45"/>\n')
        if i in (0, 1, 3):
            for s in (s1, s2):
                body.append(settlement(rect_points(*s)))
        if i == 2:
            body.append(settlement(rect_points(s1[0], s1[1], s2[2], s2[3])))
            for s in (s1, s2):
                body.append(polygon(rect_points(*s), stroke=ORANGE, width=1,
                                    extra='stroke-dasharray="4 3"'))
        if i == 3:
            body.append(polygon(gap_poly, ORANGE, ORANGE, 2))
        body.append('</g>\n')

    # Row 2: the three gap filters (schematic)
    y0 = 330
    body.append(line((15, y0 - 25), (905, y0 - 25), LIGHT, 1.5))
    body.append(text(15, y0, "Which gap candidates are added to the settlement "
                     f"(max_gap_size = {max_gap_size:,} m²):", size=16, weight="bold"))

    def open_side(p, q):
        return line(p, q, BUILDING, 3, DASHED)

    filters = [
        ("Filter 1", ["< max_gap_size and", "≥ 70 % contact"]),
        ("Filter 2", ["any size and", "≥ 90 % contact"]),
        ("Filter 3", ["≥ max_gap_size, 70–90 % contact:",
                      "only triangles with", "longest side < 70 m"]),
    ]
    for i, (title, subs) in enumerate(filters):
        px0 = 15 + i * 305
        body.append(text(px0, y0 + 36, title, size=16, weight="bold"))
        for k, sub in enumerate(subs):
            body.append(text(px0, y0 + 58 + 20 * k, sub, size=14, fill=MUTED))
        gx, gy = px0 + 40, y0 + 140
        if i == 0:
            body.append(settlement([(gx, gy), (gx + 30, gy), (gx + 30, gy + 110),
                                    (gx + 150, gy + 110), (gx + 150, gy), (gx + 180, gy),
                                    (gx + 180, gy + 150), (gx, gy + 150)]))
            gap_pts = rect_points(gx + 30, gy + 30, gx + 150, gy + 110)
            share = (perimeter(gap_pts) - 120) / perimeter(gap_pts) * 100
            assert share >= 70
            body.append(polygon(gap_pts, ORANGE, ORANGE, 1.5))
            body.append(open_side((gx + 30, gy + 30), (gx + 150, gy + 30)))
        elif i == 1:
            body.append(settlement(rect_points(gx, gy - 10, gx + 220, gy + 170)))
            inner = rect_points(gx + 30, gy + 20, gx + 190, gy + 140)
            assert (perimeter(inner) - 16) / perimeter(inner) * 100 >= 90
            body.append(polygon(inner, ORANGE, ORANGE, 1.5))
            body.append(polygon(rect_points(gx + 100, gy - 10, gx + 116, gy + 20), WHITE))
            body.append(open_side((gx + 100, gy + 20), (gx + 116, gy + 20)))
            body.append(line((gx + 100, gy - 10), (gx + 100, gy + 20), ORANGE, 2.5))
            body.append(line((gx + 116, gy - 10), (gx + 116, gy + 20), ORANGE, 2.5))
        else:
            neck_w, bay_w = 50, 120
            left, right = gx + 60, gx + 60 + neck_w
            bay_left, bay_right = gx + 25, gx + 25 + bay_w
            body.append(settlement([(gx, gy - 10), (gx + 200, gy - 10), (gx + 200, gy + 170),
                                    (bay_right, gy + 170), (bay_right, gy + 90),
                                    (right, gy + 90), (right, gy + 10), (left, gy + 10),
                                    (left, gy + 90), (bay_left, gy + 90),
                                    (bay_left, gy + 170), (gx, gy + 170)]))
            gap_outline = [(left, gy + 10), (right, gy + 10), (right, gy + 90),
                           (bay_right, gy + 90), (bay_right, gy + 170), (bay_left, gy + 170),
                           (bay_left, gy + 90), (left, gy + 90)]
            share = (perimeter(gap_outline) - bay_w) / perimeter(gap_outline) * 100
            assert 70 <= share < 90 and area(gap_outline) >= 4900
            ys = [gy + 10, gy + 30, gy + 50, gy + 70, gy + 90]
            for a, b in zip(ys, ys[1:]):
                for tri in ([(left, a), (right, a), (left, b)], [(right, a), (right, b), (left, b)]):
                    assert max(math.dist(p, q) for p, q in edges(tri)) < 70
                    body.append(polygon(tri, ORANGE, WHITE, 1))
            bay_tris = [[(bay_left, gy + 90), (bay_right, gy + 90), (bay_left, gy + 170)],
                        [(bay_right, gy + 90), (bay_right, gy + 170), (bay_left, gy + 170)]]
            for tri in bay_tris:
                assert max(math.dist(p, q) for p, q in edges(tri)) >= 70
                body.append(polygon(tri, WHITE, MUTED, 1, 'stroke-dasharray="4 3"'))
            body.append(open_side((bay_left, gy + 170), (bay_right, gy + 170)))

    ly = 695
    body.append(settlement(rect_points(15, ly - 13, 35, ly + 1), 2))
    body.append(text(42, ly, "settlement", size=14))
    body.append(polygon(rect_points(150, ly - 13, 170, ly + 1), ORANGE, ORANGE, 1.5))
    body.append(text(177, ly, "gap added", size=14))
    body.append(line((290, ly - 6), (318, ly - 6), BUILDING, 3, DASHED))
    body.append(text(325, ly, "boundary without settlement contact", size=14))
    body.append(text(620, ly, "Filter 3 triangles are schematic.", size=14, fill=MUTED))
    write("09_gapclose_double_buffer.svg", width, height, body)


# ---------------------------------------------------------------------------
# F10e - ErodeEmptyAreas protrusion filter
# ---------------------------------------------------------------------------

def figure_protrusion_filter():
    """F10e: which building-free voids are removed.

    Code: ErodeEmptyAreas._protrusion_filter (MAX_BUILDING_CONTACT_PCT = 20,
    MIN_FREE_EDGE_PCT = 80): the voids are subtracted from the settlement, the
    remainder parts with buildings are the built settlement. A void is removed
    when building contact < 20 % and free edge >= 80 %. Buffers per building:
    clamp(sqrt(area), MIN_BUFFER_M = 10, MAX_BUFFER_M = 100).
    """
    scale = 2.0                                      # px per metre
    bx0, by0, bx1, by1 = 40, 80, 560, 300            # settlement body
    lx1, ly0, ly1 = 690, 150, 210                    # lobe to the east
    outline = [(bx0, by0), (bx1, by0), (bx1, ly0), (lx1, ly0), (lx1, ly1),
               (bx1, ly1), (bx1, by1), (bx0, by1)]

    def on_outline(p, q):
        return any(distance_to_poly(p, [a, b]) < 1e-6 and distance_to_poly(q, [a, b]) < 1e-6
                   for a, b in edges(outline))

    def shares(points):
        """(building %, free %): in this drawing every remainder part is built,
        and the voids do not touch each other."""
        free = sum(math.dist(p, q) for p, q in edges(points) if on_outline(p, q))
        free_pct = free / perimeter(points) * 100
        return 100 - free_pct, free_pct

    interior = [(120, 150), (200, 135), (235, 190), (190, 245), (115, 230), (95, 185)]
    lobe = [(bx1, ly0), (lx1, ly0), (lx1, ly1), (bx1, ly1)]
    bay = [(300, by0), (400, by0), (415, 130), (335, 152), (288, 122)]
    voids = (interior, lobe, bay)
    (b_int, f_int), (b_lobe, f_lobe), (b_bay, f_bay) = map(shares, voids)
    assert f_int == 0                                  # kept
    assert b_lobe < 20 and f_lobe >= 80                # removed
    assert b_bay >= 20                                 # kept
    for v in voids:
        assert area(v) / scale ** 2 >= 500             # min_empty_area

    rng = random.Random(34)
    buildings = []
    for row, gy in enumerate(range(100, by1 - 10, 33)):
        x = bx0 + 16 + rng.uniform(0, 14)
        while x < bx1 - 16:
            large = rng.random() < 0.08
            w, d = (rng.uniform(22, 30), rng.uniform(14, 18)) if large else \
                   (rng.uniform(9, 14), rng.uniform(7, 10))
            ang = 6 * math.sin(x / 90 + row) + rng.uniform(-7, 7)
            cx, cy = x, gy + rng.uniform(-5, 5) + 5 * math.sin(x / 120)
            radius = min(max(math.sqrt(w * d), 10), 100) * scale   # true scale
            poly = rotated_rect(cx, cy, w * scale, d * scale, ang)
            clear = all(not inside((cx, cy), v) and distance_to_poly((cx, cy), v) > radius
                        for v in voids)
            within = all(inside(p, outline) and distance_to_poly(p, outline) > 4 for p in poly)
            nx0, ny0, nx1, ny1 = bbox(poly)
            free = all(nx1 + 3 < ox0 or ox1 + 3 < nx0 or ny1 + 3 < oy0 or oy1 + 3 < ny0
                       for ox0, oy0, ox1, oy1 in (bbox(b[0]) for b in buildings))
            if clear and within and free and rng.random() > 0.12:
                buildings.append((poly, (cx, cy), radius))
            x += w * scale + rng.uniform(5, 16)

    width, height = 720, 425
    body = [settlement(outline)]
    for _, (cx, cy), radius in buildings:
        body.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" fill="{LIGHT}" '
                    f'fill-opacity="0.75"/>\n')
    # White masks outside the settlement hide buffer parts beyond the outline
    # (no clipPath: not part of SVG Tiny)
    for mask in (rect_points(0, 0, width, by0), rect_points(0, by1, width, height),
                 rect_points(0, 0, bx0, height), rect_points(bx1, 0, width, ly0),
                 rect_points(bx1, ly1, width, height), rect_points(lx1, 0, width, height)):
        body.append(polygon(mask, WHITE))
    body.append(text(20, 30, "Building-free voids ≥ 500 m²: only protrusions are removed",
                     size=17, weight="bold"))
    body.append(text(20, 52, "removed if building contact < 20 % and free edge ≥ 80 %",
                     size=14, fill=MUTED))
    for poly, _, _ in buildings:
        body.append(polygon(poly, BUILDING))

    body.append(polygon(interior, stroke=MUTED, width=2, extra='stroke-dasharray="6 4"'))
    body.append(polygon(bay, stroke=MUTED, width=2, extra='stroke-dasharray="6 4"'))
    body.append(polygon(lobe, WHITE, BUILDING, 2.5, DASHED))
    body.append(polygon(outline, stroke=ORANGE, width=2.5))
    # Building contact: void edges that are not on the outer boundary
    for v in voids:
        for p, q in edges(v):
            if not on_outline(p, q):
                body.append(line(p, q, TEAL, 5))

    body.append(text(165, 195, f"{b_int:.0f} %", size=15, weight="bold", fill=MUTED,
                     anchor="middle"))
    body.append(text(625, 186, f"{b_lobe:.0f} %", size=15, weight="bold", fill=BUILDING,
                     anchor="middle"))
    body.append(text(350, 118, f"{b_bay:.0f} %", size=15, weight="bold", fill=MUTED,
                     anchor="middle"))
    body.append(text(20, 330, f"● interior void: building contact {b_int:.0f} % → kept",
                     size=15))
    body.append(text(20, 353, f"● protrusion: building contact {b_lobe:.0f} %, free edge "
                     f"{f_lobe:.0f} % → removed (cut out)", size=15, weight="bold"))
    body.append(text(20, 376, f"● fringe bay: building contact {b_bay:.0f} % → kept",
                     size=15))
    body.append(line((470, 371), (498, 371), TEAL, 5))
    body.append(text(506, 376, "contact with built settlement", size=14))
    body.append(text(20, 405, "Grey circles: building buffers, radius = clamp(√area, "
                     "10 m, 100 m). Dashed voids stay part of the settlement.",
                     size=13, fill=MUTED))
    write("08_protrusion_filter.svg", width, height, body)


if __name__ == "__main__":
    figure_mbr()
    figure_mst_aggregation()
    figure_edgecatch()
    figure_gapclose()
    figure_protrusion_filter()
