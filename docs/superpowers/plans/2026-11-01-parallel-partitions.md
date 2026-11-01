# Parallel Partitions (Worker Processes) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Process the partitions of an IB-Tool run in parallel worker processes on Windows, with identical results, robust resume via a run manifest, and an automatic sequential fallback.

**Architecture:** One GUI-free `run_partition()` is the only partition pipeline. Every partition (sequential or worker) writes `IB_Tool_Results/parts/<PART>.gpkg`; one final merge builds the output in the former order. On Windows, `WorkerPool` (QObject) drives N `QProcess` workers running `ibtool/partition_worker.py` over a JSON-lines protocol; a self-test decides worker vs. sequential mode. `ibtool_run.json` in the working directory guards resume and can restore the UI settings.

**Tech Stack:** Python 3.11+ (QGIS-bundled), PyQGIS 3.40–3.50, PyQt5 (`QProcess`, `QEventLoop`), pytest, stdlib only (no new dependencies).

**Spec:** `docs/superpowers/specs/2026-11-01-parallel-partitions-design.md`
**Roadmap:** `docs/superpowers/plans/2026-11-01-runtime-optimization.md` (Phase 4)

## Global Constraints

- QGIS 3.40–3.50; must work with NumPy 1.x and 2.x; Python ≥ 3.11.
- **No new dependencies** (no psutil etc.) — stdlib + QGIS/PyQt only.
- Worker mode **Windows only** for now; all platform-specific code lives in `helpers/worker_launcher.py`; on every other platform `find_worker_command()` returns `None` → sequential.
- Worker count default: `max(1, min(4, physical_cores - 1))`; `1` = sequential; UI field + CONFIG.ini (`worker_count`, `0` = automatic).
- Results must be **IDENTICAL** to the references (`compare_results.py`, tolerance 0.001 m²): QGIS 3.44 → `C:\Users\Oliver\Downloads\Test1\ibtool_reference\result_testdaten_qgis344.gpkg`, QGIS 3.40 → `...\result_testdaten_2026-11-01_deterministic.gpkg`.
- A worker-mode problem may only make a run slower, never change its result.
- Only the plugin (main process) writes the finish log and the manifest; workers never write log files.
- Developer docs (`docs/`, `ai/`, code comments) in **English**; UI strings and end-user log messages may be German.
- Every `processing.run()` passes `context=current_processing_context()` (see `ai/core/constraints.md`).
- Files are CRLF; `ibtool/ibtool.py` has a UTF-8 BOM — edit with tools that preserve both (the Edit tool does; for scripted edits use the byte-preserving pattern used before in this branch).
- **Never commit without the user's explicit go-ahead** (project rule). "Commit" steps below mean: stop, report, let the user commit.

### Test commands

- Unit/integration tests (QGIS 3.40, full pytest works there):
  `"C:\Program Files\QGIS 3.40.0\bin\python-qgis.bat" -m pytest test/<file>.py -q -p no:cacheprovider`
