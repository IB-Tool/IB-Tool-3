# Documentation Figures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Most map and screenshot tasks need the user to work live in QGIS — Claude prepares styles, captions and Markdown, the user produces the image. Steps use checkbox (`- [ ]`) syntax for tracking. The plan is designed to be worked through across **multiple sessions**: each session below is self-contained and ends in a consistent state.

**Goal:** Add figures (maps, screenshots, schematic drawings, diagrams) to the user-facing documentation, which currently contains no images at all.

**Architecture:** Images live in `docs/img/<document>/`; Mermaid diagrams are written inline in Markdown (no image file). All maps are produced from the same extent of the `Testdaten/` sample data with one shared QGIS style so figures are comparable. `docs/` is excluded from the release ZIP (`ai/core/release-conventions.md`), so image size does not affect the plugin package.

**Tech Stack:** Markdown, Mermaid, SVG (hand-written or Inkscape), PNG (QGIS print layout / screenshots). No code changes.

---

## Progress Overview

Tick a session when all its tasks are done. Figure IDs (F01–F22) are stable references — use them in commit messages.

- [ ] Session 0 — Setup and conventions
- [ ] Session 1 — Mermaid diagrams (F08, F19, F23–F25) — *Claude alone*
- [ ] Session 2 — Hero image and expected result (F01, F07)
- [ ] Session 3 — Plugin dialog screenshots (F02, F06, F18)
- [ ] Session 4 — QGIS / GitHub screenshots (F03, F04, F05)
- [ ] Session 5 — Pipeline map series (F09)
- [ ] Session 6 — Algorithm schematics (F10a–F10e) — *Claude drafts SVGs*
- [ ] Session 7 — Parameter figures (F12–F15)
- [ ] Session 8 — Input data and data preparation figures (F16, F17, F20, F21)
- [ ] Session 9 — Optional figures (F11, F22) and final review

Recommended order follows priority: 0 → 1 → 2 → 5 → 3 → 4 → 6 → 7 → 8 → 9.

---

## Conventions (apply to every task)

### Formats and sizes

| Figure type | Format | Export size | Display width |
|---|---|---|---|
| UI screenshots (plugin dialog, QGIS menus) | PNG | capture at 100 % scaling, crop to ≤ 1200 px wide, < 300 KB | `width="600"`–`700` |
| Maps / results (QGIS print layout) | PNG (WebP/JPG only with aerial background) | 1600 × 1000 px, < 500 KB | `width="800"` |
| Schematic / algorithm drawings | SVG | viewBox ≈ 800 × 400 | `width="600"`–`800` |
| Flowcharts | Mermaid inline | — | rendered by GitHub |
| Step series | one PNG composed of tiles, 600 × 600 px per tile | e.g. 1800 × 600 (3 tiles) | `width="800"` |

### File naming

`docs/img/<document>/<NN>_<content>.<ext>` — `<document>` is the Markdown file name without extension, `<NN>` a two-digit order number within that document.
Example: `docs/img/how-it-works/05_mst_clustering.png`.

Source files (QGIS project, Inkscape sources, raw screenshots) go to `docs/img/_src/` so figures can be regenerated later.

### Embedding

Use HTML `<img>` (Markdown `![]()` cannot set a width), followed by an italic caption:

```markdown
<p align="center">
  <img src="img/how-it-works/05_mst_clustering.png" width="800"
       alt="Buildings grouped into oriented minimum bounding rectangles along MST subtrees">
</p>

*Figure: MST_Clustering — buildings grouped into oriented MBRs. Data: © GeoBasis-DE/LGB.*
```

Paths are relative to the Markdown file (`img/...` from `docs/`, `docs/img/...` from `README.md`).

### Map style (shared by all map figures)

Colours come from the plugin icon (`icon.png`, `IB-Tool_Icon_2HiRes.png`): teal `#007D85` (the grid = road network), orange `#F7561A` and pink `#FFBCB0` (the letters = Innenbereich), light blue `#74B0C4` (in `icon.png`). Buildings and text use neutral greys, which the icon does not contain.

