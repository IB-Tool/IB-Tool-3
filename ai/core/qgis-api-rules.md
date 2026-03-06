# QGIS API Rules

## Core Classes

### QgsVectorLayer

```python
# Create a temporary layer
layer = QgsVectorLayer("Polygon?crs=EPSG:25832", "name", "memory")

# Feature iteration
for feature in layer.getFeatures():
    geom = feature.geometry()
```

- Always check `layer.isValid()` after creation
- Create temporary layers via `"memory"` provider
- For file-based layers: path as the first parameter

### QgsFeature

```python
feature = QgsFeature()
feature.setGeometry(geometry)
feature.setAttributes([value1, value2])
```

- Set geometry and attributes separately
- Do not set feature IDs manually — assigned by the layer
- Check `feature.hasGeometry()` before accessing geometry

### QgsGeometry

```python
geom = QgsGeometry.fromWkt(wkt_string)
geom = feature.geometry()

# Operations
buffered = geom.buffer(distance, segments)
intersection = geom.intersection(other_geom)
```

- Always validate the result of geometry operations
- `isNull()` and `isEmpty()` are different states — check both
- Prefer QGIS Processing for complex operations

## QGIS Processing

### Preferred Usage

```python
result = processing.run("native:buffer", {
    'INPUT': input_layer,
    'DISTANCE': distance,
    'SEGMENTS': 5,
    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
})
output_layer = result['OUTPUT']
```

- Use `QgsProcessing.TEMPORARY_OUTPUT` for intermediate results
- Extract the result layer from the result dict
- Use the `safe_processing_run()` wrapper for error handling

### Commonly Used Algorithms

| Algorithm | Purpose |
|-----------|---------|
| `native:buffer` | Buffer zone around geometries |
| `native:dissolve` | Merge geometries (caution with large sets) |
| `native:collect` | Collect features into multipart |
| `native:fixgeometries` | Repair invalid geometries |
| `native:intersection` | Geometric intersection |
| `native:difference` | Geometric difference |
| `native:multiparttosingleparts` | Multipart → Singlepart |
| `native:extractbyexpression` | Filter features by expression |

## API Version Compatibility

- **Target version**: QGIS 3.40–3.50
- **No deprecated API** — check the QGIS Python API documentation
- When in doubt: use the QGIS PyQGIS Developer Cookbook as reference
- Use `QgsWkbTypes` instead of deprecated enums for geometry types

## Coordinate Reference Systems

```python
# Read CRS from layer
crs = layer.crs()

# Create CRS object
crs = QgsCoordinateReferenceSystem("EPSG:25832")

# Transformation
transform = QgsCoordinateTransform(source_crs, dest_crs, QgsProject.instance())
```

- No implicit reprojection — always transform explicitly
- Verify CRS consistency between input layers before processing
