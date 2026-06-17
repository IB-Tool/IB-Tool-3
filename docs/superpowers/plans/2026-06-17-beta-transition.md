# IBTool Beta Transition — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move IBTool from alpha to controlled external beta: remove dead code, add a dependency guard, fix cross-platform folder-open, bump to 0.2.0, and write a quickstart guide.

**Architecture:** Five sequential, independently committable tasks on a new branch `BETA_Transition` created from `master` after `FIX_Overlapping_Buildings` is merged.

**Tech Stack:** Python 3.11+, QGIS 3.40+, PyQt5, `subprocess` (stdlib), `sys` (stdlib), `importlib` (stdlib, for tests only).

---

## File Map

| Action | File | What changes |
|---|---|---|
| Modify | `__init__.py` | Add `_MISSING_PACKAGES`, `_MissingDepsPlugin` stub, guard `classFactory` |
| Modify | `ibtool/ibtool.py` | Remove `ProcessingThread`, add `_open_directory()`, add `subprocess`/`sys` imports, update `cancel_processing` |
| Modify | `test/test_ibtool.py` | Remove `TestProcessingThread`, update `cancel_processing` test, add `TestOpenDirectory` |
| Modify | `test/test_init.py` | Add `TestMissingDepsPlugin` class |
| Modify | `metadata.txt` | `version=0.2.0`, `experimental=False`, update `changelog` field |
| Modify | `docs/CHANGELOG.md` | Close `## Unreleased` as `0.2.0 — 2026-06-17`, add beta-transition entries |
| Create | `docs/quickstart.md` | New user-facing quickstart guide |
| Modify | `README.md` | Add `## Quick Start` link at the top |

---

## Task 1: Merge Cleanup — Commit Dangling Files + Remove ProcessingThread

**Files:**
- Commit (untracked): `docs/superpowers/plans/2026-06-14-mst-clustering-circular-geometry-fix.md`
- Commit (untracked): `docs/superpowers/specs/2026-06-14-mst-clustering-circular-geometry-fix-design.md`
- Modify: `ibtool/ibtool.py`
- Modify: `test/test_ibtool.py`

### Prerequisites

Start from `master` after `FIX_Overlapping_Buildings` PR is merged:

```bash
git checkout master
git pull
git checkout -b BETA_Transition
```

- [ ] **Step 1: Commit the two untracked design-history files**

  ```bash
  git add docs/superpowers/plans/2026-06-14-mst-clustering-circular-geometry-fix.md
  git add docs/superpowers/specs/2026-06-14-mst-clustering-circular-geometry-fix-design.md
  git commit -m "docs: commit FIX-MBR-Orintation design history files"
  ```

- [ ] **Step 2: Remove `QThread` and `pyqtSignal` from imports in `ibtool/ibtool.py`**

  Current (lines 23–29):
  ```python
  from qgis.PyQt.QtCore import (
      QCoreApplication,
      QSettings,
      QThread,
      QTranslator,
      pyqtSignal
  )
  ```
  Replace with:
  ```python
  from qgis.PyQt.QtCore import (
      QCoreApplication,
      QSettings,
      QTranslator,
  )
  ```

- [ ] **Step 3: Update the module docstring in `ibtool/ibtool.py`**

  Current (lines 11–14):
  ```python
  Classes:
      ProcessingThread: QThread subclass (currently unused stub processing runs
          synchronously on the main thread via ``start_processing()``).
      IBTool: Main QGIS plugin class registered via ``classFactory()``.
  ```
  Replace with:
  ```python
  Classes:
      IBTool: Main QGIS plugin class registered via ``classFactory()``.
  ```

