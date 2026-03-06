# GapFix — Inter-polygon Gap Closing

## Overview

`ibtool_tools/GapFix.py` closes narrow empty gaps between adjacent settlement
polygon features and removes interior holes (inner rings). It is called as step
8 in the main processing pipeline, after gap and hole closing on individual
partitions (`GapClose.py`) and before the final output is saved.

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
[Step 1] Hole closing
         polygonstolines → polygonize → collect → buffer(0, dissolve=True)
         Polygonize creates faces for all enclosed rings including holes.
         Dissolving everything merges hole faces into surrounding area.
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
    │
    ▼
[Step 5] Validate gap zones
         Keep only zones that geometrically intersect BOTH source polygons.
         Exterior buffer fringes → discarded.
         Distant artefacts     → discarded.
    │
    ▼
[Step 6] Assign each valid gap to the neighbor with the longer shared boundary
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

### Attribute loss after hole closing

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
| `step1_dissolved` | 1 | Hole-closed, dissolved polygons |
| `step2_clean_polys` | 2 | Singlepart polygons with `gap_uid` |
| `step3_buffer_rings` | 3 | Donut rings (empty-space buffers) |
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