| Element | Style |
|---|---|
| Buildings (HU) | fill `#3C3C3C`, no stroke |
| Filtered-out buildings | fill `#BDBDBD`, 50 % opacity |
| Roads (RN) | teal `#007D85` line |
| Aux lines | light blue `#74B0C4` line |
| Partition boundary | grey `#616161` dashed, 1 px |
| Innenbereich result | fill pink `#FFBCB0`, stroke orange `#F7561A` 2 px |
| Added area (gap closed, piece snapped) | solid orange `#F7561A` |
| Rejected / removed | dark grey `#3C3C3C` dashed outline, white fill for cut-out areas |
| Accepted step, contact line | teal `#007D85` |
| Background | white (no basemap) |

Every map shows a scale bar, a north arrow (top right, small) and the attribution **© GeoBasis-DE/LGB** (see `Testdaten/LICENSE.txt`).

### Building shapes in schematics

Schematic buildings follow real patterns: individually sized (houses ≈ 9–14 × 7–10 m, occasional barns/workshops ≈ 22–30 × 14–18 m), each slightly rotated (± 5–10°) around the direction of the street they stand on, irregular spacing, no regular grids. Draw buildings and buffers at the same scale.

### SVG rules

- Explicit white background rectangle (otherwise invisible in GitHub dark mode).
- Font: `sans-serif`, ≥ 14 px at display size; text in English.
- Use the same colours as the map style table above.
- No embedded raster images; keep files < 50 KB.
- SVG Tiny features only: no `<pattern>` (hatching), no `<marker>` (arrowheads), no `<clipPath>` — Qt/QGIS do not render them. Use solid fills and draw arrowheads as small polygons.

### Language

Captions, alt texts and all documentation text in **English**. Screenshots show the **English** UI (set QGIS locale to English before capturing) unless the figure explicitly demonstrates the German UI.

---

## Session 0 — Setup and conventions

**Files:**
- Create: `docs/img/` subfolders, `docs/img/_src/`
- Create: `docs/img/_src/figures.qgz` (QGIS project, by the user)

- [ ] **Step 1: Create the folder structure**

```
docs/img/
├── _src/
├── readme/
├── quickstart/
├── how-it-works/
├── parameterization/
├── input-data/
├── data-preparation/
└── terminology/
```

Add a `.gitkeep` to empty folders.

- [ ] **Step 2: Choose the reference extent (user)**

Open all `Testdaten/` layers in QGIS. Pick one extent (≈ 800 × 500 m, scale ≈ 1:5,000–1:10,000) that contains: a dense core, a loose fringe, at least one large isolated building, a visible gap at the fringe and a small splinter settlement. Record the extent coordinates here:

`Reference extent (EPSG:25833): xmin=______ ymin=______ xmax=______ ymax=______`

- [ ] **Step 3: Build the figures project (user, Claude provides QML styles on request)**

Save `docs/img/_src/figures.qgz` with the layers styled per the map style table, plus one print layout `figure_1600x1000` (page size matching 1600 × 1000 px at the chosen DPI, map frame, scale bar, north arrow, attribution label).

- [ ] **Step 4: Run IB-Tool 3 once with Debug Mode enabled (user)**

Use the sample data, all default parameters. Keep `workspace/debug/` — its numbered GeoPackages are the data source for Session 5. Copy the relevant debug GeoPackages for the reference partition into `docs/img/_src/debug/` if they should be kept (check size first; do not commit large files without agreement).

- [ ] **Step 5: Verify**

Folder structure exists; `figures.qgz` opens and shows the reference extent with the shared style.

---

## Session 1 — Mermaid diagrams (Claude alone)

No image files. Verify rendering by pushing the branch and viewing the files on GitHub, or with a Mermaid preview in the IDE.

### Task F08: Processing pipeline flowchart

**Files:** Modify `docs/how-it-works.md` — section "Processing Pipeline"

- [ ] Add a Mermaid `flowchart TD` **above** the existing ASCII tree (keep the tree for plain-text readers):
  - Input data nodes (HU, RN, Aux, Part, Filter file) on the left
  - "Global preparation" subgraph: load layers → merge RN + Aux → global density threshold
  - "Per partition" subgraph with the 10 steps, colour-grouped: preparation (1–3), aggregation (4–6), refinement (7–10)
  - Merge all partitions → output GeoPackage
- [ ] Check step names match the ASCII tree and the README "How It Works" list exactly.

