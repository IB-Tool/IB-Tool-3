# plugins.qgis.org Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining gaps between IB-Tool 3 (v0.2.3) and the requirements/recommendations of https://plugins.qgis.org/docs/publish and https://plugins.qgis.org/docs/approval, then ship v0.2.4 as the first upload to plugins.qgis.org.

**Architecture:** Most of the publication work is already done (whitelist ZIP builder with guard + import smoke test, metadata with working links, GPL LICENSE, dependency stub, CI with flake8/bandit/detect-secrets). This plan only fixes what an approver or the automated security scan would still flag, plus one real user-facing defect (config/logs stored inside the plugin folder, which is wiped on every plugin update).

**Tech Stack:** Python 3.11, PyQGIS 3.40+, `qgis.PyQt`, pytest, `scripts/create_release_zip.py`, `ci/qgis_plugin_validate.py`.

**Spec:** https://plugins.qgis.org/docs/publish, https://plugins.qgis.org/docs/approval, `ai/core/release-conventions.md`

## Audit Result (2026-10-04, branch `Add_grafix`)

| Check | Status |
|---|---|
| metadata.txt mandatory keys, homepage/tracker/repository links, public repo, issues enabled | OK |
| License GPL-2.0-or-later, `LICENSE` file | OK |
| English description/about, dependencies stated in `about` | OK |
| No binaries, ZIP < 25 MB, no `__pycache__`/`.git` in ZIP | OK (guard) |
| flake8 on shipping code | OK (0 findings) |
| bandit on shipping code | OK (2 × Low: B110, B404 — both justified) |
| Test dataset provided (`Testdaten/`) | OK |
| **Generated file `ibtool/resources.py` ships** ("no generated files" rule) — and it is unused | FIX → Task 1 |
| **Direct `PyQt5` imports** in `helpers/data_loader.py`, `ibtool_tools/MST_Clustering.py` (QGIS guideline: use `qgis.PyQt`) | FIX → Task 2 |
| **`category=Vector` but action is put into the Plugins menu** ("put the plugin into the appropriate menu") | FIX → Task 3 |
| **CONFIG.ini + logs written into the plugin folder** → lost on every plugin update, not writable on system-wide Linux installs; reset handler uses a *different* dir (`ibtool/ibtool/` instead of the root) which is why a stray `ibtool/CONFIG.ini` exists and currently **breaks the local release build** | FIX → Task 4 |
| German code comments (11 lines) ("write comments in English") | FIX → Task 5 |
| Stray empty `i18n/af.ts` ships | FIX → Task 5 |
| Version/changelog for upload | Task 6 |
| Clean-clone build, manual install test, upload, approval | Task 7 |

## Global Constraints

- QGIS 3.40–3.50, Python 3.11+ (`metadata.txt`: `qgisMinimumVersion=3.40`, `qgisMaximumVersion=3.50`, `pythonMinimumVersion=3.11`)
- No new dependencies.
- `license=GPL-2.0-or-later`; never touch/rename `LICENSE`.
- All 11 mandatory metadata keys stay present and non-empty.
- Release ZIP only via `python scripts/create_release_zip.py` → `dist/ibtool.zip`.
- Docs/comments in English; UI strings and end-user log messages may stay German.
- Use the central `Logger`, never `print`, in plugin code.
- Never `git commit` without the user's explicit per-request instruction — the "Commit" steps below are *proposals* to be confirmed by the user.

## Review Focus

1. **Existing user with a CONFIG.ini in the old plugin folder** updates the plugin → expects their paths/parameters to still be there (Task 4, migration test).
2. **Reset-config button** → must delete and re-create the config in the *same* location it was loaded from (Task 4, reset test).
3. **Settings dir not writable / missing** → plugin must still load with defaults, no crash (Task 4, `makedirs` + `ConfigManager` already tolerates missing file).
4. **Plugin unload/reload (Plugin Reloader)** → menu entry must be removed from the Vector menu, no duplicate entries (Task 3, unload test).
5. **Release ZIP built on a dev machine with gitignored local files** → guard must fail loudly instead of shipping them (already covered by `run_guard`; Task 7 builds from a clean clone).

