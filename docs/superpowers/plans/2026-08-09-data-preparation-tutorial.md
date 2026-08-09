# Data Preparation Tutorial Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended for this plan — most tasks require live interactive input from the user, which does not fit the subagent-driven-development model) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `docs/data-preparation.md` (generic ATKIS-to-HU/RN/Aux workflow tutorial) and `docs/data-sources.md` (per-state source reference: Brandenburg, Sachsen, Sachsen-Anhalt, Berlin), cross-linked from `README.md` and `docs/input-data.md`.

**Architecture:** Two new Markdown files in `docs/`, written section by section. Sections with generic QGIS/GIS content are written directly from established project conventions (matching `docs/quickstart.md` / `docs/input-data.md` style). Sections requiring ATKIS/state-specific facts are filled from information the user supplies live during the task — never fabricated. See `docs/superpowers/specs/2026-08-09-data-preparation-tutorial-design.md` for the full design rationale.

**Tech Stack:** Markdown only, no code changes.

---

### Task 1: Scaffold `docs/data-preparation.md` with Overview

**Files:**
- Create: `docs/data-preparation.md`

- [ ] **Step 1: Create the file with title and Overview section**

```markdown
# Data Preparation Tutorial

This tutorial explains how to turn downloaded ATKIS raw data into the
**HU** (Building Footprints), **RN** (Road Network), and **Aux**
(Auxiliary Layer) inputs required by IBTool. It does not cover:

- The **Part** (Partitioning) layer — produced by a separate, dedicated
  tool.
- The **Filter File** — a separately maintained, largely static file (see
  [input-data.md → Filter File](input-data.md#filter-file) for its format).

For the exact target specification (field requirements, geometry types,
minimum feature counts) that the layers produced here must satisfy, see
[input-data.md](input-data.md). For portal links, download formats, and
dataset names for a specific German state, see
[data-sources.md](data-sources.md).

> This tutorial documents the current manual workflow. It is also intended
> as the basis for a future dedicated tool that automates these steps —
> that tool is a separate, later project.

## Workflow Overview

1. [Obtaining Raw Data](#1-obtaining-raw-data)
2. [Determining the Project CRS](#2-determining-the-project-crs)
3. [Defining the Study Area](#3-defining-the-study-area)
4. [Clipping](#4-clipping)
5. [Mapping & Merging into HU / RN / Aux](#5-mapping--merging-into-hu--rn--aux)
6. [Attribute Check & Set](#6-attribute-check--set)
7. [Export](#7-export)
8. [Validation](#8-validation)

---
```

- [ ] **Step 2: Confirm the Overview reads correctly**

Read the file back and check the section anchors (`#1-obtaining-raw-data`
etc.) match GitHub's auto-generated heading-to-anchor slugs for the
headings that will be added in later tasks (lowercase, spaces → hyphens,
`&` dropped, numbers kept). Fix now if a later task's heading text would
produce a different slug.

- [ ] **Step 3: Commit**

```bash
git add docs/data-preparation.md
git commit -m "docs: scaffold data-preparation.md with overview"
```

---

### Task 2: Scaffold `docs/data-sources.md` with per-state skeletons

**Files:**
- Create: `docs/data-sources.md`

- [ ] **Step 1: Create the file with title, intro, and one skeleton section per state**

