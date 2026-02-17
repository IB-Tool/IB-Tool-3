# Feature Processing

Rules for working with features, attributes, and layer operations.

## Feature Iteration

### Basic Pattern

```python
for feature in layer.getFeatures():
    if not feature.hasGeometry():
        continue
    geom = feature.geometry()
    # Processing
```

### With Filter

```python
# Filter by expression
request = QgsFeatureRequest().setFilterExpression('"area" > 100')
for feature in layer.getFeatures(request):
    # Only features with area > 100
```

### With Spatial Filter

```python
request = QgsFeatureRequest().setFilterRect(bounding_box)
for feature in layer.getFeatures(request):
    # Only features within the bounding box
```

### Rules

- Always check `hasGeometry()` before accessing geometry
- Prefer feature requests with filters over post-hoc filtering
- For large layers: use spatial index for performance

## Attribute Join

### Via Processing

```python
result = processing.run("native:joinattributesbylocation", {
    'INPUT': target_layer,
    'JOIN': join_layer,
    'PREDICATE': [0],  # 0 = intersects
    'JOIN_FIELDS': ['field_name'],
    'METHOD': 0,  # 0 = one-to-many
    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
})
```

### Rules

- Specify join fields explicitly — do not copy all fields
- Choose the join method deliberately (one-to-one vs. one-to-many)
- Check the result for unexpected NULL values

## Field Calculator Operations

### Via Processing

```python
result = processing.run("native:fieldcalculator", {
    'INPUT': layer,
    'FIELD_NAME': 'area_m2',
    'FIELD_TYPE': 0,  # 0 = Float
    'FORMULA': '$area',
    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
})
```

### Via Expression

```python
expression = QgsExpression('"length" < 50')
context = QgsExpressionContext()
context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))

for feature in layer.getFeatures():
    context.setFeature(feature)
    if expression.evaluate(context):
        # Feature matches the condition
```

### Rules

- Field names in double quotes: `"field_name"`
- Function calls without quotes: `$area`, `$length`
- Specify field type explicitly (0=Float, 1=Integer, 2=String)

## ID Handling

### Feature IDs

- Feature IDs (`feature.id()`) are layer-internal and not stable across operations
- After processing operations, IDs are reassigned
- Never use feature IDs as persistent references

### Custom IDs

- For stable references: use a custom attribute field (`"orig_id"`)
- Create the ID field before processing and join it back afterwards
- Dissolve loses individual IDs — save them beforehand if needed

## Layer Creation

### Temporary Layer

```python
fields = QgsFields()
fields.append(QgsField("name", QVariant.String))
fields.append(QgsField("value", QVariant.Double))

layer = QgsVectorLayer("Polygon?crs=EPSG:25832", "result", "memory")
provider = layer.dataProvider()
provider.addAttributes(fields.toList())
layer.updateFields()
```

### Adding Features

```python
provider = layer.dataProvider()
new_features = []

for geom in geometries:
    feat = QgsFeature(layer.fields())
    feat.setGeometry(geom)
    feat.setAttributes(["value1", 42.0])
    new_features.append(feat)

provider.addFeatures(new_features)
layer.updateExtents()
```

### Rules

- Collect features and add them in a single batch (performance)
- Call `updateExtents()` after adding features
- Call `updateFields()` after field changes
