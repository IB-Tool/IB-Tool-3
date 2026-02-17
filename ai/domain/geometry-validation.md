# Geometry Validation

Regeln und Prüfungen für geometrische Operationen im IBTool-Projekt.

## Pflichtprüfungen

### Null-Geometrie

Vor jedem Zugriff auf Geometrie:

```python
if not feature.hasGeometry():
    logger.warning(f"Feature {feature.id()} has no geometry — skipping")
    continue

geom = feature.geometry()
if geom.isNull():
    logger.warning(f"Feature {feature.id()} has null geometry — skipping")
    continue
```

### Leere Geometrie

Nach jeder Verarbeitungsoperation:

```python
if geom.isEmpty():
    logger.warning("Operation produced empty geometry")
```

Ursachen für leere Geometrien:
- Dissolve auf zu großem Feature-Set (bekannter Bug bei 7801+ Features)
- Intersection ohne Überlappung
- Buffer mit negativem Abstand, der die Fläche eliminiert

### Validität

Nach geometrischen Operationen (dissolve, buffer, intersection):

```python
if not geom.isGeosValid():
    logger.warning("Invalid geometry detected — attempting fix")
    geom = geom.makeValid()
```

Alternativ über Processing:

```python
fixed = processing.run("native:fixgeometries", {
    'INPUT': layer,
    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
})
```

## Multipart-Prüfung

### Wann relevant

- Nach `native:dissolve` — Ergebnis ist typischerweise MultiPolygon
- Nach `native:collect` — sammelt Features zu Multipart
- Bei Import externer Daten — Geometrietyp kann variieren

### Prüfung und Konvertierung

```python
if geom.isMultipart():
    parts = geom.asGeometryCollection()
    for part in parts:
        # Verarbeite einzelne Teile
```

Konvertierung über Processing:

```python
# Multipart → Singlepart
processing.run("native:multiparttosingleparts", {...})

# Singlepart → Multipart
processing.run("native:collect", {...})
```

## Self-Intersection

Self-Intersections entstehen häufig durch:
- Ungenaue Digitalisierung
- Puffer-Operationen an spitzen Winkeln
- Import aus externen Quellen

Erkennung:

```python
if not geom.isGeosValid():
    errors = geom.validateGeometry()
    for error in errors:
        logger.warning(f"Geometry error: {error.what()}")
```

## Topology-Checks

### Überlappung

Zwischen Siedlungsgrenzen darf es keine Überlappungen geben:

```python
intersection = geom_a.intersection(geom_b)
if not intersection.isEmpty():
    logger.warning("Overlapping geometries detected")
```

### Lücken (Gaps)

Lücken zwischen benachbarten Polygonen werden durch `GapClose` und `GapFix` behandelt. Prüfung auf Vollständigkeit:

- Vereinigung aller Polygone bilden
- Mit erwarteter Begrenzung vergleichen
- Differenz zeigt Lücken

### WKB-Typ-Prüfung

Nach Layer-Erstellung den resultierenden Geometrietyp prüfen:

```python
wkb_type = result_layer.wkbType()
if wkb_type == QgsWkbTypes.Unknown:
    logger.critical("Result layer has unknown geometry type — processing failed")
```

Dies ist ein Indikator für fehlgeschlagene Dissolve-Operationen.
