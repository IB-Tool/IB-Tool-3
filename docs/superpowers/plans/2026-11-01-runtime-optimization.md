# Runtime Optimization Roadmap

> **For agentic workers:** This is a multi-phase roadmap, not a single task plan.
> Work phase by phase. Before starting a phase, read its section, re-measure the
> baseline if the code changed, and write a detailed step plan (TDD, as in the
> other files in this folder) for that phase only. Tick checkboxes (`- [x]`) and
> fill in the **Results** lines as phases complete, so the roadmap stays the
> single source of truth across sessions. Never commit without explicit user
> instruction.

**Goal:** Reduce wall-clock runtime of a full IB-Tool run substantially, first by
removing per-call overhead in the existing single-core pipeline, then by
processing partitions in parallel worker processes.

**Branch:** `Add_multiprocessing`

**Status (2026-11-02):** Phases 0–5c committed (Phase 4 in `ea09a84`, 5a + 5b
in `fd6953c`, 5c in `9014fbe`). Phase 5d (footprint density / road filter),
the shapefile checksum fix and the `edge_catch_utils` split are implemented
and verified, **not committed**. Sample data, QGIS 3.44: 843.6 s (3.40,
start) → 262 s sequential → 101.5 s with 4 workers → 61.7 s after 5a–5c →
**58.0 s with 4 workers after 5d** (3.40: 59.9 s; sequential 144.9 s),
results identical. **Next (see "Open topics" at the end):** overlap the global
density (8.4 s, before the workers start) with the partitions — needs a
worker-protocol change (user decision); PART_64 37 s in a worker.

---

## Test environments (important)

| Install | QGIS | NumPy | Launcher | pytest |
|---|---|---|---|---|
| `C:\Program Files\QGIS 3.40.0` | 3.40.0 | 1.26.4 | `bin\python-qgis.bat` | works |
| OSGeo4W `C:\Users\Oliver\AppData\Local\Programs\OSGeo4W` (**user's GUI**) | 3.44.15 LTR | 2.5.4 | `bin\python-qgis-ltr.bat` | fails at import (`DLL load failed while importing _core`, not investigated) |

All measurements above were taken with 3.40. Run the pipeline scripts with
**both** launchers before declaring a phase done — NumPy 2 behaves differently
(2026-11-01: `np.cross` with 2-D vectors crashed MST_Clustering in the user's
GUI only; fixed).

CI (2026-11-01): test matrix QGIS 3.40 + 3.44 (`3liz/qgis-platform`, build
arg `QGIS_VERSION`). Verified locally: 983 tests pass in the 3.44 image. Both
Linux images ship **NumPy 1.26** → NumPy 2 is still only testable via the
user's OSGeo4W LTR install (headless scripts).

**Open: results differ between QGIS versions (2026-11-01).** Full run on 3.44
LTR (after the NumPy-2 fix, Phase 1 code) vs. the 3.40 reference: both 172
features, but symmetric difference 72,050 m² (~0.6 %) in 18 partitions
(e.g. PART_14: 0 m² in 3.40 vs. 15,674 m² in 3.44; PART_43 −3,322 m²).
Runtime 3.44: 672.6 s. Not investigated yet. Hypothesis (unverified):
different GEOS versions (noding / buffer / polygonize). Consequences:
(1) the reference GPKG is **version-specific** — compare 3.44 runs against a
3.44 reference; (2) determinism within 3.44 still has to be checked
(2 LTR runs); (3) ask the user whether cross-version identity is a
requirement. **Decision (user, 2026-11-01): reproducible per QGIS version is
enough; cross-version identity is not required. From Phase 2 on, verify
against a 3.44 reference.**

**3.44 reference (2026-11-01, Phase 1 code + NumPy-2 fix):** 2 full LTR runs
are IDENTICAL to each other (172 features, 11,721,173.448 m², symmetric
difference 0) → 3.44 is deterministic. Stored as
`C:\Users\Oliver\Downloads\Test1\ibtool_reference\result_testdaten_qgis344.gpkg`.
**Baseline for Phase 2 on 3.44: 675.0 s** (682.4 / 667.6 s; EdgeCatch 345 s,
MST_Clustering 82 s, GapClose 56 s, CreateMST 49 s, PatchRemove 42 s,
ImportFilter 39 s). The 3.40 reference
(`result_testdaten_2026-11-01_deterministic.gpkg`, 653 s) stays valid for 3.40.

## Baseline measurement (2026-11-01)

Measured headless with `scripts/profile_pipeline.py` (cProfile on), QGIS 3.40.0,
Windows 10, i7-7700K (4 cores / 8 threads), 32 GB RAM.
Data: `Testdaten/` — 29,232 buildings, 6,796 roads, 2,556 aux lines, 71
partitions (50 processed, 21 skipped with < 10 buildings). Debug mode off,
log level CRITICAL.

| Step | Time (s) | Share |
|---|---:|---:|
| 10 EdgeCatch | 476.6 | 55 % |
| 08 MST_Clustering | 106.8 | 12 % |
| 12 GapClose | 72.0 | 8 % |
| 07 CreateMST | 60.6 | 7 % |
| 13 PatchRemove | 46.5 | 5 % |
| 05 ImportFilter | 38.2 | 4 % |
| 00 global density | 16.5 | 2 % |
| 06 dense blocks | 14.8 | 2 % |
| 11 ErodeEmptyAreas | 12.7 | 1 % |
| rest (load, select, split, blocker, add single, local density) | 22.8 | 3 % |
| **Total** | **868.7** | |

Largest partitions: 198.5 s, 130.5 s, 72.3 s, 41.2 s, 38.0 s.
Without cProfile, runtime is roughly 10–15 % lower (smoke test: 15 partitions
in 77.9 s).

### Root causes (from cProfile)

- **68,496 `processing.run` calls.** Each call without an explicit `context`
  builds a new `QgsProcessingContext` via `dataobjects.createContext`:
  **201.7 s cumulative (23 % of total)** — `globalScope` 68.8 s,
  `globalProjectLayerScopes` 40.3 s, `resolveDefaultEncoding` 27.4 s. Pure
  overhead, no geometry work.
- **EdgeCatch is per-feature processing.** `process_single_feature`
  (`helpers/edge_catch_utils.py:871`) is called 3,625 times (once per rectangle)
  and runs ~16 `safe_processing_run` calls each (fixgeometries, extractvertices,
  extractbylocation ×3, polygonstolines, explodelines, merge, extendlines,
  polygonize, intersection, …) → 431.7 s cumulative, ~0.12 s per rectangle.
  Results are then appended one by one with `native:mergevectorlayers` into a
  growing layer (`ibtool_tools/EdgeCatch.py:87-103`) → quadratic copying.
- **MST_Clustering** builds one memory layer per group in `calc_bounding_rect`
  (`ibtool_tools/MST_Clustering.py:222`, 14,094 calls, 76.5 s cumulative,
  54 s self time in Python/numpy) and merges each rectangle individually via
  `processing.run` (`MST_Clustering.py:618-633`).
- **Same incremental-merge anti-pattern** in:
  - `ibtool/ibtool.py:1458-1466` — per partition merge + rewrite of the whole
    accumulated merge GeoPackage (quadratic in number of partitions).
  - `ibtool_tools/FootprintDensity.py:206-238` — global density, per partition.
- **O(n·m) nearest-line search without spatial index** in
  `create_shortest_lines_to_roads` (`helpers/edge_catch_utils.py:292-330`).
- `mst_utils.join_*` (`helpers/mst_utils.py:46`): 132,372 `updateFeature`
  calls, 16 s — candidate for batch `changeAttributeValues`.

### Why the CPU is not saturated

`start_processing()` (`ibtool/ibtool.py:1296`) runs all partitions sequentially
on the QGIS main thread. Only one core is used.

---

## Known issue discovered during analysis: non-deterministic output

Identical input, three runs: PART_7 produced **79, 75, and 76** rectangles
after MST_Clustering + AddSingleBuilding (PART_8 / PART_9 stable). Likely
causes (unverified): tie-breaking among equal-weight edges in MST /
clustering sort order, iteration order of feature IDs from temporary layers,
or Python hash randomization (`PYTHONHASHSEED`) on string-keyed sets/dicts.

This must be understood **before** optimizing, otherwise "result unchanged"
cannot be verified (see Phase 0).

### Root cause (confirmed 2026-11-01)

Stage fingerprinting of PART_7 over 3 fresh processes: all stage *contents* up
to and including `hu_filter_sel` and the MST are identical; only the *feature
order / FIDs* of several layers (`aux_sel`, `blocks`, `hu_filter_sel`) differ
between processes (probably `native:saveselectedfeatures` iterating a Qt hash
set whose seed is randomized per process — unverified, and harmless by itself).
The first stage with differing content is `mst_clustering`.

In-process permutation test (same inputs, `mst_clustering` only):
same building order → identical result every time; permuted building order →
74 / 77 / 78 clusters; permuted MST edge order → no effect.

Mechanism (`ibtool_tools/MST_Clustering.py:529-615`): each MST edge yields a
pair `(orig_fid1, orig_fid2)` whose orientation comes from the row order of
`native:joinattributesbylocation`, i.e. from building FIDs. The grouping branch
is asymmetric when **both** buildings are already in **different** groups:
the group of `orig_fid1` always absorbs `orig_fid2`, while `orig_fid2` stays in
its old group's member list too (`dict_member_group` is overwritten → one
building can end up in two rectangles). Same for the step-b fallback, which
creates a new pair group even if a building is already grouped.