```markdown
# Data Sources — ATKIS Raw Data by State

Reference for downloading ATKIS Basis-DLM raw data per German state. The
object-art schema (ATKIS/AAA catalog) is nationally standardized — only
the download portal, file format, and dataset/layer naming differ between
states. The shared mapping rules from raw ATKIS object classes into
IBTool's HU/RN/Aux layers are documented once, in
[data-preparation.md → Mapping & Merging](data-preparation.md#5-mapping--merging-into-hu--rn--aux) —
not repeated per state here.

Currently documented: Brandenburg, Sachsen, Sachsen-Anhalt, Berlin.

---

## Brandenburg

| Property | Value |
|---|---|
| Portal | |
| URL | |
| Download format | |
| Required datasets / layers | |
| Notes | |

---

## Sachsen

| Property | Value |
|---|---|
| Portal | |
| URL | |
| Download format | |
| Required datasets / layers | |
| Notes | |

---

## Sachsen-Anhalt

| Property | Value |
|---|---|
| Portal | |
| URL | |
| Download format | |
| Required datasets / layers | |
| Notes | |

---

## Berlin

| Property | Value |
|---|---|
| Portal | |
| URL | |
| Download format | |
| Required datasets / layers | |
| Notes | |
```

- [ ] **Step 2: Commit**

```bash
git add docs/data-sources.md
git commit -m "docs: scaffold data-sources.md with per-state tables"
```

---

### Task 3: Fill Brandenburg source table

**Files:**
- Modify: `docs/data-sources.md` (Brandenburg section)

- [ ] **Step 1: Ask the user for Brandenburg facts**

Ask exactly: "Für Brandenburg: Wie heißt das Portal, wie lautet die URL,
welches Downloadformat liefert es, welche Datensatz-/Layernamen werden
benötigt, und gibt es Besonderheiten/Fallstricke?"

- [ ] **Step 2: Fill the Brandenburg table with the answer, verbatim facts only**

No invented values — every cell comes from the user's answer. If the user
has no answer for a cell (e.g. no known quirks), leave it as `—` rather
than guessing.

- [ ] **Step 3: Commit**

```bash
git add docs/data-sources.md
git commit -m "docs: add Brandenburg ATKIS source details"
```

---

### Task 4: Fill Sachsen source table

**Files:**
- Modify: `docs/data-sources.md` (Sachsen section)

- [ ] **Step 1: Ask the user for Sachsen facts**

Same question as Task 3, for Sachsen.

- [ ] **Step 2: Fill the Sachsen table**

- [ ] **Step 3: Commit**

```bash
git add docs/data-sources.md
git commit -m "docs: add Sachsen ATKIS source details"
```

---

### Task 5: Fill Sachsen-Anhalt source table

**Files:**
- Modify: `docs/data-sources.md` (Sachsen-Anhalt section)

- [ ] **Step 1: Ask the user for Sachsen-Anhalt facts**

Same question as Task 3, for Sachsen-Anhalt.

- [ ] **Step 2: Fill the Sachsen-Anhalt table**

- [ ] **Step 3: Commit**

```bash
git add docs/data-sources.md
git commit -m "docs: add Sachsen-Anhalt ATKIS source details"
```

---

### Task 6: Fill Berlin source table

**Files:**
- Modify: `docs/data-sources.md` (Berlin section)

- [ ] **Step 1: Ask the user for Berlin facts**

Same question as Task 3, for Berlin.

- [ ] **Step 2: Fill the Berlin table**

- [ ] **Step 3: Commit**

```bash
git add docs/data-sources.md
git commit -m "docs: add Berlin ATKIS source details"
```

---

### Task 7: Write "Obtaining Raw Data" section

**Files:**
- Modify: `docs/data-preparation.md` (append after Overview)

- [ ] **Step 1: Write the section**

```markdown
## 1. Obtaining Raw Data

Download the ATKIS Basis-DLM raw data for your state from its official
geoportal. Portal links, download formats, and required dataset/layer
names per state are listed in [data-sources.md](data-sources.md).

- Check the license/attribution terms of the portal before redistributing
  any derived data (see `Testdaten/LICENSE.txt` for an example license
  note used in this project's own sample data, sourced from
  GeoBasis-DE/LGB).
- Keep the raw download unmodified in a separate folder — later steps
  (clipping, mapping) should read from it and write new files, so the
  original download can be re-used if a step needs to be repeated.

---
```

- [ ] **Step 2: Commit**

```bash
git add docs/data-preparation.md
git commit -m "docs: add Obtaining Raw Data section"
```

