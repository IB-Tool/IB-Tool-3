# QGIS 4 Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make IB-Tool 3 run unchanged on QGIS 3.40–3.x (Qt5/PyQt5) **and** QGIS 4.x (Qt6/PyQt6) from one code base, and list it as "QGIS 4 ready" on plugins.qgis.org.

**Architecture:** No new compatibility layer. Every Qt/QGIS enum is written in its fully scoped form (works on PyQt5 ≥ 5.11 and PyQt6), Qt5-only calls are replaced by their Qt5+Qt6 equivalents, and a static guard test keeps Qt5-only spellings from coming back. CI gets a QGIS 4 job; the official `pyqgis4-checker` and a manual Windows run with worker mode confirm the result.

**Tech Stack:** QGIS 3.40 / 3.44 LTR / 4.x, `qgis.PyQt` shim, pytest, Docker, GitHub Actions, `pyqgis4-checker`.

**Spec:** https://plugins.qgis.org/docs/migrate-qgis4 and https://github.com/qgis/QGIS/wiki/Plugin-migration-to-be-compatible-with-Qt5-and-Qt6 (read 2026-11-03). Key points:
- `metadata.txt`: keep `qgisMinimumVersion`, set `qgisMaximumVersion=4.99`; without it QGIS 4 does not load the plugin. `supportsQt6=True` is obsolete and must not be added.
- Import Qt only via `qgis.PyQt` (already enforced by `test/test_qt_imports.py`).
- Enums must be fully scoped (`Qt.ItemDataRole.UserRole`, `Qgis.MessageLevel.Critical`, `QgsWkbTypes.GeometryType.PolygonGeometry`, `QMessageBox.StandardButton.Ok`, …).
- `QAction` moved from QtWidgets to QtGui in Qt6.
- Test on a QGIS 4 build; plugins.qgis.org runs `pyqgis4-checker` on upload (informational, "Qt6 Check" tab).
- The automatic `pyqt5_to_pyqt6.py` script "might not do all necessary changes" → manual review required.

## Inventory (scan of 2026-11-03, shipping code = `helpers/`, `ibtool/`, `ibtool_tools/`)

Already fine: no direct `PyQt5` imports in shipping code; `.ui` loaded via `qgis.PyQt.uic`; `QgsField(..., QMetaType...)` instead of `QVariant`; `Qgis.EndCapStyle`/`JoinStyle`/`MakeValidMethod` already scoped; signals, `bytes(QByteArray)` and `QgsApplication` calls are Qt6-safe; no `QRegExp`, `QDesktopWidget`, `QTextCodec`.