- [ ] **Step 4: Delete the `ProcessingThread` class from `ibtool/ibtool.py`**

  Remove lines 80–97 entirely (from `class ProcessingThread(QThread):` through the closing of its `run` method):
  ```python
  class ProcessingThread(QThread):  # pylint: disable=too-few-public-methods
      """Thread for background processing"""
      progress_update = pyqtSignal(int)
      log_message = pyqtSignal(str)
      phase_update = pyqtSignal(int, int, str)   # phase, total, name
      finished_ok = pyqtSignal(str)              # output_path
      finished_error = pyqtSignal(str)           # error_message

      def run(self):
          """Main processing logic"""
          try:
              for i in range(101):  # Progress from 0 to 100
                  self.msleep(50)  # Simulated processing (50 ms delay)
                  self.progress_update.emit(i)  # Update progress
                  self.log_message.emit(f"Progress: {i}%")  # Send message
          except RuntimeError as e:
              self.log_message.emit(f"Error: {str(e)}")
  ```

- [ ] **Step 5: Remove `self.thread` references from `IBTool.__init__` in `ibtool/ibtool.py`**

  Remove lines 149–152:
  ```python
  # Thread for background processing
  self.thread = ProcessingThread()
  self.thread.progress_update.connect(self.update_progress)
  self.thread.log_message.connect(self.update_messages)
  ```

- [ ] **Step 6: Replace `cancel_processing` in `ibtool/ibtool.py`**

  Current (lines 175–179):
  ```python
  def cancel_processing(self):
      """Cancel processing"""
      if self.thread.isRunning():
          self.thread.terminate()  # Terminate thread
          self.update_messages("Processing canceled.")
  ```
  Replace with:
  ```python
  def cancel_processing(self):
      """Cancel processing (no-op — processing runs synchronously on the main thread)."""
      self.update_messages("Processing cannot be cancelled mid-run.")
  ```

- [ ] **Step 7: Update `test/test_ibtool.py` — remove `ProcessingThread` import**

  Current (line 50):
  ```python
  from ibtool.ibtool.ibtool import IBTool, ProcessingThread  # noqa: E402
  ```
  Replace with:
  ```python
  from ibtool.ibtool.ibtool import IBTool  # noqa: E402
  ```

- [ ] **Step 8: Delete `TestProcessingThread` class from `test/test_ibtool.py`**

  Remove lines 64–117 entirely (the full `TestProcessingThread` class with all five test methods).

- [ ] **Step 9: Replace `test_cancel_processing_when_idle_does_not_crash` in `test/test_ibtool.py`**

  Current (lines 220–229):
  ```python
  @pytest.mark.unit
  @pytest.mark.edge_case
  def test_cancel_processing_when_idle_does_not_crash(self):
      """cancel_processing must not raise when the processing thread is idle."""
      assert not self.tool.thread.isRunning(), \
          "Precondition: thread must not be running at test start"

      self.tool.cancel_processing()  # Must not raise
  ```
  Replace with:
  ```python
  @pytest.mark.unit
  def test_cancel_processing_does_not_crash(self):
      """cancel_processing must not raise."""
      self.tool.cancel_processing()  # Must not raise
  ```

- [ ] **Step 10: Run the tests and verify they pass**

  ```
  docker run --rm qgis-plugin-test pytest test/test_ibtool.py -v
  ```
  Expected: all tests pass; no `ProcessingThread` or `self.tool.thread` failures.

- [ ] **Step 11: Commit**

  ```bash
  git add ibtool/ibtool.py test/test_ibtool.py
  git commit -m "refactor: remove unused ProcessingThread stub"
  ```

---

## Task 2: Dependency Guard

**Files:**
- Modify: `__init__.py` (project root — the QGIS plugin entry point)
- Modify: `test/test_init.py`

- [ ] **Step 1: Add imports to `test/test_init.py`**

  After the existing imports at the top of the file (`import os`, `import logging`, `import configparser`), add:
  ```python
  import importlib.util
  import pytest
  from pathlib import Path
  from unittest.mock import MagicMock, patch
  ```