Frequency on PART_7: 174 MST pairs → none-grouped 68, one-grouped 50,
**both in different groups 56 (32 %)**, both in same group 0.

Proof: canonicalizing the pair orientation by a geometry key (min vertex of the
building) makes all 8 permutations produce identical output (79 clusters).
That only proves the mechanism.

**Decision (user, 2026-11-01): option A** — a building may belong to two
groups (intended); only make the orientation deterministic.

**Fix implemented (2026-11-01, not committed):** `_building_geom_key()` in
`MST_Clustering.py`; pairs oriented by it, weight ties broken by it. Test
`TestMstClusteringDeterminism` in `test/test_mst_clustering.py` (fails on old
code: {AB}+{BCD} vs {ABC}+{CD}; passes with fix). Verification: in-process
permutations of PART_7 → all identical (79 clusters); 3 fresh processes →
identical clusters; 2 full pipeline runs over the first 15 partitions →
identical `result.gpkg` (symmetric difference 0.000000 m²). Full 71-partition
double run not done yet. Full test suite: 959 passed, 2 failed in
`test_create_release_zip.py` (pre-existing: `git` not on PATH in the QGIS
Python environment, unrelated).

### Second source (found 2026-11-01 by the full 71-partition double run)

After the MST fix, 2 full runs still differed (189 vs 186 features,
66,918 m² symmetric difference, 10 partitions affected; per-partition rect
counts identical). Stage fingerprinting of PART_33 / PART_49: `rect_merged`
identical (even in order), `edge_catch` output differs (PART_33: 15 vs 19
polygons). Mechanism, each step verified:

1. `select_and_save_by_location` (`helpers/geometry_utils.py`) returned
   features in the iteration order of the selection hash set → for memory
   layers the order differs per QGIS process (3 processes → 3 order hashes;
   shapefile/GeoPackage sources stable). `native:extractbylocation` is not a
   full fix: stable for `intersects`, but for `disjoint` it also uses a hash
   set (verified by test).