| Qt5-only spelling | Replacement (works on 3.40 and 4.x) | Locations |
|---|---|---|
| `QMetaType.Double/Int/QString` (41×) | `QMetaType.Type.Double/Int/QString` | `helpers/edge_catch_utils.py`, `helpers/geometry_utils.py`, `helpers/mst_utils.py`, `ibtool_tools/Blocker.py`, `FootprintDensity.py`, `ImportFilter.py`, `MST_Clustering.py`, `PatchRemove.py`, `mst/delaunay_processor.py`, `mst/street_processor.py` |
| `.exec_()` | `.exec()` | `helpers/worker_pool.py:86`, `ibtool/ibtool.py:775`, `ibtool/ibtool.py:1559`, `scripts/profile_pipeline.py:200`, `test/test_worker_pool.py:35` |
| `QProcess.NotRunning` / `QProcess.FailedToStart` | `QProcess.ProcessState.NotRunning` / `QProcess.ProcessError.FailedToStart` | `helpers/worker_pool.py:63,181,190,229,237` |
| `QMessageBox.Yes/No` | `QMessageBox.StandardButton.Yes/No` | `ibtool/ibtool.py:597-598,984-987` |
| `QFileDialog.ShowDirsOnly \| DontResolveSymlinks` | `QFileDialog.Option.…` | `helpers/data_loader.py:88` |
| `QDialogButtonBox.Close` | `QDialogButtonBox.StandardButton.Close` | `ibtool/ibtool_dialog.py:296` |
| `Qt.Horizontal` | `Qt.Orientation.Horizontal` | `ibtool/ibtool_dialog.py:272` |
| `QAction` from `QtWidgets` | `QtGui` on Qt6, `QtWidgets` on Qt5 (try/except) | `ibtool/ibtool.py:32`, `test/test_ibtool.py:513,623,636` |
| `QgsWkbTypes.PolygonGeometry/LineGeometry/PointGeometry` | `Qgis.GeometryType.Polygon/Line/Point` | `helpers/check.py`, `helpers/edge_catch_utils.py`, `helpers/geometry_utils.py`, `helpers/overlay_utils.py`, `ibtool_tools/ErodeEmptyAreas.py`, `ImportFilter.py`, `MST_Clustering.py` |
| `QgsWkbTypes.GeometryCollection` | `Qgis.WkbType.GeometryCollection` | `helpers/overlay_utils.py:78` |
| `Qgis.Info/Warning/Critical/Success` | `Qgis.MessageLevel.…` | `helpers/logger.py:183-192`, `helpers/message.py:6-12` |
| `QgsVectorFileWriter.NoError` / `.CreateOrOverwriteFile` | `QgsVectorFileWriter.WriterError.NoError` / `QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile` | `helpers/partition_results.py:95`, `helpers/system_utils.py:190,204` |
| `QgsVectorDataProvider.CreateSpatialIndex` | `Qgis.VectorProviderCapability.CreateSpatialIndex` | `helpers/geometry_utils.py:53,102,142,177` |
| Tests: `from PyQt5…`, `QVariant.Int/String/Double`, `QMetaType.QString`, `QgsWkbTypes.LineString/MultiPolygon/PolygonGeometry`, `QLocale.Germany/German`, `@patch('PyQt5.QtWidgets.QFileDialog…')` | `qgis.PyQt`, `QMetaType.Type.…`, `Qgis.WkbType.…`, `Qgis.GeometryType.…`, `QLocale.Country.Germany`/`QLocale.Language.German`, `@patch('qgis.PyQt.QtWidgets.QFileDialog…')` | 19 test files (see Task 5) |

Static functions such as `QgsWkbTypes.flatType()`, `multiType()`, `isMultiType()`, `geometryDisplayString()` remain valid in QGIS 4 and are not touched.

## Global Constraints

- `qgisMinimumVersion=3.40` stays; `qgisMaximumVersion=4.99`; no `supportsQt6` key.
- One code base for Qt5 and Qt6 — no `if Qt6:` branches except the `QAction` import.
- Qt only via `qgis.PyQt`, never `PyQt5`/`PyQt6` — also in tests after Task 5.
- No new runtime dependencies (numpy, scipy, networkx, PyQt only).
- Must work with NumPy 1.x and 2.x.
- Processing results must be identical before and after the migration (pure spelling changes, no logic changes — see `ai/tasks/refactor-task.md`).
- Documentation in English; UI strings stay translatable via `tr()`.
- Never run `git commit` unless the user explicitly asks; "Commit" steps below mean "propose the commit".

## Review Focus

1. **Worker mode on QGIS 4 / Windows** — `helpers/worker_launcher.py` takes `pythonw.exe` from `sys.exec_prefix` and the worker inherits PATH/QT_PLUGIN_PATH; a QGIS 4 install may lay out Python differently. Expected: parallel partitions run, or a clean fallback to sequential mode with a log message. Covered by the manual check in Task 7.
2. **NULL attribute values** — PyQt6 may hand out `None` where PyQt5 gave a NULL `QVariant`. `helpers/check.py:495,575` and `helpers/edge_catch_utils.py:654` must treat both as "empty". Covered by the existing NULL-QVariant test in `test/test_edge_catch_utils.py` running in the QGIS 4 CI job (Task 6).
3. **Processing algorithm ids** — 6 calls still use `qgis:` ids (`qgis:dissolve`, `qgis:mergevectorlayers`, `qgis:fieldcalculator`, `qgis:checkvalidity`, `qgis:heatmapkerneldensityestimation`). Expected: every id resolves in QGIS 4. Covered by `test_all_processing_ids_resolve` (Task 4).
4. **Dialog loading** — `ibtool_dialog_base.ui` contains `Qt::AlignRight|Qt::AlignTrailing|Qt::AlignVCenter`, `QFrame::…`, `QFormLayout::…`; PyQt6 `uic` must load it, and the German `.qm` must load with Qt6's `QTranslator`. Covered by `test/test_ibtool_dialog.py` + translation tests in the QGIS 4 CI job (Task 6) and the manual check (Task 7).
5. **Identical results QGIS 3 vs. 4** — same sample data (`Testdaten/`) must give the same Innenbereich polygons. Covered by the manual comparison in Task 7.

