# Geometry Validation

Rules and checks for geometric operations in the IBTool project.

## Mandatory Checks

### Null Geometry

Before any geometry access:

```python
if not feature.hasGeometry():
    logger.warning(f"Feature {feature.id()} has no geometry — skipping")
    continue

geom = feature.geometry()
if geom.isNull():
    logger.warning(f"Feature {feature.id()} has null geometry — skipping")
    continue
```

### Empty Geometry

After every processing operation:

```python
if geom.isEmpty():
    logger.warning("Operation produced empty geometry")
```

Common causes of empty geometries:
- Dissolve on too-large feature sets (known bug at 7801+ features)
- Intersection with no overlap
- Buffer with negative distance that eliminates the area

### Validity

After geometric operations (dissolve, buffer, intersection):

```python
if not geom.isGeosValid():
    logger.warning("Invalid geometry detected — attempting fix")
    geom = geom.makeValid()
```

Alternatively via Processing:

```python
fixed = processing.run("native:fixgeometries", {
    'INPUT': layer,
    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
})
```

## Multipart Check

### When Relevant

- After `native:dissolve` — result is typically MultiPolygon
- After `native:collect` — collects features into multipart
- When importing external data — geometry type may vary

### Check and Conversion

```python
if geom.isMultipart():
    parts = geom.asGeometryCollection()
    for part in parts:
        # Process individual parts
```

Conversion via Processing:

```python
# Multipart → Singlepart
processing.run("native:multiparttosingleparts", {...})

# Singlepart → Multipart
processing.run("native:collect", {...})
```

## Self-Intersection

Self-intersections commonly arise from:
- Inaccurate digitization
- Buffer operations at sharp angles
- Import from external sources

Detection:

```python
if not geom.isGeosValid():
    errors = geom.validateGeometry()
    for error in errors:
        logger.warning(f"Geometry error: {error.what()}")
```

## Topology Checks

### Overlap

Settlement boundaries must not overlap:

```python
intersection = geom_a.intersection(geom_b)
if not intersection.isEmpty():
    logger.warning("Overlapping geometries detected")
```

### Gaps

Gaps between adjacent polygons are handled by `GapClose` and `GapFix`. Completeness check:

- Form the union of all polygons
- Compare with the expected boundary
- The difference reveals gaps

### WKB Type Check

After layer creation, verify the resulting geometry type:

```python
wkb_type = result_layer.wkbType()
if wkb_type == QgsWkbTypes.Unknown:
    logger.critical("Result layer has unknown geometry type — processing failed")
```

This is an indicator of failed dissolve operations.
