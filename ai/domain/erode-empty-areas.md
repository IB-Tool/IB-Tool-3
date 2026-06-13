# ErodeEmptyAreas -- Building-Free Void Removal

## Overview

`ibtool_tools/ErodeEmptyAreas.py` removes areas within a settlement polygon
where no buildings are located. It runs as Step 8 in the main processing
pipeline, immediately after `EdgeCatch` and before `GapClose`.

The step prevents parks, open fields, or water bodies enclosed by building
clusters from inflating the settlement footprint. Running before `GapClose`
ensures that large building-free voids are excluded before gap detection, so
GapClose does not attempt to bridge across areas that should stay open.

The module works entirely in memory: no intermediate files are written unless
`debug_mode=True`.

---

## Algorithm

```
Input: settlement polygon (output of patch_remove)
       buildings layer (sel_hu_layer -- buildings in current partition)
    |
    v
[Step 0] native:fixgeometries          -- repair invalid geometries
         -> fixed_input
    |
    v
[Step 0b] collect + buffer(0, dissolve=True) + fixgeometries
          -- dissolve overlapping features (snapped_rect + blocks_dense may overlap)
          -> fixed_input (reassigned; single clean polygon per disjoint cluster)
    |
    v
[Step 1] native:extractbylocation(buildings_layer, fixed_input, intersects)
         -> sel_buildings
         If sel_buildings.featureCount() == 0: return fixed_input unchanged
    |
    v
[Step 2] Per-building buffer (pure Python, QgsGeometry.buffer())
         buf_dist = clamp(sqrt(building_area), MIN_BUFFER_M, MAX_BUFFER_M)
         -> building_buffers (memory layer, one feature per building)
         If featureCount() == 0: return fixed_input unchanged
    |
    v
[Step 3] Build buffer union at Python level
         QgsGeometry.unaryUnion(buf_geoms) -> clean Polygon/MultiPolygon
         -> buffer_union (1-feature MultiPolygon memory layer)
    |
    v
[Step 4] Compute building-free void candidates
         difference(fixed_input, buffer_union) -> empty_areas
         multiparttosingleparts
         extractbyexpression(area($geometry) >= min_empty_area) -> filtered_empty
         If filtered_empty.featureCount() == 0: return fixed_input unchanged
    |
    v
[Step 4b] Contact-fraction filter
         Goal: measure what fraction of each void's perimeter runs along the
         settlement's OUTER boundary only (not inner-ring lines of existing holes).

         1. Add fid_copy (@id) to void POLYGONS before converting to lines
            -- so the ID survives all intermediate steps and can select polygons at the end
         2. native:deleteholes(settlement_layer, MIN_AREA=0)
            -- removes all interior rings; inner-ring lines (edges of existing holes)
               must not be included in the reference, or voids inside existing holes
               would incorrectly show high contact and never be removed
         3. native:polygonstolines -> settlement outer boundary line only
         4. void boundaries: polygonstolines -> multiparttosingleparts,
            record total perimeter as length_1 (qgis:fieldcalculator, $length)
         5. native:splitlinesbylength (10 m segments) on void boundary lines
         6. buffer settlement outer boundary by 0.5 m (snap distance)
         7. extractbylocation(segments, settlement_buff, intersects) -> overlapping
         8. dissolve overlapping segments by fid_copy, measure overlap length (length_2)
         9. extractbyexpression('(length_2/length_1)*100 < threshold') -> qualifying_lines
            (interior voids never appear here -- they had no overlapping segments)
        10. collect fid_copy values from qualifying_lines
        11. extractbyexpression(void_with_fid, fid_copy IN (...)) -> voids_to_remove (POLYGONS)

         If voids_to_remove.featureCount() == 0: return fixed_input unchanged
    |
    v
[Step 5] Subtract qualifying voids from settlement
         buffer voids_to_remove by 0.5 m (close sliver gaps at the cut edge)
         difference(fixed_input, voids_to_remove_buff)
         -> result (input attribute schema preserved)
```

---

## Buffer Scaling Function

```python
buf_dist = max(MIN_BUFFER_M, min(MAX_BUFFER_M, math.sqrt(building_area)))
```

| Building area (m2) | sqrt(area) | Buffer (m) |
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
| `_DEBUG_TOOL_NAME` | `"06_ErodeEmptyAreas"` | Debug folder prefix |
| `MIN_BUFFER_M` | `10.0` | Minimum per-building buffer distance (m) |
| `MAX_BUFFER_M` | `100.0` | Maximum per-building buffer distance (m) |
| `MIN_EMPTY_AREA_M2` | `500.0` | Minimum void area (m2) to enter the contact filter |
| `TOPOLOGY_GRID_SIZE` | `0.001` | Grid size for difference operations (1 mm; see code docstring) |
| `BOUNDARY_CONTACT_THRESHOLD_PCT` | `20.0` | Maximum boundary-contact fraction (%) for a void to be removed; only voids with contact BELOW this value are removed; voids with equal or higher contact (significant fringe features) are kept |
| `_BOUNDARY_SEGMENT_M` | `10.0` | Split length (m) for void boundary segments in contact measurement |
| `_BOUNDARY_SNAP_M` | `0.5` | Buffer (m) around settlement boundary to catch near-touching segments |

---

