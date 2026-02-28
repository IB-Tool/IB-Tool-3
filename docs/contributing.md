# Contributing & Development

This document covers the development setup, CI/CD pipeline, test structure, and code quality tooling for IBTool.

---

## Continuous Integration with GitHub Actions and Docker

The project uses GitHub Actions for automated tests in a Docker environment. The CI pipeline runs on every push to the `master` branch and on pull requests.

### CI Workflow (`.github/workflows/ci.yml`)

The CI workflow:
1. Checks out the repository code
2. Sets up Docker Buildx
3. Builds the Docker image based on the `Dockerfile`
4. Runs the tests inside the container with coverage reporting
5. Verifies the coverage report and fixes container-absolute paths
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
      - name: Checkout repository
        uses: actions/checkout@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Build Docker image
        run: docker build --pull -t qgis-plugin-test .

      - name: Run tests with coverage
        run: |
          docker run --rm \
            -v $(pwd):/plugins/ibtool \
            qgis-plugin-test

      - name: Verify and fix coverage report
        run: |
          if [ ! -f coverage.xml ]; then
            echo "ERROR: coverage.xml not found after test run"
            exit 1
          fi
          sed -i 's|/plugins/ibtool/||g' coverage.xml

      - name: Upload coverage reports to Codecov
        uses: codecov/codecov-action@v5
        with:
          token: ${{ secrets.CODECOV_TOKEN }}
          files: ./coverage.xml
          fail_ci_if_error: true
```

### Coverage Reporting

Test coverage is measured with `pytest-cov` and uploaded to [Codecov](https://codecov.io) on every CI run. The `coverage.xml` file is written by the container into the volume-mounted workspace, so it is available on the host after the container exits. Container-absolute paths (`/plugins/ibtool/`) are stripped before upload so Codecov can map lines back to the repository.

### Docker Environment

The `Dockerfile` is based on the official QGIS image `3liz/qgis-platform:3.40` and:

- Installs all required Python dependencies (numpy, pandas, matplotlib, scipy, sklearn, etc.)
- Configures a headless X server environment (xvfb) for GUI tests
- Sets the necessary environment variables for QGIS
- Initialises the QGIS Processing provider
- Runs the tests with pytest

### Local Development with Docker

```bash
# Build the Docker image
docker build -t qgis-plugin-test .
# Run tests
docker run --rm qgis-plugin-test
# Interactive shell inside the container
docker run --rm -it qgis-plugin-test /bin/bash
```

### System Dependencies (Docker)

| Package | Purpose |
|---------|---------|
| `xvfb` | X Virtual Framebuffer for headless GUI tests |
| `python3-pytest` | Test framework |
| `python3-numpy`, `python3-pandas`, `python3-matplotlib` | Numerical libraries |
| `python3-scipy`, `python3-sklearn` | Scientific libraries |
| `python3-networkx` | Network analysis |
| `python3-geopandas`, `python3-gdal` | Geodata processing |
| `python3-psycopg2` | PostgreSQL connection |
| `python3-shapely`, `python3-fiona` | Geometry processing |

### Customising the CI Pipeline

To modify the CI pipeline, edit:

- `.github/workflows/ci.yml` — Workflow configuration
- `Dockerfile` — Docker environment and dependencies
- `test/` — Test files and test data

### Debugging CI Failures

1. Check the GitHub Actions logs for detailed error messages.
2. Test the Docker image locally using the same commands.
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
