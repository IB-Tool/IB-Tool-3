# GapClose — Developer Reference

## Overview

`ibtool_tools/GapClose.py` is called as step 9 in the main pipeline. It
corrects two classes of topological defects in the merged settlement polygon:

- **Interior holes** — enclosed voids inside a polygon (e.g. courtyards,
  parks that were never classified as settlement).
- **Inter-cluster gaps** — narrow strips of unclassified space between
  adjacent settlement polygons.

The module exposes two public functions:
- `gap_close()` — full pipeline: block-based (Process 1) + buffer-based
  (Process 2) gap closing.
- `gap_close_in_holes()` — standalone morphological closing of gap areas
  inside interior holes. Also called internally by `gap_close()`.

---

## Process 1 — Block-based gap detection (`_close_block_gaps`)

```
dissolved_settlement
    │
    ├── [deleteholes(max_hole_size)]  → fill obvious interior rings first
    │
    ├── sym-diff with block layer     → areas in blocks but not in settlement
    │       (GRID_SIZE=0.00001)
    │
    ├── multipart → singlepart
    │
    ├── area < max_gap_size           → candidate gap fragments
    │
    ├── _gap_select(threshold=70%)    → keep candidates with ≥70% boundary on settlement
    │
    ├── merge + native:dissolve       → absorb gaps into settlement
    │
    ├── gap_close_in_holes()          → close gaps inside large interior holes
    │
    └── deleteholes(max_hole_size)    → final interior ring removal
```

---

## Process 2 — Buffer-based gap detection (`_close_buffer_gaps`)

```
settlement (holes already closed)
    │
    ├── buffer(+gap_dist, dissolve=True)   → clusters < 2×gap_dist apart merge
    │
    ├── polygonstolines → buffer(gap_dist + 0.3)
    │       → difference → interior area only (outer ring stripped)
    │
    ├── difference(original buildings)    → remove building footprints
    │
    ├── multipart → singlepart
    │
    ├── area > MIN_GAP_AREA_SCALE_FACTOR × gap_dist/15   (artefact filter)
    │
    ├── _gap_select(threshold=70%)         → size-limited gaps (final_gap1)
    ├── _gap_select(threshold=90%)         → large fully-enclosed gaps (final_gap2)
    │
    ├── area < max_gap_size                → size cap on 70%-selection (gap_poly_max_size)
    │
    ├── Filter 2c: large gaps not in final_gap2, tessellate → keep if longest
    │       triangle edge < MAX_NARROW_GAP_EXTENT_M (70 m)  → narrow_large_gaps
    │
    ├── merge(gap_poly_max_size + final_gap2 + narrow_large_gaps + settlement)
    │       + deleteduplicates + native:dissolve
    │
    ├── deleteholes(max_hole_size)
    │
    └── buffer(+TOPOLOGY_SNAP_BUFFER_M)   → close sub-mm topology gaps
```

---

## Non-obvious Design Decisions

### 1. `_dissolve_union` instead of `native:dissolve`

`native:dissolve` silently produces null or empty geometries on large
`MultiPolygon` datasets (QGIS ≤ 3.40, GEOS bug). The safe workaround used
throughout this module:

```python
fix → collect → buffer(distance=0, dissolve=True)
```

This achieves a full dissolve without the null-geometry failure.

### 2. `qgis:dissolve` in `_gap_select` fails on large building layers

Inside `_gap_select`, the input polygon is dissolved with `qgis:dissolve`.
When called with the raw building layer (`input_layer`, potentially thousands
of features), `qgis:dissolve` produces an empty result — the same GEOS bug
family. This causes `overlapping_segments=0` for all gap candidates, so all
gaps are incorrectly discarded.

**Fix in `_close_buffer_gaps`:** pass `holes_closed` (1 dissolved feature)
instead of `input_layer` to `_gap_select`. The inter-cluster gap edges lie
exactly on the perimeter of `holes_closed`, so the boundary-overlap
measurement is geometrically correct.

### 3. Three overlap filters in Process 2

| Filter | Threshold | Size cap | Purpose |
|--------|-----------|----------|---------|
| `final_gap1` / `gap_poly_max_size` | 70% | `< max_gap_size` | Captures normally enclosed gaps within the size cap |
| `final_gap2` | 90% | none | Captures large gaps that are almost fully enclosed |
| `narrow_large_gaps` (Filter 2c) | 70% | `≥ max_gap_size` + compact shape | Captures large but narrow/corridor-like gaps missed by final_gap2 |

All three are merged before the final dissolve. The 90%-filter catches gaps
that exceed `max_gap_size` but are geometrically almost fully surrounded by
settlement. Filter 2c handles the remaining case — large gaps that are only
70–90 % enclosed, but are compact (not open plazas): each candidate is
tessellated into triangles; if the longest triangle edge is below
`MAX_NARROW_GAP_EXTENT_M` (70 m), the gap is narrow enough to absorb.

### 4. `gap_close_in_holes` uses line-based buffers

Rather than buffering the hole polygon directly (which would shrink it),
the function converts hole polygons to boundary lines first. The positive
buffer then expands the boundary outward from the ring edge, correctly
closing narrow gaps inside the hole without changing the hole's overall
extent.

---

## Constants Reference

| Constant | Value | Meaning                                                     |
|----------|-------|-------------------------------------------------------------|
| `TOPOLOGY_SNAP_BUFFER_M` | `0.1` | Snap buffer to close sub-mm gaps in results                 |
| `TOPOLOGY_SNAP_BUFFER_HOLES_M` | `0.4` | Larger snap buffer during hole morphological closing        |
| `TOPOLOGY_GRID_SIZE` | `0.00001` | Grid size for sym-diff and difference operations            |
| `SEGMENT_LENGTH_M` | `10` | Gap boundary split length for overlap measurement           |
| `BOUNDARY_SNAP_BUFFER_M` | `0.5` | Buffer around settlement lines to catch near-touches        |
| `EDGE_ZONE_BUFFER_MARGIN_M` | `0.3` | Extra margin for the negative-buffer edge zone              |
| `BOUNDARY_OVERLAP_THRESHOLD_PCT` | `70` | Standard boundary-overlap filter threshold                  |
| `BOUNDARY_OVERLAP_STRICT_PCT` | `90` | Strict threshold for large fully-enclosed gaps              |
| `MAX_NARROW_GAP_EXTENT_M` | `70` | Maximum longest triangle edge (m) for Filter 2c: large gaps with all triangles below this are absorbed |
| `MIN_GAP_AREA_SCALE_FACTOR` | `200` | Base area (m²) for artefact filter; scaled by `gap_dist/15` |
| `HOLE_DETECTION_THRESHOLD_M2` | `10_000` | Fill all holes up to 1 ha to expose hole polygons           |
| `MIN_PROCESSED_HOLE_AREA_M2` | `500` | Minimum area for a morphologically closed hole to be kept   |

---

## Related Files

- `ibtool_tools/GapClose.py` — implementation
- `helpers/safe_processing.py` — `safe_processing_run()` wrapper
- `docs/how-it-works.md` — user-facing pipeline overview (Step 9)
