# Data Preparation Tutorial — Design Spec

**Date:** 2026-08-09
**Branch:** FIX_plugin_zip

## Context

IBTool requires five input datasets (HU, RN, Part, Aux, Filter file — see
`docs/input-data.md`), but the project has no documentation on how a user
actually *produces* HU, RN, and Aux from real-world raw data. Today this is
a manual, undocumented process the user (project owner, an ATKIS domain
expert) performs by hand from official ATKIS surveying data.

This is the first of two planned documentation additions (the second, an
external-facing usage guide, is a separate future brainstorming). This
tutorial is also intended to later serve as the informal specification for
a **separate future QGIS plugin** that automates the same workflow — that
plugin project is explicitly out of scope for this task; only the tutorial
text is written now.

Goal: produce a detailed, accurate tutorial that a new user can follow to
turn downloaded ATKIS raw data into valid HU/RN/Aux layers, without
guessing or fabricating domain facts.

## Scope

**In scope:**
- `docs/data-preparation.md` — generic, state-independent workflow tutorial
- `docs/data-sources.md` — per-state (Brandenburg, Sachsen, Sachsen-Anhalt,
  Berlin) factual reference: portal, format, dataset/layer names
- Cross-links from `README.md` and `docs/input-data.md`

**Out of scope (explicitly noted in the tutorial itself):**
- The **Part** layer (produced by a separate, existing dedicated tool)
- The **Filter file** (remains a separately maintained, largely static file)
- Building the automation plugin itself (future project)
- Automatic download/WFS integration (future tool will process
  manually-downloaded local files, per user decision)

## Key facts established during brainstorming

- ATKIS Basis-DLM follows the nationwide AAA object-art catalog — the
  object codes/schema are the same across states; **only download format
  and portal differ** per state. This is why the design separates the
  shared mapping rules (one place) from per-state source facts (short
  reference table each).
- Workflow order (user-specified, not the initially assumed order):
  1. Download raw data first
  2. Inspect its CRS and **fix that as the binding project CRS** — the
     study area polygon is created afterwards, in that CRS
  3. Define study area (one or more polygons)
  4. Clip
  5. Map/merge raw layers into HU/RN/Aux by a fixed rule
  6. Check/set required attributes
  7. Export — **always as GeoPackage** (not Shapefile)
  8. Validate against `docs/input-data.md`'s checklist
- All ATKIS-specific facts (portal URLs, object-art names/codes, merge
  rules) are supplied by the user during the writing phase — they must
  not be invented or guessed.

## File Structure

### `docs/data-preparation.md`

1. **Overview** — purpose, explicit exclusion of Part/Filter file, links to
   `input-data.md` (target spec) and `data-sources.md` (per-state facts),
   one-sentence forward reference to the future automation tool
2. **Obtaining Raw Data** — download raw ATKIS data; pointer to
   `data-sources.md` for the user's state; licensing/attribution note
3. **Determining the Project CRS** — inspect the CRS of the downloaded raw
   data and fix it as binding for the whole project
4. **Defining the Study Area** — create one or more selection polygons in
   the project CRS
5. **Clipping** — clip raw layers to the study area
6. **Mapping & Merging → HU / RN / Aux** — the fixed rule: which ATKIS
   object classes go into which target layer, including merging multiple
   source layers into one target layer (core section)
7. **Attribute Check & Set** — ensure `fkt`/`gfkzshh`/`funktion` (HU) is
   present; multipart dissolution for RN/Aux (required per
   `input-data.md`)
8. **Export** — always as GeoPackage; naming convention; CRS consistency
9. **Validation** — check against the `input-data.md` checklist; pointer
   to the IBTool **Check** button as the final gate
10. **Related Files** — cross-references, following existing docs style

### `docs/data-sources.md`

One section per state (Brandenburg, Sachsen, Sachsen-Anhalt, Berlin), each
a short fact table: portal name/link, download format, required
dataset/layer names, state-specific quirks. No repetition of the mapping
rules from `data-preparation.md` — purely source-specific facts.

### Cross-links

- `README.md` docs table: add both new files
- `docs/input-data.md` → "Related Files": add `data-preparation.md`

## Content Authoring Process

Facts (portal URLs, ATKIS object-art names/codes, merge rules,
state-specific quirks) come from the user, not from model knowledge. The
writing phase proceeds section-by-section in the order listed above:
for each section, ask the user for the specific facts needed, then write
the section in the existing docs style (tables, following the pattern of
`docs/input-data.md` and `docs/quickstart.md`). English only, per
`CLAUDE.md` documentation-language rule.

## Verification

No executable behavior — verification is a documentation review pass:
- Terminology matches `docs/input-data.md` (HU/RN/Aux, `fkt`/`gfkzshh`/
  `funktion`)
- All internal links resolve (README ↔ input-data.md ↔
  data-preparation.md ↔ data-sources.md)
- No fabricated domain facts — every state-specific or ATKIS-specific
  claim traces back to something the user supplied
- Written in English (docs-language convention)