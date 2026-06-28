# i18n: German UI + System Messages — Design Spec

**Date:** 2026-06-28  
**Branch:** ADD_german_ui  
**Status:** Approved

---

## Goal

Add a complete German translation for the IBTool QGIS plugin using the standard Qt Linguist workflow already scaffolded in the repo. When a user's QGIS locale is set to German (`de`), all UI labels, buttons, file-dialog titles, status messages, and validation messages appear in German. English remains the source language in code.

---

## Scope

**Translated (in scope):**
- `.ui` file strings (labels, buttons, group box titles, tooltips, step names)
- `ibtool_dialog.py` Python strings (step labels, checklist results, phase label, FilterPreviewDialog)
- `ibtool.py` Python strings (file-dialog titles, status/result messages, QMessageBox text, config log lines, phase names)
- `helpers/check.py` validation error and warning strings

**Not translated (out of scope):**
- Processing pipeline log lines in `ibtool_tools/*.py` (stay English — easier to debug)
- Code comments and docstrings (always English per project convention)
- `docs/` and `ai/` files (always English per project convention)

---

## Approach: Standard Qt Linguist (multi-context)

- English source strings in code, wrapped in `tr()` / `QCoreApplication.translate()`
- `.ui` file strings handled automatically by Qt — no code change needed
- `i18n/IBTool_de.ts` — complete XML translation file (four contexts)
- `i18n/IBTool_de.qm` — compiled binary (user runs `lrelease` once)
- QGIS reads locale from `QSettings().value('locale/userLocale')` and auto-loads `IBTool_de.qm`

---

## File Changes

| File | Change |
|------|--------|
| `ibtool/ibtool/ibtool.py` | Fix path bug; wrap all user-facing strings in `self.tr()` |
| `ibtool/ibtool/ibtool_dialog.py` | Convert module-level label constants to lazy-translated functions; wrap remaining strings |
| `ibtool/helpers/check.py` | Add module-level `_tr()` helper; wrap all validation message strings |
| `ibtool/ibtool/ibtool_dialog_base.ui` | No change needed |
| `i18n/IBTool_de.ts` | New — complete German translations (replaces near-empty `de.ts`) |
| `i18n/IBTool_de.qm` | Compiled from `IBTool_de.ts` by user with `lrelease` |
| `i18n/de.ts` | Deleted (replaced) |
| `i18n/de.qm` | Deleted (replaced) |
| `docs/contributing.md` | Add "Updating translations" section |

---

## Path Bug Fix

`ibtool.py __init__` currently looks for the `.qm` inside the nested package dir:

```python
# Wrong: self.plugin_dir == ibtool/ibtool/  →  looks in ibtool/ibtool/i18n/
locale_path = os.path.join(self.plugin_dir, 'i18n', f'IBTool_{locale}.qm')
```

Fix — use the already-computed `plugin_root`:

```python
plugin_root = os.path.dirname(self.plugin_dir)  # already computed above
locale_path = os.path.join(plugin_root, 'i18n', f'IBTool_{locale}.qm')
```

---

## String Wrapping Strategy

### `ibtool.py` — `self.tr()` (context: `IBTool`)

All user-visible strings wrapped with the existing `self.tr()` method.  
Strings currently in German in the source (e.g. `"Konfiguration aus CONFIG.ini geladen."`) are
first standardised to English, then translated in `.ts`.

### `ibtool_dialog.py` — lazy translated functions (context: `IBToolDialog`)

Module-level constants `_STEP_LABELS` and `_STEP_SHORT` cannot be translated at import time
(translator not yet installed). Replace with lazy functions:

```python
def _step_labels():
    tr = lambda s: QCoreApplication.translate('IBToolDialog', s)
    return [tr("① Input"), tr("② Parameters"), tr("③ Validation"), tr("④ Processing")]

def _step_short():
    tr = lambda s: QCoreApplication.translate('IBToolDialog', s)
    return [tr("Input"), tr("Parameters"), tr("Validation"), tr("Processing")]
```

Called each time `set_step()` runs so translation is resolved at display time.

All other strings in the file (`"✅  All checks passed"`, `"Filter entries"`, etc.) wrapped with
`QCoreApplication.translate('IBToolDialog', ...)`.

### `helpers/check.py` — module-level `_tr()` (context: `InputValidator`)

```python
from qgis.PyQt.QtCore import QCoreApplication

def _tr(text: str) -> str:
    return QCoreApplication.translate('InputValidator', text)
```

Every `add_error(...)`, `add_warning(...)`, and `return False, "..."` call uses `_tr(...)`.

### `.ui` file — no changes

Qt translates `<string>` elements automatically via `QCoreApplication.translate('IBToolDialogBase', ...)`.
The translator must be installed before `IBToolDialog()` is first instantiated (already the case —
translator is loaded in `IBTool.__init__` before `self.dlg = IBToolDialog()`).