---

### Task 1: Qt6 guard test + Qt enum / `exec_` fixes

**Files:**
- Create: `test/test_qt6_compat.py`
- Modify: `helpers/worker_pool.py`, `helpers/data_loader.py:88`, `ibtool/ibtool.py:597-598,775,984-987,1559`, `ibtool/ibtool_dialog.py:272,296`, `scripts/profile_pipeline.py:200`, `test/test_worker_pool.py:35`

**Interfaces:**
- Produces: `test/test_qt6_compat.py` with module constants `SHIPPING_DIRS = ("helpers", "ibtool", "ibtool_tools", "scripts")` and `FORBIDDEN: dict[str, str]` (group name → regex) plus helper `_offenders(pattern: str, dirs: tuple[str, ...]) -> list[str]` returning `"path:line: text"` entries. Later tasks add groups to `FORBIDDEN` and, in Task 5, `"test"` to the scanned dirs.

- [ ] **Step 1: Write the failing guard test** — parametrized over `FORBIDDEN.items()`, `assert _offenders(pattern, SHIPPING_DIRS) == []`. Initial groups:

```python
FORBIDDEN = {
    "exec_": r"\.exec_\(",
    "qt-orientation": r"\bQt\.(Horizontal|Vertical)\b",
    "qmessagebox-buttons": r"\bQMessageBox\.(Yes|No|Ok|Cancel)\b",
    "qdialogbuttonbox-buttons": r"\bQDialogButtonBox\.(Close|Ok|Cancel)\b",
    "qfiledialog-options": r"\bQFileDialog\.(ShowDirsOnly|DontResolveSymlinks)\b",
    "qprocess-enums": r"\bQProcess\.(NotRunning|Starting|Running|FailedToStart|Crashed)\b",
}
```

Skip `__pycache__`; mark `@pytest.mark.unit`.

- [ ] **Step 2: Run** `pytest test/test_qt6_compat.py -v` — Expected: FAIL, offenders listed for every group.
- [ ] **Step 3: Replace the spellings** per the Inventory table (rows `.exec_()`, `QProcess`, `QMessageBox`, `QFileDialog`, `QDialogButtonBox`, `Qt.Horizontal`).
- [ ] **Step 4: Run** `pytest test/test_qt6_compat.py test/test_worker_pool.py test/test_ibtool.py test/test_ibtool_dialog.py test/test_data_loader.py -v` — Expected: PASS.
- [ ] **Step 5: Commit** (on user request) `refactor(qt6): scope Qt enums, replace exec_()`

### Task 2: `QMetaType` and `QAction`

**Files:**
- Modify: the 10 `QMetaType` files from the Inventory, `ibtool/ibtool.py:24-36`, `test/test_ibtool.py:513,623,636`
- Test: `test/test_qt6_compat.py`

**Interfaces:**
- Consumes: `FORBIDDEN`, `_offenders` from Task 1.

- [ ] **Step 1: Add groups** to `FORBIDDEN`:
  - `"qmetatype-unscoped": r"\bQMetaType\.(?!Type\b)[A-Z]\w*"`
  - `"qaction-from-qtwidgets"`: a multiline check that `QAction` is not imported **only** from `qgis.PyQt.QtWidgets` — implement as a separate test `test_qaction_import_is_qt6_safe` asserting that every file importing `QAction` contains `from qgis.PyQt.QtGui import QAction`.
- [ ] **Step 2: Run** `pytest test/test_qt6_compat.py -v` — Expected: FAIL for the new groups.
- [ ] **Step 3: Replace** `QMetaType.X` → `QMetaType.Type.X`; in `ibtool/ibtool.py` remove `QAction` from the QtWidgets import and add

