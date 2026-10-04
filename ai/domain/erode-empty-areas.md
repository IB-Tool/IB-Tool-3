# ErodeEmptyAreas -- Building-Free Void Removal

## Overview

`ibtool_tools/ErodeEmptyAreas.py` removes areas within a settlement polygon
where no buildings are located. It runs as Step 8 in the main processing
pipeline, immediately after `EdgeCatch` and before `GapClose`.

The step removes building-free protrusions at the settlement fringe: lobes of
the settlement polygon that contain no buildings and hang off the built area
by a narrow connection. Building-free voids enclosed by built settlement
(parks, courtyards) and voids between built parts are kept. Running before `GapClose`
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
[Step 4b] Protrusion filter (pure Python, QgsGeometry)
         1. remainder = settlement - union(all voids)   (temporary)
         2. split remainder into parts; parts intersecting at least one
            building are "built parts" (QgsSpatialIndex pre-filter)
         3. buffer built parts and every void by _BOUNDARY_SNAP_M (0.5 m)
         4. per void, split the FULL perimeter (outer + inner rings) into
              building contact = perimeter inside the built-parts strip
              void contact     = rest inside the strip of the other voids
              free edge        = the rest (outer boundary towards open land,
                                 or unbuilt remainder parts)
         5. remove when building contact < max_building_contact_pct
                    AND free edge >= min_free_edge_pct
            -> voids_to_remove (POLYGONS, memory layer)
         Interior voids (100 % building contact) and voids between built
         parts are therefore always kept.
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
| `MIN_EMPTY_AREA_M2` | `500.0` | Minimum void area (m2) to enter the protrusion filter |
| `TOPOLOGY_GRID_SIZE` | `0.001` | Grid size for difference operations (1 mm; see code docstring) |
| `MAX_BUILDING_CONTACT_PCT` | `20.0` | A void is removed only when its building contact (share of perimeter bordering built parts) is BELOW this value |
| `MIN_FREE_EDGE_PCT` | `80.0` | A void is removed only when its free edge (share of perimeter bordering neither built parts nor another void) is AT LEAST this value |
| `_BOUNDARY_SNAP_M` | `0.5` | Buffer (m) around built parts and voids to catch near-touching edges |

---

## Key Parameters

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `input_layer` | -- | Settlement polygon (`QgsVectorLayer` or file path) |
| `buildings_layer` | -- | Building footprint layer (`QgsVectorLayer`) |
| `min_empty_area` | `MIN_EMPTY_AREA_M2` | Area threshold (m2): voids smaller than this are skipped entirely |
| `min_buffer_m` | `MIN_BUFFER_M` | Minimum per-building buffer distance (m) |
| `max_buffer_m` | `MAX_BUFFER_M` | Maximum per-building buffer distance (m) |
| `max_building_contact_pct` | `MAX_BUILDING_CONTACT_PCT` | Building contact must be strictly below this % for removal |
| `min_free_edge_pct` | `MIN_FREE_EDGE_PCT` | Free edge must be at least this % for removal |

Both thresholds depend on the local situation and are examples, not fixed
rules. They are function parameters only; they are not yet exposed in
CONFIG.ini or the dialog.
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

### Protrusion filter replaces the outer-contact filter (Step 4b)

Until 2026-10 the filter removed voids whose contact with the settlement OUTER
boundary was below 20 % (issue #168). That kept fringe protrusions and removed
voids with a small edge opening. The current rule measures the opposite side:
contact with the *built* remainder (settlement minus all voids, parts with
buildings only). A void is a protrusion when it barely touches built parts and
most of its edge is free.

- **Voids are subtracted only temporarily** to obtain the remainder; the final
  result still subtracts only the selected voids (Step 5).
- **Unbuilt remainder parts count as free edge.** Slivers below
  `min_empty_area` stay in the remainder; they contain no buildings and must
  not shield a protrusion.
- **Void-to-void contact is not free.** Voids from `multiparttosingleparts`
  rarely share edges, but where two voids lie within the 0.5 m snap distance
  neither counts the shared edge as free, so a protrusion split in two is kept
  rather than removed piecewise.
- **Full perimeter**: inner rings of a void (e.g. around an island of building
  buffers) count; they border built parts and raise the building contact.
- **Measurement** uses exact `QgsGeometry` intersection lengths with the 0.5 m
  strips, no segment splitting; overlaps between the built strip and a void
  strip are counted once (as building contact).

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
| `step4b_voids_to_remove` | 4b | Void POLYGONS that passed the protrusion filter and will be subtracted |
| `step5_result` | 5 | Final result |
| `exception_input` | on error | Raw input at time of crash |

---

## Related Files

- `ibtool_tools/ErodeEmptyAreas.py` -- implementation
- `ibtool_tools/PatchRemove.py` -- subsequent pipeline step (after GapClose)
- `helpers/safe_processing.py` -- `safe_processing_run()` wrapper used for all
  `processing.run()` calls
- `docs/how-it-works.md` -- full pipeline overview
