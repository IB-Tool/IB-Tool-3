
# IBTool

![QGIS Plugin](https://img.shields.io/badge/QGIS-Plugin-blue)
![License](https://img.shields.io/badge/license-GPL%20v2-green)
![Python](https://img.shields.io/badge/Python-3.12-blue)

## Projektbeschreibung

**IBTool** ist ein QGIS-Plugin, das Werkzeuge zur Verfügung stellt, um Siedlungen basierend auf Gebäudeumrissen zu analysieren und abzugrenzen. Es automatisiert komplexe Geodatenprozesse wie Clustering, Mindestflächenberechnungen und die Erstellung von Minimum Spanning Trees (MST) zur Identifikation von urbanen Strukturen.

---

## Funktionen

- **Automatisierte Verarbeitung von Geodaten:**
  - Filterung und Clusterbildung basierend auf Gebäudeumrissen.
  - Berechnung lokaler und globaler Gebäudeabdeckungsdichten.
  - Erkennung dichter Blockstrukturen aus Straßen- und Gebäude-Daten.

- **Interaktives GUI-Design:**
  - Fortschrittsbalken zur Echtzeit-Überwachung von Prozessen.
  - Filtereinstellungen für spezifische Eingabedaten über Dialoge.

- **Integration in QGIS:**
  - Unterstützung von QGIS-Logik zur Layerauswahl, Verarbeitung und Ergebnisanzeigen in Geopackages.

- **Effiziente Datenverarbeitung:**
  - Export und Speicherung selektierter oder berechneter Layer.
  - Optimierung der Ergebnisse durch Parametereinstellungen (z.B. Mindestüberlappungsraten, Gebäudeanzahl etc.).

---

## Voraussetzungen

- **QGIS**: Version 3.22 oder höher.
- **Python**: Version 3.12.
- Installierte Python-Bibliotheken:
  - `numpy`
  - `pandas`
  - `PyQt5`
  - `qgis.core`

---

## Installation

1. **Herunterladen**:
   - Lade die Repository-Dateien als ZIP herunter oder klone das Repository:
     ```bash
     git clone https://github.com/dein-repository/ibtool.git
     ```
2. **Installation im QGIS-Plugin-Ordner**:
   - Extrahiere die Projektdateien in deinen QGIS-Plugins-Ordner:
     - Windows: `C:\Users\<Benutzername>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins`
     - Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins`
3. **Aktivieren des Plugins**:
   - Starte QGIS und aktiviere IBTool in der "Plugin-Verwaltung".

---

## Verwendung

1. Starte das Plugin über die QGIS-Menüleiste unter **Plugins > IB-Tool**.
2. Lade deine Geodaten (z.B. Gebäudeumrisse, Straßennetzwerke) direkt über die Benutzeroberfläche des Tools.
3. Konfiguriere die Parametereinstellungen im Dialogfenster.
4. Beginne die Verarbeitung:
   - Überwache den Fortschritt im Fortschrittsbalken.
   - Ergebnisse werden als .gpkg-Dateien gespeichert.

---

## Eingabedateien

Das Plugin arbeitet mit verschiedenen Eingabedateien. Diese beinhalten:

- **HU (Building Footprints)**: Gebäudeumrisse.
- **RN (Road Network)**: Straßennetzwerke.
- **Part (Partitioning)**: Zonierung zur Eingrenzung des Analysebereichs.
- **Aux (Auxiliary Layers)**: Hilfsebenen zur Verfeinerung der Analysen.
- **Filter-Datei**: Eine .txt-Datei zur Definition von positiven und negativen Filtern.

---

### Projektstruktur

Nach der erfolgreichen Verarbeitung erstellt IBTool folgende Struktur:


## Lizenz

Dieses Plugin wurde unter der **GNU General Public License v2.0** lizenziert. Sie können es frei verwenden, verändern und weitergeben, solange die Bedingungen der GPL eingehalten werden.

---

## Entwickler & Kontakt

- **Autor**: 
- **Erstellt mit Unterstützung von**: [QGIS Plugin Builder](http://g-sherman.github.io/Qgis-Plugin-Builder/)

---

## Fehlerbehebung

- Stelle sicher, dass deine Eingabedaten sich im gleichen **CRS** (Koordinatensystem) befinden.
- Überprüfe, ob Abhängigkeiten (z.B. Bibliotheken) korrekt installiert sind.
- Konsultiere die Log-Nachrichten im Message-Fenster des Plugins, um Fehler zu identifizieren.

---

Viel Spaß beim Verwenden des **IBTool**-Plugins!