2. Blocker polygonizes `aux_sel` → different line order → block vertices differ
   by < 1e-9 m (float noise in noding; area/symdiff identical).
3. EdgeCatch selects roads by exact `intersects` with the block
   (`edge_catch_utils.process_single_feature`) → noise flips the predicate for
   roads ending on the block boundary (block 0: 1 vs 3 roads) → different
   polygons.

Proof: sorting `aux_sel` canonically before Blocker → blocks bit-identical
(exact WKT hash) and EdgeCatch/final output identical in 3 processes.

**Fix implemented (not committed):** `select_and_save_by_location` now writes
the selected features sorted by FID into a memory layer and restores the input
layer's previous selection (no side effect). Tests
`TestSelectAndSaveByLocation` (3 tests, all fail on old code). Full suite:
962 passed, 2 pre-existing failures (release-zip / git PATH).

**Road selection tolerance (user decision 2026-11-01: 10 cm, implemented, not
committed):** new `select_roads_near_blocks()` in `helpers/edge_catch_utils.py`
(constant `ROAD_BLOCK_TOLERANCE = 0.1`): blocks buffered by 10 cm for the road
selection only, then `extractbylocation`/`intersects` (keeps input order;
clipping to the block stays exact). Tests `TestSelectRoadsNearBlocks` (5).
Check: EdgeCatch on the *noisy* PART_33 inputs of run 1 and run 2 (previously
15 vs 19 polygons) now gives identical results (19 / 32,822.174 m²). Full
suite: 967 passed, 2 pre-existing failures. Performance note: adds one
`native:buffer` call per rectangle (will disappear with the Phase 3 rewrite).

Diagnostic scripts (scratchpad, not in repo): stage fingerprinting
`det_check.py`, permutation test `order_test.py`. Minor side finding: the
global density differs in the 15th digit between processes
(15.701401805626451 vs …455) — float summation order; negligible.

---

## Verification strategy (applies to every phase)

1. Run `scripts/profile_pipeline.py` before and after the change on the same
   data (`--out` to different folders; `--parts N` for quick checks, full run
   for the final number).
2. Compare `result.gpkg` of both runs geometrically: dissolve each, compute
   symmetric difference area. Target: 0 m² (or within the noise measured in
   Phase 0 while non-determinism persists).
3. Unit tests: `pytest test/ -v` (Docker or local) must stay green; new code
   needs tests (see `ai/core/testing-rules.md`).
4. Manual smoke test in QGIS GUI on `Testdaten` (progress bar, cancel button,
   resume via `IB_Tool2_Log_Fin.txt`, debug mode output).
5. Record the new timing in the phase's **Results** line below.

Profiling command (Windows):

```
"C:\Program Files\QGIS 3.40.0\bin\python-qgis.bat" scripts\profile_pipeline.py --out <folder> [--parts N] [--no-cprofile] > prof.txt 2>&1
```

---

## Phase 0 — Measurement & equivalence tooling

- [x] Profiling script `scripts/profile_pipeline.py` (mirrors
      `_run_partition_pipeline`, writes `result.gpkg`)
- [x] Baseline measurement (see above)
- [x] Script `scripts/compare_results.py`: feature counts, dissolved area,
      feature-signature equality, symmetric-difference area, optional
      per-partition breakdown (`--parts Testdaten\A_PART.shp`); exit code 0 =
      identical (default tolerance 0.001 m² for union/difference float noise).
      **Reference result:**
      `C:\Users\Oliver\Downloads\Test1\ibtool_reference\result_testdaten_2026-11-01_deterministic.gpkg`
      (172 features, 11,675,391.895 m²; Testdaten, default parameters).
- [x] Investigate non-determinism (PART_7) → root cause in MST_Clustering
      pair orientation, fixed with option A (see "Root cause" above)
- [x] Verify determinism on the full dataset: 2 full runs (all 71
      partitions) with all three fixes → 172 / 172 features, identical
      signatures, symmetric difference 0.000000 m², no partition differs
- [x] Re-measure baseline without cProfile (`--no-cprofile`, full run)

**Results (2026-11-01):** Pipeline is deterministic on the full sample data.
New reference baseline (no cProfile, all fixes, mean of 2 runs) for all later
phases — compare `result.gpkg` against this reference result (172 features,
11,675,391.895 m²). The reference GPKG was written to the session scratchpad
(temporary); if it is gone, regenerate it with
`scripts/profile_pipeline.py --no-cprofile` on the commit containing the
three determinism fixes:

| Step | Time (s) |
|---|---:|
| 10 EdgeCatch | 489.4 |
| 08 MST_Clustering | 94.3 |
| 12 GapClose | 65.5 |
| 07 CreateMST | 46.7 |
| 13 PatchRemove | 44.0 |
| 05 ImportFilter | 37.3 |
| 00 global density | 15.6 |
| 06 dense blocks | 14.7 |
| 11 ErodeEmptyAreas | 12.7 |
| rest | 22.0 |
| **Total** | **843.6** |

EdgeCatch +22 s vs. the pre-fix run without cProfile (467 s): the extra
`native:buffer` per rectangle from the road-selection tolerance.

---

## Phase 1 — Reuse processing context (low effort, low risk)

Expected gain: up to ~200 s of 869 s (context creation overhead).

Findings (2026-11-01, QGIS 3.40 source `processing/core/Processing.py`):
`processing.run(..., context=ctx)` still transfers output layers to the caller
via `context.takeResultLayer()` when `onFinish` is None, so outputs do not pile
up in a shared context. Creating the shared context with
`processing.tools.dataobjects.createContext()` gives identical settings
(invalid-geometry check, encoding, expression scopes) → results should be
bit-identical. Layers loaded from *string* inputs stay in the context's
temporary store → fresh context per partition bounds memory.

