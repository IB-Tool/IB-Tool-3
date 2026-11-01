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

**Status:** Phase 0 done (2026-11-01): determinism fixed and verified on the
full sample data (3 fixes, not committed). Next: Phase 1.

---

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
- [ ] Script `scripts/compare_results.py`: dissolve two result GPKGs, report
      area A, area B, symmetric-difference area, feature counts, per-partition
      differences (working prototypes exist only in the session scratchpad:
      `compare.py`, `compare_parts.py` — re-create in repo before Phase 1)
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

- [ ] Create one `QgsProcessingContext` (+ `QgsProcessingFeedback`) per
      partition and pass it through to all `processing.run` /
      `safe_processing_run` calls (`context=` keyword).
- [ ] Decide how to thread it through: explicit parameter vs. a small helper
      in `helpers/safe_processing.py` (e.g. `processing_context()` context
      manager). Keep tools stateless (see `ai/core/constraints.md`).
- [ ] Temporary outputs accumulate in `context.temporaryLayerStore()` →
      create a fresh context per partition so memory is released.
- [ ] Verify results unchanged, record timing.

**Results:** _pending_

---

## Phase 2 — Remove incremental merges (low effort, low risk)

- [ ] `MST_Clustering`: `calc_bounding_rect` returns `QgsGeometry` (+ area)
      instead of a memory layer; collect all rectangles in a list and write one
      layer with a single `addFeatures`. Keep `"shape"` mode callers working
      (check `AddSingleBuilding.py`, tests).
- [ ] `EdgeCatch.edge_catch`: collect features of each `process_single_feature`
      result in a list, build output layer once.
- [ ] `ibtool.py` partition loop: append partition results to the merge
      GeoPackage instead of re-merging + rewriting the whole layer per
      partition (keep resume behavior intact).
- [ ] `FootprintDensity` global branch: collect, merge once.
- [ ] `mst_utils` joins: batch attribute updates.
- [ ] Verify results unchanged, record timing.

**Results:** _pending_

---

## Phase 3 — Rewrite EdgeCatch per-feature pipeline (high effort, biggest gain)

EdgeCatch is 55 % of runtime. Target: replace the ~16 processing calls per
rectangle with direct `QgsGeometry` operations.

- [ ] Write characterization tests for `process_single_feature` on real
      rectangles from `Testdaten` (capture current outputs) before touching it.
- [ ] Build `QgsSpatialIndex` once per partition for blocks and road segments;
      replace `extractbylocation` calls with index lookups +
      `intersects`.
- [ ] Replace nested loop in `create_shortest_lines_to_roads` with spatial
      index `nearestNeighbor` + `QgsGeometry.nearestPoint`.
- [ ] Replace polygonize chain (polygonstolines → explodelines → merge →
      extendlines → fixgeometries → polygonize) with
      `QgsGeometry.polygonize()` on noded lines (`unaryUnion` of line
      geometries) — check edge cases documented in `ai/domain/` and
      `docs/how-it-works.md` Step 7.
- [ ] Verify results unchanged (rectangle-level comparison), record timing.

**Results:** _pending_

---

## Phase 4 — Parallel partition processing (medium–high effort)

Partitions are independent (see `docs/how-it-works.md`), inputs are already
written to GeoPackages in the workspace, and the resume log is per partition.

Design sketch (to be refined into a spec in `docs/superpowers/specs/`):

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