### Task F19: Data preparation workflow

**Files:** Modify `docs/data-preparation.md` — section "Workflow Overview"

- [ ] Add a Mermaid flowchart below the numbered list: ATKIS raw data → clip to study area → three branches:
  - HU: buildings (no merge)
  - RN: `ver01_l` + `ver02_l` → merge
  - Aux: `veg02_f` + `veg03_f` + `gew01_f` (+ marsh/bog) → merge → dissolve → polygons to lines → merge with `ver03_l`
  - all → multipart-to-singlepart check → export GPKG
- [ ] Cross-check each node against sections 4–7 of the same file.

### Task F23: Module structure (developer docs)

**Files:** Modify `docs/plugin-architecture.md` — section "UI / Logic Separation"

- [ ] Mermaid diagram: `IBTool` (ibtool.py) → `IBToolDialog`; `IBTool` → `helpers/*` and `ibtool_tools/*`; `ibtool_tools/*` → `helpers/*`.

### Task F24: CI pipeline (developer docs)

**Files:** Modify `docs/contributing.md` — sections "Workflow 1" / "Workflow 2"

- [ ] Mermaid diagram per workflow reflecting the jobs actually defined in `.github/workflows/ci.yml` and `qgis-plugin-ci.yml` (read the files, do not guess).

### Task F25: Logging destinations (developer docs)

**Files:** Modify `docs/error-handling.md` — section "Output Destinations"

- [ ] Small Mermaid diagram: Logger → dialog log box, log file in `logs/`, QGIS message bar (CRITICAL only). Verify against the text of the section.

- [ ] **Session verification:** all diagrams render on GitHub without syntax errors; no existing text removed.

---

## Session 2 — Hero image and expected result

### Task F01: README hero image

**Files:** Create `docs/img/readme/01_before_after.png`; modify `README.md` (directly below the badges, above "Quick Start")

- [ ] **Content:** two tiles side by side, same reference extent. Left: buildings + roads + Aux ("Input"). Right: same plus the Innenbereich result ("Result"). Tile labels in the top-left corner.
- [ ] **Format:** PNG, 1600 × 700 px (2 × 800 × 700), display width 800.
- [ ] Caption: *IB-Tool 3 derives the Innenbereich (§ 34 BauGB) from building footprints and the road network. Data: © GeoBasis-DE/LGB.*
- [ ] Also suitable as screenshot for plugins.qgis.org — note this in the Session 9 review.

### Task F07: Expected result of the first run

**Files:** Create `docs/img/quickstart/07_expected_result.png`; modify `docs/quickstart.md` — new subsection "Expected result" at the end of section 4

- [ ] **Content:** QGIS main window (cropped to map canvas + layers panel) with the loaded result from the sample data over the buildings.
- [ ] **Format:** PNG, 1200 × 800 px, display width 700.
- [ ] Text: one or two sentences telling the user what they should see and that a differing result points to a parameter or data issue (link to Troubleshooting).

---

## Session 3 — Plugin dialog screenshots

Set QGIS to English; use the sample data paths; Windows display scaling 100 %.

### Task F02: README dialog overview

**Files:** Create `docs/img/readme/02_dialog_step1.png`; modify `README.md` — section "Usage"

- [ ] **Content:** dialog on step 1 (Input): step indicator visible, path fields filled, green ✓ statuses, one red ✗ for illustration.
- [ ] **Format:** PNG, ≈ 1000 px wide, display width 600.

### Task F06: One screenshot per workflow step

**Files:** Create `docs/img/quickstart/06a_step1_input.png` … `06d_step4_processing.png`; modify `docs/quickstart.md` — sections "Step 1" to "Step 4"

- [ ] 06a — Input: path fields with statuses, "…" buttons.
- [ ] 06b — Parameters: default values, Debug Mode checkbox highlighted.
- [ ] 06c — Validation: checklist with ✅, ❌ and ⚠️ entries, greyed-out Start button (provoke one error, e.g. wrong CRS, and one warning).
- [ ] 06d — Processing: finished run, phase label, 100 % bar, log, the three result buttons.
- [ ] **Format:** PNG, ≈ 900 px wide each, display width 600. Optional numbered red markers (①②③) referenced in the text.
- [ ] F02 may reuse 06a — decide during the session, avoid two near-identical files.

