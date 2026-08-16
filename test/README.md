# Test Guidelines and Central Configuration

This directory contains all automated tests for **IB-Tool 3**. To keep tests
focused on assertions, shared environment settings are stored in
`test_config.ini` and applied automatically when the test package is imported.

## Configuration file

Edit `test_config.ini` to match your local QGIS installation:

```ini
[qgis]
prefix_path = C:\\Program Files\\QGIS 3.40.0
```

`config.py` reads this file and sets up environment variables such as
`QGIS_PREFIX_PATH` and `PYTHONPATH`. The function `apply_qgis_environment()`
updates `sys.path` so tests can import QGIS modules without extra setup.
`PROJECT_ROOT` is exported for tests that need an absolute path to the
repository root.

## Writing tests

* Use `from .utilities import get_qgis_app` when a QGIS application instance is
  required.
* Avoid manual `sys.path` modifications. The configuration handles common paths.
* Keep mocks that are specific to a test within the test file.
* Follow pytest conventions for test file naming (prefix with `test_`) and test function naming (prefix with `test_`).

These notes are intended for developers and AI systems extending the test suite.
Follow this structure to maintain consistent and minimal setup code.
