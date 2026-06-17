# IBTool — Quickstart Guide

This guide gets you from a fresh QGIS installation to a completed settlement
delineation run.

---

## 1. System Requirements

| Requirement | Minimum |
|---|---|
| QGIS | 3.40 |
| Python | 3.11 |
| scipy | 1.11+ |
| networkx | 3.0+ |

**numpy** and **PyQt5** are bundled with QGIS 3.40+ — no action needed.

**scipy** and **networkx** are *not* bundled with QGIS. Install them once:

```bash
# Windows — open the OSGeo4W Shell:
pip install scipy networkx

# Linux / macOS — open a terminal where QGIS's Python is active:
pip install scipy networkx
```

Then restart QGIS. If the packages are still missing after installation,
check that you ran `pip` against QGIS's Python (not a system Python). On
Windows the OSGeo4W Shell sets the correct environment automatically.

> **Tip:** If IBTool shows a red message bar immediately after loading,
> it means scipy or networkx are missing. The message contains the exact
> command to fix it.

---

## 2. Installation

1. Download the release ZIP (`IB-Tool_0.2.0.zip`).
2. Open QGIS → **Plugins** → **Manage and Install Plugins…**
3. Click **Install from ZIP**.
4. Select the downloaded ZIP and click **Install Plugin**.
5. Activate the plugin via the checkbox in the **Installed** tab.
6. The IB-Tool icon (house outline) appears in the toolbar.

---

## 3. Input Data

IBTool requires five inputs. All layers must share the **same projected CRS**
(default: ETRS89 / UTM zone 32N, EPSG:25832).

| Input | Format | Min features | Key requirement |
|---|---|---|---|
| Building footprints (HU) | `.shp` / `.gpkg` | 50 | Must have `fkt`, `funktion`, or `gfkzshh` field |
| Road network (RN) | `.shp` / `.gpkg` | 30 | Line geometry |
| Partitions | `.shp` / `.gpkg` | 1 | Polygon geometry, defines processing regions |
| Auxiliary network (Aux) | `.shp` / `.gpkg` | 10 | Line geometry |
| Filter file | `.txt` | — | `[positive]` and `[negative]` sections with ATKIS codes |

Full field specifications and filter file format: [input-data.md](input-data.md).

---

## 4. First Run

### Step 1 — Input
Open the plugin. Fill in all path fields using the **…** buttons:
- Building footprints, Road network, Partitions, Auxiliary network
- Output file (`.gpkg` — will be created or overwritten)
- Workspace folder (holds intermediate files and debug layers)
- Filter file (`.txt`)

Path fields turn green as each file is found.

### Step 2 — Parameters
For a first test run, leave all values at their defaults.

Key parameters if you want to tune them:
| Parameter | Default | Effect |
|---|---|---|
| Max gap size | 4,900 m² | Maximum area of a gap at the settlement edge that is bridged |
| Min patch size | 10,000 m² | Minimum area of a kept settlement patch |
| Min buildings per patch | 20 | Minimum building count per kept patch |

Full parameter descriptions: [parameterization.md](parameterization.md).

### Step 3 — Validation
Click **Check**. The Validation tab shows a checklist:
- ✅ green — check passed
- ❌ red — error that blocks processing; fix before continuing
- ⚠️ yellow — warning; processing can continue

The **Start** button stays grey until all errors are resolved.

### Step 4 — Processing
Click **Start**. The plugin processes each partition in sequence:
- The phase label and progress bar update for each pipeline step.
- Log messages appear in the message box.
- After completion, three buttons appear:
  - **Load result** — add the output GeoPackage to the current QGIS project
  - **Open folder** — open the output directory in the file explorer
  - **Export log** — save the log to a text file

---

## 5. Troubleshooting

### "Required packages not found: scipy, networkx"
Install the missing packages and restart QGIS — see
[System Requirements](#1-system-requirements).

### Check button stays red / Start button stays grey
Read the validation checklist in Step 3. Common causes:

| Error | Fix |
|---|---|
| CRS mismatch | Reproject all input layers to the same CRS |
| Too few features | HU ≥ 50 buildings, RN ≥ 30 segments, Aux ≥ 10 |
| Missing field | Building layer must have `fkt`, `funktion`, or `gfkzshh` |
| Output path not writable | Check folder permissions; avoid read-only drives |

### Processing produces an empty output
- Check that the filter file's `[positive]` section contains codes that
  actually appear in your `fkt` / `funktion` field.
- Enable **Debug mode** (checkbox in the Parameters tab) and re-run.
  Open the workspace folder — numbered GeoPackage snapshots in
  `debug/PART_*/` let you trace exactly where the pipeline diverges.

### Output file already exists
Delete the existing file first, or choose a different output path.
The plugin does not overwrite an existing GeoPackage.

### Windows paths with spaces
Use the **…** file-dialog buttons instead of typing paths manually.
Paths with spaces in directory names are supported when selected via
the dialog.