---

### Task 0: Never package runtime-generated files (CONFIG.ini, logs)

User requirement (2026-10-04): files created by using the plugin — `CONFIG.ini`, the `logs/` directory and log files (`logfile_*.txt`, `*.log`) — must never end up in the release ZIP, regardless of where they sit on the developer's disk. Today `is_included()` walks the real filesystem, so such a file inside a whitelisted directory is collected and only the guard's "untracked file" check stops the build (and only when git is available). Make the exclusion explicit in `is_included()` so it holds even without git and the build no longer fails because of local runtime artefacts.

**Files:**
- Modify: `scripts/create_release_zip.py` (`is_included`, new constants next to `_COMPILED_PY_EXTENSIONS`)
- Test: `test/test_create_release_zip.py` (class containing `test_pycache_inside_whitelisted_dir_is_excluded`, and the `collect_files` test class)
- Docs: `ai/core/release-conventions.md` (Release ZIP section: one bullet)

**Interfaces:**
- Produces: `RUNTIME_GENERATED_NAMES = {"config.ini"}`, `RUNTIME_GENERATED_DIRS = {"logs"}`, `_RUNTIME_LOG_PATTERNS = ("logfile_*.txt", "*.log")` in `create_release_zip.py`; `is_included(rel)` returns False for any of them at any depth (case-insensitive name match).

- [ ] **Step 1: Write failing tests** (module functions are already bound at the top of the test file as `is_included`, `collect_files`):

```python
    @pytest.mark.unit
    @pytest.mark.parametrize("rel", [
        "CONFIG.ini",
        "ibtool/CONFIG.ini",
        "helpers/config.ini",
        "ibtool/logs/logfile_2026-10-04.txt",
        "logs/logfile_2026-10-04.txt",
        "ibtool_tools/logfile_2026-10-04.txt",
        "helpers/debug.log",
    ])
    def test_runtime_generated_files_are_excluded(self, rel):
        """CONFIG.ini and log files are produced by using the plugin and must never ship."""
        assert is_included(Path(rel)) is False

    @pytest.mark.unit
    def test_regular_txt_in_whitelisted_dir_still_included(self):
        """The log-pattern exclusion must not swallow ordinary .txt files."""
        assert is_included(Path("helpers/notes.txt")) is True
```

and in the `collect_files` test class:

```python
    @pytest.mark.unit
    def test_runtime_files_on_disk_are_not_collected(self, tmp_path):
        (tmp_path / "ibtool" / "logs").mkdir(parents=True)
        (tmp_path / "ibtool" / "ibtool.py").write_text("", encoding="utf-8")
        (tmp_path / "ibtool" / "CONFIG.ini").write_text("[x]", encoding="utf-8")
        (tmp_path / "ibtool" / "logs" / "logfile_1.txt").write_text("", encoding="utf-8")

        names = {p.as_posix() for p in collect_files(tmp_path)}

        assert names == {"ibtool/ibtool.py"}
```

- [ ] **Step 2: Run — expect FAIL.** `pytest test/test_create_release_zip.py -k "runtime" -v`

- [ ] **Step 3: Implement** in `scripts/create_release_zip.py`:

```python
# Files produced by *using* the plugin (user configuration, log output).
# They must never ship, wherever they happen to sit on the build machine.
RUNTIME_GENERATED_NAMES = {"config.ini"}
RUNTIME_GENERATED_DIRS = {"logs"}
_RUNTIME_LOG_PATTERNS = ("logfile_*.txt", "*.log")
```

and in `is_included`, right after the length/whitelist checks for the root case and before the `__pycache__` check (it must apply to root files too — put it at the very top of the function):

```python
    if rel.name.lower() in RUNTIME_GENERATED_NAMES:
        return False
    if any(part.lower() in RUNTIME_GENERATED_DIRS for part in parts[:-1]):
        return False
    if any(fnmatch.fnmatch(rel.name.lower(), pat) for pat in _RUNTIME_LOG_PATTERNS):
        return False
```

