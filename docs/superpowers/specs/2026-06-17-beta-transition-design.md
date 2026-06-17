# Design: IBTool Beta Transition

**Date:** 2026-06-17  
**Branch:** to be created from master after FIX_Overlapping_Buildings is merged  
**Goal:** Move IBTool from alpha to controlled external beta — a clean ZIP handed to research colleagues. Lays groundwork for a future public plugins.qgis.org release.

---

## Scope

Five targeted workstreams. No new processing features. No automated release CI. No full user manual with screenshots (deferred until after beta feedback).

---

## 1. Merge & Cleanup

**What:** Merge the open `FIX_Overlapping_Buildings` PR into master. Remove the dead `ProcessingThread` stub from `ibtool/ibtool.py`. Commit the two untracked plan/spec files from `FIX-MBR-Orintation` (branch already merged in PR #138) — they are design-history artifacts and belong in version control.

**Why:** Start the beta from a clean, linear master with no dead code and no loose files.

**Files affected:**
- `ibtool/ibtool.py` — remove `ProcessingThread` class and its signal stubs
- `docs/superpowers/plans/2026-06-14-mst-clustering-circular-geometry-fix.md` — commit (untracked)
- `docs/superpowers/specs/2026-06-14-mst-clustering-circular-geometry-fix-design.md` — commit (untracked)

---

## 2. Dependency Guard

**Problem:** If `scipy` or `networkx` are missing, QGIS shows a cryptic Python traceback with no instructions. Testers on a fresh QGIS installation will hit this immediately and have no idea how to fix it.

**Solution:** Check for missing packages at plugin load time. If any are missing, show a persistent `QgsMessageBar` warning with the exact pip install command and keep the Start button disabled until QGIS is restarted with the packages present.

**Architecture:**

`ibtool/__init__.py` — detect missing packages before `classFactory()`:
```python
_MISSING_PACKAGES: list[str] = []
try:
    import scipy      # noqa: F401
except ImportError:
    _MISSING_PACKAGES.append("scipy")
try:
    import networkx   # noqa: F401
except ImportError:
    _MISSING_PACKAGES.append("networkx")
```

`ibtool/ibtool.py → initGui()` — after setting up the action, if `_MISSING_PACKAGES`:
```python
from ibtool import _MISSING_PACKAGES
if _MISSING_PACKAGES:
    iface.messageBar().pushMessage(
        "IBTool",
        f"Required packages missing: {', '.join(_MISSING_PACKAGES)}. "
        f"Install with: pip install {' '.join(_MISSING_PACKAGES)} — then restart QGIS.",
        level=Qgis.Critical,
        duration=0,   # persistent
    )
```

The Start button is disabled inside `run()` when `_MISSING_PACKAGES` is non-empty (early return with a repeated message bar warning).

**Files affected:**
- `ibtool/__init__.py`
- `ibtool/ibtool.py`

**Scope:** ~25 lines total. No new module, no new dependency.

---

## 3. Version & Metadata

**Current state:**
- `metadata.txt`: `version=0.1.6`, `experimental=True`, `changelog` field references `0.2.0` inconsistently
- `docs/CHANGELOG.md`: large open `## Unreleased` section covering the full UI overhaul, all helpers refactoring, ErodeEmptyAreas fixes, GapFix removal, etc.

**Changes:**

`metadata.txt`:
- `version=0.1.6` → `version=0.2.0`
- `experimental=True` → `experimental=False`
- `changelog` field: rewrite to accurately summarize the 0.2.0 release (UI overhaul, dependency guard, cross-platform fixes)

`docs/CHANGELOG.md`:
- `## Unreleased` → `## 0.2.0 — 2026-06-17`
- Add the new items from this beta-transition work (dependency guard, cross-platform fix, quickstart)

**Why 0.2.0:** The UI overhaul (4-step stepper, validation checklist, phase progress, result actions), the complete helper refactoring, and new features (GeoPackage support, checksum caching, ErodeEmptyAreas pipeline position change) together justify a minor-version bump over 0.1.x.

**Files affected:**
- `metadata.txt`
- `docs/CHANGELOG.md`

---

## 4. Cross-Platform Folder Opening

**Problem:** `os.startfile(path)` in `_open_output_dir()` is Windows-only. On Linux/Mac it raises `AttributeError`.

**Solution:** Extract a private helper `_open_directory(path)` in `ibtool.py`:

```python
def _open_directory(path: str) -> None:
    if sys.platform == "win32":
        os.startfile(path)          # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
```

`subprocess` and `sys` are standard library — `sys` is not yet imported in `ibtool.py` and must be added. No new third-party dependency.

**Files affected:**
- `ibtool/ibtool.py` (~8 lines)

---

## 5. Quickstart Guide

**Problem:** The README is developer-oriented (architecture, tests, CI badges). A researcher installing the plugin for the first time has no step-by-step entry point.

**Solution:** New file `docs/quickstart.md` with five sections:

1. **System requirements** — QGIS ≥ 3.40, Python ≥ 3.11, scipy + networkx with exact pip command
2. **Installation** — install from ZIP via QGIS Plugin Manager, step by step
3. **Input data** — what is needed (HU, RN, Partition, Aux, filter file), one sentence each, link to `docs/input-data.md` for field specs
4. **First run** — walk through the 4 dialog steps, what the Check button does, how to read validation errors
5. **Troubleshooting** — missing packages, Windows paths with spaces, CRS mismatch, minimum feature counts

The README gains a `## Quick Start` section at the top linking to `docs/quickstart.md`.

**What is NOT in scope:** Screenshots (deferred until after beta feedback stabilises the UI), full parameter reference (already in `docs/parameterization.md`), developer setup (already in `docs/contributing.md`).

**Files affected:**
- `docs/quickstart.md` (new, ~180 lines)
- `README.md` (add link, ~5 lines)

---

## Out of Scope

- Automated release ZIP in CI (stays manual via `create_release_zip.py`)
- Full user manual with screenshots
- `os.startfile` → cross-platform for any other call sites (only one exists)
- `LogLevelBox` empty-on-new-dialog bug (pre-existing, documented, not fixed here)
- New processing features

---

## Acceptance Criteria

- [ ] `FIX_Overlapping_Buildings` merged, master is clean
- [ ] `ProcessingThread` stub removed from `ibtool.py`
- [ ] Plugin loads on a QGIS instance without scipy/networkx and shows a clear, actionable error bar
- [ ] Plugin loads normally when scipy/networkx are present
- [ ] `metadata.txt` has `version=0.2.0`, `experimental=False`
- [ ] CHANGELOG `## Unreleased` closed as `0.2.0 — 2026-06-17`
- [ ] "Open folder" button works on Windows, Linux, and Mac (or fails gracefully)
- [ ] `docs/quickstart.md` exists and covers all five sections
- [ ] `README.md` links to the quickstart
- [ ] All existing tests still pass
