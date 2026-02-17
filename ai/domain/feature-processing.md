# Feature Processing

Regeln für den Umgang mit Features, Attributen und Layer-Operationen.

## Feature-Iteration

### Grundmuster

```python
for feature in layer.getFeatures():
    if not feature.hasGeometry():
        continue
    geom = feature.geometry()
    # Verarbeitung
```

### Mit Filter

```python
# Nach Ausdruck filtern
request = QgsFeatureRequest().setFilterExpression('"area" > 100')
for feature in layer.getFeatures(request):
    # Nur Features mit area > 100
```

### Mit räumlichem Filter

```python
request = QgsFeatureRequest().setFilterRect(bounding_box)
for feature in layer.getFeatures(request):
    # Nur Features im Bounding-Box-Bereich
```

### Regeln

- Immer `hasGeometry()` prüfen vor Geometriezugriff
- Feature-Requests mit Filter bevorzugen statt nachträglichem Filtern
- Bei großen Layern: räumlichen Index nutzen für Performance

## Attribute-Join

### Über Processing

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

### Regeln

- Join-Felder explizit angeben — nicht alle Felder übernehmen
- Join-Methode bewusst wählen (one-to-one vs. one-to-many)
- Ergebnis auf unerwartete NULL-Werte prüfen

## Feldrechner-Operationen

### Über Processing

```python
result = processing.run("native:fieldcalculator", {
    'INPUT': layer,
    'FIELD_NAME': 'area_m2',
    'FIELD_TYPE': 0,  # 0 = Float
    'FORMULA': '$area',
    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
})
```

### Über Expression

```python
expression = QgsExpression('"length" < 50')
context = QgsExpressionContext()
context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))

for feature in layer.getFeatures():
    context.setFeature(feature)
    if expression.evaluate(context):
        # Feature erfüllt Bedingung
```

### Regeln

- Feldnamen in doppelten Anführungszeichen: `"field_name"`
- Funktionsaufrufe ohne Anführungszeichen: `$area`, `$length`
- Feldtyp explizit angeben (0=Float, 1=Integer, 2=String)

## ID-Verarbeitung

### Feature-IDs

- Feature-IDs (`feature.id()`) sind Layer-intern und nicht stabil über Operationen hinweg
- Nach Processing-Operationen werden IDs neu vergeben
- Niemals Feature-IDs als persistente Referenz verwenden

### Eigene IDs

- Für stabile Referenzen: eigenes Attributfeld (`"orig_id"`) verwenden
- ID-Feld vor der Verarbeitung anlegen und nach der Verarbeitung zurückjoinen
- Bei Dissolve gehen individuelle IDs verloren — vorher sichern wenn nötig

## Layer-Erstellung

### Temporärer Layer

```python
fields = QgsFields()
fields.append(QgsField("name", QVariant.String))
fields.append(QgsField("value", QVariant.Double))

layer = QgsVectorLayer("Polygon?crs=EPSG:25832", "result", "memory")
provider = layer.dataProvider()
provider.addAttributes(fields.toList())
layer.updateFields()
```

### Features hinzufügen

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

### Regeln

- Features sammeln und in einem Batch hinzufügen (Performance)
- `updateExtents()` nach dem Hinzufügen aufrufen
- `updateFields()` nach Feldänderungen aufrufen