```python
try:
    from qgis.PyQt.QtGui import QAction          # Qt6 (QGIS 4)
except ImportError:
    from qgis.PyQt.QtWidgets import QAction      # Qt5 (QGIS 3)
```

Apply the same in the three places in `test/test_ibtool.py`.
- [ ] **Step 4: Run** `pytest test/ -v -m "not slow"` (Docker 3.40) — Expected: PASS, no change in field types of written layers (`test_geometry_utils.py`, `test_mst_clustering.py`, `test_footprint_density.py` cover them).
- [ ] **Step 5: Commit** (on user request) `refactor(qt6): scoped QMetaType, Qt6-safe QAction import`

### Task 3: QGIS enums

**Files:**
- Modify: `helpers/check.py`, `helpers/edge_catch_utils.py`, `helpers/geometry_utils.py`, `helpers/overlay_utils.py`, `helpers/logger.py`, `helpers/message.py`, `helpers/partition_results.py`, `helpers/system_utils.py`, `ibtool_tools/ErodeEmptyAreas.py`, `ibtool_tools/ImportFilter.py`, `ibtool_tools/MST_Clustering.py`
- Test: `test/test_qt6_compat.py`

- [ ] **Step 1: Add groups** to `FORBIDDEN`:
  - `"qgswkbtypes-enum": r"\bQgsWkbTypes\.[A-Z]\w*"` (static functions start lowercase and stay allowed)
  - `"qgis-messagelevel": r"\bQgis\.(Info|Warning|Critical|Success|NoLevel)\b"`
  - `"qgsvectorfilewriter-enum": r"\bQgsVectorFileWriter\.(NoError|CreateOrOverwriteFile|CreateOrOverwriteLayer|AppendToLayerNoNewFields|AppendToLayerAddFields)\b"`
  - `"qgsvectordataprovider-caps": r"\bQgsVectorDataProvider\.[A-Z]\w*"`
- [ ] **Step 2: Run** `pytest test/test_qt6_compat.py -v` — Expected: FAIL for the new groups.
- [ ] **Step 3: Replace** per Inventory (incl. docstrings in `logger.py`/`message.py`). `message.msg(message: object, level: Qgis.MessageLevel = Qgis.MessageLevel.Info) -> None`; `logger` mapping values become `Qgis.MessageLevel.…`.
- [ ] **Step 4: Run** `pytest test/ -v` (Docker 3.40 and 3.44) — Expected: PASS (`test_check.py`, `test_logger.py`, `test_message.py`, `test_overlay_utils.py`, `test_erode_empty_areas.py`, `test_partition_results.py`).
- [ ] **Step 5: Commit** (on user request) `refactor(qgis4): use scoped Qgis enums`

### Task 4: Processing algorithm ids resolve

**Files:**
- Create: `test/test_processing_ids.py`
- Modify (only if Step 2 fails on QGIS 4): the file calling the unresolved `qgis:` id → its `native:` equivalent

**Interfaces:**
- Produces: `_algorithm_ids() -> set[str]` — all first string arguments of `processing.run(` and `safe_processing_run(` in shipping code, regex `(?:processing\.run|safe_processing_run)\(\s*["']([a-z]+:[a-z_]+)["']`.

- [ ] **Step 1: Write** `test_all_processing_ids_resolve`: for each id assert `QgsApplication.processingRegistry().algorithmById(alg_id) is not None` (Processing initialized as in `test/conftest.py`); plus `test_algorithm_ids_found` asserting `len(_algorithm_ids()) >= 40` so a broken regex cannot pass silently.
- [ ] **Step 2: Run** in Docker 3.40 and in the QGIS 4 image from Task 6 — Expected: PASS on 3.40; on 4.x any failure names the id to replace.
- [ ] **Step 3: Replace** unresolved ids only (e.g. `qgis:fieldcalculator` → `native:fieldcalculator`); parameter names must be checked with `processing.algorithmHelp(id)` because they may differ.
- [ ] **Step 4: Run** `pytest test/ -v` — Expected: PASS on 3.40, 3.44 and 4.x.
- [ ] **Step 5: Commit** (on user request) `test(qgis4): verify processing algorithm ids`

