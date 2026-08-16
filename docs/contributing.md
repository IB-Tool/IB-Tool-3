# Contributing & Development

This document covers the development setup, CI/CD pipeline, test structure, and code quality tooling for IB-Tool 3.

This is the canonical reference for the CI/test/release conventions shared
across all three IB-Tool plugins. The companion plugins
[data_wizard](https://github.com/IB-Tool/data_wizard/blob/master/docs/contributing.md)
and [IB-Tool (Partitioning)](https://github.com/IB-Tool/Partitioning/blob/master/docs/contributing.md)
follow the same structure and only document what differs for them
(e.g. lighter Docker images, since neither depends on `numpy`/`scipy`/`networkx`).

---

## Continuous Integration with GitHub Actions and Docker

The project uses two GitHub Actions workflows:

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| **CI** | `.github/workflows/ci.yml` | push to `master`/`main`, PRs | Docker-based tests + Codecov coverage |
| **QGIS Plugin CI** | `.github/workflows/qgis-plugin-ci.yml` | push to `master`/`main`, PRs | Structure/metadata validation, lint, security scan |

---

### Workflow 1 — CI (`.github/workflows/ci.yml`)

Runs on pushes to `master`/`main` and on all pull requests.

Steps:
1. Checks out the repository
2. Sets up Docker Buildx
3. Builds the Docker image from `Dockerfile`
4. Runs the full test suite inside the container with coverage reporting
5. Verifies `coverage.xml` exists and strips container-absolute paths
6. Uploads the coverage report to Codecov

```yaml
name: CI
on:
  push:
    branches: [master, main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: docker/setup-buildx-action@v2
      - run: docker build --pull -t qgis-plugin-test .
      - run: |
          docker run --rm \
            -v $(pwd):/plugins/ibtool \
            qgis-plugin-test
      - run: |
          if [ ! -f coverage.xml ]; then exit 1; fi
          sed -i 's|/plugins/ibtool/||g' coverage.xml
      - uses: codecov/codecov-action@v5
        with:
          token: ${{ secrets.CODECOV_TOKEN }}
          files: ./coverage.xml
          fail_ci_if_error: true
```

#### Coverage Reporting

Test coverage is measured with `pytest-cov` and uploaded to [Codecov](https://codecov.io) on every CI run. The `coverage.xml` file is written by the container into the volume-mounted workspace and is available on the host after the container exits. Container-absolute paths (`/plugins/ibtool/`) are stripped before upload so Codecov can map lines back to the repository.

#### Docker Environment

The `Dockerfile` is based on the official QGIS image `3liz/qgis-platform:3.40` and:

- Installs runtime dependencies (numpy, scipy, networkx) and test dependencies (pytest, pytest-cov) via apt
- Configures a headless X server environment (xvfb) for GUI tests
- Sets the necessary environment variables for QGIS
- Initialises the QGIS Processing provider
- Runs the tests with pytest

#### Local Development with Docker

```bash
# Build the Docker image
docker build -t qgis-plugin-test .
# Run tests
docker run --rm qgis-plugin-test
# Interactive shell inside the container
docker run --rm -it qgis-plugin-test /bin/bash
```

#### System Dependencies (Docker)

| Package | Purpose | Category |
|---------|---------|----------|
| `xvfb` | X Virtual Framebuffer for headless GUI tests | CI infrastructure |
| `python3-pytest`, `python3-pytest-cov`, `python3-coverage` | Test framework and coverage | Dev/test |
| `python3-numpy` | Numerical arrays (MST, clustering) | Runtime |
| `python3-scipy` | Delaunay triangulation, spatial distance | Runtime |
| `python3-networkx` | MST graph algorithms | Runtime |

numpy and PyQt5 are bundled with QGIS 3.40+. scipy and networkx may not be present depending on the QGIS installation and platform, so they are installed explicitly via apt. When running the plugin outside Docker: `pip install scipy networkx`.

---

### Workflow 2 — QGIS Plugin CI (`.github/workflows/qgis-plugin-ci.yml`)

Runs on pushes to `master`/`main` and on all pull requests.

Steps:

| Step | Tool | What it checks |
|------|------|----------------|
| Structure + metadata validation | `ci/qgis_plugin_validate.py --auto` | `metadata.txt` completeness, required files |
| Style linting | `flake8` | PEP 8 compliance |
| Security scanning | `bandit -r . -ll` | Common Python security issues |
| Secret detection | `detect-secrets` | Accidentally committed credentials |

`Testdaten/` contains sample GIS data for manual QA and demo runs (see
[quickstart.md → Sample Data](quickstart.md#sample-data)); it is not consumed
by the automated pytest suite. The `detect-secrets` scan excludes
`Testdaten/` and `README.md`.

> **Note:** This workflow does **not** build or publish the release ZIP.
> Building `dist/*.zip` and attaching it to a GitHub Release is a manual
> step — see [Publishing a Release](#publishing-a-release) below.

#### Running checks locally

```bash
pip install flake8 bandit detect-secrets

# Style
flake8 .

# Security
bandit -r . -ll

# Secret scan
detect-secrets scan --force-use-all-plugins \
  --exclude-files 'Testdaten/.*' \
  --exclude-files 'README\.md'

# Structure validation
python ci/qgis_plugin_validate.py --auto

# Build and validate ZIP
python scripts/create_release_zip.py
python ci/qgis_plugin_validate.py --zip dist/*.zip
```

---

### Publishing a Release

The release ZIP is **not** built or attached automatically — this must be done
by hand for every release, including pre-releases (`-alpha`, `-beta`):

1. Bump `version` in `metadata.txt` and add a changelog entry (see
   [release-conventions.md](../ai/core/release-conventions.md)).
2. Build and validate the ZIP locally:
   ```bash
   python scripts/create_release_zip.py
   python ci/qgis_plugin_validate.py --zip dist/*.zip
   ```
   This produces `dist/IB-Tool-3.zip`. Both the ZIP filename and its
   internal folder name (`IB-Tool-3/`) are **constant across versions** —
   only `metadata.txt` inside the ZIP carries the version string. Users
   never need to rename anything after installing.
3. Create the GitHub Release from the tag, then **manually upload
   `dist/IB-Tool-3.zip` as a release asset**.
4. Link `dist/IB-Tool-3.zip` (not "Source code (zip)") as the download in
   any release notes or announcement.

> **Never distribute GitHub's auto-generated "Source code (zip)"/"Source
> code (tar.gz)" links.** GitHub names that archive `<repo>-<tag>.zip` and
> its internal top-level folder matches that same name — e.g. tag
> `v0.2.1-beta` produces a folder named `IB-Tool-3-0.2.1-beta`. Python's
> `importlib.import_module` treats dots in a module name as package
> separators, so QGIS fails to load a folder name containing a version
> number (`ModuleNotFoundError: No module named 'IB-Tool-3-0'`). Only
> `dist/IB-Tool-3.zip`, built via `scripts/create_release_zip.py`, has the
> required constant `IB-Tool-3/` folder name.

---

### Customising the CI Pipeline

To modify the CI pipeline, edit:

- `.github/workflows/ci.yml` — test workflow
- `.github/workflows/qgis-plugin-ci.yml` — lint/validate workflow
- `Dockerfile` — Docker environment and dependencies
- `ci/qgis_plugin_validate.py` — plugin structure validation rules
- `scripts/create_release_zip.py` — release ZIP builder (run manually, see
  [Publishing a Release](#publishing-a-release))
- `test/` — test files and test data

### Debugging CI Failures

1. Check the GitHub Actions logs for detailed error messages.
2. Test the Docker image locally (Workflow 1) or run the local commands above (Workflow 2).
3. Make sure new tests support the Docker environment (headless mode).

---

## Test Structure

Tests are located in the `test/` directory and run with pytest:

| File | Covers |
|------|--------|
| `test_init.py` | Plugin initialisation |
| `test_logger.py` | Logging system |
| `test_blocker.py` | Blocker functionality |
| `test_message.py` | Message system |
| `test_resources.py` | Resource management |
| `test_data_loader.py` | Data loading functions |
| `test_ibtool.py` | Main plugin class |
| `test_ibtool_dialog.py` | UI dialog |
| `test_footprint_density.py` | Footprint density calculations |
| `test_gap_close.py` | GapClose module |
| `test_hole_close.py` | HoleClose module |
| `test_edge_catch.py` | EdgeCatch module |
| `test_import_filter.py` | Import filter |
| `test_patch_remove.py` | PatchRemove module |
| `test_add_single_building.py` | AddSingleBuilding module |
| `test_mst_clustering.py` | MST clustering |
| `test_create_mst.py` | CreateMST module |
| `test_mst_modules.py` | MST module integration |
| `test_mst_components.py` | MST component tests |
| `test_mst_performance_edge_cases.py` | MST performance and edge-case handling |
| `test_fixtures_mst.py` | MST shared test fixtures |
| `test_mst_utils.py` | MST utility functions |
| `test_safe_processing.py` | Safe processing wrapper |
| `test_debug_utils.py` | Debug utilities |
| `test_geometry_utils.py` | Geometry utilities |
| `test_edge_catch_utils.py` | Edge catch helpers |
| `test_config_manager.py` | Configuration management |
| `test_qgis_defaults.py` | QGIS default parameters |
| `test_qgis_environment.py` | QGIS environment setup |
| `test_translations.py` | Translations / i18n |
| `test_check.py` | Input validation checks |
| `test_manage_directory.py` | Directory management |

Run tests locally:

```bash
# All tests
pytest test/ -v

# Single module
pytest test/test_blocker.py -v

# With coverage report
pytest test/ --cov=. --cov-report=html
```

For detailed test conventions see [`ai/core/testing-rules.md`](../ai/core/testing-rules.md) and [`ai/domain/mst-testing.md`](../ai/domain/mst-testing.md).

---

## Code Linting

[pylint](https://pylint.pycqa.org/) is used to ensure code quality. The default configuration is in `.pylintrc` at the project root. Some rules (`missing-docstring`, `invalid-name`) are disabled until the code is fully adjusted.

```bash
pip install pylint
pylint $(git ls-files '*.py')
```

---

## Further Reading

| Document | Content |
|----------|---------|
| [`ai/core/constraints.md`](../ai/core/constraints.md) | Binding rules for all code changes |
| [`ai/core/testing-rules.md`](../ai/core/testing-rules.md) | Test patterns and coverage targets |
| [`ai/core/architecture-guidelines.md`](../ai/core/architecture-guidelines.md) | Class design and code organisation |
| [`ai/core/debug-mode.md`](../ai/core/debug-mode.md) | Debug mode integration |
| [`docs/error-handling.md`](error-handling.md) | Logging system and error categories |

---

## Related Files

| File | Content |
|------|---------|
| [`docs/test-strategy.md`](test-strategy.md) | Test taxonomy, coverage targets, module-to-test mapping, gap backlog |
| [`docs/error-handling.md`](error-handling.md) | Logging system, error categories, debug mode |
| [`docs/plugin-architecture.md`](plugin-architecture.md) | Plugin structure and package layout |
| [`ai/core/testing-rules.md`](../ai/core/testing-rules.md) | Tactical rules: geometry checks, test structure, framework conventions |

---

## Updating Translations

The German translation file is `i18n/IBTool_de.ts`. It must be kept in sync whenever
user-facing strings change in `ibtool/ibtool.py`, `ibtool/ibtool_dialog.py`,
`ibtool/helpers/check.py`, or `ibtool/ibtool_dialog_base.ui`.

### When you change a string

1. Find the matching `<source>` element in `i18n/IBTool_de.ts`.
2. Update (or add) its `<translation>` element with the German text.
3. Recompile (see below).

### When you add a new string

1. Wrap it in `self.tr()` / `QCoreApplication.translate('<ContextName>', ...)` / `_tr()` in the source.
2. Add a new `<message>` block to the correct `<context>` in `IBTool_de.ts`:

```xml
<message>
    <source>Your new English string</source>
    <translation>Ihre neue deutsche Zeichenkette</translation>
</message>
```

Context names:
- `IBToolDialogBase` — strings from `ibtool_dialog_base.ui`
- `IBTool` — strings in `ibtool.py` (via `self.tr()`)
- `IBToolDialog` — strings in `ibtool_dialog.py`
- `InputValidator` — strings in `helpers/check.py` (via `_tr()`)

### Compile after editing

```bash
# Linux / macOS
lrelease i18n/IBTool_de.ts -qm i18n/IBTool_de.qm

# Windows (QGIS bundled lrelease)
"C:\Program Files\QGIS 3.x\bin\lrelease.exe" i18n/IBTool_de.ts -qm i18n/IBTool_de.qm
```

Reload the plugin in QGIS to pick up the new `.qm`.

### Extract new strings automatically (optional)

```bash
pylupdate5 ibtool/ibtool.py ibtool/ibtool_dialog.py \
  ibtool/helpers/check.py ibtool/ibtool_dialog_base.ui \
  -ts i18n/IBTool_de.ts
```

This adds new `<source>` entries without overwriting existing `<translation>` values.
Fill in the `<translation>` tags manually, then recompile.

### Adding a new language

Copy `i18n/IBTool_de.ts` to `i18n/IBTool_<locale>.ts` (e.g. `IBTool_fr.ts`),
fill in the `<translation>` elements, and compile with `lrelease`.
No Python changes needed — QGIS picks up the locale automatically.
