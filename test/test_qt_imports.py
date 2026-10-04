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