---

### Task 8: Write "Determining the Project CRS" section

**Files:**
- Modify: `docs/data-preparation.md` (append)

- [ ] **Step 1: Write the section**

```markdown
## 2. Determining the Project CRS

Before creating anything else, check which Coordinate Reference System
(CRS) the downloaded raw data uses (in QGIS: right-click the layer →
**Properties** → **Information**, or check the **CRS** field in the
**Layers** panel). Treat this CRS as **binding for the entire project** —
every layer created in the steps below, including the study area polygon
in the next step, must use this same CRS.

> IBTool's own default CRS is ETRS89 / UTM zone 33N (EPSG:25833), matching
> the sample data in `Testdaten/`. This is a project default, not a hard
> requirement — set the plugin's CRS field to whatever CRS your raw data
> actually uses.

If a raw layer is in a different CRS than the others (e.g. the road
network in a different CRS than the building footprints), reproject it to
the chosen project CRS before continuing (QGIS: **Vector → Data
Management Tools → Reproject Layer**).

---
```

- [ ] **Step 2: Commit**

```bash
git add docs/data-preparation.md
git commit -m "docs: add Determining the Project CRS section"
```

---

### Task 9: Write "Defining the Study Area" section

**Files:**
- Modify: `docs/data-preparation.md` (append)

- [ ] **Step 1: Write the section**

```markdown
## 3. Defining the Study Area

Create one or more polygons that outline the area to be processed, in the
project CRS determined in the previous step. A single polygon is the
common case; multiple polygons are supported for study areas made up of
disjoint regions (e.g. several separate towns) — later steps treat them as
one combined clipping mask.

In QGIS: create a new GeoPackage polygon layer (**Layer → Create Layer →
New GeoPackage Layer…**, set the CRS to the project CRS from Step 2), then
digitize the study area boundary, or import an existing boundary (e.g. an
administrative boundary) and reproject it to the project CRS if needed.

---
```

- [ ] **Step 2: Commit**

```bash
git add docs/data-preparation.md
git commit -m "docs: add Defining the Study Area section"
```

---

### Task 10: Write "Clipping" section

**Files:**
- Modify: `docs/data-preparation.md` (append)

- [ ] **Step 1: Ask the user whether a buffer around the study area is needed before clipping**

Ask exactly: "Beim Zuschnitt: schneidest du die Rohdaten exakt auf die
Untersuchungsgebiets-Polygone zu, oder pufferst du das Gebiet vorher (z.B.
um Randeffekte an MST/Blöcken zu vermeiden)? Falls ja, um wie viel?"

- [ ] **Step 2: Write the section using the answer**

```markdown
## 4. Clipping

Clip each downloaded raw layer to the study area polygon(s) from Step 3
(QGIS: **Vector → Geoprocessing Tools → Clip**, or
`native:clip` in the Processing Toolbox). If multiple study area polygons
exist, dissolve them into a single clipping mask first (**Vector →
Geoprocessing Tools → Dissolve**) so the clip runs once per raw layer.

<!-- Insert here, verbatim from the user's answer: whether/how much to
     buffer the study area before clipping, and why. -->

---
```

- [ ] **Step 3: Commit**

```bash
git add docs/data-preparation.md
git commit -m "docs: add Clipping section"
```

---

### Task 11: Write "Mapping & Merging into HU / RN / Aux" section

**Files:**
- Modify: `docs/data-preparation.md` (append)

This is the core, most detail-heavy section — take it slowly and confirm
each target layer's row before moving to the next.

- [ ] **Step 1: Ask the user for the HU mapping rule**

Ask exactly: "Welche ATKIS-Objektarten/-Layer fließen in HU (Building
Footprints), und nach welcher Regel werden sie zusammengeführt (z.B.
einfacher Merge mehrerer Quelllayer, oder gibt es eine Filterung/Auswahl
schon auf dieser Stufe)?"

