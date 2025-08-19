# IBTool CONFIG.ini Dokumentation

## Überblick

Das IBTool Plugin unterstützt jetzt Konfigurationsdateien, um die Benutzerfreundlichkeit zu verbessern und eine schnelle Wiederverwendung von Einstellungen zu ermöglichen.

## Funktionalität

### Automatisches Laden
- Bei jedem Start des Plugins wird nach einer `CONFIG.ini` im Root-Verzeichnis gesucht
- Wenn vorhanden, werden alle konfigurierten Pfade und Parameter automatisch in die GUI geladen
- Fehlende oder ungültige Pfade werden als Warnungen im Log angezeigt

### Unterstützte Konfigurationen

#### INPUT_DATA (Eingabedaten)
```ini
[INPUT_DATA]
building_footprints_path = C:/data/buildings.shp
road_network_path = C:/data/streets.shp
partitions_path = C:/data/partitions.shp
aux_layer_path = C:/data/auxiliary.shp
filter_file_path = C:/data/filter.txt
```

#### PROCESSING (Verarbeitungsparameter)
```ini
[PROCESSING]
road_length_threshold = 50.0        # Schwellwert für kurze Sackgassen (m)
coordinate_tolerance = 0.0001       # Toleranz für Koordinatenvergleiche
buffer_distance = 5.0               # Pufferabstand für Kreuzungen (m)
grid_size = 100.0                   # Rasterzellengröße (m)
min_building_count = 5              # Min. Gebäude pro Rasterzelle
density_threshold = 0.3             # Mindestdichteschwellwert (0.0-1.0)
min_cluster_size = 3                # Min. Gebäude pro Cluster
max_distance = 200.0                # Max. Abstand zwischen Clusterelementen (m)
crs_epsg = 25832                    # EPSG-Code des Koordinatensystems
output_format = gpkg                # Ausgabeformat (gpkg oder shp)
```

#### OUTPUT (Ausgabeeinstellungen)
```ini
[OUTPUT]
workspace_directory = C:/Users/Name/ibtool_workspace
output_prefix = ibtool_result        # Präfix für Ausgabedateien
auto_save = True                     # Automatisches Speichern
add_to_map = True                    # Zu QGIS-Karte hinzufügen
overwrite_existing = False           # Bestehende Dateien überschreiben
```

#### UI (Benutzeroberfläche)
```ini
[UI]
auto_load_last_used = True           # Letzte Konfiguration beim Start laden
show_progress_details = True         # Detaillierte Fortschrittsanzeige
log_level = INFO                     # Log-Level: CRITICAL, WARNING, INFO, SUCCESS
log_directory =                      # Benutzerdefiniertes Log-Verzeichnis
remember_window_size = True          # Fenstergröße merken
```

## Einrichtung

### 1. Beispiel-Konfiguration erstellen
```python
# Im Plugin-Code verfügbar:
self.create_example_config()
```

### 2. Manuelle Erstellung
1. Kopiere `CONFIG.ini.example` nach `CONFIG.ini` im Plugin-Root-Verzeichnis
2. Bearbeite die Pfade entsprechend deiner Datenstruktur
3. Entferne `#` vor den Zeilen, die du aktivieren möchtest

### 3. Pfadnotation
- Verwende vorwärts gerichtete Slashes: `C:/data/file.shp`
- Oder doppelte Backslashes: `C:\\data\\file.shp`
- Vermeide einzelne Backslashes (Escape-Zeichen)

## Verwendung

### Automatisches Laden
Nach der Plugin-Initialisierung:
- CONFIG.ini wird automatisch gelesen (falls vorhanden)
- Pfade werden in entsprechende GUI-Felder geladen
- Parameter werden auf konfigurierte Werte gesetzt
- Log-Nachrichten informieren über geladene/fehlende Konfiguration

### Speichern aktueller Einstellungen
```python
# Speichert aktuellen GUI-Status in CONFIG.ini
self.save_current_config()
```

### Programmatischer Zugriff
```python
# Zugriff auf Konfiguration
config = self.config_manager.get_config()
print(config.processing.road_length_threshold)

# Verarbeitungsparameter für Algorithmen abrufen
params = self.get_processing_config()
```

## Vorteile

### ✅ Zeitersparnis
- Keine wiederholte manuelle Konfiguration
- Sofortige Arbeitsbereitschaft nach Plugin-Start

### ✅ Projektbasierte Konfiguration
- Verschiedene CONFIG.ini für verschiedene Projekte
- Einfacher Wechsel zwischen Projekteinstellungen

### ✅ Teamarbeit
- Standardisierte Konfigurationen im Team teilen
- Einheitliche Parameter für alle Teammitglieder

### ✅ Batch-Verarbeitung
- Vordefinierte Parameter für automatisierte Workflows
- Konsistente Ergebnisse bei wiederholten Analysen

## Beispiel-Workflow

### 1. Erst-Setup
```bash
# Plugin-Verzeichnis
cd C:/Users/.../python/plugins/ibtool/

# Beispiel-Konfiguration kopieren
cp CONFIG.ini.example CONFIG.ini

# Pfade anpassen
notepad CONFIG.ini
```

### 2. Konfiguration anpassen
```ini
[INPUT_DATA]
building_footprints_path = C:/projekt1/buildings.gpkg
road_network_path = C:/projekt1/roads.gpkg
partitions_path = C:/projekt1/zones.gpkg

[OUTPUT]
workspace_directory = C:/projekt1/results
```

### 3. Plugin starten
- QGIS öffnen
- IBTool starten
- Alle Pfade sind bereits konfiguriert
- Direkt mit der Analyse beginnen

## Fehlerbehebung

### CONFIG.ini wird nicht gefunden
- Prüfe, ob sich die Datei im Plugin-Root-Verzeichnis befindet
- Stelle sicher, dass der Dateiname exakt `CONFIG.ini` ist (nicht `.txt` oder andere Erweiterung)

### Pfade werden nicht geladen
- Überprüfe die Pfadnotation (verwende `/` oder `\\`)
- Stelle sicher, dass die Pfade existieren
- Prüfe die Log-Nachrichten für Hinweise

### Konfiguration wird überschrieben
- `CONFIG.ini` wird nur gelesen, nicht automatisch überschrieben
- Verwende `save_current_config()` nur bewusst zum Speichern

## Integration in Workflows

### CI/CD-Pipeline
```bash
# Automatisierte Tests mit vordefinierter Konfiguration
cp config/test_config.ini CONFIG.ini
python -m pytest tests/
```

### Verschiedene Umgebungen
```bash
# Entwicklung
cp configs/dev_config.ini CONFIG.ini

# Produktion  
cp configs/prod_config.ini CONFIG.ini
```

Die CONFIG.ini-Funktionalität macht das IBTool Plugin deutlich benutzerfreundlicher und ermöglicht effiziente, wiederholbare Arbeitsabläufe.