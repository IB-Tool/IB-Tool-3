# QGIS Processing Task Template

## Purpose

Vorlage für Aufgaben, die QGIS Processing-Algorithmen nutzen oder neue Processing-basierte Verarbeitungsschritte implementieren.

## Scope

- Verarbeitung über QGIS Processing Framework
- Saubere Parameterdefinition
- Fehlerbehandlung verpflichtend
- Debug-Modus-Integration

## Vorgehensweise

### 1. Algorithmus-Auswahl

- [ ] Passenden QGIS-Algorithmus identifizieren (`native:*`, `qgis:*`)
- [ ] API-Dokumentation prüfen (Parameter, Typen, Verhalten)
- [ ] Bekannte Bugs prüfen (z.B. `native:dissolve` bei großen Sets)
- [ ] Alternativ-Algorithmen kennen für Fallbacks

### 2. Parameterdefinition

- [ ] Alle Parameter explizit benennen (keine Defaults annehmen)
- [ ] Algorithmuskonstanten als Klassenkonstanten
- [ ] QGIS-technische Parameter aus `qgis_defaults.py`
- [ ] `QgsProcessing.TEMPORARY_OUTPUT` für Zwischenergebnisse

### 3. Implementierung

```python
from helpers.qgis_defaults import QGISDefaults

qgis_defaults = QGISDefaults()

# Über safe_processing_run für Fehlerbehandlung
result = safe_processing_run("native:buffer", {
    'INPUT': input_layer,
    'DISTANCE': self.BUFFER_DISTANCE,
    'SEGMENTS': qgis_defaults.buffer_segments,
    'END_CAP_STYLE': qgis_defaults.buffer_end_cap_style,
    'JOIN_STYLE': qgis_defaults.buffer_join_style,
    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
}, **_dbg)
```

### 4. Fehlerbehandlung

- [ ] `safe_processing_run()` statt direktem `processing.run()`
- [ ] Ergebnis-Layer auf Validität prüfen
- [ ] Leere Ergebnisse abfangen
- [ ] WKB-Typ des Ergebnis-Layers prüfen
- [ ] Debug-Layer speichern bei Fehlern

### 5. Validierung

- [ ] Ergebnis-Geometrien validieren (nicht null, nicht leer, gültig)
- [ ] Feature-Count prüfen (erwarteter Bereich)
- [ ] CRS des Ergebnis-Layers prüfen
- [ ] Multipart/Singlepart-Typ wie erwartet

## Bekannte Fallstricke

### native:dissolve

**Problem**: Silently fails bei 7801+ MultiPolygon Features, produziert leere Geometrie mit `wkbType=Unknown`.

**Workaround**:
```python
# Statt native:dissolve:
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

### Verkettete Operationen

Bei mehreren aufeinanderfolgenden Processing-Schritten:
- Zwischenergebnisse im Debug-Modus speichern
- Jeden Schritt einzeln validieren
- Nicht annehmen, dass der vorherige Schritt erfolgreich war

## Checklist

```
[ ] Algorithmus dokumentiert (welcher, warum)
[ ] Parameter vollständig und explizit
[ ] safe_processing_run() verwendet
[ ] Ergebnis validiert (Geometrie, Feature-Count, CRS)
[ ] Bekannte Bugs berücksichtigt
[ ] Debug-Modus integriert
[ ] Fehlerfall getestet
[ ] Performance bei großen Datasets berücksichtigt
```