### Task F18: Field labels mapped to abbreviations

**Files:** Create `docs/img/input-data/18_field_labels.png`; modify `docs/input-data.md` — section "UI Language"

- [ ] **Content:** input page with callouts HU, RN, Part, Aux, Filter, Output, Workspace, CRS next to the fields.
- [ ] **Format:** PNG, ≈ 900 px wide, display width 600.

---

## Session 4 — QGIS / GitHub screenshots

### Task F03: Install from ZIP

**Files:** Create `docs/img/quickstart/03_install_from_zip.png`; modify `docs/quickstart.md` — section 2, after step 3/4

- [ ] **Content:** plugin manager, tab "Install from ZIP", "…" button and "Install Plugin" marked in red.
- [ ] **Format:** PNG, ≈ 1000 px wide, display width 600.

### Task F04: Correct release asset

**Files:** Create `docs/img/quickstart/04_release_asset.png`; modify `docs/quickstart.md` — section 2, step 1 (optionally also referenced in README Troubleshooting)

- [ ] **Content:** GitHub release page; `ibtool.zip` framed green, "Source code (zip)" framed red / struck through.
- [ ] **Format:** PNG, ≈ 900 px wide, display width 600.

### Task F05: Create empty GeoPackage

**Files:** Create `docs/img/quickstart/05_new_geopackage.png`; modify `docs/quickstart.md` — section "Creating the output file"

- [ ] **Content:** QGIS Browser, right-click on *GeoPackage* → *New GeoPackage File…*
- [ ] **Format:** PNG, cropped ≈ 500 × 350 px, display width 400.

---

## Session 5 — Pipeline map series (F09)

**Files:** Create `docs/img/how-it-works/01_blocker.png` … `10_patch_remove.png`; modify `docs/how-it-works.md` — one figure per "Step N" section, placed after the introductory paragraph and before the pseudocode.

Data source: debug GeoPackages from Session 0, Step 4. All tiles use the reference extent and shared style. Format: PNG 800 × 600 (single) or 1800 × 600 (triptych), display width 600 / 800.

- [ ] **F09-01 Blocker** — road + Aux lines, resulting blocks in random pastel fills; ideally two tiles: street blocks vs. city blocks.
- [ ] **F09-02 ImportFilter** (triptych) — stage 1: positive (green) vs. negative (red) buildings; stage 2: 50 m density buffer as dashed outline, negative buildings outside it greyed/struck; stage 3: small buildings removed.
- [ ] **F09-03 FootprintDensity** — blocks coloured by BCR (sequential ramp, legend with classes), blocks > 18 % with bold outline.
- [ ] **F09-04 CreateMST** (triptych) — Delaunay triangulation; MST; MST with road-crossing edges cut (red).
- [ ] **F09-05 MST_Clustering** — buildings with oriented MBRs per group.
- [ ] **F09-06 AddSingleBuilding** — one large isolated building outside the clusters with its MBR highlighted.
- [ ] **F09-07 EdgeCatch** — before/after snapping to the road (map complement to schematic F10c).
- [ ] **F09-08 ErodeEmptyAreas** — settlement polygon, building buffers (size ∝ √area), removed void hatched.
- [ ] **F09-09 GapClose** — before/after: hole > 1 ha cut out, narrow gap ≤ 70 m closed.
- [ ] **F09-10 PatchRemove** — splinter areas outlined red and removed, remaining result.
- [ ] **Verification:** every figure's content matches the pseudocode of its section (thresholds, colours in legend); if the sample data lacks a case (e.g. no hole > 1 ha), note it in the caption or switch to a schematic instead of fabricating.

---

## Session 6 — Algorithm schematics (Claude drafts SVGs)

**Files:** Create SVGs in `docs/img/how-it-works/`; modify `docs/how-it-works.md`. Claude writes the SVG by hand, the user reviews it in the browser and on GitHub (light and dark mode).

All five SVGs are generated by `docs/img/_src/make_schematics.py` (stdlib only; re-run after changing a threshold). The script asserts every number it prints (BCR, contact shares, distances) against the drawn geometry and the thresholds from the code.