### Task 5: Make the test suite Qt6-ready

**Files:**
- Modify: `test/test_add_single_building.py`, `test_blocker.py`, `test_check.py`, `test_create_mst.py`, `test_data_loader.py`, `test_edge_catch.py`, `test_edge_catch_utils.py`, `test_fixtures_mst.py`, `test_footprint_density.py`, `test_geometry_utils.py`, `test_hole_close.py`, `test_ibtool_dialog.py`, `test_import_filter.py`, `test_mst_clustering.py`, `test_mst_components.py`, `test_mst_utils.py`, `test_nodes_detect.py`, `test_overlay_utils.py`, `test_patch_remove.py`, `test/layer_factories.py` (if affected)
- Modify: `test/test_qt_imports.py`, `test/test_qt6_compat.py`

- [ ] **Step 1: Extend guards**: `test_qt_imports.py` also scans `test/` (excluding itself); `test_qt6_compat.py` scans `SHIPPING_DIRS + ("test",)` (excluding itself) and gains groups `"qvariant-types": r"\bQVariant\.(Int|String|Double|Bool|LongLong|Date|DateTime)\b"` and `"qlocale-enum": r"\bQLocale\.(Germany|German)\b"`; `@patch` targets `'PyQt5.…'` are caught by the import guard regex extended to `["']PyQt[56]\.`.
- [ ] **Step 2: Run** `pytest test/test_qt_imports.py test/test_qt6_compat.py -v` — Expected: FAIL, listing the 19 files.
- [ ] **Step 3: Replace** per the last Inventory row. `QgsField(name, QVariant.Int)` → `QgsField(name, QMetaType.Type.Int)`; `QVariant()` as a NULL value stays (it exists in PyQt6). Keep test assertions unchanged.
- [ ] **Step 4: Run** `pytest test/ -v` in Docker 3.40 — Expected: PASS, same test count as before Task 5.
- [ ] **Step 5: Commit** (on user request) `test(qt6): remove PyQt5 imports and Qt5-only enums from tests`

### Task 6: QGIS 4 in Docker/CI + pyqgis4-checker

**Files:**
- Modify: `Dockerfile`, `.github/workflows/ci.yml`
- Modify (if needed): `test/conftest.py` (QgsApplication init under Qt6)

- [ ] **Step 1: Find the image**: `docker pull 3liz/qgis-platform:4.0`; if the tag does not exist, use `qgis/qgis:4.0` (or the current `qgis/qgis` 4.x release tag). If the base changes, make it a second build arg `QGIS_IMAGE` (default `3liz/qgis-platform`) so 3.40/3.44 stay unchanged.
- [ ] **Step 2: Build and run locally**: `docker build --build-arg QGIS_VERSION=4.0 -t qgis-plugin-test:4 .` then `docker run --rm qgis-plugin-test:4` — Expected: full suite PASS (incl. Task 4 test). Fix failures in the owning module; new Qt6 spellings found here get a `FORBIDDEN` group.
- [ ] **Step 3: Add** `"4.0"` to the CI matrix in `.github/workflows/ci.yml` and update the matrix comment (supported range 3.40–4.x).
- [ ] **Step 4: Run pyqgis4-checker** following the README of https://github.com/qgis/pyqgis4-checker against the plugin root (or `dist/ibtool.zip` from `python scripts/create_release_zip.py`) — Expected: no findings; document remaining informational findings in the PR.
- [ ] **Step 5: Commit** (on user request) `ci: test against QGIS 4`

### Task 7: Metadata, docs, manual Windows verification

**Files:**
- Modify: `metadata.txt` (`qgisMaximumVersion=4.99`, changelog line), `test/test_init.py`, `docs/CHANGELOG.md`, `CLAUDE.md` (Prerequisites), `README.md`, `docs/quickstart.md`, `ai/core/release-conventions.md`, `ai/core/qgis-api-rules.md` (add "always use fully scoped enums; import QAction Qt6-safe")

