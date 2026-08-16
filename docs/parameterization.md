# Parameterization

*Based on Harig 2024, TU Dresden — Automated Delineation of Inner Development Areas Including Result Evaluation.*

This document is the reference for all IB-Tool 3 processing parameters: what each one controls, its mathematical background, and practical guidance for tuning. For the algorithmic context of each parameter within the processing pipeline, see [docs/how-it-works.md](how-it-works.md).

---

## Introduction

IB-Tool 3 performs the **automated delineation of the Innenbereich (§ 34 BauGB)** — the coherently built-up part of a municipality — based on geometric and topographic object data. The aim is a **uniform, data-driven, and reproducible** approximation of that legally defined area; see [terminology.md](terminology.md) for the definition, for the relationship to the term *Urban Growth Boundary* used in the international publication, and for which source covers which part of the method.

The parameter values documented here follow the dissertation **Harig (2024)**.

The methodology combines:

- **Building footprints (HU-DE)** as an indicator of actual development
- **Topographic line data (ATKIS road network)** to partition the spatial structure
- **Auxiliary geometries (ATKIS forests, water bodies, bogs, and swamps)**
- **Density-based clustering algorithms** to identify developed areas
- **Graph-based aggregation (Minimum Spanning Tree)** to merge contiguous built-up zones

The goal is an **objective and reproducible delineation** that remains planimetrically interpretable. The method forms a core component for **settlement monitoring**, **inner-development potential analyses**, and **urban sprawl studies** (cf. Harig 2024, Chap. 1.2, 1.4, 8.4).

---

## Processing Workflow

The processing follows the workflow described in the dissertation (see Fig. 4.1–4.10 in Harig 2024):

1. **Partitioning** of the study area into *street blocks* using the road network.
2. **City block generation** by removing non-enclosed portions (Fig. 4.6).
3. **Building coverage ratio (BCR)** calculation per block based on building footprint area (Fig. 4.7).
4. **Filtering** of small or irrelevant buildings (e.g. garages, outbuildings).
5. **Identification of dense blocks** according to density thresholds (Chap. 4.5.3).
6. **Aggregation** using a *Minimum Spanning Tree* algorithm (Chap. 4.4.6).
7. **Post-processing**: filling building gaps and connecting adjacent settlements (Fig. 4.10).

The configurable **parameters** control different stages of this process and govern its sensitivity, spatial coherence, and level of generalisation.

---

## Parameter Reference

### `min_overlap_blocks` — Minimum Overlap for Dense Blocks

- **Type:** Float
- **Function:** Controls the identification of densely built-up blocks in `identify_dense_blocks()`.
- **Definition:** Specifies the minimum share of a block that must be covered by building footprints for it to be classified as "densely developed".
- **Background:** This parameter operationalises the **building coverage ratio (BCR)** described in the dissertation, defined as the ratio of building footprint area to total block area (cf. Harig 2024, Chap. 4.4.3, p. 29 f.).
- **Effect:**
  - **High values** (e.g. > 25) — only very compact, enclosed built-up blocks are recognised as settlements (e.g. town centres).
  - **Low values** (e.g. < 15) — looser development patterns are also captured (e.g. rural areas).
- **Recommended range:** 18–22 (cf. Chap. 4.5.3, empirical calibration).
- **Notes:** This step precedes the clustering and boundary-snapping stages. Its primary benefit is computational: blocks that can safely be classified as inner development are excluded from all subsequent steps. The default of 18 is intentionally conservative so that the false-positive rate remains very low.

---

### `global_footprint_density` — Global Building Coverage Ratio

- **Type:** Float
- **Function:** Used as a fallback reference threshold for the full study area when no local density values are available (`calc_footprint_density()`).
- **Definition:** Mean building coverage ratio across all partitions of the study area.
- **Background:** Provides robustness in areas of sparse development or incomplete building data (cf. Harig 2024, Chap. 4.5.3).
- **Effect:**
  - Low values (< 10) → buildings in relatively loose development patterns are also aggregated.
  - High values (> 20) → only very dense settlement cores are aggregated.
- **Recommended setting:** Automatic calculation (0 = auto); set manually for highly heterogeneous study areas.
- **Notes:** This value specifically affects small or dispersed settlements. In those cases its influence is substantial.

---

### `min_area` — Minimum Building Area

- **Type:** Float
- **Function:** Filters out undersized building objects in `input_hu_filter()`.
- **Definition:** Buildings with a footprint area below this threshold are removed from all subsequent calculations.
- **Goal:** Exclusion of non-settlement-relevant structures (e.g. garden sheds, carports, outbuildings).
- **Background:** Small buildings and outbuildings do not meet the conditions required to establish a contiguous development context. They are therefore removed at the beginning of the pipeline.
- **Recommended values:** 50–60 m², depending on the local context and regional average.
- **Effect:** At the settlement fringe, boundaries are drawn directly along residential buildings. Outbuildings at the rear of plots are thus excluded.

---

### `min_bdg_count` — Minimum Building Count

- **Type:** Integer
- **Function:** Defines the minimum number of buildings required for a cluster to be recognised as a valid settlement or locality.
- **Usage:** Applies during post-processing (`patch_remove()`): patches below this threshold are removed.
- **Background:** Based on empirical analysis (Harig 2024, Chap. 4.5.6) and expert surveys (Appendix A.1.3), a locality is only considered an independent inner development area from approximately **20 buildings or 1 ha** of area.
- **Recommended values:** 15–25 buildings.
- **Effect:**
  - Prevents isolated groups of buildings from being classified as settlements.
  - Stabilises results in rural areas.

---

### `min_patch_size` — Minimum Patch Size

