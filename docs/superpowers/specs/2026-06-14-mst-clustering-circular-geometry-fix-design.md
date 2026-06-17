# Design: MST Clustering — Winkelberechnung bei runden Geometrien

**Datum:** 2026-06-14
**Branch:** FIX-MBR-Orintation
**Betroffene Datei:** `ibtool_tools/MST_Clustering.py`

## Problem

`mst_clustering()` sammelt alle Polygon-Kanten aller Gebäude und berechnet daraus den dominanten Ausrichtungswinkel via `_main_angle()`. Kreisförmige Gebäude (reine Kreise oder gemischte Polygone aus Kreis + Rechteck) erzeugen viele kurze Bogensegmente gleichmäßig über alle Richtungen. Diese verwässern die Winkelverteilung und kippen den dominanten Winkel weg von der tatsächlichen Ausrichtung der rechteckigen Gebäude im Cluster.

## Lösung: Relativer Kantenlängen-Filter pro Gebäude (Ansatz B)

### Kern-Idee

Für jedes Gebäude werden nur Kanten in den Winkelpool aufgenommen, die mindestens **20 % der längsten Kante dieses Gebäudes** lang sind. Kurze Bogensegmente fallen automatisch raus; lange, gerade Kanten (Rechteckseiten) bleiben erhalten.

### Neue Konstante

```python
# Minimum edge length as a fraction of the longest edge per building.
# Edges below this threshold are excluded from the dominant-angle calculation
# to prevent arc segments of circular geometries from skewing the result.
_MIN_EDGE_LENGTH_RATIO = 0.20
```

### Änderung in `mst_clustering()`

Nach dem bestehenden Block:
```python
dict_hu = dict(list(hu_line_array))
```

wird folgender Filterungsschritt eingefügt:

```python
filtered_dict_hu = {}
for fid, edge_rows in dict_hu.items():
    max_len = max(row[4] for row in edge_rows)
    filtered = [row for row in edge_rows if row[4] >= max_len * _MIN_EDGE_LENGTH_RATIO]
    filtered_dict_hu[fid] = filtered if len(filtered) >= 2 else edge_rows
dict_hu = filtered_dict_hu
```

`dict_hu` wird anschließend unverändert weiterverwendet. Keine Änderung an `calc_bounding_rect()` nötig.

### Grenzfälle

| Szenario | Verhalten |
|---|---|
| Reiner Kreis (alle Kanten gleich lang) | Alle würden gefiltert → Fallback: ungefilterte Liste verwenden |
| Gemischtes Polygon (Kreis + Rechteck) | Bogensegmente raus, Rechteckkanten bleiben |
| Cluster mit < 5 Punkten | Bereits durch bestehenden Guard `len(point_list) > 4` in `calc_bounding_rect()` abgefangen |
| Rechteck mit ungleichen Seiten | Alle 4 Seiten bleiben (kürzeste ≥ ~40–50 % der längsten bei normalen Gebäuden) |

## Architektur

- **Änderungsumfang:** ~5 Zeilen in `mst_clustering()`, eine neue Modul-Konstante
- **Keine Änderung** an `calc_bounding_rect()`, `_main_angle()` oder anderen Funktionen
- **Kompatibilität:** Rein interne mathematische Vorfilterung, keine API-Änderung

## Tests

### `test_min_edge_filter_pure_circle`
- **Input:** Ein Kreis-Polygon (N gleichmäßige Bogensegmente) + ein klar ausgerichtetes Rechteck (z.B. 45°)
- **Erwartung:** `calc_bounding_rect()` liefert einen Winkel nahe 45°, nicht einer Mischung
- **Methode:** Direkter Aufruf mit `mode="list"`, kein QGIS-Layer nötig

### `test_min_edge_filter_mixed_polygon`
- **Input:** Ein gemischtes Polygon (Kreisbogen + zwei Rechteckseiten) + ein Referenzrechteck
- **Erwartung:** Winkel entspricht dem Rechteck, Bogensegmente haben keinen Einfluss
- **Methode:** Direkter Aufruf mit `mode="list"`

## Threshold-Begründung

- Bogensegmente eines N-Eck-Kreises: Länge ≈ `2π·r / N` — bei N=36 ist das ≈ 17 % des Durchmessers
- Kürzeste Seite eines typischen Gebäuderechtecks: ≈ 40–100 % der längsten Seite
- 20 % als Schwelle liegt sicher zwischen diesen Bereichen und braucht keine Kalibrierung per Datensatz