- [x] **F10a MBR (Algorithm 1)** — `05a_mbr_algorithm.svg`, 860 × 400: building edges → direction groups (±10°) with summed lengths → rectangle along the dominant group; dashed axis-aligned box for comparison.
- [x] **F10b MST aggregation (Algorithm 2)** — `05b_mst_aggregation.svg`, 920 × 390: 4 panels, edges added shortest first, BCR per step, rejected extension in red (both the group extension and the pair fallback fail).
- [x] **F10c EdgeCatch 7b** — `07_edgecatch_schematic.svg`, 900 × 420: corner-to-road lines with rule-3a removal, polygonised pieces < 2 × rectangle area, result.
- [x] **F10d GapClose 9b** — `09_gapclose_double_buffer.svg`, 920 × 720: settlement → +15 m buffer → outer 15 m removed → minus settlement = gap; filters 1–3 below.
- [x] **F10e ErodeEmptyAreas protrusion filter** — `08_protrusion_filter.svg`, 720 × 425: interior void (100 % building contact, kept), building-free lobe (16 % building contact, 84 % free edge, removed), fringe bay (70 % building contact, kept). Replaced the earlier `08_contact_fraction.svg` after the filter rule changed on 2026-10-04.
- [x] **Verification:** thresholds and labels checked against the code; SVGs are valid XML, < 50 KB, all links in `how-it-works.md` resolve. Rendered with Qt (QGIS Python) for a visual check.
- [ ] **User review:** view `docs/how-it-works.md` on GitHub in light and dark mode.

---

## Session 7 — Parameter figures

**Files:** Create in `docs/img/parameterization/`; modify `docs/parameterization.md`.

- [ ] **F12 `min_overlap_blocks` sensitivity** — `01_min_overlap_blocks.png`, 1800 × 600 (3 tiles): values 15 / 18 / 25 on the reference extent (user runs three times). Optionally the same for `global_footprint_density`.
- [x] **F13 `max_gap_size`** — `02_max_gap_size.svg`, 700 × 300: 70 m × 70 m square = 4,900 m²; one gap closed, one too large.
- [x] **F14 hole vs. gap** — `03_hole_vs_gap.svg`, 700 × 330: hole (inside, fully enclosed) vs. gap (at the fringe, partly enclosed).
- [x] **F15 `min_area`** — `04_min_area.svg`, 600 × 300: plot with house (kept) and garage/shed (removed), boundary before/after.
- [x] Gap thresholds (from `ibtool_tools/GapClose.py`): ≥ 70 % border contact for gaps < `max_gap_size`, ≥ 90 % for any size, and for large 70–90 % gaps every tessellated triangle with longest side < 70 m. Draw F13/F14 accordingly.

---

## Session 8 — Input data and data preparation figures

- [ ] **F16 input layers overview** — `docs/img/input-data/16_input_layers.png`, 1600 × 400 (4 tiles HU / RN / Aux / Part, same extent) *or* SVG layer-stack 700 × 450; section "Overview" of `docs/input-data.md`.
- [ ] **F17 partitions** — `docs/img/input-data/17_partitions.png`, 1000 × 700: partition polygons labelled `PART_<n>` over buildings; section "Part — Partitioning".
- [ ] **F20 study area** — `docs/img/data-preparation/20_study_area.svg`, 600 × 400: area of interest dashed, generously drawn study polygon solid; section 3 of `docs/data-preparation.md`.
- [ ] **F21 assembling Aux** — `docs/img/data-preparation/21_assemble_aux.png`, 1600 × 400 (4 tiles: merge → dissolve → polygons to lines → merge with railway lines); section "Assembling Aux".

---

## Session 9 — Optional figures and final review

- [ ] **F11 accuracy chart (optional)** — `docs/img/how-it-works/11_accuracy.svg`, 600 × 200, horizontal bars for the three study areas. Load the `dataviz` skill before drawing.
- [ ] **F22 Innenbereich vs. UGB (optional)** — `docs/img/terminology/22_innenbereich_vs_ugb.svg`, 700 × 300: boundary around existing development vs. policy line further out for future growth.
- [ ] **Link check** — every `<img src=...>` points to an existing file:

```bash
grep -rhoE 'img/[A-Za-z0-9_/.-]+\.(png|svg|jpg|webp)' README.md docs/*.md | sort -u | while read p; do
  [ -f "docs/$p" ] || [ -f "$p" ] || echo "MISSING: $p"
done
```

