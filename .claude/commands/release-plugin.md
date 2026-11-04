---
description: Use this skill when a new IB-Tool 3 version is to be released or published on plugins.qgis.org — for example "neue Version veröffentlichen", "Release vorbereiten", "release 0.3.0", "auf plugins.qgis.org hochladen", "Version hochzählen", "ist das Plugin bereit für den Upload?". Also use it when checking whether the plugin still meets the plugins.qgis.org or QGIS 4 requirements before an upload.
---

# /release-plugin — Prepare an IB-Tool 3 release for plugins.qgis.org

Release version: **$ARGUMENTS** (if empty: propose one in Step 1 and ask).

Fixed rules are enforced by `ci/qgis_plugin_validate.py` and the tests — this skill
runs them and covers what they cannot judge. Do not restate or re-implement a rule
here; if a new deterministic rule is needed, add it to the validator with a test.

Repository rules: https://plugins.qgis.org/docs/publish, /docs/approval,
/docs/migrate-qgis4. Project rules: `ai/core/release-conventions.md`.

Follow the steps in order. Report each step's result to the user.

---

## Step 1 — Version number

- Latest release: `git tag --list "v*" --sort=-v:refname | head -1`.
- Semver while 0.x: new supported platform, changed results, or changed config/resume
  format → minor (`0.3.0`); fixes only → patch (`0.2.6`). Pre-releases: `-beta`.
- The new version must be greater than every `v*` tag (checked in Step 5).

## Step 2 — Changelogs (two formats, same content)

1. `docs/CHANGELOG.md`: rename `## Unreleased` to `## X.Y.Z — YYYY-MM-DD` (today).
   Nothing may stay under "Unreleased".
2. `metadata.txt` `changelog=`: prepend **one line** `X.Y.Z - …` for end users, in
   English, written from the CHANGELOG section. Cover every user-visible change:
   supported QGIS/Python versions, changed results, new settings, fixed bugs a user
   could have hit. Leave out internal refactoring, tests and CI. Keep older entries.
3. `metadata.txt` `version=X.Y.Z`.

## Step 3 — Texts users see on plugins.qgis.org (judgment, no validator covers this)

Read `metadata.txt` `description`, `about` and `tags` against the code as it is now:

- Supported QGIS versions and Qt (e.g. "QGIS 3.40–4.x") — no stale "QGIS 3.40+" wording.
- Dependencies and how to install them on each platform (scipy, networkx; OSGeo4W
  shell per QGIS installation) — required by the publish rules.
- Platform limits (worker processes are Windows-only, other platforms run
  sequentially) and data limits (ATKIS function codes).
- `homepage`, `tracker`, `repository` still open the GitHub pages (reviewers check
  links on every update).

Also check `README.md` and `docs/quickstart.md` for the same facts.

## Step 4 — Tests

- Local QGIS 3.40: `"C:\Program Files\QGIS 3.40.0\bin\python-qgis.bat" -m pytest test/ -q`
  (2 known failures in `test_create_release_zip.py` when git is not on PATH).
- Docker QGIS 3.44 and 4.0, one after another (parallel builds crashed the daemon):
  `docker build --build-arg QGIS_VERSION=<v> -t qgis-plugin-test:<v> .` then
  `docker run --rm qgis-plugin-test:<v>` — expect exit 0.

## Step 5 — Package checks

```bash
python ci/qgis_plugin_validate.py --auto
python scripts/create_release_zip.py
python ci/qgis_plugin_validate.py --zip dist/ibtool.zip --release
```

All lines must be `OK:`. `--release` fails while the version equals an existing tag.

pyqgis4-checker (same as the CI job `qt6-check` and the "Qt6 Check" tab on upload):
copy `__init__.py metadata.txt helpers ibtool ibtool_tools scripts test` into
`<scratch>/ibtool/` (not the repo — avoids `.venv`), then
`docker run --rm --workdir /workspace/ -v "<scratch>:/workspace/" ghcr.io/qgis/pyqgis4-checker:main-ubuntu pyqt5_to_pyqt6.py --dry_run --logfile /workspace/pyqt6_checker.log ibtool`
— the log must contain only the header line.

## Step 6 — Run on real QGIS (reviewers install and run plugins at random)

Headless, both installs (OSGeo4W: `python-qgis-ltr.bat` = 3.44 LTR, `python-qgis.bat` = 4.x):
`scripts/profile_pipeline.py --out <dir> --workers 4 --no-cprofile`, plus `--workers 1`
on QGIS 4, then `scripts/compare_results.py <ref>/result.gpkg <cand>/result.gpkg`
→ `RESULT: IDENTICAL`. Exit 2 from the pipeline means the worker self-test failed.

Ask the user for the GUI check (cannot be done headless): install `dist/ibtool.zip`
in QGIS 3.44 and QGIS 4 (restart QGIS after installing), open the dialog, run the
sample data, German UI, filter preview, result buttons.

## Step 7 — Commit, tag, upload (user decides)

Never commit, tag or push without the user's explicit instruction. When asked:
commit `release: X.Y.Z`, tag `vX.Y.Z`. The upload is done by the user:

1. plugins.qgis.org → log in → *Upload a plugin* → `dist/ibtool.zip` (never GitHub's
   "Source code (zip)").
2. Version page: **Security** tab must show no critical issue (critical blocks the
   version); **Qt6 Check** tab should be empty.
3. GitHub release from the tag with `dist/ibtool.zip` attached.
4. Approval is manual (volunteers, weekdays). Once approved and
   `qgisMaximumVersion >= 4.0`, the plugin appears in the QGIS 4 Ready list.

---

## Quick reference — repository rule → where it is checked

| Rule | Checked by |
|------|------------|
| Required metadata, LICENSE, folder name | validator `--auto` / `--zip` |
| `qgisMaximumVersion >= 4.0`, no `supportsQt6` | validator, `test_init.py` |
| Changelog entry for current version | validator |
| New version number | validator `--release` |
| ZIP <= 25 MB, no binaries, hidden or generated files | validator `--zip` |
| No Qt5-only code | `test_qt6_compat.py`, CI `qt6-check` |
| Security scan, secrets | CI: bandit, detect-secrets |
| Accurate description/about, dependencies, platform limits | **Step 3 (manual)** |
| Runs without crashing QGIS 3 and 4 | Steps 4 and 6 |

## Common mistakes

- `about` still names old QGIS versions or misses a platform limit → Step 3.
- metadata changelog lists internals but not the user-visible QGIS 4 support.
- CHANGELOG left under "Unreleased" while `metadata.txt` has the new version.
- ZIP built from a dirty tree: `create_release_zip.py` refuses untracked files that
  would ship, but packs uncommitted edits of tracked files silently. Build the upload
  ZIP after the release commit (on user request), or it differs from the tagged code.
- Testing only on QGIS 3.40: the user's GUI runs 3.44 LTR with NumPy 2.
