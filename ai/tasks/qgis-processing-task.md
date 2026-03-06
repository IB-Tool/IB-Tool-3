# QGIS Processing Task Template

## Purpose

Template for tasks that use QGIS Processing algorithms or implement new processing-based steps.

## Scope

- Processing via the QGIS Processing framework
- Clean parameter definition
- Error handling mandatory
- Debug mode integration

## Procedure

### 1. Algorithm Selection

- [ ] Identify the appropriate QGIS algorithm (`native:*`, `qgis:*`)
- [ ] Check API documentation (parameters, types, behavior)
- [ ] Check for known bugs (e.g. `native:dissolve` on large sets)
- [ ] Know alternative algorithms for fallbacks

### 2. Parameter Definition

- [ ] Name all parameters explicitly (do not assume defaults)
- [ ] Algorithm constants as class constants
- [ ] QGIS technical parameters from `qgis_defaults.py`
- [ ] `QgsProcessing.TEMPORARY_OUTPUT` for intermediate results

### 3. Implementation

```python
from helpers.qgis_defaults import QGISDefaults

qgis_defaults = QGISDefaults()

# Via safe_processing_run for error handling
result = safe_processing_run("native:buffer", {
    'INPUT': input_layer,
    'DISTANCE': self.BUFFER_DISTANCE,
    'SEGMENTS': qgis_defaults.buffer_segments,
    'END_CAP_STYLE': qgis_defaults.buffer_end_cap_style,
    'JOIN_STYLE': qgis_defaults.buffer_join_style,
    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
}, **_dbg)
```

### 4. Error Handling

- [ ] Use `safe_processing_run()` instead of direct `processing.run()`
- [ ] Validate the result layer
- [ ] Catch empty results
- [ ] Check the WKB type of the result layer
- [ ] Save debug layers on errors

### 5. Validation

- [ ] Validate result geometries (not null, not empty, valid)
- [ ] Check feature count (expected range)
- [ ] Check the CRS of the result layer
- [ ] Multipart/singlepart type as expected

## Known Pitfalls

### native:dissolve

**Problem**: Silently fails on 7801+ MultiPolygon features, producing empty geometry with `wkbType=Unknown`.

**Workaround**:
```python
# Instead of native:dissolve:
collected = safe_processing_run("native:collect", {
    'INPUT': input_layer,
    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
}, **_dbg)['OUTPUT']

dissolved = safe_processing_run("native:buffer", {
    'INPUT': collected,
    'DISTANCE': 0,
    'DISSOLVE': True,
    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
}, **_dbg)['OUTPUT']
```

### Chained Operations

For multiple sequential processing steps:
- Save intermediate results in debug mode
- Validate each step individually
- Do not assume the previous step succeeded

## Checklist

```
[ ] Algorithm documented (which one, why)
[ ] Parameters complete and explicit
[ ] safe_processing_run() used
[ ] Result validated (geometry, feature count, CRS)
[ ] Known bugs accounted for
[ ] Debug mode integrated
[ ] Error case tested
[ ] Performance with large datasets considered
[ ] pylint <changed_module> — no new warnings, score must not decrease
```