(`import fnmatch` at the top; `parts = rel.parts` must be defined before this block.) Keep the git "untracked file" guard as a second safety net.

- [ ] **Step 4: Run — expect PASS.** `pytest test/test_create_release_zip.py -v`

- [ ] **Step 5: Verify on the real repo** — `python scripts/create_release_zip.py` now passes guard and smoke test even with the local `ibtool/CONFIG.ini` present; `python -c "import zipfile;n=zipfile.ZipFile('dist/ibtool.zip').namelist();print([x for x in n if 'config.ini' in x.lower() or 'log' in x.lower()])"` → `[]` (note: `helpers/logger.py` contains "log" — filter it out mentally or match `/logs/`, `.log`, `logfile_`).

- [ ] **Step 6: Docs** — `ai/core/release-conventions.md`, Release ZIP section, add: "Runtime-generated files (`CONFIG.ini`, `logs/`, `logfile_*.txt`, `*.log`) are excluded by `is_included()` at any depth and must never ship."

- [ ] **Step 7: Commit (after user approval)** — `fix(release): never package CONFIG.ini or log files`

---

### Task 1: Remove the unused generated `resources.py` / `resources.qrc`

The plugin loads its icon by file path (`ibtool/ibtool.py:258`), nothing imports `resources.py`. `test/test_resources.py` tests `:/plugins/IBTool/icon.png`, which only works because the module happens to be imported elsewhere in tests — it is not a runtime requirement.

**Files:**
- Delete: `ibtool/resources.py`, `resources.qrc`, `test/test_resources.py`
- Modify: `scripts/create_release_zip.py:44` (remove `"resources.qrc"` from `WHITELIST_FILES`)
- Modify: `test/test_create_release_zip.py:83` (remove `"resources.qrc"` from the expected list)
- Modify: `pb_tool.cfg:60` (`resource_files:` → empty), `Makefile:59` (`COMPILED_RESOURCE_FILES =` empty) and the `RESOURCE_SRC` line `Makefile:80` (delete), `compile.bat:13` (delete the `pyrcc5` line)
- Modify: `docs/contributing.md:234`, `docs/test-strategy.md:192` (remove the `test_resources.py` rows)

- [ ] **Step 1: Write the failing test** — append to `test/test_create_release_zip.py`:

```python
@pytest.mark.unit
def test_no_generated_qt_resource_module_ships():
    """plugins.qgis.org forbids generated files such as compiled Qt resources."""
    repo_root = Path(__file__).resolve().parent.parent
    files = collect_files(repo_root)
    names = {p.name for p in files}
    assert "resources.py" not in names
    assert "resources_rc.py" not in names
    assert "resources.qrc" not in names
```

(`collect_files` is already bound at module level in that test file.)

- [ ] **Step 2: Run it — expect FAIL**

Run: `pytest test/test_create_release_zip.py::test_no_generated_qt_resource_module_ships -v`
Expected: FAIL (`resources.py` / `resources.qrc` in names)

- [ ] **Step 3: Delete the files and update whitelist/build tooling/docs** as listed under *Files*:

```bash
git rm ibtool/resources.py resources.qrc test/test_resources.py
```

- [ ] **Step 4: Verify no reference remains**

Run: `git grep -n "resources\.py\|resources\.qrc\|qInitResources\|:/plugins/IBTool" -- ':!docs/CHANGELOG.md' ':!docs/superpowers'`
Expected: no output.

- [ ] **Step 5: Run tests — expect PASS**

Run: `pytest test/test_create_release_zip.py test/test_ibtool.py -v`

- [ ] **Step 6: Commit (after user approval)** — `chore: drop unused generated Qt resource module`

---

### Task 2: Replace direct `PyQt5` imports with `qgis.PyQt`

**Files:**
- Modify: `helpers/data_loader.py:12` → `from qgis.PyQt.QtWidgets import QFileDialog`
- Modify: `ibtool_tools/MST_Clustering.py:20` → `from qgis.PyQt.QtCore import QMetaType`
- Test: `test/test_encoding.py` (or a new `test/test_qt_imports.py` if that file is encoding-only)