- [ ] **Step 1: Write failing test** in `test/test_init.py`: `test_metadata_supports_qgis4` — `qgisMaximumVersion == "4.99"`, `qgisMinimumVersion == "3.40"`, `"supportsQt6" not in metadata`.
- [ ] **Step 2: Run** `pytest test/test_init.py -v` — Expected: FAIL (`3.50`).
- [ ] **Step 3: Update** `metadata.txt` and docs (supported range "QGIS 3.40–4.x"; scipy/networkx install hint also for QGIS 4 OSGeo4W shell).
- [ ] **Step 4: Run** `pytest test/test_init.py -v` and `python ci/qgis_plugin_validate.py` — Expected: PASS.
- [ ] **Step 5: Manual check on Windows QGIS 4** (user, see "How to verify"): `pip install scipy networkx` in the QGIS 4 OSGeo4W shell; install `dist/ibtool.zip`; run `Testdaten/` with workers = 4 and with workers = 1; compare feature count and total area of the result with a QGIS 3.44 run of the same data — Expected: identical; log shows workers started (or a clean fallback message); German UI loads; dialog, filter preview, result buttons work.
- [ ] **Step 6: Commit** (on user request) `release: declare QGIS 4 compatibility`

## How to verify (manual, Windows)

1. Install QGIS 4 in parallel (OSGeo4W installer, separate profile is created automatically).
2. In the QGIS 4 OSGeo4W shell: `pip install scipy networkx`.
3. Plugins → Install from ZIP → `dist/ibtool.zip`.
4. Run the sample data (`Testdaten/`) once with 4 workers, once with 1; check the log for worker start/fallback.
5. Load both results and the QGIS 3.44 result; compare with *Vector → Analysis Tools → Basic statistics* on `$area` (count and sum must match).
6. Switch QGIS locale to German, restart, check that all UI texts are German.

---

## Status (2026-11-03, paused by user) — resume here

Everything below is **uncommitted** on branch `qgis4_migration` (~60 files). Ledger with all rulings:
`.superpowers/sdd/2026-11-03-qgis4-migration/progress.md` (git-ignored).

**Done (Tasks 1–5, Task 6 tests, Task 7 code/docs):**
- All Qt/QGIS enums scoped, `exec()`, Qt6-safe `QAction` import, tests Qt6-ready, guards
  `test/test_qt6_compat.py` (incl. root `*.py`, `QDialog.DialogCode`, UTF-8 BOM check), `test/test_qt_imports.py`
  (now scans `test/`), `test/test_processing_ids.py`, `test_metadata_supports_qgis4`.
- `metadata.txt`: `qgisMaximumVersion=4.99`; CI matrix `["3.40", "3.44", "4.0"]`; README, CLAUDE.md,
  `ai/core/qgis-api-rules.md`, `test/__init__.py`, CHANGELOG (Unreleased) updated.
- Found by the QGIS 4 run, not in the original inventory: `helpers/system_utils.version_check()` refused
  Python > 3.12 and QGIS > 3.50 (plugin would abort on QGIS 4). Python upper bound removed, `MAX_QGIS = 49999`.
  Root `__init__.py` `Qgis.Critical` → `Qgis.MessageLevel.Critical`; BOM removed from `ibtool/ibtool.py`.

**Verified:**
- Local QGIS 3.40 (Windows): 1201 passed, only the 2 known `test_create_release_zip` git-on-PATH failures.
- Docker, CI-like (only git-tracked files mounted over `/plugins/ibtool`): QGIS 3.44.15 (Qt 5.15, Py 3.12,
  NumPy 1.26) and QGIS 4.0.3 (Qt 6.8.2, Py 3.13, NumPy 2.2): 1204 passed, exit 0, twice each.
- Processing ids incl. `qgis:*` all resolve on QGIS 4.0.

**Open:**
1. **Exit 139 (segfault at interpreter shutdown, after all tests pass)** on QGIS 3.44 only when running the
   image built by `docker build .` (bakes untracked local files, e.g. `docs/img/_src/**` debug GPKGs, into
   `/plugins/ibtool`). HEAD in the same image via mount: exit 0; branch via mount (= CI): exit 0. Not
   reproducible CI-style → likely local-build artefact, not yet proven. If CI's 3.44 job shows exit 139, start
   here (faulthandler shows no Python frame; reduction stuck at 14 files → object-count/teardown order).
   Option: extend `.dockerignore` with `docs/img/_src`.