**Design conflict:** `ai/core/constraints.md` forbids global variables /
requires stateless tools; 190 `processing.run` calls in 17 files. Options:
(A) pass `context` explicitly through all tool/helper signatures, or
(B) a scoped "ambient" context in `helpers/` (context manager per partition,
documented exception to the rule). **Decision (user, 2026-11-01): B.**

Implementation (2026-11-01, not committed):
- `helpers/processing_context.py`: `ContextVar` + `shared_processing_context()`
  (creates context via `dataobjects.createContext(feedback)`, owns its
  `QgsProcessingFeedback` for its lifetime — avoids a dangling per-call
  feedback pointer, which the monkeypatch experiment had) and
  `current_processing_context()` (None outside a block).
- All 87 direct `processing.run()` calls (15 files, incl. `safe_processing.py`)
  pass `context=current_processing_context()` — added via AST script, keeps
  the existing module-level `processing` mocks in tests working.
  (Earlier "190 calls" was a grep miscount that included `safe_processing_run`.)
- `ibtool.py`: one block for loading, one for global density, one per
  partition; `scripts/profile_pipeline.py` mirrors this.
- `ai/core/constraints.md`: documented exception + rule "every
  `processing.run()` passes `context=current_processing_context()`".
- Tests: `test/test_processing_context.py` (9), 2 new context tests in
  `test_safe_processing.py`; mocks there accept `**kwargs`. Suite: 978 passed,
  2 pre-existing failures.

Experiment result (2026-11-01; monkeypatched copy of the profiler, scratchpad
`profile_ctx.py`, one `createContext()` per partition, all 71 partitions,
no cProfile): **843.6 s → 642.7 s (−201 s, −24 %)**; result vs. reference:
IDENTICAL (172 features, symmetric difference 0, no partition differs).
Biggest gains: EdgeCatch 489 → 325 s, MST_Clustering 94 → 83 s, GapClose
66 → 54 s.

- [x] Create one `QgsProcessingContext` (+ `QgsProcessingFeedback`) per
      partition and pass it through to all `processing.run` /
      `safe_processing_run` calls (`context=` keyword).
- [x] Decide how to thread it through → option B (scoped ContextVar)
- [x] Fresh context per partition (layers from string inputs are released)
- [x] Verify results unchanged (full run vs. reference), record timing
- [x] Manual smoke test in the QGIS GUI (progress, cancel, resume, debug mode)
      — covered by the user's GUI tests after the UI fix and Phase 4 (both OK)

**Results (2026-11-01):** full run, all 71 partitions, no cProfile:
**843.6 s → 653.2 s (−190 s, −23 %)**; `compare_results.py` vs. reference:
IDENTICAL (172 features, symmetric difference 0, no partition differs).
EdgeCatch 489 → 331 s, MST_Clustering 94 → 85 s, GapClose 66 → 54 s,
PatchRemove 44 → 41 s. New reference timing for Phase 2: **653 s**.

---

## Phase 2 — Remove incremental merges (low effort, low risk)

- [x] `MST_Clustering`: new `_bounding_rect_geometry()` (geometry + area, no
      layer) used for the ~14,000 candidate evaluations; rectangles collected
      in one layer, merged once. `calc_bounding_rect()` API unchanged (wraps
      the helper). Golden test `TestMstClusteringGolden` (exact WKT + order
      recorded with the old code) stays green.
- [x] `EdgeCatch.edge_catch`: results collected, merged once via new
      `geometry_utils.merge_layers_prepending()` (same feature order as the
      former incremental merge; falls back to one-by-one merge on failure;
      "all merges failed → return grouped_bdgs" kept).
- [x] `ibtool.py` partition loop: append partition results to the merge
      GeoPackage instead of re-merging + rewriting the whole layer per
      partition (keep resume behavior intact). **Obsolete (2026-11-02):**
      since Phase 4 every partition writes its own result file and
      `merge_results()` merges once at the end.
- [x] `FootprintDensity` global branch: one merge over all partitions in
      partition order (float sum of overlaps stays bit-identical; single
      partition → no merge, as before).
- [x] `mst_utils.join_array_to_polygons`: grid index (cell = tolerance,
      ±2 cells) instead of nested loop; first match in array order kept;
      attributes written in one edit session. Equivalence test vs. the former
      implementation (random data, near-duplicates, misses).
- [x] Verify results unchanged: 3.44 vs 3.44 reference IDENTICAL, 3.40 vs
      3.40 reference IDENTICAL (0 partitions differ)
- [x] pylint: R0914 in `mst_utils.py` fixed by extracting `_build_grid()` /
      `_first_match_index()` (9.74 → 9.84); other changed files improved
      (EdgeCatch 9.09 → 9.26, MST_Clustering 9.11 → 9.25,
      FootprintDensity 7.09 → 7.29)

---

**Results Phase 2 (2026-11-01), full runs, no cProfile:**

| | 3.44 before | 3.44 Phase 2 | 3.40 before | 3.40 Phase 2 |
|---|---:|---:|---:|---:|
| **Total** | **675.0 s** | **554.3 s (−18 %)** | **653.2 s** | **542.4 s (−17 %)** |
| MST_Clustering | 81.5 | 10.3 | 84.9 | 10.9 |
| EdgeCatch | 345.5 | 310.9 | 330.9 | 305.1 |
| CreateMST | 48.6 | 42.3 | 46.5 | 41.1 |

New baseline for Phase 3 on 3.44: **554 s**, of which EdgeCatch 311 s (56 %).

## Interlude — UI freeze / progress bar bugfix (option A, 2026-11-01)

User report: progress bar never worked, window hangs while processing
continues in the background. Causes (pre-existing): pipeline on the main
thread with `processEvents()` only at 8 phase changes per partition; progress
bar overwritten alternately with fixed per-partition values and overall
progress; no UI lock (nested Start possible). Decision (user): option A now,
Phase 4 (worker processes) will make the main thread fully free later.