- [ ] **Step 2: Append `TestMissingDepsPlugin` class to `test/test_init.py`**

  Append after the existing `TestInit` class:
  ```python

  # ---------------------------------------------------------------------------
  # Helpers
  # ---------------------------------------------------------------------------

  def _load_root_init():
      """Load IB-Tool-3/__init__.py directly, bypassing the conftest virtual package.

      Returns the module object with _MISSING_PACKAGES, _MissingDepsPlugin,
      and classFactory defined as module-level names.
      """
      init_path = Path(__file__).resolve().parent.parent / "__init__.py"
      spec = importlib.util.spec_from_file_location("_plugin_root_init", init_path)
      mod = importlib.util.module_from_spec(spec)
      spec.loader.exec_module(mod)
      return mod


  # ---------------------------------------------------------------------------
  # TestMissingDepsPlugin
  # ---------------------------------------------------------------------------

  class TestMissingDepsPlugin:
      """Tests for the _MissingDepsPlugin stub class in the root __init__.py."""

      @pytest.mark.unit
      def test_missing_packages_is_empty_when_scipy_and_networkx_present(self):
          """In the Docker test env, scipy and networkx are available — list must be empty."""
          mod = _load_root_init()

          assert mod._MISSING_PACKAGES == [], (
              f"Expected no missing packages in test env, got: {mod._MISSING_PACKAGES}"
          )

      @pytest.mark.unit
      def test_initGui_pushes_critical_message(self):
          """_MissingDepsPlugin.initGui must push a Critical message bar entry."""
          mod = _load_root_init()
          mock_iface = MagicMock()

          with patch("qgis.core.Qgis") as mock_qgis:
              mock_qgis.Critical = 2
              plugin = mod._MissingDepsPlugin(mock_iface, ["scipy"])
              plugin.initGui()

          mock_iface.messageBar.return_value.pushMessage.assert_called_once()

      @pytest.mark.unit
      def test_initGui_message_names_all_missing_packages(self):
          """The message bar text must name every package in the missing list."""
          mod = _load_root_init()
          mock_iface = MagicMock()

          with patch("qgis.core.Qgis"):
              plugin = mod._MissingDepsPlugin(mock_iface, ["scipy", "networkx"])
              plugin.initGui()

          call_text = str(mock_iface.messageBar.return_value.pushMessage.call_args)
          assert "scipy" in call_text
          assert "networkx" in call_text

      @pytest.mark.unit
      def test_initGui_message_includes_pip_install_command(self):
          """The message bar text must contain a pip install command."""
          mod = _load_root_init()
          mock_iface = MagicMock()

          with patch("qgis.core.Qgis"):
              plugin = mod._MissingDepsPlugin(mock_iface, ["scipy"])
              plugin.initGui()

          call_text = str(mock_iface.messageBar.return_value.pushMessage.call_args)
          assert "pip install" in call_text

      @pytest.mark.unit
      def test_unload_does_not_raise(self):
          """_MissingDepsPlugin.unload must be a safe no-op."""
          mod = _load_root_init()
          plugin = mod._MissingDepsPlugin(MagicMock(), ["scipy"])

          plugin.unload()  # Must not raise

      @pytest.mark.unit
      def test_classFactory_returns_missing_deps_plugin_when_packages_absent(self):
          """classFactory must return _MissingDepsPlugin when _MISSING_PACKAGES is non-empty."""
          mod = _load_root_init()
          mod._MISSING_PACKAGES = ["scipy"]

          result = mod.classFactory(MagicMock())

          assert isinstance(result, mod._MissingDepsPlugin)
  ```

- [ ] **Step 3: Run the tests and verify they fail**

  ```
  docker run --rm qgis-plugin-test pytest test/test_init.py::TestMissingDepsPlugin -v
  ```
  Expected: `AttributeError: module '_plugin_root_init' has no attribute '_MissingDepsPlugin'`

