# GapFix — Inter-polygon Gap Closing

## Overview

`ibtool_tools/GapFix.py` closes narrow empty gaps between adjacent settlement
polygon features. It is called as step 8 in the main processing pipeline,
after gap and hole closing on individual partitions (`GapClose.py`) and before
the final output is saved.

Hole closing is **not** done by this tool — interior holes are preserved and
pass through unchanged. Hole handling lives in a separate pipeline step.

The module works entirely in memory: no intermediate files are written unless
`debug_mode=True`.

---

## Algorithm

```
Input polygons
    │
    ▼
[Step 0] native:fixgeometries          — repair invalid geometries
    │
    ▼
[Step 1] Dissolve adjacent polygons (interior holes preserved)
         collect → buffer(0, dissolve=True)
         Merges touching/overlapping polygons. Interior holes pass
         through unchanged — hole closing is handled elsewhere.
    │
    ▼
[Step 2] multiparttosingleparts + addautoincrementalfield (gap_uid)
         Assigns a unique integer ID to each polygon.
    │
    ▼
[Step 3] Build donut rings per polygon
         buffer(max_gap) → difference(all originals)
         Each ring covers only empty space around its source polygon.
    │
    ▼
[Step 4] Pairwise spatial-index intersection of all rings
         ring_i ∩ ring_j = gap zone between polygon i and polygon j
         MultiPolygon intersections are split into single connected
         components, so each gap piece is classified independently.
    │
    ▼
[Step 5] Validate gap zones
         Keep only zones that geometrically intersect BOTH source polygons.
         Exterior buffer fringes → discarded.
         Distant artefacts     → discarded.
    │
    ▼
[Step 5b] Linearity filter (erosion + area-fraction)
          eroded = gap_geom.buffer(-erosion_width)
          keep if (area(gap) - area(eroded)) / area(gap) >= linearity_area_fraction
          → narrow corridors (incl. branching/tree-like shapes) pass
          → blocky zones (plazas, real open spaces) are discarded and stay open
    │
    ▼
[Step 6] Assign each linear gap to the neighbor with the longer shared boundary
         (measured as intersection().length())
    │
    ▼
Output memory layer (MultiPolygon, same CRS as input)
```

---

## Key Parameters

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `max_gap` | `10.0` | Buffer distance (m); defines the maximum closable gap width |
| `erosion_width` | `None` (= `max_gap / 2`) | Half-width (m) of the negative buffer used by the Step 5b linearity filter |
| `linearity_area_fraction` | `0.7` | Minimum fraction of the gap-zone area that must vanish under erosion for the gap to count as linear. `0.0` disables the filter |
| `Inputpoly` | — | Input polygon layer (`QgsVectorLayer` or file path) |
| `InputRoadnetwork` | `None` | **Unused** — kept for API compatibility only |
| `bufferwidth` | `70` | **Unused** — kept for API compatibility only |
| `debug_mode` | `False` | Save intermediate layers to `workspace_path` |

---

## Known Limitations / Workarounds

### `native:dissolve` is intentionally avoided

`native:dissolve` silently produces null or empty geometries on large
`MultiPolygon` datasets (QGIS ≤ 3.40). The workaround used throughout this
module:

```python
# Instead of native:dissolve:
collected = native:collect(input)
dissolved = native:buffer(collected, distance=0, dissolve=True)
```

This achieves the same topology merge without the null-geometry failure.

### Attribute loss after the global dissolve

The global dissolve in Step 1 rebuilds polygon topology from scratch.
Original feature attributes (settlement name, class, etc.) are **lost**.
The output carries only the synthetic `gap_uid` integer field.
Downstream code must not rely on any original field values being preserved.

### Metric CRS required

`max_gap` is interpreted as meters. Passing a geographic CRS (degrees) will
produce meaningless buffer distances. Always call `gap_fix` with a projected,
metric input layer.

---

## Error Handling

Any unhandled exception inside `gap_fix` is:
1. Logged at `CRITICAL` level via `Logger.log()`
2. If `debug_mode=True`: the raw input layer is saved as `exception_input`
3. Re-raised to the caller

The function returns the (possibly invalid) input layer unchanged — without
raising — when the input has zero valid features.

---

## Debug Layers (when `debug_mode=True`)

| Suffix | After step | Content |
|--------|-----------|---------|
| `step0_fixed` | 0 | Geometry-fixed input |
| `step1_dissolved` | 1 | Dissolved polygons (interior holes preserved) |
| `step2_clean_polys` | 2 | Singlepart polygons with `gap_uid` |
| `step3_buffer_rings` | 3 | Donut rings (empty-space buffers) |
| `step5b_linear_gaps` | 5b | Gap zones classified as linear (will be merged). Attributes: `uid_a`, `uid_b`, `linearity_index` (= `frac_removed`), `total_area`, `eroded_area` |
| `step5b_discarded_blocky_gaps` | 5b | Gap zones classified as blocky (stay open). Same attribute schema as `step5b_linear_gaps` |
| `gap_fix_result` | 6 | Final output with gaps filled |
| `exception_input` | on error | Raw input at time of crash |

All layers are written to `{workspace_path}/08_GapFix/`.

---

## Related Files

- `ibtool_tools/GapFix.py` — implementation
- `ibtool_tools/GapClose.py` — per-partition hole/gap closing (called earlier)
- `helpers/safe_processing.py` — `safe_processing_run()` wrapper used for all
  `processing.run()` calls
- `docs/how-it-works.md` — full pipeline overview