- [x] `ui_heartbeat()` / `heartbeat()` in `helpers/processing_context.py`;
      ticked from `current_processing_context()` (before every
      `processing.run()`), explicit tick in the MST grouping loop
- [x] `IBTool._keep_ui_alive()` (processEvents + cancel),
      `ProcessingCancelledError(BaseException)`
- [x] Monotonic overall progress `_overall_percent()`; skipped partitions counted
- [x] UI lock `_set_processing_ui_locked()`, re-entrant Start ignored
- [x] Tests (unit), full suite green
- [x] Full 3.44 run: result IDENTICAL to 3.44 reference; 73,308
      heartbeats; **longest gap 21.6 s, in GapClose**
- [x] User GUI test #1: view jumped to the validation page (re-validation in
      `start_processing()` called `set_step(2)`; with locked step buttons the
      progress page was unreachable — regression of this fix) → fixed
      (`show_page=not is_valid`), test `test_valid_input_keeps_processing_page_visible`.
      Buttons were NOT greyed → user's QGIS still ran the old modules
      (plugin registers a virtual `ibtool` package; "reload plugin" does not
      reliably reload `ibtool.*` submodules) → **restart QGIS before GUI tests**.
- [x] GUI smoke test #2 by user after QGIS restart: **OK** (2026-11-01)
- **Remaining freeze, root cause measured:** one single C++ call,
  `qgis:symmetricaldifference` in `GapClose._close_block_gaps` (284 blocks vs.
  1 settlement polygon, `GRID_SIZE=1e-5`): 21.96 s of 24.8 s GapClose on
  PART_64. A heartbeat cannot run during a C++ call. Variants on PART_64:
  without GRID_SIZE 7.1 s but different result (259 vs 224 features);
  "blocks − settlement" with grid = 23.1 s (the expensive half),
  "settlement − blocks" 0.2 s. Idea (unverified): clip the settlement to
  each block's extent before the difference. Options: optimize this step
  (also saves runtime) or accept until Phase 4 (worker processes).
- **GRID_SIZE experiment (user proposal: 10 cm, 2026-11-01), PART_64,
  `qgis:symmetricaldifference`:** 1e-5 → 21.1 s / 224 features; 1e-3 → 21.0 s
  / 225; **1e-2 and 0.1 → algorithm fails** ("Could not write feature", also
  with INVALID_FEATURE_HANDLING=1; presumably snap-rounding collapses thin
  parts to lines). Grid size is not the speed lever. Danger: in the pipeline
  `safe_processing_run` would treat the failure as a geometry error and the
  last-resort retry drops GRID_SIZE **silently** (→ third, unintended result,
  259 features). A 10 cm grid would need an own sym-diff via `QgsGeometry`
  with grid parameter + polygon-part extraction = method change with new
  reference → proposed as separate topic after Phase 3.
- **Decision (user, 2026-11-01):** keep the grid; speed up the sym-diff by
  clipping the settlement per block — "speed with unchanged stability of the
  whole process" → only accepted if the full run stays IDENTICAL to the
  reference. Plan: (1) Python re-implementation of the sym-diff with
  `QgsGeometry` + grid 1e-5 must reproduce `qgis:symmetricaldifference`
  bit-identically (WKT + order); (2) then add the per-block clip and measure.
- **Result (2026-11-01):** (1) re-implementation bit-identical on PART_64
  (21.3 s, like QGIS). (2) per-block clip (`clipped()` or GEOS bbox
  intersection): 0.4 s but result changes by 168–184k m² → rejected.
  (3) **cached overlay union** (QGIS recomputes the same grid union of the
  settlement for every block): 0.49 s, bit-identical → implemented as
  `GapClose._symmetrical_difference()` (+ fallback to the QGIS algorithm).
  First full run: 70/71 partitions identical, **PART_56 different
  (5,940 m²)** → root cause: grid difference returned a GeometryCollection
  (polygons + collapsed line remnants), `convertToType()` returned null and
  the whole block was dropped → fixed with `_polygon_parts()` (keeps polygon
  parts like QGIS); PART_56 sym-diff now identical. **Full runs 3.44 + 3.40
  vs. references: IDENTICAL (0 partitions differ).** GapClose 54 → 23 s,
  total 3.44: 554 → 521 s, 3.40: 542 → 516 s; longest heartbeat gap
  21.6 → 9.2 s (now in PatchRemove). Helpers moved to
  `helpers/overlay_utils.py` (GapClose exceeded 1000 lines; pylint GapClose
  9.22 → 9.24, overlay_utils 10.0). Not committed.
- **New baseline for Phase 3 (3.44): 521 s**, EdgeCatch 311 s (60 %).
  Remaining UI gaps > 5 s: PatchRemove (9.2 s) — to be looked at if needed.

## Phase 3 — Rewrite EdgeCatch per-feature pipeline (high effort, biggest gain)

EdgeCatch is 55 % of runtime. Target: replace the ~16 processing calls per
rectangle with direct `QgsGeometry` operations.

