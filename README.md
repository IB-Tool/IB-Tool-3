# IBTool

![QGIS Plugin](https://img.shields.io/badge/QGIS-Plugin-blue)
![License](https://img.shields.io/badge/license-GPL%20v2-green)
[![Coverage](https://codecov.io/gh/your-username/IB-Tool-3/branch/main/graph/badge.svg)](https://codecov.io/gh/your-username/IB-Tool-3)
![Python](https://img.shields.io/badge/Python-3.11-blue)


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

- **QGIS**: Version 3.40-3.50
- **Python**: Version >= 3.11

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
     - Hinweis: Installationspfad kann unsichtbar sein und muss dann erst über die Ordnereinstellung sichtbar gemacht werden
3. **QGIS-Pfad konfigurieren (optional)**:
   - IBTool erkennt QGIS automatisch über die Umgebungsvariable `QGIS_PREFIX_PATH` oder übliche Installationsorte.
   - Ist QGIS an einem anderen Ort installiert, setze `QGIS_PREFIX_PATH` manuell, z.B.:
     ```bash
     export QGIS_PREFIX_PATH=/opt/qgis
     ```
4. **Aktivieren des Plugins**:
   - Starte QGIS und aktiviere IBTool in der "Plugin-Verwaltung".

---

## Verwendung

1. Starte das Plugin über die QGIS-Menüleiste unter **Plugins > IB-Tool**.
2. Lade deine Geodaten (z.B. Gebäudeumrisse, Straßennetzwerke) direkt über die Benutzeroberfläche des Tools.
3. Lege einen Workspace-Ordner fest. Dieser dient zum Abspeichern von Zwischen- und Endergebnissen.
4. Konfiguriere die Parametereinstellungen im Dialogfenster.
5. Beginne die Verarbeitung:
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


## Logging-System

Das IBTool verfügt über ein umfassendes Logging-System, das Meldungen an drei verschiedenen Stellen ausgibt:

1. In der Benutzeroberfläche (Nachrichtenfenster)
2. In einer Logdatei im konfigurierbaren Log-Verzeichnis
3. In den QGIS-Meldungen

### Log-Levels

Das System unterstützt vier verschiedene Log-Levels, die in absteigender Priorität sind:

- **CRITICAL**: Kritische Fehler, die die Ausführung beeinträchtigen
- **WARNING**: Warnungen, die auf mögliche Probleme hinweisen
- **INFO**: Informationsmeldungen über den normalen Ablauf
- **SUCCESS**: Detaillierte Erfolgs- und Debug-Meldungen

Bei der Auswahl eines Log-Levels werden alle Nachrichten dieses Levels und der höheren Priorität angezeigt. Beispiel: Bei Auswahl von "INFO" werden INFO-, WARNING- und CRITICAL-Meldungen angezeigt, aber keine SUCCESS-Meldungen.

### Konfiguration

Das Log-Level kann über die Benutzeroberfläche eingestellt werden:

1. Wählen Sie im Dropdown-Menü "Log-Level" den gewünschten Detaillierungsgrad aus.
2. Optional: Wählen Sie ein anderes Verzeichnis für die Logdateien über den "Log-Verzeichnis" Button.

### Logdateien

Die Logdateien werden standardmäßig im Unterverzeichnis "logs" des Plugins gespeichert und mit einem Zeitstempel im Format `logfile_YYYY-MM-DD_HH-MM-SS.txt` versehen. Bei jedem Start des Plugins wird eine neue Logdatei erstellt.


## Lizenz

Dieses Plugin wurde unter der **GNU General Public License v2.0** lizenziert. Sie können es frei verwenden, verändern und weitergeben, solange die Bedingungen der GPL eingehalten werden.

---

## Entwickler

- **Autor**: Oliver Harig
- **Erstellt mit Unterstützung von**: [QGIS Plugin Builder](http://g-sherman.github.io/Qgis-Plugin-Builder/)

---

## Fehlerbehebung

- Stelle sicher, dass deine Eingabedaten sich im gleichen **CRS** (Koordinatensystem) befinden.
- Überprüfe, ob Abhängigkeiten (z.B. Bibliotheken) korrekt installiert sind.
- Konsultiere die Log-Nachrichten im Message-Fenster des Plugins, um Fehler zu identifizieren.

---

Viel Spaß beim Verwenden des **IBTool**-Plugins!