- **Type:** Float (m²)
- **Function:** Used in `patch_remove()` to discard small settlement fragments.
- **Definition:** Patches whose area falls below this threshold are rejected as settlement areas.
- **Background:** Corresponds to the empirically determined minimum size of a locality (Chap. 4.5.6).
- **Recommended value:** 10,000 m².
- **Effect:**
  - Small fragments are removed → cleaner inner-development boundaries.
  - Reduces over-segmentation in sparsely populated areas.
  - **Note:** Shape is not taken into account; only area is evaluated.

---

### `max_hole_size` — Maximum Hole Size

- **Type:** Float (m²)
- **Function:** Used in `gap_close()` to fill undeveloped areas enclosed within contiguous settlement geometries.
- **Definition:** Specifies the maximum area up to which open spaces inside a settlement polygon are filled (treated as inner development rather than open land).
- **Background:** Reflects planning definitions of the inner development area.
- **Recommended value:** 10,000 m².
- **Effect:**
  - Smaller open spaces (gardens, courtyards, playgrounds, meadows, car parks) are incorporated.
  - Prevents excessive fragmentation of settlement areas.

---

### `max_gap_size` — Maximum Gap Size

- **Type:** Float (m²)
- **Function:** Used in `gap_close()` to bridge gaps at the settlement fringe.
- **Definition:** Specifies the area threshold below which gaps at the settlement boundary are closed.
- **Background:** Building gaps count as inner development. Which undeveloped area can still be considered a gap is highly contested and difficult to define precisely — local conditions must always be considered. As a general rule, the looser the surrounding development, the larger a gap may be before it falls outside the inner development area.
- **Recommended value:** 40–100 m (equivalent to 4,900 m² at 70 m radius).
- **Effect:** The algorithm identifies areas located between existing settlement cluster polygons that border those polygons along at least 75 % of their perimeter. Only when the share of contact with settlement areas is substantially greater than that with open land is the area classified as a gap. Such areas are then incorporated into the inner development polygon (cf. Harig 2024, Chap. 4.5.4, Fig. 4.10).

---

### `footprint_density_threshold` — Density Threshold for Dense-Block Identification in PatchRemove

- **Type:** Float
- **Function:** Passed to `identify_dense_blocks()` during `patch_remove()` to determine which blocks are considered densely developed before the final merge step.
- **Definition:** Minimum building coverage ratio (BCR) required for a block to be classified as a dense block and retained regardless of patch size.
- **Background:** Conceptually identical to `min_overlap_blocks`, but applied specifically within the `patch_remove` post-processing step to preserve high-density areas even if they would otherwise fall below the `min_patch_size` threshold.
- **Default:** 18 (fixed internal threshold; not currently exposed in the UI).
- **Effect:** Dense blocks with BCR ≥ 18 % and a combined footprint area ≥ `footprint_area_sum` are always retained, even if their polygon area is below `min_patch_size`.

---

### `footprint_area_sum` — Minimum Footprint Area Sum for Dense Block Retention

- **Type:** Float (m²)
- **Function:** Used in `patch_remove()` alongside `footprint_density_threshold` to decide which dense blocks are retained.
- **Definition:** Minimum total building footprint area within a dense block for it to be kept in the final output.
- **Background:** Prevents very small but technically "dense" blocks (e.g. a single large building surrounded by a tiny polygon) from artificially inflating the settlement area.
- **Default:** 6,000 m² (fixed internal threshold; not currently exposed in the UI).
- **Effect:** A dense block is retained only if its polygon area is ≥ `min_patch_size` **or** its total footprint area is ≥ `footprint_area_sum`. This ensures that compact, fully developed micro-blocks are not discarded.

---

## Parameter Summary

| Parameter | Default value | Primary effect | Sensitivity |
|-----------|--------------|----------------|-------------|
| `min_overlap_blocks` | 18 | Reduces processing time; pre-classifies dense blocks | high |
| `global_footprint_density` | auto (0) | Delineation of small / sparse settlements | high |
| `min_area` | 56.8 m² | Excludes small buildings at the settlement edge | low |
| `min_bdg_count` | 20 | Minimum building count per locality | medium |
| `min_patch_size` | 10,000 m² | Noise suppression; removes splinter areas | medium |
| `max_hole_size` | 10,000 m² | Fills enclosed open spaces within settlements | medium |
| `max_gap_size` | 4,900 m² | Bridges building gaps at the settlement edge | high |
| `footprint_density_threshold`* | 18 | Dense-block retention threshold in PatchRemove | low |
| `footprint_area_sum`* | 6,000 m² | Minimum footprint area for dense-block retention | low |

\* Internal threshold — currently set as a fixed default in `ibtool.py`, not exposed in the UI.

---

## References

The full reference list, with the role of each source, is in
[terminology.md → References](terminology.md#references--which-source-covers-what).
The parameter values on this page are taken from:

- Harig, O. (2024): *Automatisierte Abgrenzung von Innenbereichen einschließlich Ergebnisevaluierung – Grundlage für ein Siedlungsflächenmonitoring.* TU Dresden, Faculty of Environmental Sciences.
  - Chapter 4.4 — Methodology
  - Chapter 4.5 — Parameterisation of the Method
  - Appendix A.1.3 — Expert Survey
- Bukies, M.; Meyer, G.; Rabe, H. (2009): *Abgrenzung des Innenbereichs im unbeplanten Siedlungsgebiet.*
- Spannowsky et al. (2020, 2022): *Baugesetzbuch — Commentary on § 34 BauGB.*

---

## Related Files

| File | Content |
|------|---------|
| [`docs/how-it-works.md`](how-it-works.md) | Full algorithmic pipeline with pseudocode for each step |
| [`docs/input-data.md`](input-data.md) | Input layer specifications, filter file format |
| [`docs/error-handling.md`](error-handling.md) | Logging system and debug mode |