**Harness (2026-11-01):** `scripts/edge_catch_harness.py` (dump / record /
check). Cases (7 partitions, 1,927 rectangles: PART_64, 43, 25, 56, 33, 7, 49)
and golden data in
`C:\Users\Oliver\Downloads\Test1\ibtool_reference\edgecatch_cases\`
(recorded on QGIS 3.44 with the code before Phase 3). Run with
`python-qgis-ltr.bat scripts\edge_catch_harness.py check --cases <dir>`.
Criterion: per rectangle the same multiset of (WKT 17 digits, attributes);
the feature order within a rectangle's result already varies between
processes with the original code (verified: 261/1,927 rects differ only in
order on an unchanged rerun) → not counted. Final proof: full runs vs.
references. Baseline: 166 s for 1,927 rects; ~135 s of it in ~31,000
processing calls (≈4.4 ms each, overhead-dominated): extractbylocation 31.7,
fixgeometries 23.7, polygonize 9.0, intersection 8.5, buffer 8.0,
extendlines 7.9, extractbyexpression 7.8, extractvertices 7.7,
explodelines 7.6, merge 7.5, polygonstolines 7.2 s.
Side fix: `process_single_feature` now also skips a NULL-QVariant `Area`
(only `None` was handled; QGIS 3.40 returns NULL QVariant for missing
values — crashed the harness on PART_56 rect #130).

**Implementation (2026-11-01, not committed):**
- Step lab (scratchpad `step_lab.py`) compared every step with its
  QgsGeometry candidate on identical inputs, all 1,926 rects, strict order:
  fixgeometries = `makeValid(Structure)` ✓; extractvertices + delete first ✓;
  block/road selection ✓ **only after emulating extractbylocation's order**
  (two code paths: iterate target if it has fewer features, else per intersect
  geometry with provider `setFilterRect` order, skipping found ids); the
  polygonstolines → explodelines → merge → extendlines → fixgeometries →
  polygonize chain ✓ (strictly identical). The final `native:intersection`
  returns the same features in an **undefined order** (candidates fetched via
  `setFilterFids` on a hash set) — source of the order variation of the
  original EdgeCatch output.
- `helpers/overlay_utils.py`: `make_valid_polygon`, `extract_intersecting`,
  `polygonize_lines`, `intersection_with`, `checked()` +
  `GeometryOperationError` (null result with GEOS error → raise; also applied
  to the GapClose sym-diff).
- `edge_catch_utils.process_single_feature`: area check → geometry path
  `_process_single_feature_geometry` → on any exception (WARNING) fallback to
  the unchanged processing version `_process_single_feature_processing`.
  `create_shortest_lines_to_roads`, `filter_ortho_lines`,
  `_build_minimized_lines_from_selection` split into list cores
  (`_shortest_connections`, `_filter_ortho_items`, `_minimized_chains`) + the
  unchanged layer wrappers (used by the fallback and existing tests) — a
  memory layer costs ≈3.6 ms to create.
- Harness: **175 s → 65 s → 21 s** (1,927 rects), IDENTICAL. Full runs after
  the first step (65 s version): 3.44 521 → 335 s, 3.40 516 → 333 s, both
  IDENTICAL to their references; EdgeCatch 311 → 118 s. **Full runs of the
  21 s version: 3.44 521 → 262 s, 3.40 516 → 252 s, both IDENTICAL;
  EdgeCatch 311 → 44 s.**

**Results Phase 3 (2026-11-01), full runs, no cProfile (3.44 / 3.40):**
total 262 / 252 s. Remaining steps (3.44): CreateMST 43, PatchRemove 41,
ImportFilter 37, EdgeCatch 44, GapClose 24, dense blocks 15, global
density 13, ErodeEmptyAreas 12, MST_Clustering 11 s. Longest UI heartbeat
gap 10.2 s (PatchRemove). Overall since the start (3.40, no cProfile):
843.6 → 252 s (−70 %, 3.3×), result identical (after the determinism fixes).
**Next baseline (3.44): 262 s.**
- Tests: `test/test_overlay_utils.py` (each function vs. its QGIS
  algorithm), fallback tests in `test_edge_catch_utils.py`; suite 1,030 passed.
- [x] Follow-up: `edge_catch_utils.py` >1000 lines (C0302) → ortho-line
  filter rules moved unchanged into `helpers/ortho_line_filter.py`
  (2026-11-02; 1,177 → 870 lines; harness IDENTICAL, 1,927 rects, 21.8 s).

Original checklist (planned before the harness; done in the form described
above):

- [x] Characterization tests → `scripts/edge_catch_harness.py` golden data
      (1,927 real rectangles).
- [x] Spatial lookups instead of `extractbylocation` →
      `overlay_utils.extract_intersecting` (same output order).
- [ ] Nested loop in `_shortest_connections` (each building vertex × each
      road segment of the block) is still O(n·m). Not worth it: the whole
      geometry path is ~7 s on PART_64; a spatial index must keep the
      "first line wins on equal distance" rule. Left open.
- [x] Polygonize chain → `overlay_utils.polygonize_lines` (strictly
      identical to the algorithm chain).
- [x] Verify results unchanged, record timing (see Results Phase 3).

---

## Phase 4 — Parallel partition processing (medium–high effort)

Partitions are independent (see `docs/how-it-works.md`), inputs are already
written to GeoPackages in the workspace, and the resume log is per partition.

**Spec (2026-11-01, approved by the user):**
`docs/superpowers/specs/2026-11-01-parallel-partitions-design.md` —
supersedes the sketch below (worker pool via QProcess, Windows-only launcher
strategy, worker count automatic + UI field, run manifest
`ibtool_run.json` incl. settings restore, per-partition result files +
single final merge, recompute list in-process). Spec approved by the user.
**Implementation plan:** `docs/superpowers/plans/2026-11-01-parallel-partitions.md`
(10 tasks) — **implemented and committed 2026-11-01 (`ea09a84`; inline
execution, ledger in `.superpowers/sdd/2026-11-01-parallel-partitions/progress.md`).**

Results (all RESULT: IDENTICAL vs. the references):
- QGIS 3.44, `profile_pipeline.py`: 4 workers 157.3 s, 3 workers 166.4 s,
  1 worker 375.9 s. **These timings are invalid**: a game (ClearedHot.exe)
  used ~2.4 of the 4 cores during the runs (global density 12.8 → 19.5 s with
  unchanged code; PART_64 92 s instead of 60 s even alone). Re-measure on an
  idle machine; target 3.44 with 3–4 workers < 100 s (LPT estimate 62–83 s).
- QGIS 3.40, `IBTool.start_processing()` (3 workers): 178.4 s under the same
  load; resume of the finished run 33.2 s (nothing recomputed).
- `scripts/resume_test.py` (3.44, 3 workers, killed after 26 partitions):
  26 skipped, orphaned workers gone after 2.9 s, identical.
- **Idle machine, QGIS 3.44, 4 workers: 101.5 s** (was 262 s sequential,
  −61 %; load 2.6 s, global density 13.9 s, partitions 82.7 s); identical.
  The partition phase is bounded by PART_64 (80.1 s in a worker vs. 59.7 s
  alone: ~1.3× slowdown per partition when 4 run at once; sum of partition
  times 318 s vs. 246 s). Further gains need a faster PART_64 (single-step
  optimizations: CreateMST, PatchRemove, ImportFilter) or overlapping the
  global density with the first partitions.
- GUI test by the user: OK.
- Follow-ups: ~~shapefile checksum covers only the `.shp`~~ **fixed
  2026-11-02** (`compute_file_checksum` hashes the existing sidecars
  `.shx/.dbf/.prj/.cpg/.qpj` as tagged sections; a `.shp` without sidecars
  keeps its plain MD5; also fixes the validation cache; runs begun before
  report their shapefile inputs as changed once); ~~`edge_catch_utils.py`
  > 1000 lines~~ **done 2026-11-02**. (The `0,0000…` validation error for Global
  Footprint Density appeared only in the headless test harness; the GUI
  run with 0 works.)

### Phase 5a — CreateMST: `nodes_detect` without processing (2026-11-01)

- [x] Profile CreateMST on PART_64 (3.44): 13.8 s, of which `native:aggregate`
      in `nodes_detect` 8.8 s, `selectbylocation` ×3 1.5 s, rest ≈ 1.5 s.
- [x] `nodes_detect` counts first/last vertices by exact x in Python; former
      chain kept as `_nodes_detect_processing` (fallback + test reference).
      Findings while matching the chain: no rounding of the `x-coord` field
      (precision 10 is metadata only); `native:aggregate` unites the group
      geometries (identical points merge); grouping by x only is a quirk of
      the ArcPy port (a dead end sharing x with a junction is not detected) —
      kept for identical results.
- [x] Verified: 50 calls on the sample data, 0 mismatches (1,691 nodes);
      33.8 s → 0.3 s summed; full runs identical on 3.44 and 3.40.
- [x] Timing (4 workers, CPU base load 14–24 %): 3.44 89.2 s (PART_64 69.5 s,
      parallel phase 71.5 s), 3.40 92.4 s.
- [x] Committed (`fd6953c`).

### Phase 5b — identify_dense_blocks: area fields (2026-11-01)

- [x] Profile PatchRemove on PART_64 (3.44): 10.1 s, of which
      `identify_dense_blocks` 9.5 s — `globalProjectLayerScopes` per feature
      (7,216 calls, 7.1 s) + one `updateFeature` per feature (2.1 s).
- [x] `_store_area`: one expression context per layer, values written with one
      `changeAttributeValues` call; also speeds up step 06 (dense blocks).
- [x] Verified: full runs identical on 3.44 (4 workers and sequential) and 3.40.
- [x] Timing (CPU base load 0–10 %): 4 workers 71.8 s (3.44 and 3.40),
      PART_64 51.1 s; sequential 3.44 177.0 s (06_dense_blocks 1.3 s,
      13_patch_remove 6.0 s).
- [x] Committed (`fd6953c`).

### Phase 5c — ImportFilter: LIKE filter in Python (2026-11-01)

- [x] Profile ImportFilter on PART_64 (3.44): 12.8 s, of which
      `extractbyexpression` ×3 7.1 s (positive/negative filter: `fkt LIKE …`
      OR-chains), dissolve 2.2 s, selectbylocation 1.7 s.
- [x] Cause: QGIS LIKE builds its regular expression per evaluation — even a
      prepared `QgsExpression` loop takes ~0.45 ms per building.
- [x] `_extract_by_codes`: one precompiled Python regex for codes of
      `[A-Za-z0-9_]` on text fields, same LIKE rules; fallback to the
      algorithm otherwise. Identical output (ids, attributes, WKB) on all
      29,232 sample buildings, 10–12 s → 0.2 s per filter.
- [x] Verified: full runs identical on 3.44 (4 workers and sequential) and 3.40.
- [x] Timing (CPU base load 12–17 %): 4 workers 3.44 61.7 s, 3.40 64.8 s,
      PART_64 40.3 s; sequential 3.44 154.5 s (05_import_filter 15.5 s).
- [x] Committed (`9014fbe`; the CHANGELOG entry was left uncommitted).

### Phase 5d — footprint density + EdgeCatch road filter (2026-11-02)

- [x] Per-call-site timing of all processing algorithms on PART_64 (3.44;
      scratchpad wrapper hooking `Processing.runAlgorithm`): 24,735
      `updateFeature` calls (4.2 s) + `native:aggregate` (2.2 s) in
      `footprint_density`; `extractbyexpression "seg_id" IN (…)` 3.0 s +
      `extractbylocation` 2.6 s in `filter_roads_near_buildings`.
- [x] `footprint_density`: sums per `BLOCK_ID` in intersection order and the
      result layer built in Python (`_footprint_density_python`); former chain
      kept as `_footprint_density_processing` (fallback + test reference).
      Test `TestFootprintDensityFast` (exact WKB + float attributes, field
      definitions, order, empty case, fallback).
- [x] `filter_roads_near_buildings`: set lookup + order-preserving memory copy
      (`_copy_features_where`) instead of the IN-list expression. Test
      `TestFilterRoadsNearBuildingsSelection` (ids, order, WKB, attributes vs.
      the expression). The `extractbylocation` stays: invalid-geometry
      handling of the processing context (stop → `safe_processing_run`
      repair) would have to be emulated.
- [x] Verified: full runs IDENTICAL — 3.44 4 workers, 3.44 sequential, 3.40
      4 workers. Suite (3.40): 1,162 passed, 2 pre-existing failures
      (release-zip / git PATH).
- [x] Timing (3.44): 4 workers **58.0 s** (global density 8.4 s, parallel
      phase 44.6 s, PART_64 37.3 s in a worker); 3.40 4 workers 59.9 s;
      sequential 144.9 s (02_local_density 5.2, 05_import_filter 15.5,
      07_create_mst 9.8, 08_mst_clustering 10.5, 10_edge_catch 37.8,
      11_erode 12.1, 12_gap_close 23.6 s).
- [ ] Commit (user).
- Side finding: in worker mode PART_64 logs `[CRITICAL] PolyArea is zero in
  MST_Clustering calc_bounding_rect` 3× (only visible because workers
  forward log lines; MST_Clustering and its inputs unchanged; result
  identical). Not investigated.

### Open topics (2026-11-02)

- **Overlap the global density with the partitions** (≤ 8.4 s of 58 s):
  `run_partition` needs the value already in step 02 (local density uses it
  as fallback when a partition has ≤ 5 inner blocks). Options: workers start
  and wait for the value (protocol change of the Phase 4 spec), or the global
  density itself is computed per partition in the workers (its per-partition
  `_select_block` is independent; only the final mean is global). Needs a
  user decision.
- Global density partition extraction (`extractbyexpression` +
  2× `extractbylocation` per partition, ~2 s) → Python only if the
  invalid-geometry behaviour of the processing context is emulated.
- PART_64 critical path (37 s in a worker): EdgeCatch ~12 s (geometry path
  7 s, road filter `extractbylocation` 2.6 s), ImportFilter 4.2 s, Erode
  2.8–4.7 s, GapClose 2.9 s, local density 2.4 s.
- pytest under OSGeo4W 3.44 (`DLL load failed while importing _core`) not
  investigated.

Original design sketch (superseded by the Phase 4 spec/plan, kept for history):

- [ ] Extract partition pipeline into a GUI-free module (e.g.
      `helpers/partition_runner.py`) callable from both the plugin and a worker
      script — removes `self._update_phase` dependency (progress via callback).
- [ ] Worker script (`ibtool/worker.py` or similar): initializes
      `QgsApplication` + `Processing`, processes one partition, writes
      `IB_Tool_Results/parts/PART_<name>.gpkg`, prints progress lines to
      stdout, exit code signals success.
- [ ] Launch workers from the plugin with `QProcess` (not `multiprocessing`:
      on Windows `sys.executable` is `qgis.exe`). Interpreter: QGIS Python
      (`python-qgis.bat` / `sys.exec_prefix\python.exe` + env vars from
      `o4w_env.bat`); must also work on Linux/macOS installs.
- [ ] Scheduler: N workers (default `min(physical cores, 4–6)`, configurable
      in UI/CONFIG.ini), largest partitions first (by building count),
      keep GUI responsive via Qt event loop (no blocking main thread).
- [ ] Main process: write resume log on worker success, merge part GPKGs once
      at the end, progress bar = completed buildings / total.
- [ ] Cancel button: terminate running workers, keep finished parts.
- [ ] Logging: per-worker log file + forward stdout lines to dialog log.
- [ ] Debug mode: per-partition debug folders already exist — verify no
      shared-file write conflicts (GeoPackage = SQLite: concurrent readers OK,
      writers must use separate files).
- [ ] Fallback: sequential in-process mode when workers=1 or launching fails.
- [ ] Verify results unchanged vs sequential, record timing for 1/2/4/6 workers.

Expected: bounded by the largest partition (198 s at baseline) and core
count; ~3.5–4× on 4 cores. Combined with Phases 1–3, rough estimate
870 s → 80–120 s (unverified).

**Results:** _pending_

---

## Decisions log

| Date | Decision |
|---|---|
| 2026-11-01 | Parallelize by **process per partition**, not threads (GIL-bound Python loops; `processing.run` not thread-safe in plugin context). |
| 2026-11-01 | Order: Phase 0 → 1 → 2 → 3 → 4. Algorithmic fixes first because they also speed up each worker and single large partitions. |
| 2026-11-01 | MST_Clustering non-determinism: option A (deterministic pair orientation by geometry key). A building may belong to two groups — intended by the method. |
| 2026-11-01 | `select_and_save_by_location` outputs features sorted by FID and restores the input selection (fixes process-dependent order at the source). |
| 2026-11-01 | EdgeCatch road-per-block selection uses a 10 cm tolerance (`ROAD_BLOCK_TOLERANCE`). |
| 2026-11-01 | Results must be reproducible per QGIS version; identity across versions (3.40 vs 3.44) is not required. Development reference = QGIS 3.44 LTR. |
| 2026-11-01 | UI freeze fixed with option A (heartbeat + monotonic progress + UI lock); GUI test OK. |
| 2026-11-01 | GapClose grid stays at 1e-5 (10 cm makes the QGIS algorithm fail). Speed-ups must keep the result identical ("speed with unchanged stability"): sym-diff with cached union accepted, per-block clipping rejected. |
| 2026-11-01 | Phase 4: fixed worker pool via QProcess (approach A); Windows only for now, launcher kept platform-pluggable (`find_worker_command`) for a later release on more systems; worker count automatic (cores − 1, max 4) + UI field; worker mode used automatically when the self-test passes. |
| 2026-11-01 | Phase 4: one working directory = one run; `ibtool_run.json` with input checksums, parameters, versions; resume is checked against it and the plugin offers to take over its settings ("Prüfen + Einstellungen übernehmen"). |
| 2026-11-01 | Phase 4 result: 3.44 262 → 101.5 s with 4 workers, identical; target < 100 s missed by 1.5 s — PART_64 is the critical path. |