- [ ] **Step 2: Ask the user for the RN mapping rule**

Ask exactly: "Welche ATKIS-Objektarten/-Layer fließen in RN (Road
Network), und nach welcher Regel werden sie zusammengeführt?"

- [ ] **Step 3: Ask the user for the Aux mapping rule**

Ask exactly: "Welche ATKIS-Objektarten/-Layer fließen in Aux (Auxiliary
Layer), und nach welcher Regel werden sie zusammengeführt?"

- [ ] **Step 4: Write the section**

```markdown
## 5. Mapping & Merging into HU / RN / Aux

Each target layer is assembled from one or more ATKIS source layers by a
fixed rule:

| Target Layer | ATKIS Object Classes (source layers) | Merge Rule | Notes |
|---|---|---|---|
| HU | <!-- from Step 1 --> | <!-- from Step 1 --> | |
| RN | <!-- from Step 2 --> | <!-- from Step 2 --> | |
| Aux | <!-- from Step 3 --> | <!-- from Step 3 --> | |

In QGIS, combine multiple source layers into one target layer with
**Vector → Data Management Tools → Merge Vector Layers**
(`native:mergevectorlayers`), then save the result as its own GeoPackage
layer.

---
```

Fill the table cells with the user's verbatim answers — do not invent
ATKIS object-art names or codes.

- [ ] **Step 5: Commit**

```bash
git add docs/data-preparation.md
git commit -m "docs: add Mapping & Merging section"
```

---

### Task 12: Write "Attribute Check & Set" section

**Files:**
- Modify: `docs/data-preparation.md` (append)

- [ ] **Step 1: Ask the user if any attribute needs to be computed/set (not just checked)**

Ask exactly: "Beim Schritt 'Attribute prüfen bzw. setzen': gibt es Fälle,
in denen `fkt`/`gfkzshh`/`funktion` in den ATKIS-Rohdaten fehlt und aktiv
gesetzt werden muss (und wie), oder ist es nach dem Merge in Schritt 5
immer schon vorhanden?"

- [ ] **Step 2: Write the section using the answer**

```markdown
## 6. Attribute Check & Set

After mapping and merging, verify the resulting layers satisfy
[input-data.md](input-data.md)'s field requirements:

- **HU** must have one of `fkt`, `gfkzshh`, or `funktion`, holding the
  ATKIS building function code.
- **RN** and **Aux** must not contain multipart geometries — dissolve with
  **Vector → Geometry Tools → Multipart to Singleparts**
  (`native:multiparttosingleparts`) if the merge in Step 5 produced any.

<!-- Insert here, verbatim from the user's answer: whether/how the
     function-code field needs to be actively set rather than just
     checked. -->

---
```

- [ ] **Step 3: Commit**

```bash
git add docs/data-preparation.md
git commit -m "docs: add Attribute Check & Set section"
```

---

### Task 13: Write "Export" section

**Files:**
- Modify: `docs/data-preparation.md` (append)

- [ ] **Step 1: Ask the user for the file naming convention, if any**

Ask exactly: "Beim Export: verwendest du eine feste Namenskonvention für
die GPKG-Dateien (z.B. Präfix, Gebietscode), oder ist der Name frei
wählbar?"

- [ ] **Step 2: Write the section using the answer**

```markdown
## 7. Export

Export HU, RN, and Aux each as their own **GeoPackage** (`.gpkg`) — always
GeoPackage, not Shapefile, for this workflow. Use **Export → Save
Features As…** in QGIS, format **GeoPackage**, and confirm the CRS matches
the project CRS from Step 2.

<!-- Insert here, verbatim from the user's answer: naming convention, or
     state that the name is freely chosen if the user said so. -->

---
```

- [ ] **Step 3: Commit**

```bash
git add docs/data-preparation.md
git commit -m "docs: add Export section"
```

---

### Task 14: Write "Validation" section