- [ ] **Step 4: Implement the dependency guard in `__init__.py`**

  After the existing virtual package registration block (after line 41, before `def classFactory`), insert:

  ```python

  # ---------------------------------------------------------------------------
  # Dependency check — runs at import time, before any heavy tool imports.
  # ---------------------------------------------------------------------------
  _MISSING_PACKAGES: list[str] = []
  for _pkg in ("scipy", "networkx"):
      try:
          __import__(_pkg)
      except ImportError:
          _MISSING_PACKAGES.append(_pkg)


  class _MissingDepsPlugin:
      """Minimal plugin stub shown when required packages are absent.

      Displays a clear, actionable error in the QGIS message bar instead of
      a cryptic Python traceback from a failed deep import.
      """

      def __init__(self, iface, missing: list) -> None:
          self._iface = iface
          self._missing = missing

      def initGui(self) -> None:  # pylint: disable=invalid-name
          """Push a persistent Critical message bar entry listing the missing packages."""
          from qgis.core import Qgis
          pkg = ", ".join(self._missing)
          cmd = " ".join(self._missing)
          self._iface.messageBar().pushMessage(
              "IBTool — Missing dependencies",
              f"Required packages not found: {pkg}. "
              f"Fix with: pip install {cmd} — then restart QGIS.",
              level=Qgis.Critical,
              duration=0,
          )

      def unload(self) -> None:
          pass
  ```

  Replace `classFactory` with:
  ```python
  # noinspection PyPep8Naming
  def classFactory(iface):  # pylint: disable=invalid-name
      """Load IBTool class from file IBTool.

      Returns _MissingDepsPlugin when scipy or networkx are absent so the user
      sees a clear install prompt instead of a Python traceback.

      :param iface: A QGIS interface instance.
      :type iface: QgsInterface
      """
      if _MISSING_PACKAGES:
          return _MissingDepsPlugin(iface, _MISSING_PACKAGES)
      from .ibtool.ibtool import IBTool
      return IBTool(iface)
  ```

- [ ] **Step 5: Run the tests and verify they pass**

  ```
  docker run --rm qgis-plugin-test pytest test/test_init.py -v
  ```
  Expected: all tests pass, including the new `TestMissingDepsPlugin` class.

- [ ] **Step 6: Run the full suite to check for regressions**

  ```
  docker run --rm qgis-plugin-test pytest test/ -v
  ```
  Expected: all previously passing tests still pass.

- [ ] **Step 7: Commit**

  ```bash
  git add __init__.py test/test_init.py
  git commit -m "feat: add dependency guard for missing scipy/networkx"
  ```

---

## Task 3: Cross-Platform Folder Opening

**Files:**
- Modify: `ibtool/ibtool.py`
- Modify: `test/test_ibtool.py`

- [ ] **Step 1: Append `TestOpenDirectory` class to `test/test_ibtool.py`**

  Append after the last class in the file:
  ```python

  # ---------------------------------------------------------------------------
  # TestOpenDirectory — unit tests for _open_directory
  # ---------------------------------------------------------------------------

  class TestOpenDirectory:
      """Unit tests for the module-level _open_directory helper."""

      @pytest.mark.unit
      def test_win32_calls_os_startfile(self):
          """On win32, _open_directory must call os.startfile with the given path."""
          from ibtool.ibtool.ibtool import _open_directory
          with patch("ibtool.ibtool.ibtool.sys") as mock_sys, \
               patch("ibtool.ibtool.ibtool.os.startfile") as mock_sf:
              mock_sys.platform = "win32"
              _open_directory("/tmp/result")
          mock_sf.assert_called_once_with("/tmp/result")

      @pytest.mark.unit
      def test_darwin_calls_open(self):
          """On macOS, _open_directory must call subprocess.Popen(['open', path])."""
          from ibtool.ibtool.ibtool import _open_directory
          with patch("ibtool.ibtool.ibtool.sys") as mock_sys, \
               patch("ibtool.ibtool.ibtool.subprocess.Popen") as mock_popen:
              mock_sys.platform = "darwin"
              _open_directory("/tmp/result")
          mock_popen.assert_called_once_with(["open", "/tmp/result"])

      @pytest.mark.unit
      def test_linux_calls_xdg_open(self):
          """On Linux, _open_directory must call subprocess.Popen(['xdg-open', path])."""
          from ibtool.ibtool.ibtool import _open_directory
          with patch("ibtool.ibtool.ibtool.sys") as mock_sys, \
               patch("ibtool.ibtool.ibtool.subprocess.Popen") as mock_popen:
              mock_sys.platform = "linux"
              _open_directory("/tmp/result")
          mock_popen.assert_called_once_with(["xdg-open", "/tmp/result"])
  ```

