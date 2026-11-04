"""Every Processing algorithm id used by the plugin must exist in the running QGIS.

Guards the QGIS 4 migration: legacy ``qgis:`` aliases may disappear between
major versions; this test names the id that no longer resolves.
"""
import re
from pathlib import Path

import pytest

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from qgis.core import QgsApplication  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SHIPPING_DIRS = ("helpers", "ibtool", "ibtool_tools")
_CALL = re.compile(r"(?:processing\.run|safe_processing_run)\(\s*[\"']([a-z]+:[a-z_]+)[\"']")


def _algorithm_ids():
    """All literal algorithm ids passed to processing.run / safe_processing_run."""
    ids = set()
    for d in SHIPPING_DIRS:
        for py in (ROOT / d).rglob("*.py"):
            if "__pycache__" not in py.parts:
                ids.update(_CALL.findall(py.read_text(encoding="utf-8")))
    return ids


@pytest.fixture(scope="module")
def registry():
    from processing.core.Processing import Processing
    Processing.initialize()
    return QgsApplication.processingRegistry()


@pytest.mark.unit
def test_algorithm_ids_found():
    assert len(_algorithm_ids()) >= 40


@pytest.mark.unit
def test_all_processing_ids_resolve(registry):
    missing = sorted(i for i in _algorithm_ids() if registry.algorithmById(i) is None)
    assert missing == []
