# Parallel Partitions (Worker Processes) — Design Spec

**Date:** 2026-11-01
**Branch:** Add_multiprocessing
**Roadmap:** `docs/superpowers/plans/2026-11-01-runtime-optimization.md`, Phase 4

## Goal

Process the partitions of a run in parallel worker processes so that a full
run gets considerably faster, while

- the result stays **identical** to a sequential run (same reference result,
  per QGIS version — see the roadmap's decisions log),
- cancel, progress, debug mode and **resume after a complete restart** keep
  working and become more robust,
- a problem in worker mode can only make a run slower (sequential), never
  change its result.

The plugin is published on plugins.qgis.org and must stay flexible for many
systems: worker mode is implemented and tested for **Windows** now; the
platform-specific part is isolated so other platforms can be added later.
Everywhere else the plugin runs sequentially as today.

## Success Criteria

- QGIS 3.44 LTR (user's GUI, OSGeo4W, NumPy 2.5): full run on `Testdaten`
  **< 100 s** (today 262 s), `scripts/compare_results.py` vs. the 3.44
  reference: **IDENTICAL**; same on QGIS 3.40 vs. its reference.
- The dialog stays responsive during the whole run; Cancel takes effect within
  1–2 s, also in the largest partition.
- Resuming after a hard kill / restart gives a result IDENTICAL to an
  uninterrupted run.
- No orphaned worker processes after closing QGIS or the dialog.

## Measured Basis (2026-11-01, QGIS 3.44, after Phase 3)

Total 262 s: load 2.4 s + global density 12.8 s (sequential preparation) +
50 partitions 246.5 s. Longest-processing-time-first scheduling:

| Workers | Partition makespan |
|---:|---:|
| 1 | 246.5 s |
| 2 | 123.6 s |
| 3 | 82.7 s |
| 4 | 62.2 s |
| ≥ 6 | 59.7 s (bounded by PART_64 alone) |

Expected full run with 3–4 workers: ~80–100 s incl. preparation and worker
start-up (estimate, to be measured).

## Decisions (user, 2026-11-01)

| Topic | Decision |
|---|---|
| Approach | **A** — fixed worker pool via `QProcess`, each worker initialises QGIS once and processes partitions sent to it (rejected: Python `multiprocessing` — embedded interpreter, poor Qt integration; `qgis_process` per partition — QGIS start-up per partition, plugin registration) |
| Platforms | Worker mode on **Windows** only for now; platform-specific code isolated in one module so other platforms can be added later; elsewhere sequential |
| Worker count | **Automatic + field in the UI** (Parameter page, stored in CONFIG.ini): default `max(1, min(4, physical_cores − 1))`; `1` = sequential |
| Default / rollout | Tool must stay flexible for many systems: worker mode is used automatically where the launcher finds an interpreter **and** the self-test passes; otherwise sequential with an INFO/WARNING log line |
| Run manifest | Working directory = one self-contained run. `ibtool_run.json` in the working directory: used to **check** resume **and** offered to **restore the UI settings** when an existing working directory is selected. CONFIG.ini stays in the QGIS profile (last used UI settings) |

## Architecture

### Components

| Unit | Responsibility | Depends on |
|---|---|---|
| `helpers/partition_pipeline.py` (new) | `run_partition(name, inputs, crs, params, workspace, debug_mode, global_density, progress)` — the partition pipeline (today `IBTool._run_partition_pipeline`) without UI; progress via callback `progress(phase, phase_name)`. Returns `(result_layer or None, building_count)`. **The only implementation** — used by the sequential path and the workers | `ibtool_tools/*`, helpers |
| `helpers/worker_launcher.py` (new) | Platform-specific part. `find_worker_command() -> Optional[WorkerCommand]` (interpreter path, arguments, environment); Windows strategy now (OSGeo4W and standalone installer: `python.exe` from `sys.exec_prefix`, environment inherited from the QGIS process); other platforms return `None`. `default_worker_count()` | stdlib, QGIS |
| `ibtool/partition_worker.py` (new) | Worker program: initialise `QgsApplication` (no GUI) + Processing, register the `ibtool` package, open the input GeoPackages once, read JSON-line commands from stdin, run `run_partition`, write `parts/<PART>.gpkg`, emit JSON-line events on stdout; exits on `exit`, on stdin EOF, or when the parent process is gone | `partition_pipeline` |
| `helpers/worker_pool.py` (new) | Plugin side: `QObject` that starts N `QProcess` workers, runs the self-test, schedules partitions (largest first), parses events, emits Qt signals (`progress`, `log`, `partition_done`, `partition_failed`, `finished`), `cancel()` | `worker_launcher`, Qt |
| `helpers/run_manifest.py` (new) | Read/write/compare `ibtool_run.json`; validate finished partitions; atomic writes | `system_utils.compute_file_checksum` |
| `ibtool/ibtool.py` (changed) | `start_processing()`: common preparation, manifest check, then **switch**: worker pool if `workers > 1` and a worker command exists and the self-test passes; otherwise sequential loop. Both paths: per-partition result files, final merge. `_run_partition_pipeline` becomes a thin wrapper around `run_partition` | all above |
| Parameter page + `config_manager` (changed) | Field "Worker-Prozesse" (spin box, 1–16, default automatic) | |

All new files live in `helpers/` and `ibtool/`, which are in
`WHITELIST_DIRS` of `scripts/create_release_zip.py`; the worker script is
started by path from the installed plugin folder, so it must ship in the
release ZIP (covered by the whitelist; the import smoke test checks its
imports).

### Common preparation (main process, sequential, unchanged semantics)

1. Validate inputs, write/compare the run manifest (see Resume).
2. Load input layers into the workspace GeoPackages (as today) and **also save
   the merged aux/road line layer** (`aux_layers_line`, today in memory) to
   `layer_aux_line.gpkg`. Before implementation it is verified that reading it
   back gives the same feature order (and therefore identical results).
3. Compute the global footprint density (unless set manually).
4. Determine the partition list; skip finished partitions (Resume).

### Worker Protocol

One JSON object per line. Worker output lines carry the prefix `IBTOOL `;
everything else on stdout/stderr (QGIS/GDAL messages) is ignored for control
and kept (last 50 lines) for error reports.

Plugin → worker (stdin):

| Message | Content |
|---|---|
| `init` (once) | input GeoPackage paths (`hu`, `rn`, `part`, `aux_line`), CRS auth id, numeric parameters, filter file path, workspace path, debug mode, global density, log level, parent PID |
| `run` | `{"partition": "PART_64"}` |
| `exit` | finish cleanly |

Worker → plugin (stdout):

| Event | Content |
|---|---|
| `ready` | QGIS/Processing initialised (also the self-test) |
| `progress` | partition, phase (2–8), phase name |
| `log` | level, message (the plugin writes it to its log with a `[PART_x]` prefix — workers never write log files) |
| `done` | partition, building count, result file path or `null` (skipped), feature count, seconds |
| `error` | partition, message, traceback |

### Scheduling and Results

- Before dispatching, the plugin estimates the building count per partition
  via a spatial index (only used for ordering). Largest first; each idle
  worker gets the next partition. Ordering affects run time only.
- Every finished partition — in **both** modes — is written to
  `IB_Tool_Results/parts/<PART>.gpkg`: written under a temporary name, then
  renamed (atomic). Then the plugin appends the finish line to
  `IB_Tool2_Log_Fin.txt` and flushes it (`flush` + `os.fsync`). Only the plugin
  writes the finish log.
- **Final merge** after all partitions: read the part files in partition-list
  order, **drop the GeoPackage `fid` field** (it would cause duplicate primary
  keys when writing the output GeoPackage), and merge with
  `merge_layers_prepending(results, base_layer, crs)` — the same feature order
  as today's incremental merge. Sequential and parallel runs therefore produce
  the output with the same code from the same files. The per-partition
  rewrite of `IB_Tool_merge_temp.gpkg` (quadratic) is dropped.

### Progress and UI

- Overall progress = Σ(partition building share × phase fraction) over all
  partitions, monotonic, as introduced by the UI fix.
- Status line, e.g. "3 Worker · 12 von 50 Partitionen fertig · läuft: PART_64,
  PART_43, PART_25".
- In worker mode the plugin waits in a `QEventLoop` driven by pool signals;
  the main thread is free, so the dialog stays responsive without heartbeats.
  The existing heartbeat stays active for the sequential path and inside the
  workers (parent-process check).

## Errors, Cancel, Fallback

Principle: a worker-mode problem never changes the result; at worst the run
gets slower.

| Situation | Behaviour |
|---|---|
| `workers == 1`, not Windows, or no worker command | sequential path; reason logged (INFO) |
| Self-test fails (no `ready` within 60 s, or the worker exits) | stop workers, **sequential path**; WARNING with the worker's last output lines |
| Worker process exits unexpectedly during a partition | start a replacement worker; partition goes to the **recompute list**; others continue |
| Worker reports `error` | partition goes to the recompute list |
| Recompute list (after the pool has finished) | the plugin processes these partitions **in its own process**, exactly as today; a genuine data error appears with the same message as today |
| More than half of the workers crashed | stop the pool; remaining partitions run sequentially |
| Cancel | kill all workers (terminate, then kill after 2 s), delete temporary part files; finished parts and finish-log lines stay (resumable) |
| Dialog closed / QGIS closed / plugin unloaded during a run | plugin kills all workers |
| QGIS crashes | each worker checks during its heartbeat whether the parent process (PID from `init`) still exists and exits otherwise |

Not covered on purpose: a worker that hangs without crashing (large
partitions legitimately run long; a fixed timeout would give false alarms).
Cancel handles it.

`ProcessingCancelledError` derives from `BaseException` (since the UI fix);
the pool translates Cancel into stopping the workers, the sequential path
keeps the existing heartbeat mechanism.

## Resume

### Files in the working directory

| File | Purpose |
|---|---|
| `ibtool_run.json` | run manifest (new) |
| `IB_Tool_Results/parts/<PART>.gpkg` | result of each finished partition (new) |
| `IB_Tool_Results/IB_Tool2_Log_Fin.txt` | finish log; new line format `PART_64\tparts/PART_64.gpkg\t23` or `PART_9\tskipped` |

### Run manifest `ibtool_run.json`

Contents: format version; input paths and checksums (HU, RN, Part, Aux,
filter file); all processing parameters incl. CRS and partition selection;
plugin version; QGIS version; worker count; created/updated timestamps;
status (`running`, `cancelled`, `failed`, `finished`). Written atomically
(temp file + rename).

### Behaviour

- **Start with "Part-Log löschen" checked:** clear results, new manifest.
- **Start without it (resume):**
  1. Manifest exists and matches current inputs, parameters and QGIS version
     → resume.
  2. Manifest differs → do **not** resume; message listing the differences
     (e.g. "Gebäude-Datei geändert", "QGIS 3.40 → 3.44"); the user either
     starts fresh or restores the previous settings.
  3. For every partition in the finish log: part file exists, opens, and has
     the logged feature count → done; otherwise recompute only this
     partition (WARNING).
  4. Leftover temporary part files are deleted; an incomplete last line in
     the finish log is ignored.
- **Order guarantee:** part file renamed first, finish line second — a crash
  in between leaves a file without a log line (partition recomputed); a log
  line without a complete file cannot occur.
- **Restore settings:** when the user selects a working directory that
  contains a manifest, the dialog offers to load its inputs and parameters
  into the UI ("Einstellungen aus dem Arbeitsverzeichnis übernehmen?").
- **Migration from the previous format:** old finish-log lines (plain names)
  plus `IB_Tool_merge_temp.gpkg` → `IB_Tool_merge_temp.gpkg` is used as the
  base layer of the final merge (as today) and only the remaining partitions
  are processed; logged as "kein Manifest (älterer Lauf)".

### After a complete restart (user procedure)

Start QGIS, open the plugin (settings come from CONFIG.ini or, on request, from
the manifest), leave "Part-Log löschen" unchecked, Start. The plugin reloads
the inputs, recomputes the global density (deterministic), checks the manifest
and the finished parts, processes the rest and merges everything in the fixed
order.

## Debug Mode

Supported in worker mode: each partition already writes to its own folder
`debug/PART_x/`, so there are no write conflicts.

## Testing

### Unit tests (also run in CI on Linux, without real workers)

- `worker_launcher`: Windows interpreter discovery (paths mocked), `None` on
  other platforms, `default_worker_count()` for 1, 2, 4, 16 cores.
- Protocol: encode/decode, lines without prefix ignored.
- `worker_pool` with a **fake worker** script (simulates partitions): largest
  first, crash → replacement + recompute list, `error`, failed self-test →
  sequential, cancel kills all and removes temporary files.
- `run_manifest` / resume: missing / corrupt / wrong feature count → only that
  partition recomputed; manifest mismatch → no resume with a readable list of
  differences; old format + `merge_temp` migrated; truncated last log line
  ignored; atomic writes.
- Final merge: feature order equals the former incremental merge; `fid`
  dropped; output GeoPackage writable.

### Verification with real data

- `scripts/profile_pipeline.py --workers N` uses the real pool.
- Full runs with 1, 3 and 4 workers on QGIS 3.44 and 3.40, each
  `compare_results.py` vs. the reference → **IDENTICAL**; timing recorded.
- Resume test: hard-kill a run after about half of the partitions, restart,
  resume → IDENTICAL.
- **First implementation step (risk spike):** verify that a Python process
  started from the QGIS process via `QProcess` on OSGeo4W inherits a working
  environment (DLL paths, `QGIS_PREFIX_PATH`, Processing).

### GUI tests (user, after restarting QGIS)

Progress and status line with several workers; Cancel during PART_64; closing
QGIS during a run (no leftover `python.exe` in the task manager); restart and
resume incl. the "restore settings" prompt.

## Out of Scope

- Worker mode on Linux/macOS (launcher strategy to be added later).
- Parallelising inside a partition or the global preparation.
- Detecting hung (non-crashing) workers.
- Further single-step optimisations (CreateMST, PatchRemove, ImportFilter) —
  separate roadmap items.
