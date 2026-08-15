# Data Preparation Tutorial

This tutorial explains how to turn downloaded ATKIS raw data into the
**HU** (Building Footprints), **RN** (Road Network), and **Aux**
(Auxiliary Layer) inputs required by IBTool. It does not cover:

- The **Part** (Partitioning) layer — produced by the companion plugin
  **[IB-Tool (Partitioning)](https://github.com/IB-Tool/ibtoolpartion)**.
- The **Filter File** — a separately maintained, largely static file (see
  [input-data.md → Filter File](input-data.md#filter-file) for its format).

For the exact target specification (field requirements, geometry types,
minimum feature counts) that the layers produced here must satisfy, see
[input-data.md](input-data.md). For portal links, download formats, and
dataset names for a specific German state, see
[data-sources.md](data-sources.md).

> **You probably do not need to do this by hand.** The companion plugin
> **[Data Wizard](https://github.com/IB-Tool/data_wizard)** automates the
> whole workflow below — CRS handling, study-area clipping, and the
> mapping into `HU.gpkg` / `RN.gpkg` / `AUX_L.gpkg`.
>
> This tutorial remains the reference for what Data Wizard does under the
> hood: read it to understand or verify the plugin's output, to work with
> data it cannot handle, or to do the conversion in another tool.

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

Draw the polygon(s) **larger than the actual area of interest** — the
clipping step below cuts exactly to this polygon, so a tight boundary
would introduce edge effects at the border (e.g. buildings or road
segments cut off mid-feature right where they matter for later
processing).

---

## 4. Clipping

Clip each downloaded raw layer to the study area polygon(s) from Step 3
(QGIS: **Vector → Geoprocessing Tools → Clip**, or
`native:clip` in the Processing Toolbox) — an exact clip to the polygon
boundary, no additional buffer at this stage, since the polygon itself was
already drawn larger than the actual area of interest. If multiple study
area polygons exist, dissolve them into a single clipping mask first
(**Vector → Geoprocessing Tools → Dissolve**) so the clip runs once per
raw layer.

---

## 5. Mapping & Merging into HU / RN / Aux

Each target layer is assembled from the clipped ATKIS/ALKIS source layers
by a fixed rule:

| Target Layer | Source layers | Merge rule |
|---|---|---|
| HU | ALKIS **Gebäude** / **Hausumringe** (buildings) | No merge needed — a single source layer. After clipping, check that it contains the required function-code column (`fkt`, `gfkzshh`, or `funktion`). |
| RN | `ver01_l.shp`, `ver02_l.shp` | Simple merge of both files (QGIS: **Vector → Data Management Tools → Merge Vector Layers**, `native:mergevectorlayers`) — no filtering. |
| Aux | `ver03_l.shp` (railway lines), `veg02_f.shp` (forest), `veg03_f.shp` (woody vegetation/shrubs), marsh/bog features (if available), `gew01_f.shp` (water bodies) | See step-by-step below — several polygon layers must be converted to lines before the final merge. |

### Assembling Aux

`ver03_l.shp` is already a line layer and needs no conversion. The
remaining sources are polygons and are merged, dissolved, and converted to
lines as a batch, then combined with `ver03_l.shp`:

1. Merge the polygon sources — `veg02_f.shp` (forest), `veg03_f.shp`
   (woody vegetation/shrubs), marsh/bog ("Sumpf", "Moor") features (if
   available in the raw data), and `gew01_f.shp` (water bodies) — into one
   polygon layer (**Vector → Data Management Tools → Merge Vector
   Layers**, `native:mergevectorlayers`).
2. Dissolve the merged polygon layer (**Vector → Geoprocessing Tools →
   Dissolve**, `native:dissolve`).
3. Convert the dissolved polygon boundary to lines (**Vector → Geometry
   Tools → Polygons to Lines**, `native:polygonstolines`).
4. Merge the resulting line layer with `ver03_l.shp` into the final Aux
   layer (**Vector → Data Management Tools → Merge Vector Layers**).

---

## 6. Attribute Check & Set

After mapping and merging, verify the resulting layers satisfy
[input-data.md](input-data.md)'s field requirements:

- **HU**: the ALKIS building source already carries the function-code
  field (`fkt`, `gfkzshh`, or `funktion`) — this only needs to be
  **checked**, not set. Confirm the field made it through clipping (open
  the attribute table and check the column is present and populated).
- **RN** and **Aux**: must not contain multipart geometries — dissolve
  with **Vector → Geometry Tools → Multipart to Singleparts**
  (`native:multiparttosingleparts`) if the merge in Step 5 produced any.

---

## 7. Export

Export HU, RN, and Aux each as their own **GeoPackage** (`.gpkg`) — always
GeoPackage, not Shapefile, for this workflow. Use **Export → Save
Features As…** in QGIS, format **GeoPackage**, and confirm the CRS matches
the project CRS from Step 2.

File names are freely chosen — they are selected explicitly in the IBTool
dialog, so no fixed naming convention is required. Keep names QGIS/Python
compatible: avoid spaces and special characters (use plain ASCII letters,
digits, `_`/`-`) that could cause problems when the file is referenced by
path later.

---

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
