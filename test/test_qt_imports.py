"""Guard: code and tests must import Qt via qgis.PyQt, never PyQt5/PyQt6 directly.

Direct imports (and mock targets such as ``patch('PyQt5.QtWidgets...')``) tie
the code to one Qt major version and break on QGIS 4 (Qt6) or QGIS 3 (Qt5).
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCANNED_DIRS = ("helpers", "ibtool", "ibtool_tools", "test")
THIS_FILE = Path(__file__).resolve()
_DIRECT_QT = re.compile(r"^\s*(from|import)\s+PyQt[56]\b|[\"']PyQt[56]\.", re.MULTILINE)


@pytest.mark.unit
def test_no_direct_pyqt_imports():
    offenders = []
    for d in SCANNED_DIRS:
        for py in (ROOT / d).rglob("*.py"):
            if "__pycache__" in py.parts or py.resolve() == THIS_FILE:
                continue
            if _DIRECT_QT.search(py.read_text(encoding="utf-8")):
                offenders.append(py.relative_to(ROOT).as_posix())
    assert offenders == []