- [ ] **Step 2: Run the tests and verify they fail**

  ```
  docker run --rm qgis-plugin-test pytest test/test_ibtool.py::TestOpenDirectory -v
  ```
  Expected: `ImportError: cannot import name '_open_directory' from 'ibtool.ibtool.ibtool'`

- [ ] **Step 3: Add `subprocess` and `sys` imports to `ibtool/ibtool.py`**

  Current stdlib imports (lines 20–21):
  ```python
  import json
  import os
  ```
  Replace with:
  ```python
  import json
  import os
  import subprocess
  import sys
  ```

- [ ] **Step 4: Add `_open_directory` function to `ibtool/ibtool.py`**

  Insert as a module-level function directly before `class IBTool` (after the import block and the `logger = MainLogger` line):
  ```python

  def _open_directory(path: str) -> None:
      """Open a directory in the system file explorer, cross-platform.

      Args:
          path: Absolute path to the directory to open.
      """
      if sys.platform == "win32":
          os.startfile(path)  # nosec B606 — path validated by caller
      elif sys.platform == "darwin":
          subprocess.Popen(["open", path])  # nosec B603, B607
      else:
          subprocess.Popen(["xdg-open", path])  # nosec B603, B607
  ```

- [ ] **Step 5: Update `_open_output_dir` in `ibtool/ibtool.py`**

  Current:
  ```python
  def _open_output_dir(self):
      """Open the output directory in the file explorer."""
      folder = self._last_output_folder or os.path.dirname(self._last_output_path)
      if folder and os.path.isdir(folder):
          os.startfile(folder)  # nosec B606 — path validated by os.path.isdir above
      else:
          msg("Output directory not found.")
  ```
  Replace with:
  ```python
  def _open_output_dir(self):
      """Open the output directory in the file explorer."""
      folder = self._last_output_folder or os.path.dirname(self._last_output_path)
      if folder and os.path.isdir(folder):
          _open_directory(folder)
      else:
          msg("Output directory not found.")
  ```

- [ ] **Step 6: Run the new tests and verify they pass**

  ```
  docker run --rm qgis-plugin-test pytest test/test_ibtool.py::TestOpenDirectory -v
  ```
  Expected: all 3 tests pass.

- [ ] **Step 7: Run the full suite to check for regressions**

  ```
  docker run --rm qgis-plugin-test pytest test/ -v
  ```
  Expected: all previously passing tests still pass.

- [ ] **Step 8: Commit**

  ```bash
  git add ibtool/ibtool.py test/test_ibtool.py
  git commit -m "fix: replace os.startfile with cross-platform _open_directory"
  ```

---

## Task 4: Version & Metadata

**Files:**
- Modify: `metadata.txt`
- Modify: `docs/CHANGELOG.md`

No new tests required — metadata structure is covered by the existing `test/test_init.py::TestInit::test_read_init`.

- [ ] **Step 1: Update `metadata.txt`**

  Make three changes:

  Change `version=0.1.6` to:
  ```
  version=0.2.0
  ```

  Change `experimental=True` to:
  ```
  experimental=False
  ```

  Replace the `changelog=` line with:
  ```
  changelog=0.2.0 - Dependency guard: missing scipy/networkx shows a clear pip install prompt instead of a traceback. Cross-platform folder-open (Linux/Mac/Windows). Complete UI overhaul: 4-step stepper, per-field validation, phase progress, result actions. Full helpers refactoring (docstrings, type hints, snake_case). All processing tools support debug mode. GeoPackage inputs. Checksum-based validation cache. 35 test modules.
  ```