**Files:**
- Modify: `docs/data-preparation.md` (append)

- [ ] **Step 1: Write the section**

```markdown
## 8. Validation

Before using the exported layers in IBTool, check them against the full
validation checklist in
[input-data.md → Validation Checks](input-data.md#validation-checks):
geometry types, minimum feature counts, required fields, and CRS
consistency across HU/RN/Part/Aux.

The final, authoritative check happens inside the plugin itself: load all
five inputs into IBTool and click **Check** (see
[quickstart.md → Step 3 — Validation](quickstart.md#step-3--validation)).
Errors (red ❌) must be resolved before a run can start; warnings (yellow
⚠️) are informational.

---

## Related Files

| File | Content |
|------|---------|
| [`docs/input-data.md`](input-data.md) | Target layer specification and full validation checklist |
| [`docs/data-sources.md`](data-sources.md) | Per-state ATKIS portal, format, and dataset names |
| [`docs/quickstart.md`](quickstart.md) | First run in IBTool once the input layers are ready |
```

- [ ] **Step 2: Commit**

```bash
git add docs/data-preparation.md
git commit -m "docs: add Validation and Related Files sections"
```

---

### Task 15: Cross-link from README.md and input-data.md

**Files:**
- Modify: `README.md` (Input Data section, around line 169-176)
- Modify: `docs/input-data.md` (Related Files table, around line 164-171)

- [ ] **Step 1: Add a line to `README.md`'s Input Data section**

In `README.md`, after the existing sentence "A ready-to-use sample dataset
is included in the `Testdaten/` folder — see..." add:

```markdown
Don't have HU/RN/Aux data yet? See
**[docs/data-preparation.md](docs/data-preparation.md)** for a tutorial on
producing them from official ATKIS raw data.
```

- [ ] **Step 2: Add a row to `docs/input-data.md`'s Related Files table**

In `docs/input-data.md`, add a row to the "Related Files" table (before
the `helpers/check.py` row):

```markdown
| [`docs/data-preparation.md`](data-preparation.md) | Tutorial: producing HU/RN/Aux from ATKIS raw data |
| [`docs/data-sources.md`](data-sources.md) | Per-state ATKIS portal, format, and dataset reference |
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/input-data.md
git commit -m "docs: cross-link data-preparation and data-sources tutorials"
```

---

### Task 16: Final review pass

**Files:**
- Review: `docs/data-preparation.md`, `docs/data-sources.md`, `README.md`, `docs/input-data.md`

- [ ] **Step 1: Check every internal Markdown link resolves**

```bash
grep -oE '\]\([a-zA-Z0-9_./#-]+\.md[^)]*\)' docs/data-preparation.md docs/data-sources.md docs/input-data.md README.md
```

For each `path.md` (and `path.md#anchor`) found, confirm the target file
exists at that relative path, and — for anchors — that a heading in the
target produces that exact GitHub slug.

- [ ] **Step 2: Check terminology consistency**

Confirm `docs/data-preparation.md` and `docs/data-sources.md` use exactly
`HU`, `RN`, `Aux` (not `Part`) and `fkt`/`gfkzshh`/`funktion` matching
`docs/input-data.md`'s terms.

- [ ] **Step 3: Confirm no leftover placeholder cells**

```bash
grep -n '<!--' docs/data-preparation.md docs/data-sources.md
```

Expected: no output (all HTML comments from the templates in Tasks 10-13
should have been replaced with real content by then; if any remain,
resolve them with the user before proceeding).

- [ ] **Step 4: Confirm English throughout**

Read both new files fully; every sentence must be English per the
project's documentation-language convention (`CLAUDE.md`).

- [ ] **Step 5: Commit any fixes**

```bash
git add docs/data-preparation.md docs/data-sources.md README.md docs/input-data.md
git commit -m "docs: fix links and terminology in data preparation tutorial"
```

(Skip this step if Steps 1-4 found nothing to fix.)
