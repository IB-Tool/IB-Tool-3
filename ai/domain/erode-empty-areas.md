# ErodeEmptyAreas — Building-Free Void Removal

## Overview

`ibtool_tools/ErodeEmptyAreas.py` removes areas within a settlement polygon
where no buildings are located. It runs as the final per-partition step
(Step 09) in the main processing pipeline, immediately after `PatchRemove`.

The step prevents parks, open fields, or water bodies enclosed by building
clusters from inflating the settlement footprint.

The module works entirely in memory: no intermediate files are written unless
`debug_mode=True`.

---

## Algorithm

```
Input: settlement polygon (output of patch_remove)
       buildings layer (sel_hu_layer — buildings in current partition)
    │
    ▼
[Step 0] native:fixgeometries          — repair invalid geometries
         → fixed_input
    │
    ▼
[Step 1] native:extractbylocation(buildings_layer, fixed_input, intersects)
         → sel_buildings
         If sel_buildings.featureCount() == 0: return fixed_input unchanged
    │
    ▼
[Step 2] Per-building buffer (pure Python, QgsGeometry.buffer())
         buf_dist = clamp(sqrt(building_area), MIN_BUFFER_M, MAX_BUFFER_M)
         → building_buffers (memory layer, one feature per building)
         If featureCount() == 0: return fixed_input unchanged
    │
    ▼
[Step 3] Dissolve buffer union
         collect → buffer(0, dissolve=True)
         → buffer_union
    │
    ▼
[Step 4] Compute building-free void candidates
         difference(fixed_input, buffer_union) → empty_areas
         multiparttosingleparts
         extractbyexpression(area($geometry) >= min_empty_area) → filtered_empty
         If filtered_empty.featureCount() == 0: return fixed_input unchanged
    │
    ▼
[Step 4b] Contact-fraction filter
         For each void, measure: what fraction of its boundary runs along
         the settlement's outer boundary? (mirrors _gap_select in GapClose.py)
           1. settlement boundary → polygonstolines
           2. void boundaries → polygonstolines, split into 10 m segments,
              record total length (length_1) and stable fid_copy
           3. buffer settlement boundary by 0.5 m (snap distance)
           4. extractbylocation(segments, settlement_buff, intersects) → overlapping
           5. dissolve overlapping segments by fid_copy, measure overlap length (length_2)
           6. extractbyexpression('(length_2/length_1)*100 >= threshold') → high_contact
           7. extractbylocation(voids, high_contact, disjoint) → voids_to_remove
         If voids_to_remove.featureCount() == 0: return fixed_input unchanged
    │
    ▼
[Step 5] Subtract qualifying voids from settlement
         difference(fixed_input, voids_to_remove)
         → result (input attribute schema preserved)
```

---

## Buffer Scaling Function

```python
buf_dist = max(MIN_BUFFER_M, min(MAX_BUFFER_M, math.sqrt(building_area)))
```

| Building area (m²) | sqrt(area) | Buffer (m) |
|---|---|---|
| 25 | 5 | **10** (min clamp) |
| 100 | 10 | 10 |
| 2 500 | 50 | 50 |
| 10 000 | 100 | **100** (max clamp) |

Small buildings get a minimum 10 m protection zone; very large buildings up
to 100 m. The formula gives each building a buffer proportional to its
geometric "radius", so building clusters naturally merge their zones in dense
areas while isolated buildings still protect a reasonable surroundings.

---

## Module Constants

| Constant | Value | Meaning |
|---|---|---|
| `_DEBUG_TOOL_NAME` | `"09_ErodeEmptyAreas"` | Debug folder prefix |
| `MIN_BUFFER_M` | `10.0` | Minimum per-building buffer distance (m) |
| `MAX_BUFFER_M` | `100.0` | Maximum per-building buffer distance (m) |
| `MIN_EMPTY_AREA_M2` | `500.0` | Minimum void area (m²) to enter the contact filter |
| `TOPOLOGY_GRID_SIZE` | `0.00001` | Grid size for difference operations |
| `BOUNDARY_CONTACT_THRESHOLD_PCT` | `30.0` | Maximum boundary-contact fraction (%) for a void to be removed; voids at or above this value are kept |
| `_BOUNDARY_SEGMENT_M` | `10.0` | Split length (m) for void boundary segments in contact measurement |
| `_BOUNDARY_SNAP_M` | `0.5` | Buffer (m) around settlement boundary to catch near-touching segments |

---

## Key Parameters

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `input_layer` | — | Settlement polygon (`QgsVectorLayer` or file path) |
| `buildings_layer` | — | Building footprint layer (`QgsVectorLayer`) |
| `min_empty_area` | `MIN_EMPTY_AREA_M2` | Area threshold (m²): voids smaller than this are skipped entirely |
| `min_buffer_m` | `MIN_BUFFER_M` | Minimum per-building buffer distance (m) |
| `max_buffer_m` | `MAX_BUFFER_M` | Maximum per-building buffer distance (m) |
| `contact_threshold_pct` | `BOUNDARY_CONTACT_THRESHOLD_PCT` | Maximum boundary-contact % for a void to be removed; higher-contact voids are kept |
| `workspace_path` | `None` | Absolute path for debug layer output |
| `debug_mode` | `False` | Save intermediate layers to `workspace_path` |

---

## Known Limitations / Workarounds

### `native:dissolve` is intentionally avoided

`native:dissolve` silently produces null or empty geometries on large
`MultiPolygon` datasets (QGIS ≤ 3.40). The workaround used in Step 3:

```python
# Instead of native:dissolve:
collected = native:collect(buf_layer)
buffer_union = native:buffer(collected, distance=0, dissolve=True)
```

This achieves the same topology merge without the null-geometry failure.

### Metric CRS required

`sqrt(area)` is interpreted in metres. Passing a geographic CRS (degrees)
will produce meaningless buffer distances. Always call `erode_empty_areas`
with a projected, metric input layer.

### Attribute preservation

The input layer's attribute schema (from `patch_remove`) is preserved in the
output. The `native:difference` operation retains the INPUT layer's schema and
drops any attributes from the overlay layer.

---

## Error Handling

Any unhandled exception inside `erode_empty_areas` is:
1. Logged at `CRITICAL` level via `Logger.log()`
2. If `debug_mode=True`: the raw input layer is saved as `exception_input`
3. Re-raised to the caller

The function returns `input_layer` unchanged — without raising — when the
input has zero valid features or when `buildings_layer` is empty.

---

## Debug Layers (when `debug_mode=True`)

All layers are written to `{workspace_path}/09_ErodeEmptyAreas/`.

| Suffix | After step | Content |
|--------|-----------|---------|
| `step0_fixed` | 0 | Geometry-fixed input |
| `step1_sel_buildings` | 1 | Buildings selected within settlement boundary |
| `step2_building_buffers` | 2 | Individual per-building buffer polygons |
| `step3_buffer_union` | 3 | Dissolved union of all building buffers |
| `step4_empty_areas` | 4 | Raw empty areas (before area filter) |
| `step4_filtered_empty_areas` | 4 | Empty areas passing the `min_empty_area` threshold |
| `step4b_voids_to_remove` | 4b | Voids that passed the contact filter (contact < threshold) and will be subtracted |
| `step5_result` | 5 | Final result |
| `exception_input` | on error | Raw input at time of crash |

---

## Related Files

- `ibtool_tools/ErodeEmptyAreas.py` — implementation
- `ibtool_tools/PatchRemove.py` — preceding pipeline step
- `helpers/safe_processing.py` — `safe_processing_run()` wrapper used for all
  `processing.run()` calls
- `docs/how-it-works.md` — full pipeline overview
