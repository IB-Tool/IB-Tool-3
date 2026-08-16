# IB-Tool 3 — Quickstart Guide

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

**scipy** and **networkx** are not always bundled with QGIS — some
installations (e.g. the standalone QGIS installer with an optional full
Python stack) already include them, in which case no action is needed. If
IB-Tool 3 reports them missing, install them once:

```bash
# Windows — open the OSGeo4W Shell:
pip install scipy networkx

# Linux / macOS — open a terminal where QGIS's Python is active:
pip install scipy networkx
```

**Finding the OSGeo4W Shell on Windows:** Start Menu → **OSGeo4W** →
**OSGeo4W Shell**, or **Start Menu** → **QGIS <version>** → **OSGeo4W
Shell** (the exact folder name depends on the installer used). If it
doesn't appear in the Start Menu, look for `OSGeo4W.bat` in the QGIS
installation directory (typically `C:\OSGeo4W\` or
`C:\Program Files\QGIS <version>\`).

Then restart QGIS. If the packages are still missing after installation,
check that you ran `pip` against QGIS's Python (not a system Python). On
Windows the OSGeo4W Shell sets the correct environment automatically.

> **Tip:** If IB-Tool 3 shows a red message bar immediately after loading,
> it means scipy or networkx are missing. The message contains the exact
> command to fix it.

---

## 2. Installation

1. Download the release ZIP (`IB-Tool-3.zip`) from [GitHub Releases](https://github.com/IB-Tool/IB-Tool-3/releases) — not the "Source code (zip)" link.
2. Open QGIS → **Plugins** → **Manage and Install Plugins…**
3. Click **Install from ZIP**.
4. Select the downloaded ZIP and click **Install Plugin**.
5. Activate the plugin via the checkbox in the **Installed** tab.
6. The IB-Tool icon (house outline) appears in the toolbar.

---

## 3. Input Data

IB-Tool 3 requires five inputs. All layers must share the **same projected CRS**
(plugin default: ETRS89 / UTM zone 33N, EPSG:25833 — matches the sample
dataset below, see [Sample Data](#sample-data)).

| Input | Format | Min features | Key requirement |
|---|---|---|---|
| Building footprints (HU) | `.shp` / `.gpkg` | 50 | Must have `fkt`, `funktion`, or `gfkzshh` field |
| Road network (RN) | `.shp` / `.gpkg` | 30 | Line geometry |
| Partitions | `.shp` / `.gpkg` | 1 | Polygon geometry, defines processing regions |
| Auxiliary network (Aux) | `.shp` / `.gpkg` | 10 | Line geometry |
| Filter file | `.txt` | — | `[positive]` and `[negative]` sections with ATKIS codes |

Full field specifications and filter file format: [input-data.md](input-data.md).

### Sample Data

The repository ships a ready-to-use sample dataset in the `Testdaten/` folder
(project root) so you can try a first run without preparing your own data:

| File | Role |
|---|---|
| `A_HU.shp` | Building footprints (HU) |
| `A_RN.shp` | Road network (RN) |
| `A_PART.shp` | Partitions |
| `A_AUX.shp` | Auxiliary network (Aux) |
| `IB-Tool2_Filter.txt` | Filter file |

All shapefiles in `Testdaten/` use **ETRS89 / UTM zone 33N (EPSG:25833)**,
which matches the plugin's default CRS — no CRS change is needed in the
plugin UI when running with the sample data.

See `Testdaten/LICENSE.txt` for data licensing (GeoBasis-DE/LGB for `A_AUX`,
`A_HU`, `A_RN`; MIT for `A_PART`).

---

## 4. First Run

### Step 1 — Input
Open the plugin. Fill in all path fields using the **…** buttons:
- Building footprints, Road network, Partitions, Auxiliary network
  (use the files from `Testdaten/` for a first trial run, see [Sample Data](#sample-data))
- Output file — must point to a **GeoPackage that already exists as an empty
  file** (see [Creating the output file](#creating-the-output-file) below)
- Workspace folder (holds intermediate files and debug layers)
- Filter file (`.txt`)

Path fields turn green as each file is found.

#### Creating the output file

Before starting a run, create an **empty GeoPackage** for the Output file
field: in the QGIS Browser panel, right-click **GeoPackage** → **New
GeoPackage File…**, choose a location, and give it an **individual,
descriptive name** (e.g. `result_2026-07-01.gpkg`). Select that empty file in
the Output file field — the plugin writes the result into it (overwriting its
contents) when processing finishes.

Avoid a generic name such as `output.gpkg`, especially when testing with the
shared sample data, so that repeated runs or parallel test sessions don't
silently overwrite each other's results.

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
The plugin overwrites the contents of the GeoPackage selected as the Output
file. If you want to keep a previous result, copy it elsewhere first or
create a new, individually named empty GeoPackage for the new run — see
[Creating the output file](#creating-the-output-file).

### Windows paths with spaces
Use the **…** file-dialog buttons instead of typing paths manually.
Paths with spaces in directory names are supported when selected via
the dialog.