- Known unrelated failures: 2 tests in `test/test_create_release_zip.py` (git not on PATH in that environment).
- QGIS 3.44 LTR (user's GUI; pytest does not start there — `DLL load failed`): run scripts with
  `"C:\Users\Oliver\AppData\Local\Programs\OSGeo4W\bin\python-qgis-ltr.bat" scripts\<script>.py ...`
- Docker 3.44 image (NumPy 1.26): `docker build --build-arg QGIS_VERSION=3.44 -t ibtool-test-344 . && docker run --rm ibtool-test-344`

## Review Focus

1. **Working directory path with spaces and umlauts** (e.g. `C:\Daten\IB Läufe\Testlauf 1`) — workers must start, read inputs and write parts; expected: same result as without special characters. Test: Task 6 `test_worker_handles_path_with_space_and_umlaut`.
2. **Partition names that are not valid file names** (`PART/7`, `Teil: Nord`, `"A"`) — part files must still be written and found again on resume; expected: sanitized, collision-free file names. Test: Task 4 `test_part_file_name_is_sanitized_and_unique`.
3. **Changing only the worker count between interruption and resume** — must NOT block resume. Test: Task 5 `test_worker_count_does_not_invalidate_resume`.
4. **Output GeoPackage open/locked or parts folder not writable** — expected: clear error message, no corrupted finish log, finished parts kept. Test: Task 4 `test_failed_part_write_leaves_no_finish_line`.
5. **Slow or blocked worker start (antivirus, cold disk)** — expected: self-test timeout → sequential fallback with WARNING, run completes. Test: Task 7 `test_selftest_timeout_falls_back`.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `helpers/worker_launcher.py` | new | Platform-specific: find worker interpreter/environment (Windows), `default_worker_count()`, parent-process check |
| `helpers/worker_protocol.py` | new | JSON-lines protocol: message builders, `encode()`, `parse_line()` |
| `helpers/partition_pipeline.py` | new | `run_partition()` — the partition pipeline without UI |
| `helpers/partition_results.py` | new | Part files (atomic write, sanitized names), finish log (new + old format), resume validation, final merge |
| `helpers/run_manifest.py` | new | `ibtool_run.json`: build, write (atomic), read, compare |
| `helpers/worker_pool.py` | new | `WorkerPool(QObject)`: QProcess workers, self-test, scheduling, crash/error → recompute list, cancel |
| `ibtool/partition_worker.py` | new | Worker program (stdin → `run_partition` → stdout events) |
| `ibtool/ibtool.py` | modify | `start_processing()` orchestration, `_run_partition_pipeline` → wrapper, cancel/unload kill workers, manifest restore prompt, worker-count field |
| `ibtool/ibtool_dialog_base.ui` | modify | `WorkerCountBox` (QSpinBox) in `formLayoutDebug` row 6 |
| `helpers/config_manager.py` | modify | `ProcessingConfig.worker_count` (0 = automatic) |
| `i18n/IBTool_de.ts` / `.qm` | modify | translations for new UI strings |
| `scripts/profile_pipeline.py` | modify | `--workers N` uses the real pool |
| `scripts/resume_test.py` | new | Dev tool: hard-kill a run mid-way, resume, compare |
| `test/test_worker_launcher.py`, `test_worker_protocol.py`, `test_partition_pipeline.py`, `test_partition_results.py`, `test_run_manifest.py`, `test_worker_pool.py`, `test_partition_worker.py` | new | tests |
| `test/fake_worker.py` | new | fake worker for pool tests (no QGIS) |
| `test/test_ibtool.py` | modify | orchestration tests; existing `TestRunPartitionPipeline` patch targets move to `ibtool.helpers.partition_pipeline` |
| docs: `CHANGELOG.md`, `how-it-works.md` (Output section), `CONFIG_README.md`, `plugin-architecture.md`, roadmap | modify | documentation |

---

### Task 1: Worker launcher + environment spike

**Files:**
- Create: `helpers/worker_launcher.py`
- Test: `test/test_worker_launcher.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class WorkerCommand: program: str; arguments: list[str]`
  - `find_worker_command(plugin_root: str) -> Optional[WorkerCommand]`
  - `default_worker_count(physical_cores: Optional[int] = None) -> int`
  - `physical_core_count() -> int`
  - `parent_alive(pid: int) -> bool`
  - constant `WORKER_SCRIPT = "ibtool/partition_worker.py"` (relative to plugin root)

- [ ] **Step 1: Write the failing tests**

```python
# test/test_worker_launcher.py
# -*- coding: utf-8 -*-
"""Tests for helpers/worker_launcher.py (platform-specific worker start)."""
import os
from unittest.mock import patch

import pytest

from ibtool.helpers import worker_launcher as wl


class TestDefaultWorkerCount:

    @pytest.mark.unit
    @pytest.mark.parametrize("cores, expected", [(1, 1), (2, 1), (4, 3), (5, 4), (16, 4)])
    def test_formula(self, cores, expected):
        assert wl.default_worker_count(cores) == expected

    @pytest.mark.unit
    def test_uses_detected_cores(self):
        with patch.object(wl, "physical_core_count", return_value=4):
            assert wl.default_worker_count() == 3


class TestFindWorkerCommand:

    @pytest.mark.unit
    def test_none_on_non_windows(self, tmp_path):
        with patch.object(wl.sys, "platform", "linux"):
            assert wl.find_worker_command(str(tmp_path)) is None

    @pytest.mark.unit
    def test_windows_prefers_pythonw(self, tmp_path):
        prefix = tmp_path / "apps" / "Python312"
        prefix.mkdir(parents=True)
        (prefix / "python.exe").write_text("")
        (prefix / "pythonw.exe").write_text("")
        plugin = tmp_path / "plugin"
        (plugin / "ibtool").mkdir(parents=True)
        (plugin / "ibtool" / "partition_worker.py").write_text("")
        with patch.object(wl.sys, "platform", "win32"), \
                patch.object(wl.sys, "exec_prefix", str(prefix)):
            cmd = wl.find_worker_command(str(plugin))
        assert cmd.program == str(prefix / "pythonw.exe")
        assert cmd.arguments == ["-u", str(plugin / "ibtool" / "partition_worker.py")]

    @pytest.mark.unit
    def test_windows_without_interpreter_returns_none(self, tmp_path):
        with patch.object(wl.sys, "platform", "win32"), \
                patch.object(wl.sys, "exec_prefix", str(tmp_path)):
            assert wl.find_worker_command(str(tmp_path)) is None

    @pytest.mark.unit
    def test_windows_without_worker_script_returns_none(self, tmp_path):
        (tmp_path / "python.exe").write_text("")
        with patch.object(wl.sys, "platform", "win32"), \
                patch.object(wl.sys, "exec_prefix", str(tmp_path)):
            assert wl.find_worker_command(str(tmp_path / "noplugin")) is None


class TestParentAlive:

    @pytest.mark.unit
    def test_own_process_is_alive(self):
        assert wl.parent_alive(os.getpid()) is True

    @pytest.mark.unit
    def test_unused_pid_is_not_alive(self):
        assert wl.parent_alive(0x7FFFFFF0) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `"C:\Program Files\QGIS 3.40.0\bin\python-qgis.bat" -m pytest test/test_worker_launcher.py -q -p no:cacheprovider`
Expected: ImportError `cannot import name 'worker_launcher'`.

- [ ] **Step 3: Implement `helpers/worker_launcher.py`**

```python
# -*- coding: utf-8 -*-
"""Platform-specific part of the worker mode (Phase 4).

Everything that depends on the operating system is here: how to start a
worker (interpreter + script), how many workers to use by default and how a
worker checks that the QGIS process still exists. Worker mode is currently
implemented for Windows (OSGeo4W and the standalone installer); on other
platforms ``find_worker_command`` returns ``None`` and the plugin runs
sequentially. A new platform = a new branch in ``find_worker_command`` and
``parent_alive``.

Copyright: (C) 2026 by Oliver Harig
License: GNU General Public License v2 or later
"""
import ctypes
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

WORKER_SCRIPT = os.path.join("ibtool", "partition_worker.py")
MAX_DEFAULT_WORKERS = 4
"""Upper bound of the automatic worker count (more brought no gain on the sample data)."""


@dataclass(frozen=True)
class WorkerCommand:
    """Program and arguments to start one worker process."""
    program: str
    arguments: list = field(default_factory=list)


def find_worker_command(plugin_root: str) -> Optional[WorkerCommand]:
    """Return how to start a worker on this system, or ``None`` (→ sequential).

    Windows: the Python interpreter of the running QGIS (``sys.exec_prefix``);
    ``pythonw.exe`` is preferred so no console window appears. The worker
    inherits the environment of the QGIS process (PATH with the QGIS DLLs,
    QT_PLUGIN_PATH, ...); QGIS paths are passed in the ``init`` message.

    Args:
        plugin_root: Plugin folder containing ``ibtool/partition_worker.py``.
    """
    if sys.platform != "win32":
        return None
    script = os.path.join(plugin_root, WORKER_SCRIPT)
    if not os.path.isfile(script):
        return None
    for name in ("pythonw.exe", "python.exe"):
        candidate = os.path.join(sys.exec_prefix, name)
        if os.path.isfile(candidate):
            return WorkerCommand(candidate, ["-u", script])
    return None


def physical_core_count() -> int:
    """Number of physical CPU cores (Windows API), else logical cores // 2, at least 1."""
    if sys.platform == "win32":
        try:
            return _windows_physical_cores()
        except (OSError, AttributeError, ValueError):
            pass
    return max(1, (os.cpu_count() or 2) // 2)


def _windows_physical_cores() -> int:
    """Count ``RelationProcessorCore`` entries of GetLogicalProcessorInformation."""
    class _Info(ctypes.Structure):  # SYSTEM_LOGICAL_PROCESSOR_INFORMATION (x64: 32 bytes)
        _fields_ = [("mask", ctypes.c_size_t), ("relationship", ctypes.c_int),
                    ("_union", ctypes.c_byte * 16)]
    kernel32 = ctypes.windll.kernel32
    size = ctypes.c_ulong(0)
    kernel32.GetLogicalProcessorInformation(None, ctypes.byref(size))
    count = size.value // ctypes.sizeof(_Info)
    if count == 0:
        raise ValueError("no processor information")
    buffer = (_Info * count)()
    if not kernel32.GetLogicalProcessorInformation(buffer, ctypes.byref(size)):
        raise OSError("GetLogicalProcessorInformation failed")
    cores = sum(1 for info in buffer if info.relationship == 0)   # RelationProcessorCore
    if cores < 1:
        raise ValueError("no cores reported")
    return cores


def default_worker_count(physical_cores: Optional[int] = None) -> int:
    """``max(1, min(4, physical_cores - 1))`` — leaves one core for QGIS/Windows."""
    cores = physical_cores if physical_cores is not None else physical_core_count()
    return max(1, min(MAX_DEFAULT_WORKERS, cores - 1))


def parent_alive(pid: int) -> bool:
    """True if a process with *pid* exists (used by workers to detect a crashed QGIS)."""
    if sys.platform == "win32":
        synchronize, wait_timeout = 0x00100000, 0x102
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == wait_timeout
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: same command as Step 2. Expected: all PASS (`test_unused_pid_is_not_alive` may need a PID not in use; `0x7FFFFFF0` is not a valid Windows PID).

- [ ] **Step 5: Environment spike (risk check, real QGIS)**

Write `C:\Users\Oliver\AppData\Local\Temp\claude\...\scratchpad\spike_worker_env.py` (throwaway) that, run with `python-qgis-ltr.bat`, starts `find_worker_command(plugin_root).program` via `QProcess` with arguments `["-c", "import sys; sys.path[:0] = <parent sys.path entries containing 'qgis'>; from qgis.core import QgsApplication; a = QgsApplication([], False); a.initQgis(); import processing; print('IBTOOL {\"type\": \"ready\"}', flush=True)"]` and waits for the line (60 s). Then ask the user to paste the same 15-line snippet into the **QGIS 3.44 Python console** (GUI process environment) and report the output.
Expected: `ready` in both cases. If the GUI case fails: record the error in the roadmap and adjust `find_worker_command` (e.g. add `PATH` entries from `QgsApplication.prefixPath()`) before continuing.

- [ ] **Step 6: Commit** (only with the user's go-ahead)

```bash
git add helpers/worker_launcher.py test/test_worker_launcher.py
git commit -m "feat: add worker launcher (Windows) for parallel partitions"
```

---

### Task 2: Worker protocol

**Files:**
- Create: `helpers/worker_protocol.py`
- Test: `test/test_worker_protocol.py`

**Interfaces:**
- Produces:
  - `PREFIX = "IBTOOL "`
  - `encode(message: dict) -> str` (one line incl. `\n`, worker → plugin lines carry `PREFIX`)
  - `encode_command(message: dict) -> bytes` (plugin → worker, no prefix, UTF-8 + `\n`)
  - `parse_line(line: str) -> Optional[dict]` (`None` for lines without prefix or invalid JSON)
  - builders: `init_message(**kw) -> dict`, `run_message(partition: str) -> dict`, `exit_message() -> dict`, `ready_event() -> dict`, `progress_event(partition, phase, phase_name) -> dict`, `log_event(level, message) -> dict`, `done_event(partition, buildings, result_path, feature_count, seconds) -> dict`, `error_event(partition, message, traceback_text) -> dict`
  - message `type` values: `init`, `run`, `exit`, `ready`, `progress`, `log`, `done`, `error`

- [ ] **Step 1: Write the failing tests**

```python
# test/test_worker_protocol.py
# -*- coding: utf-8 -*-
"""Tests for helpers/worker_protocol.py (JSON-lines protocol plugin <-> worker)."""
import pytest

from ibtool.helpers import worker_protocol as wp


class TestProtocol:

    @pytest.mark.unit
    def test_event_round_trip(self):
        line = wp.encode(wp.done_event("PART_64", 7139, "parts/PART_64.gpkg", 23, 59.7))
        assert line.startswith(wp.PREFIX) and line.endswith("\n")
        assert wp.parse_line(line) == {"type": "done", "partition": "PART_64", "buildings": 7139,
                                       "result": "parts/PART_64.gpkg", "features": 23,
                                       "seconds": 59.7}

    @pytest.mark.unit
    @pytest.mark.parametrize("line", ["", "QGIS: warning foo\n", "IBTOOL not json\n",
                                      "IBTOOL [1, 2]\n", "IBTOOL {\"no_type\": 1}\n"])
    def test_foreign_or_broken_lines_are_ignored(self, line):
        assert wp.parse_line(line) is None

    @pytest.mark.unit
    def test_unicode_and_paths_survive(self):
        msg = wp.log_event("INFO", "Pfad C:\\Daten\\IB Läufe\\Teil: Nord")
        assert wp.parse_line(wp.encode(msg)) == msg

    @pytest.mark.unit
    def test_command_encoding(self):
        raw = wp.encode_command(wp.run_message("PART_7"))
        assert raw == b'{"type": "run", "partition": "PART_7"}\n'

    @pytest.mark.unit
    def test_one_line_per_message(self):
        msg = wp.error_event("PART_1", "boom", "Traceback...\nline 2\n")
        assert wp.encode(msg).count("\n") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `"C:\Program Files\QGIS 3.40.0\bin\python-qgis.bat" -m pytest test/test_worker_protocol.py -q -p no:cacheprovider`
Expected: ImportError.

- [ ] **Step 3: Implement `helpers/worker_protocol.py`**

```python
# -*- coding: utf-8 -*-
"""JSON-lines protocol between the plugin and its worker processes.

One JSON object per line. Worker → plugin lines start with ``PREFIX`` so that
stray output of QGIS/GDAL on stdout can never be mistaken for a message.
Plugin → worker commands are plain JSON lines on stdin.

Copyright: (C) 2026 by Oliver Harig
License: GNU General Public License v2 or later
"""
import json
from typing import Optional

PREFIX = "IBTOOL "


def encode(message: dict) -> str:
    """Worker → plugin: one prefixed line (JSON escapes newlines in strings)."""
    return PREFIX + json.dumps(message, ensure_ascii=False) + "\n"


def encode_command(message: dict) -> bytes:
    """Plugin → worker: one UTF-8 JSON line for the worker's stdin."""
    return (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")


def parse_line(line: str) -> Optional[dict]:
    """Return the message of a prefixed line, ``None`` for anything else."""
    if not line.startswith(PREFIX):
        return None
    try:
        message = json.loads(line[len(PREFIX):])
    except ValueError:
        return None
    if not isinstance(message, dict) or "type" not in message:
        return None
    return message


def init_message(**fields) -> dict:
    """Plugin → worker, once: inputs, CRS, parameters, workspace, ... (see worker)."""
    return {"type": "init", **fields}


def run_message(partition: str) -> dict:
    return {"type": "run", "partition": partition}


def exit_message() -> dict:
    return {"type": "exit"}


def ready_event() -> dict:
    return {"type": "ready"}


def progress_event(partition: str, phase: int, phase_name: str) -> dict:
    return {"type": "progress", "partition": partition, "phase": phase, "phase_name": phase_name}


def log_event(level: str, message: str) -> dict:
    return {"type": "log", "level": level, "message": message}


def done_event(partition: str, buildings: int, result_path: Optional[str],
               feature_count: int, seconds: float) -> dict:
    return {"type": "done", "partition": partition, "buildings": buildings,
            "result": result_path, "features": feature_count, "seconds": seconds}


def error_event(partition: str, message: str, traceback_text: str) -> dict:
    return {"type": "error", "partition": partition, "message": message,
            "traceback": traceback_text}
```

- [ ] **Step 4: Run tests to verify they pass** — same command; Expected: PASS.

- [ ] **Step 5: Commit** (only with the user's go-ahead) — `git add helpers/worker_protocol.py test/test_worker_protocol.py`

---

### Task 3: GUI-free partition pipeline

**Files:**
- Create: `helpers/partition_pipeline.py`
- Modify: `ibtool/ibtool.py:1228-1371` (`_run_partition_pipeline` → thin wrapper)
- Modify: `test/test_ibtool.py` (`TestRunPartitionPipeline` patch targets)
- Test: `test/test_partition_pipeline.py`

**Interfaces:**
- Produces:
  - `PHASES = {2: "Calculate Blocks", 3: "Apply Filter", 4: "Calculate MST", 5: "Clustering", 6: "Erode Empty Areas", 7: "Close Gaps", 8: "Remove Patches"}`
  - `PHASE_PERCENT = {2: 10, 3: 20, 4: 35, 5: 50, 6: 70, 7: 80, 8: 90}` (progress within a partition)
  - `run_partition(part_name: str, layers: dict, spatial_reference, workspace_path: str, debug_mode: bool, global_footprint_density: float, params: dict, progress: Optional[Callable[[int, str], None]] = None, on_selected: Optional[Callable[[int], None]] = None) -> tuple[Optional[QgsVectorLayer], int]`
    — `layers` keys `layer_part`, `layer_hu`, `layer_rn`, `aux_layers_line`; `params` as `_parse_numeric_params()` + `input_filter`; `on_selected(building_count)` is called right after the building selection (IBTool uses it for `_progress_part_hu`).

- [ ] **Step 1: Write the failing test** (structure test; equality is proven by full runs in Task 9)

```python
# test/test_partition_pipeline.py
# -*- coding: utf-8 -*-
"""Tests for helpers/partition_pipeline.py — the only partition pipeline implementation."""
from unittest.mock import MagicMock, patch

import pytest

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from ibtool.helpers import partition_pipeline as pp  # noqa: E402

_PARAMS = {"min_overlap_blocks": 18.0, "global_footprint_density": 0.0, "min_area": 57.0,
           "min_bdg_count": 20, "min_patch_size": 10000.0, "max_hole_size": 10000.0,
           "max_gap_size": 4900.0, "part_start": -1, "part_end": -1, "input_filter": "f.txt"}


def _layers():
    return {k: MagicMock() for k in ("layer_part", "layer_hu", "layer_rn", "aux_layers_line")}


class TestRunPartition:

    @pytest.mark.unit
    def test_skips_partition_with_fewer_than_10_buildings(self):
        hu = MagicMock()
        hu.featureCount.return_value = 5
        seen = []
        with patch.object(pp, "processing"), \
                patch.object(pp, "select_and_save_by_location", return_value=hu), \
                patch.object(pp, "logger"):
            result, count = pp.run_partition("PART_1", _layers(), MagicMock(), "/ws/", False,
                                             15.7, _PARAMS, on_selected=seen.append)
        assert (result, count) == (None, 5)
        assert seen == [5]

    @pytest.mark.unit
    def test_reports_all_phases_in_order(self):
        sel = MagicMock()
        sel.featureCount.return_value = 100
        phases = []
        with patch.object(pp, "processing"), \
                patch.object(pp, "select_and_save_by_location", return_value=sel), \
                patch.object(pp, "logger"), \
                patch.multiple(pp, calc_footprint_density=MagicMock(return_value=15.0),
                               blocker=MagicMock(), input_hu_filter=MagicMock(),
                               identify_dense_blocks=MagicMock(), calculate_mst=MagicMock(),
                               mst_clustering=MagicMock(), add_single_bdg=MagicMock(),
                               edge_catch=MagicMock(), erode_empty_areas=MagicMock(),
                               gap_close=MagicMock(), patch_remove=MagicMock(return_value="R")):
            result, count = pp.run_partition("PART_2", _layers(), MagicMock(), "/ws/", False, 15.7,
                                             _PARAMS, progress=lambda p, n: phases.append((p, n)))
        assert result == "R" and count == 100
        assert phases == sorted(pp.PHASES.items())

    @pytest.mark.unit
    def test_mst_failure_skips_partition(self):
        sel = MagicMock()
        sel.featureCount.return_value = 100
        with patch.object(pp, "processing"), \
                patch.object(pp, "select_and_save_by_location", return_value=sel), \
                patch.object(pp, "logger"), \
                patch.multiple(pp, calc_footprint_density=MagicMock(return_value=15.0),
                               blocker=MagicMock(), input_hu_filter=MagicMock(),
                               identify_dense_blocks=MagicMock(),
                               calculate_mst=MagicMock(return_value=None)):
            assert pp.run_partition("PART_3", _layers(), MagicMock(), "/ws/", False, 15.7,
                                    _PARAMS) == (None, 100)
```

- [ ] **Step 2: Run to verify it fails** — `... -m pytest test/test_partition_pipeline.py ...` → ImportError.

- [ ] **Step 3: Create `helpers/partition_pipeline.py`**

Move the body of `IBTool._run_partition_pipeline` (`ibtool/ibtool.py:1252-1371`) unchanged into `run_partition`, with exactly these substitutions:
- `self._progress_part_hu = anz_hu` → `if on_selected: on_selected(anz_hu)`
- every `self._update_phase(N, 9, "<name>", self._overall_percent(P))` → `_report(progress, N)`
- `logger` = `Logger` from `.logger`; imports become relative (`from ..ibtool_tools.Blocker import blocker`, `from .geometry_utils import select_and_save_by_location`, `from .processing_context import current_processing_context`, `from qgis import processing`, `from qgis.core import QgsProcessing`).
- The partition banner (`"###...#"`, `f"PARTITION: {part_name} - {i} of {n}"`) stays in `IBTool` (it needs index/count) — not in `run_partition`.

```python
# helpers/partition_pipeline.py (head; body = moved code with the substitutions above)
# -*- coding: utf-8 -*-
"""The partition pipeline (steps 1–10 for one partition) without any UI.

Single implementation used by the sequential path (IBTool) and by the worker
processes (ibtool/partition_worker.py), so both compute exactly the same.
Progress is reported via callback instead of dialog updates.
"""
import os
from typing import Callable, Optional

from qgis import processing
from qgis.core import QgsProcessing

from .geometry_utils import select_and_save_by_location
from .logger import Logger as logger
from .processing_context import current_processing_context
from ..ibtool_tools.AddSingleBuilding import add_single_bdg
from ..ibtool_tools.Blocker import blocker
from ..ibtool_tools.CreateMST import calculate_mst
from ..ibtool_tools.EdgeCatch import edge_catch
from ..ibtool_tools.ErodeEmptyAreas import erode_empty_areas
from ..ibtool_tools.FootprintDensity import calc_footprint_density, identify_dense_blocks
from ..ibtool_tools.GapClose import gap_close
from ..ibtool_tools.ImportFilter import input_hu_filter
from ..ibtool_tools.MST_Clustering import mst_clustering
from ..ibtool_tools.PatchRemove import patch_remove

PHASES = {2: "Calculate Blocks", 3: "Apply Filter", 4: "Calculate MST", 5: "Clustering",
          6: "Erode Empty Areas", 7: "Close Gaps", 8: "Remove Patches"}
"""Phase numbers/names reported during a partition (English; translated by the UI)."""

PHASE_PERCENT = {2: 10, 3: 20, 4: 35, 5: 50, 6: 70, 7: 80, 8: 90}
"""Progress within a partition at the start of each phase (percent)."""


def _report(progress: Optional[Callable[[int, str], None]], phase: int) -> None:
    if progress:
        progress(phase, PHASES[phase])


def run_partition(  # pylint: disable=too-many-arguments,too-many-locals
        part_name, layers, spatial_reference, workspace_path, debug_mode,
        global_footprint_density, params, progress=None, on_selected=None):
    """Run the delineation pipeline for one partition (see docs/how-it-works.md).

    Args:
        part_name: Partition identifier (``NAME`` field).
        layers: Dict with ``layer_part``, ``layer_hu``, ``layer_rn``, ``aux_layers_line``.
        spatial_reference: QgsCoordinateReferenceSystem for all outputs.
        workspace_path: Workspace directory (trailing slash).
        debug_mode: Save intermediate debug layers.
        global_footprint_density: Pre-computed global density threshold.
        params: ``_parse_numeric_params()`` dict + ``input_filter`` (path).
        progress: Optional ``callback(phase, phase_name)`` at the start of phases 2–8.
        on_selected: Optional ``callback(building_count)`` right after the building selection.

    Returns:
        ``(result_layer or None, building_count)``.
    """
    # ... moved body (unchanged except for the substitutions listed above) ...
```

> The moved body must be copied verbatim from `ibtool/ibtool.py:1256-1371` (from `if debug_mode and workspace_path:` to `return patch_removed, anz_hu`). Do not "improve" anything while moving.

Then replace the method in `ibtool/ibtool.py` (keep the docstring, shorten it to refer to `run_partition`):

```python
    def _run_partition_pipeline(  # pylint: disable=too-many-arguments
            self, part_name, part_index, part_count,
            layers, spatial_reference, workspace_path,
            debug_mode, global_footprint_density, params):
        """Run one partition in this process (sequential path / recompute list).

        Thin wrapper around :func:`helpers.partition_pipeline.run_partition`
        that adds the partition banner and the dialog progress updates.
        """
        logger.log("###############################", 'CRITICAL')
        logger.log(f"PARTITION: {part_name} - {part_index} of {part_count}", 'CRITICAL')

        def _progress(phase, phase_name):
            self._update_phase(phase, 9, phase_name,
                               self._overall_percent(PHASE_PERCENT[phase]))

        def _selected(count):
            self._progress_part_hu = count

        return run_partition(part_name, layers, spatial_reference, workspace_path,
                             debug_mode, global_footprint_density, params,
                             progress=_progress, on_selected=_selected)
```

Imports in `ibtool.py`: add `from ibtool.helpers.partition_pipeline import run_partition, PHASE_PERCENT`; remove the tool imports that are now unused there (`blocker`, `input_hu_filter`, `calculate_mst`, `mst_clustering`, `add_single_bdg`, `edge_catch`, `gap_close`, `patch_remove`, `erode_empty_areas`, `identify_dense_blocks`; keep `calc_footprint_density` — used for the global density).

Phase names for translation: `test_every_phase_name_has_german_translation` parses `_update_phase(\d+, \d+, "name"` in `ibtool.py`. Phases 2–8 are now passed as variables → update that test to collect names from `ibtool.py` **plus** `PHASES.values()`; it must still find 9 names.

- [ ] **Step 4: Update `test/test_ibtool.py::TestRunPartitionPipeline`**

Change every patch target `"ibtool.ibtool.ibtool.<name>"` for the moved names (`processing`, `select_and_save_by_location`, tool functions) to `"ibtool.helpers.partition_pipeline.<name>"`; keep `"ibtool.ibtool.ibtool.logger"` for the banner and add `"ibtool.helpers.partition_pipeline.logger"`. Update `test_every_phase_name_has_german_translation` as described.

- [ ] **Step 5: Run tests**

Run: `... -m pytest test/test_partition_pipeline.py test/test_ibtool.py -q -p no:cacheprovider` → PASS; then the full suite → only the 2 known failures.

- [ ] **Step 6: Verify identical results (sequential, real data)**

`scripts/profile_pipeline.py` must call `run_partition` instead of its own copy of the pipeline: replace the body of `run_partition` in the script by a call to `ibtool.helpers.partition_pipeline.run_partition(name, {"layer_part": part, "layer_hu": hu, "layer_rn": rn, "aux_layers_line": aux_line}, crs, ws, False, gfd, {**P, "min_bdg_count": 20, "input_filter": FILTER}, progress=...)` where `progress` records phase timing into `TIMES` (phase `N` → step name of the next phase start). Then:
`python-qgis-ltr.bat scripts\profile_pipeline.py --out <dir> --no-cprofile` and `scripts\compare_results.py <3.44 reference> <dir>\result.gpkg --parts Testdaten\A_PART.shp` → **IDENTICAL**.

- [ ] **Step 7: Commit** (only with the user's go-ahead)

---

### Task 4: Partition results (part files, finish log, final merge)

**Files:**
- Create: `helpers/partition_results.py`
- Test: `test/test_partition_results.py`

**Interfaces:**
- Consumes: `merge_layers_prepending(layers, base_layer, crs)` from `helpers/geometry_utils.py`
- Produces:
  - `PARTS_DIR = "parts"` (below `IB_Tool_Results`)
  - `part_file_name(partition: str) -> str` — sanitized, collision-free (`"PART_64.gpkg"`, `"Teil_ Nord_3f2a1c.gpkg"` for unsafe names: unsafe chars → `_` + 6-char hash of the original name)
  - `write_part_result(layer: QgsVectorLayer, partition: str, results_dir: str) -> tuple[str, int]` — atomic (temp name + `os.replace`), returns `(relative path "parts/<file>", feature_count)`
  - `@dataclass FinishedPart: partition: str; result: Optional[str]; features: Optional[int]` (`result=None` = skipped; `features=None` = old format line)
  - `append_finished(log_path: str, part: FinishedPart) -> None` (line `name\tpath\tcount` or `name\tskipped`, flush + `os.fsync`)
  - `read_finished(log_path: str) -> dict[str, FinishedPart]` (new format + old plain names; ignores a truncated last line, i.e. one without `\n` that does not parse)
  - `validate_finished(results_dir: str, finished: dict) -> tuple[dict, list[str]]` — `(valid, recompute)`: part file exists, opens, feature count matches; old-format entries are kept as valid (they live in `merge_temp`)
  - `cleanup_temporary(results_dir: str) -> None` (delete `parts/*.tmp.gpkg`)
  - `merge_results(results_dir: str, order: list[str], finished: dict, base_layer, crs) -> QgsVectorLayer` — loads part files in `order` (skipped / old-format entries contribute nothing), drops field `fid`, `merge_layers_prepending(layers, base_layer, crs)`

- [ ] **Step 1: Write the failing tests**

```python
# test/test_partition_results.py
# -*- coding: utf-8 -*-
"""Tests for helpers/partition_results.py (part files, finish log, final merge)."""
import os
from unittest.mock import patch

import pytest
from qgis.core import QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsVectorLayer

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from ibtool.helpers import partition_results as pr  # noqa: E402
from ibtool.helpers.geometry_utils import create_empty_layer  # noqa: E402

CRS = QgsCoordinateReferenceSystem("EPSG:25833")


def _layer(xs, field="Area"):
    layer = QgsVectorLayer(f"MultiPolygon?crs=EPSG:25833&field={field}:double", "r", "memory")
    feats = []
    for x in xs:
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"MultiPolygon ((({x} 0, {x + 10} 0, {x + 10} 10, {x} 10, {x} 0)))"))
        f.setAttributes([100.0])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    return layer


class TestPartFiles:

    @pytest.mark.unit
    def test_part_file_name_is_sanitized_and_unique(self):
        assert pr.part_file_name("PART_64") == "PART_64.gpkg"
        a, b = pr.part_file_name("Teil: Nord"), pr.part_file_name("Teil/ Nord")
        assert a != b and a.endswith(".gpkg")
        assert not any(c in a for c in '<>:"/\\|?*')

    @pytest.mark.integration
    def test_write_is_atomic_and_counts_features(self, tmp_path):
        rel, count = pr.write_part_result(_layer([0, 20, 40]), "PART_1", str(tmp_path))
        assert rel == "parts/PART_1.gpkg" and count == 3
        assert os.path.isfile(tmp_path / "parts" / "PART_1.gpkg")
        assert not list((tmp_path / "parts").glob("*.tmp.gpkg"))

    @pytest.mark.integration
    def test_failed_part_write_leaves_no_finish_line(self, tmp_path):
        log = tmp_path / "fin.txt"
        with patch.object(pr.os, "replace", side_effect=OSError("locked")):
            with pytest.raises(OSError):
                pr.write_part_result(_layer([0]), "PART_1", str(tmp_path))
        assert not log.exists()
        assert not (tmp_path / "parts" / "PART_1.gpkg").exists()


class TestFinishLog:

    @pytest.mark.unit
    def test_round_trip_new_format(self, tmp_path):
        log = str(tmp_path / "fin.txt")
        pr.append_finished(log, pr.FinishedPart("PART_64", "parts/PART_64.gpkg", 23))
        pr.append_finished(log, pr.FinishedPart("PART_9", None, None))
        assert pr.read_finished(log) == {
            "PART_64": pr.FinishedPart("PART_64", "parts/PART_64.gpkg", 23),
            "PART_9": pr.FinishedPart("PART_9", None, None)}

    @pytest.mark.unit
    def test_old_format_and_truncated_line(self, tmp_path):
        log = tmp_path / "fin.txt"
        log.write_text("\nPART_1\nPART_2\nPART_3\tparts/PART_3.gp", encoding="utf-8")
        got = pr.read_finished(str(log))
        assert set(got) == {"PART_1", "PART_2"}
        assert got["PART_1"].features is None and got["PART_1"].result == pr.OLD_FORMAT


class TestValidateAndMerge:

    @pytest.mark.integration
    def test_validate_detects_missing_and_wrong_count(self, tmp_path):
        ok_rel, n = pr.write_part_result(_layer([0, 20]), "A", str(tmp_path))
        bad_rel, _ = pr.write_part_result(_layer([0]), "B", str(tmp_path))
        finished = {"A": pr.FinishedPart("A", ok_rel, n), "B": pr.FinishedPart("B", bad_rel, 5),
                    "C": pr.FinishedPart("C", "parts/C.gpkg", 1),
                    "S": pr.FinishedPart("S", None, None)}
        valid, recompute = pr.validate_finished(str(tmp_path), finished)
        assert set(valid) == {"A", "S"} and sorted(recompute) == ["B", "C"]

    @pytest.mark.integration
    def test_merge_order_equals_former_incremental_merge(self, tmp_path):
        rels = {}
        for name, x in (("P1", 0), ("P2", 100), ("P3", 200)):
            rel, n = pr.write_part_result(_layer([x]), name, str(tmp_path))
            rels[name] = pr.FinishedPart(name, rel, n)
        base = create_empty_layer("global_merge_layer", "Polygon", CRS.authid())
        merged = pr.merge_results(str(tmp_path), ["P1", "P2", "P3"], rels, base, CRS)
        xs = [round(f.geometry().boundingBox().xMinimum()) for f in merged.getFeatures()]
        assert xs == [200, 100, 0]                 # last partition first, as before
        assert "fid" not in [f.name() for f in merged.fields()]
```

(`pr.OLD_FORMAT` is the marker string `"<merge_temp>"` used as `result` for old-format lines.)

- [ ] **Step 2: Run to verify failure** → ImportError.

- [ ] **Step 3: Implement `helpers/partition_results.py`**

```python
# -*- coding: utf-8 -*-
"""Per-partition result files, finish log, resume validation and final merge.

Order guarantee for resume: a part file is written under a temporary name and
renamed (atomic); only then the finish line is appended and flushed. A crash
in between leaves a file without a finish line (partition recomputed); a
finish line without a complete file cannot occur.
"""
import glob
import hashlib
import os
import re
from dataclasses import dataclass
from typing import Optional

from qgis.core import (QgsCoordinateTransformContext, QgsFeatureRequest, QgsVectorFileWriter,
                       QgsVectorLayer)

from .geometry_utils import merge_layers_prepending

PARTS_DIR = "parts"
OLD_FORMAT = "<merge_temp>"
"""``result`` marker of finish-log lines written by versions before 0.2.5."""
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class FinishedPart:
    partition: str
    result: Optional[str]      # relative part file, None = skipped, OLD_FORMAT = in merge_temp
    features: Optional[int]


def part_file_name(partition: str) -> str:
    """File name for a partition's result; unsafe names get a hash suffix (unique)."""
    safe = _UNSAFE.sub("_", partition).strip(" .") or "part"
    if safe == partition:
        return f"{safe}.gpkg"
    digest = hashlib.sha1(partition.encode("utf-8")).hexdigest()[:6]
    return f"{safe}_{digest}.gpkg"


def write_part_result(layer, partition, results_dir):
    """Write *layer* atomically to ``<results_dir>/parts``; return ``(rel_path, count)``."""
    parts = os.path.join(results_dir, PARTS_DIR)
    os.makedirs(parts, exist_ok=True)
    name = part_file_name(partition)
    final = os.path.join(parts, name)
    temp = final[:-len(".gpkg")] + ".tmp.gpkg"
    if os.path.exists(temp):
        os.remove(temp)
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = "result"
    err = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, temp, QgsCoordinateTransformContext(), opts)
    if err[0] != QgsVectorFileWriter.NoError:
        raise OSError(f"Teilergebnis {partition} konnte nicht geschrieben werden: {err[1]}")
    try:
        os.replace(temp, final)
    except OSError:
        if os.path.exists(temp):
            os.remove(temp)
        raise
    return f"{PARTS_DIR}/{name}", layer.featureCount()


def append_finished(log_path, part):
    """Append one finish line and force it to disk."""
    if part.result is None:
        line = f"{part.partition}\tskipped\n"
    else:
        line = f"{part.partition}\t{part.result}\t{part.features}\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def read_finished(log_path):
    """Parse the finish log (new and old format); ignore an incomplete last line."""
    if not os.path.isfile(log_path):
        return {}
    with open(log_path, "r", encoding="utf-8") as f:
        content = f.read()
    lines = content.split("\n")
    complete = lines[:-1] if not content.endswith("\n") else lines
    result = {}
    for raw in complete:
        cols = raw.strip("\r").split("\t")
        if not cols[0].strip():
            continue
        name = cols[0].strip()
        if len(cols) == 1:
            result[name] = FinishedPart(name, OLD_FORMAT, None)
        elif len(cols) == 2 and cols[1] == "skipped":
            result[name] = FinishedPart(name, None, None)
        elif len(cols) == 3 and cols[2].isdigit():
            result[name] = FinishedPart(name, cols[1], int(cols[2]))
    tail = lines[-1].strip("\r") if not content.endswith("\n") else ""
    if tail and "\t" not in tail:            # old format has no trailing newline per line
        result[tail] = FinishedPart(tail, OLD_FORMAT, None)
    return result


def validate_finished(results_dir, finished):
    """Split finished partitions into ``valid`` and names to ``recompute``."""
    valid, recompute = {}, []
    for name, part in finished.items():
        if part.result is None or part.result == OLD_FORMAT:
            valid[name] = part
            continue
        path = os.path.join(results_dir, part.result)
        layer = QgsVectorLayer(f"{path}|layername=result", name, "ogr") if os.path.isfile(path) else None
        if layer is not None and layer.isValid() and layer.featureCount() == part.features:
            valid[name] = part
        else:
            recompute.append(name)
    return valid, recompute


def cleanup_temporary(results_dir):
    for path in glob.glob(os.path.join(results_dir, PARTS_DIR, "*.tmp.gpkg")):
        os.remove(path)


def merge_results(results_dir, order, finished, base_layer, crs):
    """Merge part files in partition order like the former incremental merge."""
    layers = []
    for name in order:
        part = finished.get(name)
        if part is None or part.result in (None, OLD_FORMAT):
            continue
        path = os.path.join(results_dir, part.result)
        source = QgsVectorLayer(f"{path}|layername=result", name, "ogr")
        memory = source.materialize(QgsFeatureRequest())
        fid_index = memory.fields().lookupField("fid")      # GeoPackage primary key column
        if fid_index >= 0:
            memory.dataProvider().deleteAttributes([fid_index])
            memory.updateFields()
        layers.append(memory)
    return merge_layers_prepending(layers, base_layer, crs)
```

> Note on `read_finished`: the old version wrote `"\n" + name` (newline **before** each name), so the last old-format line has no trailing newline but is complete. New-format lines always end with `\n`; a new-format line without `\n` is incomplete and ignored. The tail rule above implements exactly this (old-format tail = no tab → valid; new-format tail with tabs → ignored). Adjust the test fixture if the rule is refined.

- [ ] **Step 4: Run tests → PASS**; then full suite.

- [ ] **Step 5: Commit** (only with the user's go-ahead)

---

### Task 5: Run manifest

**Files:**
- Create: `helpers/run_manifest.py`
- Test: `test/test_run_manifest.py`

**Interfaces:**
- Consumes: `compute_file_checksum(path) -> str` from `helpers/system_utils.py`
- Produces:
  - `MANIFEST_NAME = "ibtool_run.json"`, `FORMAT_VERSION = 1`
  - `build_manifest(inputs: dict[str, str], params: dict, crs_authid: str, plugin_version: str, qgis_version: str, worker_count: int) -> dict` — `inputs` keys `hu`, `rn`, `part`, `aux`, `filter`; checksums computed here
  - `read_manifest(workspace: str) -> Optional[dict]`
  - `write_manifest(workspace: str, manifest: dict, status: str) -> None` (atomic; sets `status`, `updated`, keeps `created`)
  - `compare_manifests(stored: dict, current: dict) -> list[str]` — German, user-readable differences; ignores `worker_count`, `status`, timestamps, input **paths** (only checksums count)
  - `manifest_to_ui_settings(manifest: dict) -> dict` (inputs paths + params, for the restore prompt)

- [ ] **Step 1: Write the failing tests**

```python
# test/test_run_manifest.py
# -*- coding: utf-8 -*-
"""Tests for helpers/run_manifest.py (ibtool_run.json)."""
import json

import pytest

from ibtool.helpers import run_manifest as rm


def _inputs(tmp_path, hu_content="hu"):
    files = {}
    for key, content in (("hu", hu_content), ("rn", "rn"), ("part", "part"), ("aux", "aux"),
                         ("filter", "filter")):
        p = tmp_path / f"{key}.dat"
        p.write_text(content)
        files[key] = str(p)
    return files


def _manifest(tmp_path, **kw):
    args = dict(inputs=_inputs(tmp_path), params={"min_area": 57.0, "part_list": "#"},
                crs_authid="EPSG:25833", plugin_version="0.2.5", qgis_version="3.44.15",
                worker_count=3)
    args.update(kw)
    return rm.build_manifest(**args)


class TestManifest:

    @pytest.mark.unit
    def test_write_read_round_trip_and_atomic(self, tmp_path):
        m = _manifest(tmp_path)
        rm.write_manifest(str(tmp_path), m, "running")
        stored = rm.read_manifest(str(tmp_path))
        assert stored["status"] == "running" and stored["inputs"]["hu"]["checksum"]
        assert not list(tmp_path.glob("*.tmp"))

    @pytest.mark.unit
    def test_identical_runs_have_no_differences(self, tmp_path):
        assert rm.compare_manifests(_manifest(tmp_path), _manifest(tmp_path)) == []

    @pytest.mark.unit
    def test_worker_count_does_not_invalidate_resume(self, tmp_path):
        assert rm.compare_manifests(_manifest(tmp_path, worker_count=3),
                                    _manifest(tmp_path, worker_count=1)) == []

    @pytest.mark.unit
    def test_changed_input_param_and_qgis_version_are_reported(self, tmp_path):
        old = _manifest(tmp_path)
        (tmp_path / "hu.dat").write_text("changed")
        new = _manifest(tmp_path, params={"min_area": 60.0, "part_list": "#"},
                        qgis_version="3.40.0")
        diffs = rm.compare_manifests(old, new)
        assert any("Gebäude" in d for d in diffs)
        assert any("min_area" in d for d in diffs)
        assert any("3.44.15 → 3.40.0" in d for d in diffs)

    @pytest.mark.unit
    def test_moved_input_with_same_content_is_ok(self, tmp_path):
        old = _manifest(tmp_path)
        moved = tmp_path / "elsewhere"
        moved.mkdir()
        (moved / "hu.dat").write_text("hu")
        new_inputs = dict(_inputs(tmp_path), hu=str(moved / "hu.dat"))
        assert rm.compare_manifests(old, _manifest(tmp_path, inputs=new_inputs)) == []

    @pytest.mark.unit
    def test_missing_or_broken_manifest_reads_none(self, tmp_path):
        assert rm.read_manifest(str(tmp_path)) is None
        (tmp_path / rm.MANIFEST_NAME).write_text("{broken")
        assert rm.read_manifest(str(tmp_path)) is None

    @pytest.mark.unit
    def test_ui_settings(self, tmp_path):
        s = rm.manifest_to_ui_settings(_manifest(tmp_path))
        assert s["inputs"]["hu"].endswith("hu.dat") and s["params"]["min_area"] == 57.0
```

- [ ] **Step 2: Run → ImportError.**

- [ ] **Step 3: Implement `helpers/run_manifest.py`**

```python
# -*- coding: utf-8 -*-
"""Run manifest ``ibtool_run.json``: one working directory = one run.

Records inputs (path + checksum), parameters, CRS and versions so that a run
can be resumed safely after a restart and its settings restored in the UI.
"""
import json
import os
import time
from typing import Optional

from .system_utils import compute_file_checksum

MANIFEST_NAME = "ibtool_run.json"
FORMAT_VERSION = 1
_INPUT_LABELS = {"hu": "Gebäude-Datei", "rn": "Straßen-Datei", "part": "Partitions-Datei",
                 "aux": "Hilfslinien-Datei", "filter": "Filter-Datei"}


def build_manifest(inputs, params, crs_authid, plugin_version, qgis_version, worker_count):
    return {
        "format_version": FORMAT_VERSION,
        "inputs": {key: {"path": path, "checksum": compute_file_checksum(path) if path else ""}
                   for key, path in inputs.items()},
        "params": dict(params),
        "crs": crs_authid,
        "plugin_version": plugin_version,
        "qgis_version": qgis_version,
        "worker_count": worker_count,
    }


def read_manifest(workspace):
    path = os.path.join(workspace, MANIFEST_NAME)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("format_version") == FORMAT_VERSION else None


def write_manifest(workspace, manifest, status):
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    data = dict(manifest, status=status, updated=now)
    data.setdefault("created", now)
    path = os.path.join(workspace, MANIFEST_NAME)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def compare_manifests(stored, current):
    """User-readable differences that forbid resuming (empty list = resume allowed)."""
    diffs = []
    for key, label in _INPUT_LABELS.items():
        old = stored.get("inputs", {}).get(key, {}).get("checksum")
        new = current.get("inputs", {}).get(key, {}).get("checksum")
        if old != new:
            diffs.append(f"{label} geändert")
    for name in sorted(set(stored.get("params", {})) | set(current.get("params", {}))):
        old, new = stored.get("params", {}).get(name), current.get("params", {}).get(name)
        if old != new:
            diffs.append(f"Parameter {name}: {old} → {new}")
    for key, label in (("crs", "Koordinatensystem"), ("qgis_version", "QGIS"),
                       ("plugin_version", "IB-Tool")):
        if stored.get(key) != current.get(key):
            diffs.append(f"{label} {stored.get(key)} → {current.get(key)}")
    return diffs


def manifest_to_ui_settings(manifest):
    return {"inputs": {k: v.get("path", "") for k, v in manifest.get("inputs", {}).items()},
            "params": dict(manifest.get("params", {})), "crs": manifest.get("crs")}
```

- [ ] **Step 4: Run tests → PASS.**
- [ ] **Step 5: Commit** (only with the user's go-ahead)

---

### Task 6: Worker program

**Files:**
- Create: `ibtool/partition_worker.py`
- Test: `test/test_partition_worker.py` (integration, real QGIS, uses `Testdaten`)

**Interfaces:**
- Consumes: `worker_protocol` (Task 2), `run_partition` (Task 3), `write_part_result` (Task 4), `parent_alive` (Task 1), `ui_heartbeat` / `shared_processing_context` (`helpers/processing_context.py`).
- Produces (process contract):
  - started as `<python> -u ibtool/partition_worker.py`, first stdin line = `init` message with keys: `plugin_root`, `sys_path` (list), `prefix_path`, `inputs` (`hu`, `rn`, `part`, `aux_line` GPKG paths), `crs`, `params` (incl. `input_filter`), `workspace`, `results_dir`, `debug_mode`, `global_density`, `log_level`, `parent_pid`.
  - emits `ready` after QGIS/Processing init and opening the inputs; then per `run`: `progress`… then `done` or `error`; exits on `exit`, stdin EOF, or when `parent_alive(parent_pid)` is false (checked in the heartbeat, ≥ every 2 s).
  - `Logger` output is forwarded as `log` events (no files, no QGIS message log).

- [ ] **Step 1: Write the failing integration test**

```python
# test/test_partition_worker.py
# -*- coding: utf-8 -*-
"""Integration tests: run the real worker program on sample data."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from qgis.core import QgsApplication  # noqa: E402

from ibtool.helpers import worker_protocol as wp  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "Testdaten"


def _prepare_inputs(ws):
    """Load sample data into GPKGs like IBTool does (incl. aux_line)."""
    from qgis import processing
    from qgis.core import QgsCoordinateReferenceSystem
    from ibtool.helpers.geometry_utils import load_to_geopackage
    crs = QgsCoordinateReferenceSystem("EPSG:25833")
    out = {}
    for key, name in (("hu", "A_HU"), ("rn", "A_RN"), ("part", "A_PART"), ("aux", "A_AUX")):
        out[key] = str(ws / f"layer_{key}.gpkg")
        load_to_geopackage(str(DATA / f"{name}.shp"), out[key], f"layer_{key}", crs)
    processing.run("qgis:mergevectorlayers", {"LAYERS": [out["aux"], out["rn"]], "CRS": crs,
                                              "OUTPUT": str(ws / "layer_aux_line.gpkg")})
    out["aux_line"] = str(ws / "layer_aux_line.gpkg")
    return out


def _run_worker(ws, partitions):
    inputs = _prepare_inputs(ws)
    init = wp.init_message(
        plugin_root=str(ROOT), sys_path=[p for p in sys.path if p], prefix_path=QgsApplication.prefixPath(),
        inputs=inputs, crs="EPSG:25833",
        params={"min_overlap_blocks": 18.0, "global_footprint_density": 0.0, "min_area": 57.0,
                "min_bdg_count": 20, "min_patch_size": 10000.0, "max_hole_size": 10000.0,
                "max_gap_size": 4900.0, "part_start": -1, "part_end": -1,
                "input_filter": str(DATA / "IB-Tool2_Filter.txt")},
        workspace=str(ws) + "/", results_dir=str(ws / "IB_Tool_Results"), debug_mode=False,
        global_density=15.701401805626455, log_level="CRITICAL", parent_pid=os.getpid())
    commands = [wp.encode_command(init)] + [wp.encode_command(wp.run_message(p)) for p in partitions] \
        + [wp.encode_command(wp.exit_message())]
    proc = subprocess.run([sys.executable, "-u", str(ROOT / "ibtool" / "partition_worker.py")],
                          input=b"".join(commands), capture_output=True, timeout=600, check=False)
    events = [wp.parse_line(l) for l in proc.stdout.decode("utf-8", "replace").splitlines()]
    return proc, [e for e in events if e]


@pytest.mark.integration
@pytest.mark.slow
def test_worker_processes_partitions(tmp_path):
    proc, events = _run_worker(tmp_path, ["PART_9", "PART_1"])
    types = [e["type"] for e in events]
    assert types[0] == "ready", proc.stderr.decode(errors="replace")[-2000:]
    done = {e["partition"]: e for e in events if e["type"] == "done"}
    assert done["PART_9"]["result"] == "parts/PART_9.gpkg" and done["PART_9"]["features"] >= 1
    assert done["PART_1"]["result"] is None                       # < 10 buildings → skipped
    assert (tmp_path / "IB_Tool_Results" / "parts" / "PART_9.gpkg").is_file()
    assert proc.returncode == 0


@pytest.mark.integration
@pytest.mark.slow
def test_worker_handles_path_with_space_and_umlaut(tmp_path):
    ws = tmp_path / "IB Läufe" / "Testlauf 1"
    ws.mkdir(parents=True)
    proc, events = _run_worker(ws, ["PART_9"])
    assert [e["type"] for e in events if e["type"] in ("ready", "done")] == ["ready", "done"], \
        proc.stderr.decode(errors="replace")[-2000:]
```

- [ ] **Step 2: Run → fails** (`partition_worker.py` missing).

- [ ] **Step 3: Implement `ibtool/partition_worker.py`**

```python
# -*- coding: utf-8 -*-
"""IB-Tool worker process: computes partitions for the plugin (worker mode).

Started by ``helpers/worker_pool.py`` with the QGIS Python interpreter.
Protocol: ``helpers/worker_protocol.py``. Reads the ``init`` line first using
only the standard library (sys.path / QGIS paths come from the plugin), then
initialises QGIS once and processes ``run`` commands until ``exit``/EOF.
"""
import json
import os
import sys
import time
import traceback
import types


def _emit(message):
    from ibtool.helpers import worker_protocol as wp  # pylint: disable=import-outside-toplevel
    sys.stdout.write(wp.encode(message))
    sys.stdout.flush()


def _bootstrap(init):
    sys.path[:0] = [p for p in init["sys_path"] if p not in sys.path]
    root = init["plugin_root"]
    if "ibtool" not in sys.modules:                 # same virtual package as __init__.py
        pkg = types.ModuleType("ibtool")
        pkg.__path__ = [root]
        sys.modules["ibtool"] = pkg
    from qgis.core import QgsApplication  # pylint: disable=import-outside-toplevel
    QgsApplication.setPrefixPath(init["prefix_path"], True)
    app = QgsApplication([], False)
    app.initQgis()
    from processing.core.Processing import Processing  # pylint: disable=import-outside-toplevel
    Processing.initialize()
    return app


def main():  # pylint: disable=too-many-locals
    line = sys.stdin.readline()
    if not line:
        return 1
    init = json.loads(line)
    app = _bootstrap(init)                          # noqa: F841 (keep QgsApplication alive)

    # pylint: disable=import-outside-toplevel
    from qgis.core import QgsCoordinateReferenceSystem, QgsVectorLayer
    from ibtool.helpers import worker_protocol as wp
    from ibtool.helpers.logger import Logger
    from ibtool.helpers.partition_pipeline import run_partition
    from ibtool.helpers.partition_results import write_part_result
    from ibtool.helpers.processing_context import shared_processing_context, ui_heartbeat
    from ibtool.helpers.worker_launcher import parent_alive

    Logger.set_sink(lambda level, message: _emit(wp.log_event(level, message)))   # before any log
    Logger.set_log_level(init["log_level"])

    crs = QgsCoordinateReferenceSystem(init["crs"])
    layers = {
        "layer_hu": QgsVectorLayer(init["inputs"]["hu"], "layer_hu", "ogr"),
        "layer_rn": QgsVectorLayer(init["inputs"]["rn"], "layer_rn", "ogr"),
        "layer_part": QgsVectorLayer(init["inputs"]["part"], "layer_part", "ogr"),
        "aux_layers_line": QgsVectorLayer(init["inputs"]["aux_line"], "aux_layers_line", "ogr"),
    }
    parent_pid = init["parent_pid"]
    last_check = [0.0]

    def _guard():                                   # heartbeat: exit if QGIS is gone
        now = time.monotonic()
        if now - last_check[0] >= 2.0:
            last_check[0] = now
            if not parent_alive(parent_pid):
                os._exit(3)                         # pylint: disable=protected-access

    _emit(wp.ready_event())
    with ui_heartbeat(_guard):
        for raw in sys.stdin:
            command = json.loads(raw)
            if command["type"] == "exit":
                break
            name = command["partition"]
            started = time.perf_counter()
            try:
                with shared_processing_context():
                    result, count = run_partition(
                        name, layers, crs, init["workspace"], init["debug_mode"],
                        init["global_density"], init["params"],
                        progress=lambda p, n, _name=name: _emit(wp.progress_event(_name, p, n)))
                    rel, features = (None, 0) if result is None else \
                        write_part_result(result, name, init["results_dir"])
                _emit(wp.done_event(name, count, rel, features, time.perf_counter() - started))
            except Exception as e:  # pylint: disable=broad-exception-caught
                _emit(wp.error_event(name, str(e), traceback.format_exc()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`Logger.set_sink(callback)` is new: add to `helpers/logger.py` a class attribute `sink = None`; in `Logger.log`, when `cls.sink` is set, call `cls.sink(level, message)` **instead of** file/message box/QGIS message log (after the level filter). Add a unit test in `test/test_logger.py`:

```python
@pytest.mark.unit
def test_sink_receives_messages_instead_of_outputs():
    from ibtool.helpers.logger import Logger
    got = []
    Logger.set_sink(lambda level, message: got.append((level, message)))
    try:
        Logger.log("hello", level="CRITICAL")
    finally:
        Logger.set_sink(None)
    assert got == [("CRITICAL", "hello")]
```

- [ ] **Step 4: Run** `... -m pytest test/test_partition_worker.py test/test_logger.py -q -p no:cacheprovider` → PASS (slow tests take ~1 min).
- [ ] **Step 5: Commit** (only with the user's go-ahead)

---

### Task 7: Worker pool

**Files:**
- Create: `helpers/worker_pool.py`, `test/fake_worker.py`
- Test: `test/test_worker_pool.py`

**Interfaces:**
- Consumes: `WorkerCommand` (Task 1), `worker_protocol` (Task 2).
- Produces:
  - `class WorkerPool(QObject)` with signals
    `progress = pyqtSignal(str, int, str)` (partition, phase, phase_name),
    `log = pyqtSignal(str, str)` (level, message incl. `[PART]` prefix),
    `partition_done = pyqtSignal(dict)` (the `done` event),
    `finished = pyqtSignal()`
  - `WorkerPool(command: WorkerCommand, worker_count: int, init_fields: dict, ready_timeout_s: float = 60.0)`
  - `selftest() -> bool` — starts **one** worker, waits for `ready` (local `QEventLoop` + `QTimer`), returns False on timeout/exit (then all processes are killed)
  - `run(partitions: list[str]) -> None` — partitions already sorted (largest first); starts remaining workers, dispatches, emits `finished` when all are done/failed
  - `recompute: list[str]` — partitions of crashed/erroring workers
  - `running: dict[str, str]` — worker id → partition currently processed
  - `cancel() -> None` — terminate, kill after 2 s, emit `finished`
  - `stderr_tail(n=50) -> list[str]`

- [ ] **Step 1: Fake worker** (no QGIS; behaviour controlled by partition name)

```python
# test/fake_worker.py
"""Fake IB-Tool worker for pool tests (no QGIS). Partition name controls behaviour:
'crash*' → exit(9) mid-partition, 'error*' → error event, 'slow*' → sleep 2 s,
anything else → done. Env FAKE_NO_READY=1 → never sends ready."""
import json
import os
import sys
import time

PREFIX = "IBTOOL "


def emit(msg):
    sys.stdout.write(PREFIX + json.dumps(msg) + "\n")
    sys.stdout.flush()


init = json.loads(sys.stdin.readline())
print("QGIS noise line that must be ignored", flush=True)
if os.environ.get("FAKE_NO_READY"):
    time.sleep(30)
    sys.exit(0)
emit({"type": "ready"})
for raw in sys.stdin:
    cmd = json.loads(raw)
    if cmd["type"] == "exit":
        break
    name = cmd["partition"]
    emit({"type": "progress", "partition": name, "phase": 2, "phase_name": "Calculate Blocks"})
    if name.startswith("crash"):
        sys.exit(9)
    if name.startswith("error"):
        emit({"type": "error", "partition": name, "message": "boom", "traceback": "tb"})
        continue
    if name.startswith("slow"):
        time.sleep(2)
    emit({"type": "log", "level": "INFO", "message": f"did {name}"})
    emit({"type": "done", "partition": name, "buildings": 10, "result": f"parts/{name}.gpkg",
          "features": 1, "seconds": 0.0})
```

- [ ] **Step 2: Write the failing tests**

```python
# test/test_worker_pool.py
# -*- coding: utf-8 -*-
"""Tests for helpers/worker_pool.py with a fake worker (runs on every platform)."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from qgis.PyQt.QtCore import QEventLoop, QTimer  # noqa: E402

from ibtool.helpers.worker_launcher import WorkerCommand  # noqa: E402
from ibtool.helpers.worker_pool import WorkerPool  # noqa: E402

FAKE = WorkerCommand(sys.executable, ["-u", str(Path(__file__).with_name("fake_worker.py"))])


def _run(pool, partitions, timeout_ms=30000):
    done, logs = [], []
    pool.partition_done.connect(done.append)
    pool.log.connect(lambda level, msg: logs.append(msg))
    loop = QEventLoop()
    pool.finished.connect(loop.quit)
    QTimer.singleShot(timeout_ms, loop.quit)
    pool.run(partitions)
    loop.exec_()
    return done, logs


class TestWorkerPool:

    @pytest.mark.integration
    def test_all_partitions_done_and_noise_ignored(self):
        pool = WorkerPool(FAKE, 2, {})
        assert pool.selftest()
        done, logs = _run(pool, ["a", "b", "c", "d"])
        assert sorted(d["partition"] for d in done) == ["a", "b", "c", "d"]
        assert any("[a] did a" in m for m in logs)
        assert pool.recompute == []

    @pytest.mark.integration
    def test_largest_first_order_is_kept(self):
        pool = WorkerPool(FAKE, 1, {})
        assert pool.selftest()
        done, _ = _run(pool, ["big", "mid", "small"])
        assert [d["partition"] for d in done] == ["big", "mid", "small"]

    @pytest.mark.integration
    def test_crash_and_error_go_to_recompute_list(self):
        pool = WorkerPool(FAKE, 2, {})
        assert pool.selftest()
        done, _ = _run(pool, ["a", "crash1", "error1", "b"])
        assert sorted(d["partition"] for d in done) == ["a", "b"]
        assert sorted(pool.recompute) == ["crash1", "error1"]

    @pytest.mark.integration
    def test_selftest_timeout_falls_back(self):
        with patch.dict(os.environ, {"FAKE_NO_READY": "1"}):
            pool = WorkerPool(FAKE, 2, {}, ready_timeout_s=1.0)
            assert pool.selftest() is False
        assert pool.process_count() == 0

    @pytest.mark.integration
    def test_cancel_stops_all_workers(self):
        pool = WorkerPool(FAKE, 2, {})
        assert pool.selftest()
        QTimer.singleShot(300, pool.cancel)
        done, _ = _run(pool, ["slow1", "slow2", "slow3", "slow4"], timeout_ms=10000)
        assert len(done) < 4
        assert pool.process_count() == 0

    @pytest.mark.integration
    def test_majority_crash_stops_pool(self):
        pool = WorkerPool(FAKE, 2, {})
        assert pool.selftest()
        done, _ = _run(pool, ["crash1", "crash2", "crash3", "a", "b"])
        assert set(pool.recompute) >= {"crash1", "crash2"}
        assert {d["partition"] for d in done} | set(pool.recompute) == \
            {"crash1", "crash2", "crash3", "a", "b"}
```

- [ ] **Step 3: Run → ImportError.**

- [ ] **Step 4: Implement `helpers/worker_pool.py`**

```python
# -*- coding: utf-8 -*-
"""Worker pool: N QProcess workers computing partitions (plugin side).

Runs in the QGIS main thread; everything is signal-driven, so the dialog stays
responsive. Crashed or failing partitions are collected in ``recompute`` and
processed by the plugin in its own process afterwards (same behaviour as the
sequential path). If more than half of the started workers crashed, no new
workers are started and the remaining partitions go to ``recompute``.
"""
from collections import deque

from qgis.PyQt.QtCore import QEventLoop, QObject, QProcess, QTimer, pyqtSignal

from . import worker_protocol as wp

KILL_GRACE_MS = 2000


class _Worker:
    """State of one worker process."""

    def __init__(self, ident, process):
        self.ident = ident
        self.process = process
        self.buffer = b""
        self.ready = False
        self.partition = None
        self.stderr = deque(maxlen=50)


class WorkerPool(QObject):  # pylint: disable=too-many-instance-attributes
    progress = pyqtSignal(str, int, str)
    log = pyqtSignal(str, str)
    partition_done = pyqtSignal(dict)
    finished = pyqtSignal()

    def __init__(self, command, worker_count, init_fields, ready_timeout_s=60.0, parent=None):
        super().__init__(parent)
        self._command = command
        self._count = max(1, worker_count)
        self._init = wp.init_message(**init_fields)
        self._timeout_ms = int(ready_timeout_s * 1000)
        self._workers = {}
        self._queue = deque()
        self._next_id = 0
        self._crashes = 0
        self._started = 0
        self._stopping = False
        self._ready_waiter = None
        self.recompute = []

    # -- lifecycle -------------------------------------------------------------
    def process_count(self):
        return sum(1 for w in self._workers.values()
                   if w.process.state() != QProcess.NotRunning)

    def selftest(self):
        """Start one worker and wait for ``ready``; on failure kill everything."""
        worker = self._start_worker()
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        worker.process.finished.connect(loop.quit)
        self._ready_waiter = loop
        timer.start(self._timeout_ms)
        if not worker.ready:
            loop.exec_()
        self._ready_waiter = None
        if worker.ready:
            return True
        self._kill_all()
        return False

    def run(self, partitions):
        self._queue.extend(partitions)
        while len(self._workers) < min(self._count, len(self._queue)) and not self._stopping:
            self._start_worker()
        for worker in list(self._workers.values()):
            self._dispatch(worker)
        self._check_finished()

    def cancel(self):
        self._stopping = True
        self._queue.clear()
        self._kill_all()
        self.finished.emit()

    def stderr_tail(self, n=50):
        lines = []
        for worker in self._workers.values():
            lines.extend(list(worker.stderr)[-n:])
        return lines[-n:]

    # -- internals -------------------------------------------------------------
    def _start_worker(self):
        process = QProcess(self)
        ident = f"w{self._next_id}"
        self._next_id += 1
        worker = _Worker(ident, process)
        self._workers[ident] = worker
        process.readyReadStandardOutput.connect(lambda w=worker: self._on_stdout(w))
        process.readyReadStandardError.connect(lambda w=worker: self._on_stderr(w))
        process.finished.connect(lambda code, status, w=worker: self._on_exit(w))
        process.start(self._command.program, self._command.arguments)
        process.write(wp.encode_command(self._init))
        self._started += 1
        return worker

    def _dispatch(self, worker):
        if not worker.ready or worker.partition is not None or self._stopping:
            return
        if not self._queue:
            worker.process.write(wp.encode_command(wp.exit_message()))
            return
        worker.partition = self._queue.popleft()
        worker.process.write(wp.encode_command(wp.run_message(worker.partition)))

    def _on_stdout(self, worker):
        worker.buffer += bytes(worker.process.readAllStandardOutput())
        *lines, worker.buffer = worker.buffer.split(b"\n")
        for raw in lines:
            message = wp.parse_line(raw.decode("utf-8", "replace").rstrip("\r"))
            if message:
                self._handle(worker, message)

    def _on_stderr(self, worker):
        text = bytes(worker.process.readAllStandardError()).decode("utf-8", "replace")
        worker.stderr.extend(text.splitlines())

    def _handle(self, worker, message):
        kind = message["type"]
        if kind == "ready":
            worker.ready = True
            if self._ready_waiter is not None:
                self._ready_waiter.quit()
            self._dispatch(worker)
        elif kind == "progress":
            self.progress.emit(message["partition"], message["phase"], message["phase_name"])
        elif kind == "log":
            prefix = f"[{worker.partition}] " if worker.partition else ""
            self.log.emit(message["level"], prefix + message["message"])
        elif kind == "done":
            worker.partition = None
            self.partition_done.emit(message)
            self._dispatch(worker)
            self._check_finished()
        elif kind == "error":
            self.log.emit("WARNING", f"[{message['partition']}] Worker-Fehler: {message['message']} "
                                     "– wird im Hauptprozess nachgerechnet")
            self.recompute.append(message["partition"])
            worker.partition = None
            self._dispatch(worker)
            self._check_finished()

    def _on_exit(self, worker):
        if self._stopping:
            return
        if worker.partition is not None:                 # crashed during a partition
            self._crashes += 1
            self.recompute.append(worker.partition)
            self.log.emit("WARNING", f"[{worker.partition}] Worker beendet sich unerwartet – "
                                     "wird im Hauptprozess nachgerechnet")
            worker.partition = None
            if self._crashes * 2 > self._started:        # majority crashed → stop the pool
                self.recompute.extend(self._queue)
                self._queue.clear()
            elif self._queue:
                self._start_worker()
        self._check_finished()

    def _check_finished(self):
        busy = any(w.partition is not None for w in self._workers.values())
        if not self._queue and not busy and not self._stopping:
            self._stopping = True
            QTimer.singleShot(0, self._finish)

    def _finish(self):
        for worker in self._workers.values():
            if worker.process.state() != QProcess.NotRunning:
                worker.process.write(wp.encode_command(wp.exit_message()))
                worker.process.waitForFinished(KILL_GRACE_MS)
        self._kill_all()
        self.finished.emit()

    def _kill_all(self):
        for worker in self._workers.values():
            if worker.process.state() != QProcess.NotRunning:
                worker.process.terminate()
                if not worker.process.waitForFinished(KILL_GRACE_MS):
                    worker.process.kill()
                    worker.process.waitForFinished(KILL_GRACE_MS)
```

- [ ] **Step 5: Run tests → PASS** (adjust timings if the CI machine is slow; never weaken assertions about results/recompute).
- [ ] **Step 6: Commit** (only with the user's go-ahead)

---

### Task 8: Orchestration in `IBTool.start_processing()`

**Files:**
- Modify: `ibtool/ibtool.py` (`start_processing`, `cancel_processing`, `unload`, new helpers)
- Test: `test/test_ibtool.py` (new class `TestParallelOrchestration`)

**Interfaces:**
- Consumes: Tasks 1–7.
- Produces (methods on `IBTool`):
  - `_effective_worker_count() -> int` (UI value; `0` → `default_worker_count()`)
  - `_dispatch_partitions(names: list[str], ctx: dict, worker_count: int) -> None` — the switch: sequential if `worker_count <= 1`, no worker command or failed self-test; else parallel, then the recompute list sequentially
  - `_prepare_manifest(workspace, inputs, params, crs, del_part_log) -> bool` (False = do not start; shows a `QMessageBox.warning` with differences)
  - `_process_partitions_sequential(names, ctx) -> None`
  - `_process_partitions_parallel(names, ctx, command, worker_count) -> list[str]` (returns recompute list; empty if all done)
  - `_on_partition_finished(name, rel_path, features, buildings, results_dir, log_fin) -> None` (single place that appends the finish line and updates progress)
  - `self._pool: Optional[WorkerPool]`

**Flow of the new `start_processing()`** (replace the code from `# Phase 1: Load Data` to the end of the partition loop; keep validation, UI lock, heartbeat, cancel handling, Save Output):

1. Phase 1: load layers (unchanged) **+** save `aux_layers_line` to `workspace/layer_aux_line.gpkg` and reload it as OGR layer (used by both paths, so sequential and worker read identical data).
2. Global density (unchanged).
3. `results_dir = workspace + "IB_Tool_Results"`; `cleanup_temporary(results_dir)`.
4. Manifest: `current = build_manifest(...)`; if `del_part_log` → clear `parts/`, finish log, `merge_temp`, write manifest `running`; else `stored = read_manifest(workspace)`: `None` + finish log with entries → INFO "kein Manifest (älterer Lauf)" and continue; `stored` + differences → `QMessageBox.warning(...)` listing differences, abort run (no processing); else continue. Write manifest `running`.
5. `finished = read_finished(log_fin)`; `valid, recompute = validate_finished(results_dir, finished)`; log WARNING for each `recompute`; `todo = [p for p in part_list if p not in valid]`.
6. Estimate buildings per partition (for order + progress): `QgsSpatialIndex` over `layer_hu` feature bboxes; per partition count index hits of its bbox → `estimates`; `todo.sort(key=lambda p: -estimates[p])` for the pool (sequential keeps `part_list` order).
7. `worker_count = self._effective_worker_count()`; `command = find_worker_command(self.plugin_dir)` (when `worker_count > 1`); if command: pool + `selftest()`; on failure WARNING with `stderr_tail()` → sequential.
8. Parallel: `self._pool.run(todo)`; local `QEventLoop` until `finished`; on `partition_done` → `_on_partition_finished`; then process `pool.recompute` sequentially (`_process_partitions_sequential`).
9. Sequential: for each name → `_run_partition_pipeline` (Task 3) → `write_part_result` (or skipped) → `_on_partition_finished`.
10. Final merge: base layer = `merge_temp` if it exists and the finish log has `OLD_FORMAT` entries, else empty layer → `merge_results(results_dir, part_list, read_finished(log_fin), base, crs)`.
11. Save Output (unchanged); write manifest `finished`. On cancel: manifest `cancelled`; on exception: `failed`.

- [ ] **Step 1: Write failing tests** (mocked; real data in Task 9)

```python
class TestParallelOrchestration:
    """start_processing chooses worker vs. sequential mode and keeps resume safe."""

    @classmethod
    def setup_class(cls):
        cls.tool = _make_tool()

    @pytest.mark.unit
    def test_effective_worker_count_auto(self):
        self.tool.dlg.WorkerCountBox.setValue(0)
        with patch("ibtool.ibtool.ibtool.default_worker_count", return_value=3):
            assert self.tool._effective_worker_count() == 3
        self.tool.dlg.WorkerCountBox.setValue(2)
        assert self.tool._effective_worker_count() == 2

    @pytest.mark.unit
    def test_manifest_mismatch_blocks_resume(self, tmp_path):
        with patch("ibtool.ibtool.ibtool.read_manifest", return_value={"x": 1}), \
                patch("ibtool.ibtool.ibtool.compare_manifests", return_value=["Gebäude-Datei geändert"]), \
                patch("ibtool.ibtool.ibtool.QMessageBox") as box:
            ok = self.tool._prepare_manifest(str(tmp_path) + "/", {}, {}, "EPSG:25833", False)
        assert ok is False
        assert "Gebäude-Datei geändert" in box.warning.call_args.args[2]

    @pytest.mark.unit
    def test_no_worker_command_runs_sequential(self):
        with patch("ibtool.ibtool.ibtool.find_worker_command", return_value=None), \
                patch.object(self.tool, "_process_partitions_sequential") as seq, \
                patch.object(self.tool, "_process_partitions_parallel") as par:
            self.tool._dispatch_partitions(["P1", "P2"], ctx={}, worker_count=3)
        seq.assert_called_once()
        par.assert_not_called()

    @pytest.mark.unit
    def test_failed_selftest_runs_sequential(self):
        pool = MagicMock()
        pool.selftest.return_value = False
        with patch("ibtool.ibtool.ibtool.find_worker_command", return_value=MagicMock()), \
                patch("ibtool.ibtool.ibtool.WorkerPool", return_value=pool), \
                patch.object(self.tool, "_process_partitions_sequential") as seq:
            self.tool._dispatch_partitions(["P1"], ctx={"init_fields": {}}, worker_count=3)
        seq.assert_called_once()

    @pytest.mark.unit
    def test_recompute_list_runs_in_process(self):
        with patch("ibtool.ibtool.ibtool.find_worker_command", return_value=MagicMock()), \
                patch.object(self.tool, "_process_partitions_parallel", return_value=["P2"]), \
                patch.object(self.tool, "_process_partitions_sequential") as seq, \
                patch("ibtool.ibtool.ibtool.WorkerPool") as pool_cls:
            pool_cls.return_value.selftest.return_value = True
            self.tool._dispatch_partitions(["P1", "P2"], ctx={"init_fields": {}}, worker_count=3)
        seq.assert_called_once_with(["P2"], {"init_fields": {}})

    @pytest.mark.unit
    def test_cancel_kills_pool(self):
        self.tool._is_processing = True
        self.tool._pool = MagicMock()
        try:
            self.tool.cancel_processing()
            self.tool._pool.cancel.assert_called_once()
        finally:
            self.tool._is_processing = False
            self.tool._pool = None
```

`_dispatch_partitions(names, ctx, worker_count)` is the switch (steps 7–8): `ctx` bundles `layers`, `crs`, `workspace`, `results_dir`, `log_fin`, `params`, `debug_mode`, `global_density`, `estimates`, `init_fields`.

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement** in `ibtool/ibtool.py`:
  - imports: `from ibtool.helpers.worker_launcher import find_worker_command, default_worker_count`, `from ibtool.helpers.worker_pool import WorkerPool`, `from ibtool.helpers.partition_results import (...)`, `from ibtool.helpers.run_manifest import (...)`, `QEventLoop` from `qgis.PyQt.QtCore`.
  - `__init__`: `self._pool = None`.
  - `cancel_processing()`: when processing and `self._pool` → `self._pool.cancel()` (plus the existing flag).
  - `unload()` and the dialog close callback: `if self._pool: self._pool.cancel()`.
  - `_process_partitions_parallel(names, ctx, command, worker_count)`: create `WorkerPool(command, worker_count, ctx["init_fields"])`, connect `progress` → update per-partition progress (overall percent = Σ estimate_share × PHASE_PERCENT[phase]/100 over running partitions + done), `log` → `logger.log`, `partition_done` → `_on_partition_finished`; run with `QEventLoop`; on `ProcessingCancelledError` flag set via Cancel → raise after the loop; return `pool.recompute`.
  - Status line via `self.dlg.phaseLabel.setText(f"{n} Worker · {done} von {total} Partitionen fertig · läuft: {', '.join(running)}")`.
  - `init_fields` = `plugin_root=self.plugin_dir`, `sys_path=list(sys.path)`, `prefix_path=QgsApplication.prefixPath()`, input GPKG paths (`layer_hu.gpkg`, `layer_rn.gpkg`, `layer_part.gpkg`, `layer_aux_line.gpkg`), `crs=crs.authid()`, `params`, `workspace`, `results_dir`, `debug_mode`, `global_density`, `log_level=self.dlg.LogLevelBox.currentText() or "INFO"`, `parent_pid=os.getpid()`.

- [ ] **Step 4: Run tests** (`test_ibtool.py` + full suite) → PASS.
- [ ] **Step 5: Commit** (only with the user's go-ahead)

---

### Task 9: UI field, config, settings restore, translations

**Files:**
- Modify: `ibtool/ibtool_dialog_base.ui` (`formLayoutDebug`, new row 6)
- Modify: `helpers/config_manager.py` (`ProcessingConfig.worker_count: int = 0`, load/save `worker_count`)
- Modify: `ibtool/ibtool.py` (`_apply_config_to_ui`, `_save_config_from_ui`, `_delete_config`, restore prompt)
- Modify: `i18n/IBTool_de.ts` + recompile `.qm` (via `compile.bat`)
- Test: `test/test_config_manager.py`, `test/test_ibtool.py`

**Interfaces:**
- Produces: `self.dlg.WorkerCountBox` (QSpinBox, min 0, max 16, special value text `"Automatisch"` for 0, tooltip "Anzahl paralleler Worker-Prozesse (nur Windows). 0 = automatisch (Kerne − 1, höchstens 4), 1 = nacheinander."); `IBTool._offer_manifest_restore(workspace: str) -> None`.

- [ ] **Step 1: Failing tests**

```python
# test/test_config_manager.py
@pytest.mark.unit
def test_worker_count_round_trip(tmp_path):
    from ibtool.helpers.config_manager import ConfigManager
    cm = ConfigManager(str(tmp_path))
    cm.update_config(processing={"worker_count": 3})
    cm.save_config()
    cm2 = ConfigManager(str(tmp_path))
    cm2.load_config()
    assert cm2.config.processing.worker_count == 3

@pytest.mark.unit
def test_worker_count_defaults_to_auto(tmp_path):
    from ibtool.helpers.config_manager import ConfigManager
    assert ConfigManager(str(tmp_path)).config.processing.worker_count == 0
```

```python
# test/test_ibtool.py
class TestManifestRestorePrompt:

    @classmethod
    def setup_class(cls):
        cls.tool = _make_tool()

    @pytest.mark.unit
    def test_offers_restore_when_manifest_differs_and_applies_on_yes(self, tmp_path):
        manifest = {"inputs": {"hu": {"path": "C:/x/hu.gpkg"}}, "params": {"min_area": 60.0},
                    "crs": "EPSG:25833"}
        with patch("ibtool.ibtool.ibtool.read_manifest", return_value=manifest), \
                patch("ibtool.ibtool.ibtool.QMessageBox") as box:
            box.question.return_value = box.Yes
            self.tool._offer_manifest_restore(str(tmp_path))
        assert self.tool.dlg.HuPath.text() == "C:/x/hu.gpkg"
        assert self.tool.dlg.MinAreaBox.value() == 60

    @pytest.mark.unit
    def test_no_prompt_without_manifest(self, tmp_path):
        with patch("ibtool.ibtool.ibtool.QMessageBox") as box:
            self.tool._offer_manifest_restore(str(tmp_path))
        box.question.assert_not_called()
```

- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement**
  - `.ui`: inside `formLayoutDebug` after the `DebugModeBox` item add rows 6 (`QLabel name="labelWorkerCount"` text `Worker processes (parallel)`) and (`QSpinBox name="WorkerCountBox"`, min 0, max 16, value 0, `specialValueText` `Automatic`, tooltip as above). Text in English (translated via `.ts`).
  - `config_manager`: field, `section.getint('worker_count', 0)`, save `str(...)`, add to `get_processing_parameters`.
  - `ibtool.py`: `_apply_config_to_ui` sets `WorkerCountBox`; `_save_config_from_ui` stores `worker_count`; `_delete_config` resets to 0; `WorkspacePath.editingFinished` and `select_workspace_file` call `_offer_manifest_restore(path)`: if a manifest exists and its inputs/params differ from the UI → `QMessageBox.question(self.dlg, "IB-Tool", "Dieses Arbeitsverzeichnis enthält einen begonnenen Lauf.\nEinstellungen (Eingabedaten und Parameter) daraus übernehmen?")` → on Yes set `HuPath`, `RnPath`, `PartPath`, `AuxPath`, `FilterPath`, parameter boxes, CRS from `manifest_to_ui_settings`.
  - `i18n/IBTool_de.ts`: add entries for the two new UI strings ("Worker processes (parallel)" → "Worker-Prozesse (parallel)", "Automatic" → "Automatisch", tooltip); run `compile.bat` (lrelease) to rebuild `IBTool_de.qm`.
- [ ] **Step 4: Run tests → PASS**; `test_translations.py` must stay green.
- [ ] **Step 5: Commit** (only with the user's go-ahead)

---

### Task 10: Verification with real data, resume test, docs

**Files:**
- Modify: `scripts/profile_pipeline.py` (`--workers N`)
- Create: `scripts/resume_test.py`
- Modify: `docs/CHANGELOG.md`, `docs/how-it-works.md` (Output section: parts/manifest), `docs/CONFIG_README.md` (`worker_count`), `docs/plugin-architecture.md` (worker mode), `docs/superpowers/plans/2026-11-01-runtime-optimization.md` (Phase 4 results)

- [ ] **Step 1: `profile_pipeline.py --workers N`** — after the global density: if `N > 1`, build `init_fields` like Task 8, `WorkerPool(find_worker_command(PLUGIN), N, init_fields)`, `selftest()` (fail → exit 2 with stderr tail), run partitions sorted by estimate in a `QEventLoop`, recompute list in-process; then `merge_results(...)` and save `result.gpkg`. With `N == 1` the sequential path also writes part files and uses `merge_results` (same code as the plugin).

- [ ] **Step 2: Full runs + compare** (each must print `RESULT: IDENTICAL`; record timings)

```
python-qgis-ltr.bat scripts\profile_pipeline.py --out <d1> --no-cprofile --workers 1
python-qgis-ltr.bat scripts\profile_pipeline.py --out <d3> --no-cprofile --workers 3
python-qgis-ltr.bat scripts\profile_pipeline.py --out <d4> --no-cprofile --workers 4
python-qgis-ltr.bat scripts\compare_results.py <3.44 reference> <dN>\result.gpkg --parts Testdaten\A_PART.shp
```
Repeat with `"C:\Program Files\QGIS 3.40.0\bin\python-qgis.bat"` against the 3.40 reference. Success: 3.44 with 3–4 workers **< 100 s**.

- [ ] **Step 3: `scripts/resume_test.py`** — runs `profile_pipeline.py --workers 3 --out <d>` as a subprocess, kills it (`proc.kill()`) once ≥ 25 lines `done` appeared in the finish log, then reruns with `--resume` (new flag: do not clear `parts/` / finish log, use manifest) and compares the result with the reference → must be IDENTICAL; also asserts that the second run skipped the partitions already in the finish log.

- [ ] **Step 4: Docs** — CHANGELOG (0.2.5 "Performance": worker mode with numbers; "Changed": per-partition result files + `ibtool_run.json`, `IB_Tool_merge_temp.gpkg` no longer written; resume checks), `how-it-works.md` Output section, `CONFIG_README.md` (`worker_count`, 0 = automatic), `plugin-architecture.md` (worker mode diagram/units), roadmap Phase 4 checkboxes + results.

- [ ] **Step 5: GUI test by the user** (after a QGIS restart): progress/status line with several workers; Cancel during PART_64 (reacts ≤ 2 s); close QGIS during a run → no `python.exe`/`pythonw.exe` left in the task manager; restart → resume incl. "Einstellungen übernehmen?" prompt; result identical.

- [ ] **Step 6: Commit** (only with the user's go-ahead)

---

## Self-Review (done while writing)

- Spec coverage: components (Tasks 1–8), protocol (2), scheduling/results/merge (4, 7, 8), progress/status line (8), errors/fallback table (7, 8), cancel/unload/orphans (1 `parent_alive`, 6 guard, 8), resume/manifest/migration/restore (4, 5, 8, 9), debug mode (unchanged per-partition folders; covered by `run_partition`), tests (all tasks + 10), out-of-scope respected.
- Placeholders: the only intentionally abbreviated code is the verbatim move in Task 3 Step 3, with exact source lines and substitution rules.
- Names consistent across tasks: `run_partition`, `PHASE_PERCENT`, `write_part_result`, `FinishedPart`, `merge_results`, `WorkerCommand`, `find_worker_command`, `WorkerPool.selftest/run/cancel/recompute`, `build_manifest/compare_manifests/read_manifest/write_manifest`.
