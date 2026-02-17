# QGIS API Rules

## Kern-Klassen

### QgsVectorLayer

```python
# Erstellen eines temporären Layers
layer = QgsVectorLayer("Polygon?crs=EPSG:25832", "name", "memory")

# Feature-Iteration
for feature in layer.getFeatures():
    geom = feature.geometry()
```

- Immer `layer.isValid()` prüfen nach Erstellung
- Temporäre Layer über `"memory"` Provider erstellen
- Für Datei-basierte Layer: Pfad als ersten Parameter

### QgsFeature

```python
feature = QgsFeature()
feature.setGeometry(geometry)
feature.setAttributes([value1, value2])
```

- Geometrie und Attribute separat setzen
- Feature-ID nicht manuell setzen — wird vom Layer vergeben
- `feature.hasGeometry()` prüfen bevor auf Geometrie zugegriffen wird

### QgsGeometry

```python
geom = QgsGeometry.fromWkt(wkt_string)
geom = feature.geometry()

# Operationen
buffered = geom.buffer(distance, segments)
intersection = geom.intersection(other_geom)
```

- Ergebnis von Geometrieoperationen immer auf Validität prüfen
- `isNull()` und `isEmpty()` sind verschiedene Zustände — beide prüfen
- Für komplexe Operationen QGIS Processing bevorzugen

## QGIS Processing

### Bevorzugte Nutzung

```python
result = processing.run("native:buffer", {
    'INPUT': input_layer,
    'DISTANCE': distance,
    'SEGMENTS': 5,
    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
})
output_layer = result['OUTPUT']
```

- `QgsProcessing.TEMPORARY_OUTPUT` für Zwischenergebnisse
- Ergebnis-Layer aus dem Result-Dict extrahieren
- `safe_processing_run()` Wrapper für Fehlerbehandlung nutzen

### Häufig verwendete Algorithmen

| Algorithmus | Zweck |
|-------------|-------|
| `native:buffer` | Pufferzone um Geometrien |
| `native:dissolve` | Geometrien zusammenführen (Vorsicht bei großen Sets) |
| `native:collect` | Features zu Multipart sammeln |
| `native:fixgeometries` | Ungültige Geometrien reparieren |
| `native:intersection` | Geometrische Verschneidung |
| `native:difference` | Geometrische Differenz |
| `native:multiparttosingleparts` | Multipart → Singlepart |
| `native:extractbyexpression` | Features nach Ausdruck filtern |

## API-Versionskompatibilität

- **Zielversion**: QGIS 3.40–3.50
- **Keine deprecated API** verwenden — prüfe die QGIS Python API Dokumentation
- Bei Unsicherheit: QGIS PyQGIS Developer Cookbook als Referenz nutzen
- `QgsWkbTypes` statt veralteter Enums für Geometrietypen

## Koordinatensysteme

```python
# CRS aus Layer lesen
crs = layer.crs()

# CRS-Objekt erstellen
crs = QgsCoordinateReferenceSystem("EPSG:25832")

# Transformation
transform = QgsCoordinateTransform(source_crs, dest_crs, QgsProject.instance())
```

- Keine implizite Reprojektion — immer explizit transformieren
- CRS-Konsistenz zwischen Input-Layern vor Verarbeitung prüfen
