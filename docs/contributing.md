# Contributing & Development

This document covers the development setup, CI/CD pipeline, test structure, and code quality tooling for IBTool.

---

## Continuous Integration with GitHub Actions and Docker

The project uses two GitHub Actions workflows:

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| **CI** | `.github/workflows/ci.yml` | push to `master`/`main`, PRs | Docker-based tests + Codecov coverage |
| **QGIS Plugin CI** | `.github/workflows/qgis-plugin-ci.yml` | push to `master`/`main`, PRs | Lint, security scan, ZIP build + validation |

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

All runtime packages are also bundled with QGIS 3.40+ and are only listed here to ensure they are available in the Docker test environment where QGIS is not the system package manager.

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
| Build release ZIP | `scripts/create_release_zip.py` | Produces `dist/*.zip` |
| Validate release ZIP | `ci/qgis_plugin_validate.py --zip dist/*.zip` | ZIP structure and manifest |
| Upload artifact | `actions/upload-artifact@v4` | `dist/*.zip` retained for 30 days |

The `detect-secrets` scan excludes `Testdaten/` and `README.md`.

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

### Customising the CI Pipeline

To modify the CI pipeline, edit:

- `.github/workflows/ci.yml` — test workflow
- `.github/workflows/qgis-plugin-ci.yml` — lint/validate/release workflow
- `Dockerfile` — Docker environment and dependencies
- `ci/qgis_plugin_validate.py` — plugin structure validation rules
- `scripts/create_release_zip.py` — release ZIP builder
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
| `test_gap_fix.py` | GapFix module |
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