- [ ] **Size check** — no image above its size budget:

```bash
find docs/img -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.webp' \) -size +500k
find docs/img -type f -name '*.svg' -size +50k
```

- [ ] **Visual check on GitHub** — view README and all touched docs in light **and** dark mode.
- [ ] **Alt texts** — every `<img>` has a meaningful `alt`.
- [ ] **plugins.qgis.org** — decide whether F01/F06 are uploaded as plugin screenshots.
- [ ] **CHANGELOG** — add an entry to `docs/CHANGELOG.md` ("docs: add figures to user documentation").
- [ ] Commit only when the user explicitly asks (per session or at the end).

---

## Session Log

Record per session what was done and anything open, so the next session can resume without re-reading everything.

| Date | Session | Done | Open / notes |
|---|---|---|---|
| 2026-09-24 | 6 | F10a–F10e created and embedded in `how-it-works.md`; generator `docs/img/_src/make_schematics.py`. Doc text aligned with code: Algorithm 1 (±10° direction groups, 20 % short-edge filter), Algorithm 2 (pair fallback after a rejected extension), Step 7 EdgeCatch rewritten (20 m segments, filter rules 1–4, factor 2 area filter; old text described 10 m / 1.5× / 5× / 4,900 m²), Step 9b double buffer (15.3 m edge zone, minus settlement). | Rulings: (1) SVG Tiny only — no `<pattern>`/`<marker>` (Qt/QGIS do not render them), "added" areas use solid fill instead of hatching; added to the SVG rules above. (2) F10a compares with the axis-aligned box, not the area-minimal rectangle (not computed by the code). (3) F10b uses an example threshold t = 25 % (the real one is the local BCR). (4) F10e shows three voids incl. the interior case. Open: user review on GitHub (light/dark). Code TODO seen: `edge_catch_utils.py:992` "verify operator direction". |
| 2026-09-24 | 6 (rev.) | User feedback applied: (1) palette switched to the icon colours (teal `#007D85`, orange `#F7561A`, pink `#FFBCB0`) — map style table updated; (2) schematic buildings now individually sized and rotated along streets, drawn at true scale with their buffers (new "Building shapes" convention). Geometry is now computed with ports of `_main_angle`/`calc_bounding_rect` and `apply_filter_rules` (rules 1–4), so F10a/F10c show what the code would output. | Ruling: rejected/removed elements use dark grey instead of red (red is not in the icon and clashes with the orange). F10a dominant direction is 21° — the literal `_main_angle` port picks it from the largest group (18–33°); the pick follows the code's run-index logic. Open: user review on GitHub (light/dark). |
| 2026-10-04 | 7 | F13–F15 created as SVGs in `docs/img/parameterization/` and embedded in `parameterization.md` (`min_area`, `max_hole_size`, `max_gap_size` sections); generator `docs/img/_src/make_parameter_figures.py` (reuses helpers from `make_schematics.py`; `write()` got an `out_dir` parameter). `min_area` definition corrected to the code: dissolved groups of touching buildings > 56.8 m² are kept, then single buildings > 35 m². | Open: F12 (needs three QGIS runs with `min_overlap_blocks` 15 / 18 / 25 by the user). Rulings: (1) F14 is 700 × 330 instead of 700 × 300 to fit a legend line. (2) F15 boundary is a convex hull with a 3 m margin, labelled schematic — the real boundary comes from the MBR/EdgeCatch steps. (3) F13's large gap is a 90 × 80 m rectangle: too large for Filter 1, < 90 % contact, and both tessellation triangles span the 120 m diagonal, so Filter 3 adds nothing either. Code note (not fixed): `input_hu_filter` guards with `building_count > min_area` (compares a feature count with an area). Session 6 user review (GitHub light/dark) still open. |
| 2026-10-04 | 6 (rev. 2) | F10e redrawn as `08_protrusion_filter.svg` because ErodeEmptyAreas now removes building-free protrusions (building contact < 20 % and free edge ≥ 80 %) instead of voids with low outer-boundary contact. `how-it-works.md` Step 8 rewritten accordingly. | Open: user review on GitHub (light/dark) for the new F10e. |