## Key Parameters

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `input_layer` | -- | Settlement polygon (`QgsVectorLayer` or file path) |
| `buildings_layer` | -- | Building footprint layer (`QgsVectorLayer`) |
| `min_empty_area` | `MIN_EMPTY_AREA_M2` | Area threshold (m2): voids smaller than this are skipped entirely |
| `min_buffer_m` | `MIN_BUFFER_M` | Minimum per-building buffer distance (m) |
| `max_buffer_m` | `MAX_BUFFER_M` | Maximum per-building buffer distance (m) |
| `contact_threshold_pct` | `BOUNDARY_CONTACT_THRESHOLD_PCT` | Maximum boundary-contact % for a void to be removed; only voids with contact strictly below this value are removed |
| `workspace_path` | `None` | Absolute path for debug layer output |
| `debug_mode` | `False` | Save intermediate layers to `workspace_path` |

---

## Known Limitations / Workarounds

### `native:collect` is replaced with Python-level union (Steps 0b and 3)

`native:collect` in QGIS 3.40 fails with "Konnte Objekt nicht schreiben" when
the input layer has a declared `Polygon` type but contains `MultiPolygon`
features (e.g. buffers of multi-part buildings, or polygons split by
`fixgeometries`). The algorithm creates a `GeometryCollection` output from
the mixed input, which QGIS cannot write to a `MultiPolygon` sink.

Both Step 0b (dissolve `fixed_input`) and Step 3 (dissolve building buffers)
use `QgsGeometry.unaryUnion()` / iterative `QgsGeometry.combine()` instead:

```python
# Step 3 -- replaces collect + buffer(0, dissolve=True) + fixgeometries:
geoms = [feat.geometry() for feat in layer.getFeatures() if ...]
union_geom = QgsGeometry.unaryUnion(geoms)  # GEOS GEOSUnaryUnion, no feature sink
```

`QgsGeometry.unaryUnion()` calls GEOS `GEOSUnaryUnion()` directly and always
returns a clean `Polygon` or `MultiPolygon`, bypassing the feature-sink write
path entirely.

### Input must be pre-dissolved (Step 0b)

`blocks_merge` (the function's `input_layer`) is a merge of `snapped_rect` and
`blocks_dense`, two polygon layers that overlap in the same partition area. Two
compounding issues arise:

1. `native:difference` on overlapping/coincident-edge features can produce a
   `GeometryCollection` output (polygon + shared-edge line component) that QGIS
   cannot write to a `MultiPolygon` sink -> "Konnte Objekt nicht schreiben".
2. `native:fixgeometries(METHOD=1)` (Make Valid) can collapse degenerate thin
   polygons to `LineString` or `Point` geometries. When `native:collect` then
   tries to write the mixed-type collection to a `Polygon` output sink, the type
   mismatch causes the same write failure.

**Step 0b** dissolves `fixed_input` using `QgsGeometry.combine()` (GEOS union at
the Python level -- no QGIS feature sink involved). Only features with
`PolygonGeometry` type are included; collapsed Line/Point features are silently
dropped. The combined geometry is converted to `MultiPolygon` and stored in a
fresh memory layer. A single clean `MultiPolygon` always produces `Polygon` or
`MultiPolygon` output from `native:difference`, never a `GeometryCollection`.

Side effect: the output layer's attribute schema is the dissolved layer's schema
(minimal attributes), not the per-feature schema of the original `blocks_merge`.

### Contact filter uses exterior ring only (Step 4b)

`polygonstolines` on a polygon with holes produces lines for ALL rings (exterior
AND interior). Interior ring lines are the edges of existing holes in the
settlement. Measuring void contact against all rings would cause voids inside
existing holes to show high contact with those inner-ring lines and would never
be selected for removal.

**Fix**: `native:deleteholes(MIN_AREA=0)` is applied to the settlement before
`polygonstolines`, so only the true outer boundary is used as the reference.

### Contact filter returns polygons (Step 4b)

`fid_copy` is assigned to the void POLYGON layer in Step 4b (before line
conversion), not to the line layer. After identifying qualifying `fid_copy`
values in the dissolved overlap result, the final `extractbyexpression` selects
matching polygon features from the void layer. This ensures that the return
value of `_contact_fraction_filter` is always a polygon layer that can be
correctly buffered and subtracted in Step 5.

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

The function returns `input_layer` unchanged -- without raising -- when the
input has zero valid features or when `buildings_layer` is empty.

---

## Debug Layers (when `debug_mode=True`)

All layers are written to `{workspace_path}/06_ErodeEmptyAreas/`.

| Suffix | After step | Content |
|--------|-----------|---------|
| `step0b_dissolved` | 0b | Dissolved input (overlapping features merged) |
| `step1_sel_buildings` | 1 | Buildings selected within settlement boundary |
| `step2_building_buffers` | 2 | Individual per-building buffer polygons |
| `step3_buffer_union` | 3 | Dissolved union of all building buffers |
| `step4_empty_areas` | 4 | Raw empty areas (before area filter) |
| `step4_filtered_empty_areas` | 4 | Empty areas passing the `min_empty_area` threshold |
| `step4b_voids_to_remove` | 4b | Void POLYGONS that passed the contact filter (contact < threshold) and will be subtracted |
| `step5_result` | 5 | Final result |
| `exception_input` | on error | Raw input at time of crash |

---

## Related Files

- `ibtool_tools/ErodeEmptyAreas.py` -- implementation
- `ibtool_tools/PatchRemove.py` -- subsequent pipeline step (after GapClose)
- `helpers/safe_processing.py` -- `safe_processing_run()` wrapper used for all
  `processing.run()` calls
- `docs/how-it-works.md` -- full pipeline overview