- [ ] **Step 1: Write the failing test** — `test/test_qt_imports.py`:

```python
"""Guard: shipping code must import Qt via qgis.PyQt, never PyQt5/PyQt6 directly."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SHIPPING_DIRS = ("helpers", "ibtool", "ibtool_tools")
_DIRECT_QT = re.compile(r"^\s*(from|import)\s+PyQt[56]\b", re.MULTILINE)


@pytest.mark.unit
def test_no_direct_pyqt_imports_in_shipping_code():
    offenders = []
    for d in SHIPPING_DIRS:
        for py in (ROOT / d).rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            if _DIRECT_QT.search(py.read_text(encoding="utf-8")):
                offenders.append(py.relative_to(ROOT).as_posix())
    assert offenders == []
```

- [ ] **Step 2: Run — expect FAIL** listing the two files.

Run: `pytest test/test_qt_imports.py -v`

- [ ] **Step 3: Change the two import lines** as listed above (keep the existing `# pylint: disable=no-name-in-module` comment on the data_loader line).

- [ ] **Step 4: Run — expect PASS**, plus `pytest test/test_data_loader.py test/test_mst_clustering.py -v`.

- [ ] **Step 5: Commit (after user approval)** — `refactor: import Qt through qgis.PyQt`

---

### Task 3: Register the action in the Vector menu (matches `category=Vector`)

**Files:**
- Modify: `ibtool/ibtool.py` — `add_action()` (~line 246) and `unload()` (~line 270)
- Test: `test/test_ibtool.py` (class around line 576, `TestUnload` or equivalent)

- [ ] **Step 1: Write failing tests** in the unload test class and a new menu test:

```python
    @pytest.mark.unit
    def test_unload_removes_vector_menu_entry(self):
        """unload must remove each action from the Vector menu."""
        from qgis.PyQt.QtWidgets import QAction
        tool = _make_tool()
        tool.iface = MagicMock()
        tool.actions = [QAction("A"), QAction("B")]

        with patch("ibtool.ibtool.ibtool.logger"):
            tool.unload()

        assert tool.iface.removePluginVectorMenu.call_count == 2
        tool.iface.removePluginMenu.assert_not_called()

    @pytest.mark.unit
    def test_add_action_uses_vector_menu(self):
        """add_action must put the action into the Vector menu, not Plugins."""
        tool = _make_tool()
        tool.iface = MagicMock()
        tool.add_action("icon.png", text="IB-Tool", callback=lambda: None,
                        parent=None)
        tool.iface.addPluginToVectorMenu.assert_called_once()
        tool.iface.addPluginToMenu.assert_not_called()
```

(Adjust the `add_action` keyword names to the real signature at `ibtool/ibtool.py:203`.)

- [ ] **Step 2: Run — expect FAIL.** `pytest test/test_ibtool.py -k "vector_menu" -v`

- [ ] **Step 3: Implement**

```python
        if add_to_menu:
            self.iface.addPluginToVectorMenu(
                self.menu,
                action)
```

```python
        for action in self.actions:
            self.iface.removePluginVectorMenu(
                self.menu,
                action)
            self.iface.removeToolBarIcon(action)
```

(`unload` currently passes `self.tr(u'&IB-Tool')`; use `self.menu` so add/remove use the identical string.) Update any existing test asserting `removePluginMenu`.

- [ ] **Step 4: Run — expect PASS.** `pytest test/test_ibtool.py -v`

- [ ] **Step 5: Docs** — README/quickstart: wherever "Plugins → IB-Tool" is described, change to "Vector → IB-Tool" (`git grep -n "Plugins menu\|Plugins →\|Plugins >"`).

- [ ] **Step 6: Commit (after user approval)** — `fix: place IB-Tool under the Vector menu to match its category`

---

### Task 4: Store CONFIG.ini and logs in the QGIS profile, not the plugin folder