- [ ] **Step 2: Update `docs/CHANGELOG.md` — close the Unreleased section**

  Replace `## Unreleased` (line 10) with the version header, and add a fresh empty `## Unreleased` above it:

  ```markdown
  ## Unreleased

  ---

  ## 0.2.0 — 2026-06-17
  ```

  Then at the end of the existing `## Unreleased` content (before the first `---` separator that separates it from `## 2026-03-03`), append:

  ```markdown
  ### Added
  - **Dependency guard** (`__init__.py`): Plugin detects missing `scipy`/`networkx` at load
    time and shows a persistent `QgsMessageBar` error with the exact `pip install` command
    instead of a cryptic Python traceback.
  - **Cross-platform folder open** (`ibtool/ibtool.py`): `_open_directory()` replaces
    `os.startfile()` — uses `open` on macOS and `xdg-open` on Linux.
  - **Quickstart guide** (`docs/quickstart.md`): Step-by-step installation and first-run
    guide for non-developer users.

  ### Changed
  - **Version** (`metadata.txt`): bumped from `0.1.6` to `0.2.0`.
  - **Experimental flag** (`metadata.txt`): `experimental=True` → `experimental=False`.

  ### Removed
  - **`ProcessingThread` stub** (`ibtool/ibtool.py`): Dead code removed;
    `cancel_processing` updated to a no-op with an informational message.
  ```

- [ ] **Step 3: Verify the existing metadata test still passes**

  ```
  docker run --rm qgis-plugin-test pytest test/test_init.py::TestInit -v
  ```
  Expected: PASS.

- [ ] **Step 4: Commit**

  ```bash
  git add metadata.txt docs/CHANGELOG.md
  git commit -m "chore: bump version to 0.2.0, set experimental=False"
  ```

---

## Task 5: Quickstart Guide

**Files:**
- Create: `docs/quickstart.md`
- Modify: `README.md`

No automated tests — verify by reading through both files.