2. Re-run `pyqgis4-checker` (dry run) after the root-`__init__` and BOM fixes; first run only found those two:
   `docker run --rm --pull always --workdir /workspace/ -v "<copy>:/workspace/" ghcr.io/qgis/pyqgis4-checker:main-ubuntu pyqt5_to_pyqt6.py --dry_run --logfile /workspace/pyqt6_checker.log ibtool`
   (run on a copy of `__init__.py metadata.txt helpers ibtool ibtool_tools scripts test`, not the repo — avoids `.venv`).
3. Final whole-branch review (executing-plans skill), then commit on user request.
4. Manual Windows QGIS 4 check (section "How to verify"), especially worker mode (`helpers/worker_launcher.py`).
5. Deferred minors: `QgsVectorFileWriter.writeAsVectorFormat()` deprecated (`helpers/geometry_utils.py:73,77`,
   works on 4.0); `MIN_PYTHON = (3, 9)` vs `pythonMinimumVersion=3.11` in metadata; pre-existing
   `SyntaxWarning` in `test/test_import_filter.py:470`.

**Disk note:** Docker data was moved to another drive by the user (C: had filled up). Local images
`qgis-plugin-test:4.0` / `:3.44` can be removed with `docker rmi`.

### Update 2026-11-04 — open items 1–3 closed

- **Exit 139:** `.dockerignore` now excludes `docs/img/_src/{debug,IB_Tool_Results,figures_preview.png}` and
  `symbology-style.db` (also added to `.gitignore`). Rebuilt 3.44 image: exit 0 in three runs.
- **pyqgis4-checker** re-run: one finding (`QVariant()` as NULL in `test/test_edge_catch_utils.py`) → `qgis.core.NULL`;
  second run clean.
- **Final review** done ("with fixes"); fixed: `docs/contributing.md`, `docs/quickstart.md`, `Dockerfile` header,
  `test/test_qgis_environment.py` docstring, CHANGELOG "Fixed" bullets, `ai/core/release-conventions.md` invariant,
  guard extended (`qt-namespace-unscoped`, `qgsfeaturerequest-enum`, `qgsprocessing-sourcetype`), NULL tests in
  `test/test_check.py` assert the NULL branch.
- **Verified:** local 3.40: 1204 passed (+2 known git-on-PATH failures); Docker 3.44 and 4.0: 1207 passed, exit 0.
- **Still open:** manual Windows QGIS 4 check (item 4, user), deferred minors (item 5), commit on user request.

### Update 2026-11-04 (2) — items 4 and 5 closed

- **Item 4 (QGIS 4 on Windows), headless:** local OSGeo4W QGIS 4.2.3 (Qt 6.11) with scipy/networkx installed;
  `scripts/profile_pipeline.py` on `Testdaten/` with `--workers 4` and `--workers 1`, compared with
  `scripts/compare_results.py` against a QGIS 3.44 LTR run (4 workers): IDENTICAL (172 features, sym. diff 0 m²);
  worker self-test passed, no recompute. Not covered headless: GUI dialog, German UI, result buttons (user check).
- **Item 5:** `MIN_PYTHON = (3, 11)` (+ sync test with metadata), `writeAsVectorFormat` -> `writeAsVectorFormatV3`
  (+ content test), `SyntaxWarning` in `test/test_import_filter.py` fixed.
- **Left:** short GUI check on QGIS 4 by the user; commit on user request.

### Update 2026-11-04 (3) — release 0.3.0 prepared

- plugins.qgis.org rules added to `ci/qgis_plugin_validate.py` (+ `test/test_plugin_validate.py`), CI job
  `qt6-check`, project skill `/release-plugin` (`.claude/commands/release-plugin.md`). CI builds no ZIP (user decision).
- Release prepared with the skill: `version=0.3.0`, metadata changelog/about updated, `docs/CHANGELOG.md` section
  `0.3.0 — 2026-11-04`, README for QGIS 4. `MIN_PYTHON` stays 3.11 (user decision, Ubuntu 22.04 / Python 3.10 refused).
- Left: GUI check on QGIS 3.44 and 4 (user), commit + tag `v0.3.0` + upload on user request.