QGIS deletes and replaces the plugin folder on every update → user configuration and logs are lost. Additionally `ibtool.py:116` uses the plugin root while the reset handler at `ibtool.py:882` uses `self.plugin_dir` (`…/ibtool/ibtool`) — two different locations.

Target: `<QGIS profile>/ibtool/CONFIG.ini` and `<QGIS profile>/ibtool/logs/` (`QgsApplication.qgisSettingsDirPath()`), with a one-time migration of a legacy `<plugin root>/CONFIG.ini`.

**Files:**
- Modify: `helpers/system_utils.py` (add `get_user_config_dir`, `migrate_legacy_config`)
- Modify: `ibtool/ibtool.py:113-116` and `:870-882`
- Test: `test/test_system_utils.py`, `test/test_ibtool.py`
- Docs: `docs/CONFIG_README.md`, `docs/error-handling.md` (log location), `README.md` troubleshooting

**Interfaces:**
- Produces: `get_user_config_dir(settings_dir: str | None = None) -> str` — returns `<settings_dir>/ibtool`, creates it; `settings_dir` defaults to `QgsApplication.qgisSettingsDirPath()`.
- Produces: `migrate_legacy_config(legacy_dir: str, target_dir: str) -> bool` — copies `legacy_dir/CONFIG.ini` to `target_dir` if the target has none; returns True if copied. Never deletes the legacy file.
- Produces: `IBTool.config_dir: str` used by both `__init__` and the reset handler.

- [ ] **Step 1: Write failing tests** — `test/test_system_utils.py`:

```python
@pytest.mark.unit
class TestUserConfigDir:
    def test_returns_ibtool_subdir_and_creates_it(self, tmp_path):
        from helpers.system_utils import get_user_config_dir
        result = get_user_config_dir(str(tmp_path))
        assert result == os.path.join(str(tmp_path), "ibtool")
        assert os.path.isdir(result)

    def test_migrates_legacy_config_once(self, tmp_path):
        from helpers.system_utils import migrate_legacy_config
        legacy, target = tmp_path / "legacy", tmp_path / "target"
        legacy.mkdir(); target.mkdir()
        (legacy / "CONFIG.ini").write_text("[paths]\nx=1\n", encoding="utf-8")

        assert migrate_legacy_config(str(legacy), str(target)) is True
        assert (target / "CONFIG.ini").read_text(encoding="utf-8") == "[paths]\nx=1\n"
        assert (legacy / "CONFIG.ini").exists()

    def test_does_not_overwrite_existing_target(self, tmp_path):
        from helpers.system_utils import migrate_legacy_config
        legacy, target = tmp_path / "legacy", tmp_path / "target"
        legacy.mkdir(); target.mkdir()
        (legacy / "CONFIG.ini").write_text("old", encoding="utf-8")
        (target / "CONFIG.ini").write_text("new", encoding="utf-8")

        assert migrate_legacy_config(str(legacy), str(target)) is False
        assert (target / "CONFIG.ini").read_text(encoding="utf-8") == "new"

    def test_no_legacy_file_is_noop(self, tmp_path):
        from helpers.system_utils import migrate_legacy_config
        assert migrate_legacy_config(str(tmp_path / "nope"), str(tmp_path)) is False
```

(Match the import style already used in `test/test_system_utils.py`.)

And in `test/test_ibtool.py`:

```python
    @pytest.mark.unit
    def test_config_manager_uses_profile_dir_not_plugin_dir(self):
        tool = _make_tool()
        assert tool.config_manager.plugin_root_dir == tool.config_dir
        assert not tool.config_dir.startswith(os.path.dirname(tool.plugin_dir))
```

and a reset test asserting the re-created `ConfigManager` gets `tool.config_dir` (patch `ibtool.ibtool.ibtool.ConfigManager` and inspect `call_args`; locate the reset method name around `ibtool.py:870`).

- [ ] **Step 2: Run — expect FAIL.** `pytest test/test_system_utils.py -k "UserConfigDir" test/test_ibtool.py -k "config_dir or profile_dir" -v`

