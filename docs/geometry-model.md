# Geometry Model

## Supported Geometry Types

The plugin works with three primary geometry types:

| Type | QGIS Class | Usage |
|------|-----------|-------|
| Polygon | `QgsWkbTypes.Polygon` | Building footprints (HU), partitioning zones (Part) |
| MultiPolygon | `QgsWkbTypes.MultiPolygon` | Dissolved settlement boundaries, buffered areas |
| LineString / MultiLineString | `QgsWkbTypes.LineString` | Road networks (RN), MST edges |

## Multipart Geometries

### When They Arise

- After `native:dissolve` or `native:collect` operations
- When merging adjacent features
- As intermediate results in buffering pipelines

### Handling Rules

1. **Always check `isMultipart()`** before accessing geometry parts
2. **Use `asMultiPolygon()` / `asMultiPolyline()`** for iteration over parts
3. **Convert singlepart ↔ multipart** explicitly using `native:multiparttosingleparts` or `native:collect`
4. **Known bug**: `native:dissolve` silently fails on large MultiPolygon sets (7801+ features), producing empty/null geometry. Use `native:collect` → `native:buffer(distance=0, dissolve=True)` as workaround.

## Geometry Validation

### Required Checks

| Check | Method | When |
|-------|--------|------|
| Null geometry | `feature.hasGeometry()` | Before any geometry access |
| Empty geometry | `geometry.isEmpty()` | After processing operations |
| Validity | `geometry.isGeosValid()` | After dissolve, buffer, intersection |
| WKB type | `layer.wkbType()` | After creating result layers |

### Fix Geometries

Use `native:fixgeometries` as a preprocessing step when input data quality is uncertain. This resolves:

- Self-intersections
- Ring ordering issues
- Duplicate vertices

## Layer-Level Checks

Before processing, validate input layers:

1. **Feature count**: `layer.featureCount() > 0`
2. **Geometry type**: `layer.geometryType() == QgsWkbTypes.PolygonGeometry`
3. **CRS match**: All input layers must share the same CRS
4. **Field existence**: Verify required attribute fields before access

## Coordinate Reference Systems

- All layers in a processing run must use the same CRS
- CRS is propagated from input to output layers
- No on-the-fly reprojection within tools — user must ensure CRS consistency

## Topology Considerations

- Settlement boundaries must be topologically clean (no gaps, no overlaps)
- Gap and hole closing tools (`GapClose`, `HoleClose`) address topological defects
- Edge detection (`EdgeCatch`) handles boundary alignment with partition edges