- [ ] **Step 1: Create `docs/quickstart.md`**

  Create the file with the following content:

  ````markdown
  # IBTool — Quickstart Guide

  This guide gets you from a fresh QGIS installation to a completed settlement
  delineation run.

  ---

  ## 1. System Requirements

  | Requirement | Minimum |
  |---|---|
  | QGIS | 3.40 |
  | Python | 3.11 |
  | scipy | 1.11+ |
  | networkx | 3.0+ |

  **numpy** and **PyQt5** are bundled with QGIS 3.40+ — no action needed.

  **scipy** and **networkx** are *not* bundled with QGIS. Install them once:

  ```bash
  # Windows — open the OSGeo4W Shell:
  pip install scipy networkx

  # Linux / macOS — open a terminal where QGIS's Python is active:
  pip install scipy networkx
  ```

  Then restart QGIS. If the packages are still missing after installation,
  check that you ran `pip` against QGIS's Python (not a system Python). On
  Windows the OSGeo4W Shell sets the correct environment automatically.

  > **Tip:** If IBTool shows a red message bar immediately after loading,
  > it means scipy or networkx are missing. The message contains the exact
  > command to fix it.

  ---

  ## 2. Installation

  1. Download the release ZIP (`IB-Tool_0.2.0.zip`).
  2. Open QGIS → **Plugins** → **Manage and Install Plugins…**
  3. Click **Install from ZIP**.
  4. Select the downloaded ZIP and click **Install Plugin**.
  5. Activate the plugin via the checkbox in the **Installed** tab.
  6. The IB-Tool icon (house outline) appears in the toolbar.

  ---

  ## 3. Input Data

  IBTool requires five inputs. All layers must share the **same projected CRS**
  (default: ETRS89 / UTM zone 32N, EPSG:25832).

  | Input | Format | Min features | Key requirement |
  |---|---|---|---|
  | Building footprints (HU) | `.shp` / `.gpkg` | 50 | Must have `fkt`, `funktion`, or `gfkzshh` field |
  | Road network (RN) | `.shp` / `.gpkg` | 30 | Line geometry |
  | Partitions | `.shp` / `.gpkg` | 1 | Polygon geometry, defines processing regions |
  | Auxiliary network (Aux) | `.shp` / `.gpkg` | 10 | Line geometry |
  | Filter file | `.txt` | — | `[positive]` and `[negative]` sections with ATKIS codes |

  Full field specifications and filter file format: [input-data.md](input-data.md).

  ---

  ## 4. First Run

  ### Step 1 — Input
  Open the plugin. Fill in all path fields using the **…** buttons:
  - Building footprints, Road network, Partitions, Auxiliary network
  - Output file (`.gpkg` — will be created or overwritten)
  - Workspace folder (holds intermediate files and debug layers)
  - Filter file (`.txt`)

  Path fields turn green as each file is found.

  ### Step 2 — Parameters
  For a first test run, leave all values at their defaults.

  Key parameters if you want to tune them:
  | Parameter | Default | Effect |
  |---|---|---|
  | Max gap distance | 15 m | Maximum width of a gap that is bridged |
  | Min patch size | 1 ha | Minimum area of a kept settlement patch |
  | Min buildings per patch | 20 | Minimum building count per kept patch |

  Full parameter descriptions: [parameterization.md](parameterization.md).

  ### Step 3 — Validation
  Click **Check**. The Validation tab shows a checklist:
  - ✅ green — check passed
  - ❌ red — error that blocks processing; fix before continuing
  - ⚠️ yellow — warning; processing can continue

  The **Start** button stays grey until all errors are resolved.

  ### Step 4 — Processing
  Click **Start**. The plugin processes each partition in sequence:
  - The phase label and progress bar update for each pipeline step.
  - Log messages appear in the message box.
  - After completion, three buttons appear:
    - **Load result** — add the output GeoPackage to the current QGIS project
    - **Open folder** — open the output directory in the file explorer
    - **Export log** — save the log to a text file

  ---

  ## 5. Troubleshooting

  ### "Required packages not found: scipy, networkx"
  Install the missing packages and restart QGIS — see
  [System Requirements](#1-system-requirements).

  ### Check button stays red / Start button stays grey
  Read the validation checklist in Step 3. Common causes:

  | Error | Fix |
  |---|---|
  | CRS mismatch | Reproject all input layers to the same CRS |
  | Too few features | HU ≥ 50 buildings, RN ≥ 30 segments, Aux ≥ 10 |
  | Missing field | Building layer must have `fkt`, `funktion`, or `gfkzshh` |
  | Output path not writable | Check folder permissions; avoid read-only drives |

  ### Processing produces an empty output
  - Check that the filter file's `[positive]` section contains codes that
    actually appear in your `fkt` / `funktion` field.
  - Enable **Debug mode** (checkbox in the Parameters tab) and re-run.
    Open the workspace folder — numbered GeoPackage snapshots in
    `debug/PART_*/` let you trace exactly where the pipeline diverges.

  ### Output file already exists
  Delete the existing file first, or choose a different output path.
  The plugin does not overwrite an existing GeoPackage.

  ### Windows paths with spaces
  Use the **…** file-dialog buttons instead of typing paths manually.
  Paths with spaces in directory names are supported when selected via
  the dialog.
  ````

- [ ] **Step 2: Add a Quick Start link to `README.md`**

  Find the line in `README.md` that reads `## Description` (currently the first section header after the badge block).

  Insert two lines before `## Description`:
  ```markdown
  ## Quick Start

  New to IBTool? → **[docs/quickstart.md](docs/quickstart.md)** — installation, input requirements, and a step-by-step first run.

  ---

  ```

- [ ] **Step 3: Commit**

  ```bash
  git add docs/quickstart.md README.md
  git commit -m "docs: add quickstart guide for beta testers"
  ```

---

## Final: Push and Open PR

```bash
git push -u origin BETA_Transition
```

Open a pull request from `BETA_Transition` → `master`.

After merging, build the release ZIP:
```bash
python scripts/create_release_zip.py
```

The resulting `IB-Tool_0.2.0.zip` is ready to send to beta testers.