- [ ] **Step 3: Implement** in `helpers/system_utils.py`:

```python
def get_user_config_dir(settings_dir: str | None = None) -> str:
    """Return the per-profile IB-Tool directory for CONFIG.ini and logs.

    Lives in the QGIS profile so it survives plugin updates and is writable
    even when the plugin itself is installed system-wide.
    """
    if settings_dir is None:
        from qgis.core import QgsApplication
        settings_dir = QgsApplication.qgisSettingsDirPath()
    path = os.path.join(settings_dir, "ibtool")
    os.makedirs(path, exist_ok=True)
    return path


def migrate_legacy_config(legacy_dir: str, target_dir: str) -> bool:
    """Copy a pre-0.2.4 CONFIG.ini from the plugin folder once; never overwrite."""
    src = os.path.join(legacy_dir, "CONFIG.ini")
    dst = os.path.join(target_dir, "CONFIG.ini")
    if not os.path.isfile(src) or os.path.exists(dst):
        return False
    shutil.copy2(src, dst)
    return True
```

(add `import shutil` if missing). In `ibtool/ibtool.py.__init__`:

```python
        plugin_root = os.path.dirname(self.plugin_dir)
        self.config_dir = get_user_config_dir()
        migrate_legacy_config(plugin_root, self.config_dir)
        self.config_manager = ConfigManager(self.config_dir)
```

and in the reset handler replace `ConfigManager(self.plugin_dir)` with `ConfigManager(self.config_dir)` (and make sure `cfg_path` there is derived from `self.config_manager.config_file_path`). Logs follow automatically: `ConfigManager` defaults `log_directory` to `<plugin_root_dir>/logs`.

If `_make_tool()` in tests constructs `IBTool` without QGIS app settings, patch `get_user_config_dir` to return `tmp_path` there.

- [ ] **Step 4: Run full suite — expect PASS.** `pytest test/ -v`

