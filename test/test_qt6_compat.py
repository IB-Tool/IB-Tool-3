"""Guard: no Qt5-only spellings that break under Qt6 / PyQt6 (QGIS 4).

Every Qt and QGIS enum must be written fully scoped (e.g.
``QMessageBox.StandardButton.Yes``, ``Qgis.MessageLevel.Info``); this works on
PyQt5 >= 5.11 (QGIS 3.40+) and on PyQt6 (QGIS 4). ``exec_()`` no longer exists
in PyQt6. See docs/superpowers/plans/2026-11-03-qgis4-migration.md.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SHIPPING_DIRS = ("helpers", "ibtool", "ibtool_tools", "scripts")
SCANNED_DIRS = SHIPPING_DIRS + ("test",)
THIS_FILE = Path(__file__).resolve()

FORBIDDEN = {
    "exec_": r"\.exec_\(",
    "qt-orientation": r"\bQt\.(Horizontal|Vertical)\b",
    "qmessagebox-buttons": r"\b(QMessageBox|_QMB)\.(Yes|No|Ok|Cancel)\b",
    "qdialogbuttonbox-buttons": r"\bQDialogButtonBox\.(Close|Ok|Cancel)\b",
    "qfiledialog-options": r"\bQFileDialog\.(ShowDirsOnly|DontResolveSymlinks)\b",
    "qdialog-dialogcode": r"\bQDialog\.(Accepted|Rejected)\b",
    "qprocess-enums": r"\bQProcess\.(NotRunning|Starting|Running|FailedToStart|Crashed)\b",
    "qmetatype-unscoped": r"\bQMetaType\.(?!Type\b)[A-Z]\w*",
    # QGIS enums (static functions such as QgsWkbTypes.flatType() start lowercase and stay allowed)
    "qgswkbtypes-enum": r"\bQgsWkbTypes\.[A-Z]\w*",
    "qgis-messagelevel": r"\bQgis\.(Info|Warning|Critical|Success|NoLevel)\b",
    "qgsvectorfilewriter-enum": (r"\bQgsVectorFileWriter\.(NoError|CreateOrOverwriteFile|CreateOrOverwriteLayer"
                                 r"|AppendToLayerNoNewFields|AppendToLayerAddFields)\b"),
    "qgsvectordataprovider-caps": r"\bQgsVectorDataProvider\.[A-Z]\w*",
    # QgsField(name, QVariant.Int) -> QgsField(name, QMetaType.Type.Int)
    "qvariant-types": r"\bQVariant\.(Int|String|Double|Bool|LongLong|Date|DateTime)\b",
    "qlocale-enum": r"\bQLocale\.(Germany|German|English|UnitedStates)\b",
    # Generic: every member of the Qt namespace is an enum value or enum type; an
    # unscoped value (Qt.AlignLeft, Qt.UserRole, Qt.WaitCursor) is followed by no
    # further attribute, a scoped one (Qt.AlignmentFlag.AlignLeft) is.
    "qt-namespace-unscoped": r"\bQt\.[A-Z]\w*\b(?!\.)",
    "qgsfeaturerequest-enum": r"\bQgsFeatureRequest\.[A-Z]\w*\b(?!\.)",
    "qgsprocessing-sourcetype": r"\bQgsProcessing\.Type[A-Z]\w*",
}

# QAction lives in QtGui on Qt6 and in QtWidgets on Qt5: a QtWidgets import of
# QAction is only allowed as the fallback of a QtGui import.
_QTWIDGETS_IMPORT = re.compile(r"from\s+qgis\.PyQt\.QtWidgets\s+import\s+(\([^)]*\)|[^\n]*)")
_QT6_QACTION = "from qgis.PyQt.QtGui import QAction"


def _python_files(dirs):
    """Python files in *dirs* (recursive) plus the plugin-root files such as ``__init__.py``."""
    yield from sorted(ROOT.glob("*.py"))
    for d in dirs:
        for py in sorted((ROOT / d).rglob("*.py")):
            if "__pycache__" in py.parts or py.resolve() == THIS_FILE:
                continue
            yield py


def _offenders(pattern, dirs):
    """Return ``"path:line: text"`` for every line in *dirs* matching *pattern*."""
    regex = re.compile(pattern)
    hits = []
    for py in _python_files(dirs):
        for no, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if regex.search(line):
                hits.append(f"{py.relative_to(ROOT).as_posix()}:{no}: {line.strip()}")
    return hits


@pytest.mark.unit
@pytest.mark.parametrize("pattern", FORBIDDEN.values(), ids=FORBIDDEN.keys())
def test_no_qt5_only_spelling(pattern):
    assert _offenders(pattern, SCANNED_DIRS) == []


def _qaction_offenders(dirs):
    offenders = []
    for py in _python_files(dirs):
        text = py.read_text(encoding="utf-8")
        from_widgets = any(re.search(r"\bQAction\b", m.group(1)) for m in _QTWIDGETS_IMPORT.finditer(text))
        if from_widgets and _QT6_QACTION not in text:
            offenders.append(py.relative_to(ROOT).as_posix())
    return offenders


@pytest.mark.unit
def test_qaction_import_is_qt6_safe():
    assert _qaction_offenders(SCANNED_DIRS) == []


@pytest.mark.unit
def test_no_utf8_bom():
    """pyqgis4-checker (run by plugins.qgis.org on upload) cannot parse files starting with a BOM."""
    offenders = [py.relative_to(ROOT).as_posix() for py in _python_files(SCANNED_DIRS)
                 if py.read_bytes().startswith(b"\xef\xbb\xbf")]
    assert offenders == []