---

## Translation File: `i18n/IBTool_de.ts`

Four `<context>` blocks.

### Context: `IBToolDialogBase` (from `.ui`)

| Source | German |
|--------|--------|
| ① Input | ① Eingabe |
| ② Parameters | ② Parameter |
| ③ Validation | ③ Validierung |
| ④ Processing | ④ Verarbeitung |
| Input Data | Eingabedaten |
| Building Footprints * | Gebäudegrundrisse * |
| Road Network * | Straßennetz * |
| Partitions * | Partitionen * |
| Auxiliary Data | Hilfsdaten |
| Output File * | Ausgabedatei * |
| Workspace * | Arbeitsverzeichnis * |
| Filter TXT (optional) | Filter TXT (optional) |
| Log Directory | Log-Verzeichnis |
| Spatial Reference | Koordinatenreferenzsystem |
| Show Filter Entries... | Filtereinträge anzeigen... |
| Settlement Analysis | Siedlungsanalyse |
| Min. Block Overlap (%) | Min. Blocküberlappung (%) |
| Global Footprint Density (%) | Globale Grundrissdichte (%) |
| Min. Building Area (sqm) | Min. Gebäudefläche (m²) |
| Min. Building Count | Min. Gebäudeanzahl |
| Min. Patch Size (sqm) | Min. Patchgröße (m²) |
| Max. Hole Size (sqm) | Max. Lochgröße (m²) |
| Max. Gap Size (sqm) | Max. Lückengröße (m²) |
| Validation Checklist | Validierungsliste |
| (no validation run yet) | (noch keine Validierung durchgeführt) |
| Debugging | Fehlersuche |
| Partition Start (default -1) | Partitionsstart (Standard -1) |
| Partition End (default -1) | Partitionsende (Standard -1) |
| Partition List (default #) | Partitionsliste (Standard #) |
| Log Level | Logbuch-Stufe |
| Delete PartLog at Start | PartLog beim Start löschen |
| Save Faulty Features (Debug Mode) | Fehlerhafte Objekte speichern (Debug-Modus) |
| Ready | Bereit |
| Copy Log | Log kopieren |
| Load Result | Ergebnis laden |
| Open Directory | Verzeichnis öffnen |
| Export Log | Log exportieren |
| Save Config | Konfiguration speichern |
| Reset Config | Konfiguration zurücksetzen |
| Delete CONFIG.ini and reset all fields to defaults | CONFIG.ini löschen und alle Felder zurücksetzen |
| ← Back | ← Zurück |
| Next → | Weiter → |
| Check | Prüfen |
| Start | Start |
| Cancel | Abbrechen |
| Minimum percentage overlap of inner blocks (0–100). Recommended: 15–25 | Mindestüberlappung der inneren Blöcke (0–100). Empfehlung: 15–25 |
| Global building footprint density in %. Value 0 = calculate automatically. | Globale Grundrissdichte in %. Wert 0 = automatisch berechnen. |
| Minimum building footprint area in sqm. Smaller buildings are ignored. Recommended: 50–100 sqm | Mindestfläche der Gebäudegrundrisse in m². Kleinere Gebäude werden ignoriert. Empfehlung: 50–100 m² |
| Minimum number of buildings to form a settlement area. Recommended: 10–30 | Mindestanzahl Gebäude für eine Siedlungsfläche. Empfehlung: 10–30 |
| Minimum size of an inner area patch in sqm. Recommended: 5000–20000 sqm | Mindestgröße einer Innenfläche in m². Empfehlung: 5000–20000 m² |
| Maximum size of holes in sqm that are automatically closed. Recommended: 5000–20000 sqm | Maximale Lochgröße in m², die automatisch geschlossen wird. Empfehlung: 5000–20000 m² |
| Maximum size of gaps in sqm that are closed. Recommended: 2000–10000 sqm | Maximale Lückengröße in m², die geschlossen wird. Empfehlung: 2000–10000 m² |

### Context: `IBTool` (from `ibtool.py`)

| Source | German |
|--------|--------|
| &IB-Tool | &IB-Tool |
| IB-Tool | IB-Tool |
| Select building footprints file | Gebäudegrundrisse auswählen |
| Select road network file | Straßennetzlayer auswählen |
| Select partitions file | Partitionslayer auswählen |
| Select auxiliary data file | Hilfsdatenlayer auswählen |
| Select output file | Ausgabedatei auswählen |
| Select workspace folder | Arbeitsverzeichnis auswählen |
| Select filter config file | Filterkonfigurationsdatei auswählen |
| Select log directory | Log-Verzeichnis auswählen |
| Vector files (*.shp *.gpkg);;Shapefiles (*.shp);;GeoPackage (*.gpkg);;All Files (*) | Vektordateien (*.shp *.gpkg);;Shapefiles (*.shp);;GeoPackage (*.gpkg);;Alle Dateien (*) |
| GeoPackage (*.gpkg);;All Files (*) | GeoPackage (*.gpkg);;Alle Dateien (*) |
| Text files (*.txt);;All Files (*) | Textdateien (*.txt);;Alle Dateien (*) |
| Starting processing... | Verarbeitung wird gestartet... |
| Processing complete | Verarbeitung abgeschlossen |
| Reset Configuration | Konfiguration zurücksetzen |
| Delete CONFIG.ini and reset all fields to defaults?\nThis action cannot be undone. | CONFIG.ini löschen und alle Felder zurücksetzen?\nDiese Aktion kann nicht rückgängig gemacht werden. |
| Configuration loaded from CONFIG.ini. | Konfiguration aus CONFIG.ini geladen. |
| Configuration saved to CONFIG.ini. | Konfiguration in CONFIG.ini gespeichert. |
| Configuration reset — CONFIG.ini deleted. | Konfiguration zurückgesetzt — CONFIG.ini gelöscht. |
| Processing aborted due to validation errors. | Verarbeitung wegen Validierungsfehlern abgebrochen. |
| Output file not found. | Ausgabedatei nicht gefunden. |
| Output directory not found. | Ausgabeverzeichnis nicht gefunden. |
| No log content to export. | Kein Log-Inhalt zum Exportieren. |
| Export log | Log exportieren |
| IB-Tool result | IB-Tool Ergebnis |
| Processing cannot be cancelled mid-run. | Verarbeitung kann nicht während des Laufs abgebrochen werden. |
| Load Data | Daten laden |
| Calculate Blocks | Blöcke berechnen |
| Apply Filter | Filter anwenden |
| Calculate MST | MST berechnen |
| Clustering | Clustering |
| Erode Empty Areas | Leerflächen erodieren |
| Save Output | Ausgabe speichern |

### Context: `IBToolDialog` (from `ibtool_dialog.py`)

| Source | German |
|--------|--------|
| ① Input | ① Eingabe |
| ② Parameters | ② Parameter |
| ③ Validation | ③ Validierung |
| ④ Processing | ④ Verarbeitung |
| Input | Eingabe |
| Parameters | Parameter |
| Validation | Validierung |
| Processing | Verarbeitung |
| ✅  All checks passed | ✅  Alle Prüfungen bestanden |
| Filter entries | Filtereinträge |
| Positive filter | Positiver Filter |
| Negative filter | Negativer Filter |

### Context: `InputValidator` (from `helpers/check.py`)

| Source | German |
|--------|--------|
| No path specified | Kein Pfad angegeben |
| File or directory does not exist | Datei oder Verzeichnis existiert nicht |
| Not a directory | Kein Verzeichnis |
| Building footprints (HU) | Gebäudegrundrisse (HU) |
| Road network (RN) | Straßennetz (RN) |
| Partitioning (Part) | Partitionen (Part) |
| Auxiliary layer (Aux) | Hilfslayer (Aux) |

Note: `check.py` validation messages use f-strings with dynamic data (layer names, counts, paths).
These are translated as templates; dynamic values remain in Python. Full inventory extracted
during implementation.

---

## Documentation Update: `docs/contributing.md`

Add section **"Updating translations"** covering:

1. **When to update** — any time a user-facing string changes in `ibtool.py`, `ibtool_dialog.py`,
   `check.py`, or `ibtool_dialog_base.ui`, the corresponding `<translation>` element in
   `i18n/IBTool_de.ts` must be updated.

2. **Compile after editing**:
   ```bash
   lrelease i18n/IBTool_de.ts -qm i18n/IBTool_de.qm
   # Windows (QGIS):
   # "C:\Program Files\QGIS 3.x\bin\lrelease.exe" i18n/IBTool_de.ts
   ```

3. **Extract new strings** (optional):
   ```bash
   pylupdate5 ibtool/ibtool/ibtool.py ibtool/ibtool/ibtool_dialog.py \
     ibtool/helpers/check.py ibtool/ibtool/ibtool_dialog_base.ui \
     -ts i18n/IBTool_de.ts
   ```

4. **Adding a new language** — copy `IBTool_de.ts` to `IBTool_<locale>.ts`, fill in
   `<translation>` elements, compile with `lrelease`. No Python changes needed.

---

## Compile Instructions (for user)

After implementation, run once:

```bash
"C:\Program Files\QGIS 3.x\bin\lrelease.exe" i18n/IBTool_de.ts -qm i18n/IBTool_de.qm
```

Reload the plugin in QGIS with German locale active to verify.