- [ ] **Step 5: Docs** — `docs/CONFIG_README.md` and `docs/error-handling.md`: new location `<QGIS profile>/ibtool/CONFIG.ini` / `…/ibtool/logs/` (Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\ibtool\`), mention one-time migration.

- [ ] **Step 6: Manual check** — in QGIS: open the dialog, change a path, close → `%APPDATA%\QGIS\QGIS3\profiles\default\ibtool\CONFIG.ini` exists; press reset → file is re-created there; no new file appears under the plugin folder. Then delete the stray local `ibtool/CONFIG.ini`.

- [ ] **Step 7: Commit (after user approval)** — `fix: keep CONFIG.ini and logs in the QGIS profile so updates don't wipe them`

---

### Task 5: English code comments, remove stray translation stub

**Files:**
- Modify: `helpers/__init__.py:2`, `ibtool/ibtool.py:278,417,419,710`, `ibtool_tools/FootprintDensity.py:110,113` and remaining hits of the grep below
- Delete: `i18n/af.ts` (empty Afrikaans stub from the Plugin Builder template)

- [ ] **Step 1: List all German comments/docstrings**

Run: `git grep -nE "#.*[äöüÄÖÜß]|\"\"\".*[äöüÄÖÜß]" -- helpers ibtool ibtool_tools __init__.py`
Translate each *comment/docstring* to English. Do **not** touch user-facing strings (`msg(...)`, `logger.log(...)`, `tr(...)`) or matcher strings such as `'objekt nicht schreiben'` in `helpers/safe_processing.py:52` (that matches German GDAL output).

- [ ] **Step 2: Delete `i18n/af.ts`** and remove it from `pb_tool.cfg`/`scripts/update-strings.sh` if referenced (`git grep -n "af.ts"`).

- [ ] **Step 3: Run** `pytest test/test_translations.py test/test_ibtool.py -v` and `python -m flake8 __init__.py helpers ibtool ibtool_tools` → 0 findings.

- [ ] **Step 4: Commit (after user approval)** — `chore: translate remaining code comments to English, drop empty af.ts`

---

### Task 6: Version 0.2.4, changelog

**Files:** `metadata.txt`, `docs/CHANGELOG.md`

- [ ] **Step 1:** `metadata.txt`: `version=0.2.4`; prepend changelog line:

```
changelog=0.2.4 - First release on plugins.qgis.org. The plugin entry moved to the Vector menu. CONFIG.ini and log files are now stored in the QGIS profile (<profile>/ibtool/) so plugin updates no longer erase them; an existing CONFIG.ini is migrated automatically. Removed the unused compiled Qt resource module; Qt is imported through qgis.PyQt throughout.
 0.2.3 - …(keep existing entries)
```

- [ ] **Step 2: Decision for the user — `experimental` flag.** Option A: `experimental=False` (current; plugin appears for everyone). Option B: `experimental=True` for the first upload (only users with "Show experimental plugins" see it; recommended by many reviewers for 0.x versions with external dependencies). Ask before changing.

- [ ] **Step 3:** Add a `## [0.2.4]` section to `docs/CHANGELOG.md` with the same content in Keep-a-Changelog style used there.

- [ ] **Step 4:** `python ci/qgis_plugin_validate.py --auto` → all OK.

- [ ] **Step 5: Commit (after user approval)** — `release: 0.2.4`

---

### Task 7: Build from a clean clone, install-test, upload

Manual task, performed by the user (with Claude assisting).

- [ ] **Step 1: Merge** the feature branch into `master` via PR; wait for **both** workflows (`CI`, `QGIS Plugin CI`) to be green.

- [ ] **Step 2: Build from a clean clone** (avoids gitignored local files tripping the guard):

```bash
git clone https://github.com/IB-Tool/IB-Tool-3.git "%TEMP%\ibt-release"
cd "%TEMP%\ibt-release"
python scripts/create_release_zip.py
python ci/qgis_plugin_validate.py --zip dist/ibtool.zip
```

Expected: `Guard passed.`, `Smoke test passed.`, validator OK.

- [ ] **Step 3: Clean-profile install test (Windows)** — start QGIS with a fresh profile (`qgis-ltr --profile ibt-test`), *Plugins → Install from ZIP* → `dist/ibtool.zip`:
  - plugin loads without Python error; entry under *Vector → IB-Tool*
  - with scipy/networkx missing: the red message-bar hint appears, QGIS does not crash
  - full run on `Testdaten/` with default parameters finishes and loads the result
  - *Plugins → Uninstall* works without error
- [ ] **Step 4: Linux smoke test** (approvers expect cross-platform): `docker run` an official `qgis/qgis:release-3_40` image, unzip into its plugin dir, `qgis_process plugins enable ibtool` / start QGIS headless-free import: `python3 -c "import sys; sys.path.insert(0,'/root/.local/share/QGIS/QGIS3/profiles/default/python/plugins'); import ibtool"`.
- [ ] **Step 5: Tag + GitHub release** `v0.2.4`, attach `dist/ibtool.zip` (never GitHub's auto source ZIP).
- [ ] **Step 6: Upload** — log in at https://plugins.qgis.org with an OSGeo ID (create at https://www.osgeo.org/community/getting-started-osgeo/osgeo_userid/ if missing), *Upload a plugin* → `dist/ibtool.zip`.
- [ ] **Step 7: Security scan** — wait for the second e-mail (code quality / secrets / suspicious files). If it reports issues: fix, bump to 0.2.5, re-upload.
- [ ] **Step 8: Manual approval** — usually days to a few weeks; reply promptly to reviewer comments (they come by e-mail / plugin page). After approval verify the plugin is found in *Plugins → Manage and Install Plugins* in a clean profile.

---

## Out of Scope (follow-up candidates)

- **QGIS 4 / Qt6 support** (`qgisMaximumVersion=3.99` → `4.x`): requires Qt6 enum scoping audit; separate plan after first approval.
- Known pre-existing issue: `setup_logging_in_plugin()` populates the old dialog's `LogLevelBox` (documented, intentionally untouched).
- Removing the unused `ProcessingThread` stub.
