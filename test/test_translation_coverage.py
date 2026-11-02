# coding=utf-8
"""Static consistency checks between the source code and i18n/IBTool_de.ts.

No QGIS needed: the Python sources are parsed with ``ast`` and the ``.ts`` /
``.ui`` files with ``xml.etree``.

Checked:
- every literal ``tr()`` / ``_tr()`` string and every translatable ``.ui``
  string has a finished German translation in the matching context;
- the ``.ts`` file contains no entries the code no longer uses (strings that
  are translated through a variable are listed in ``_dynamic_sources()``);
- user-visible UI texts (phase label, message boxes, file dialogs, window
  titles) are not passed as bare string literals, i.e. they go through
  ``tr()`` and are therefore translatable.
"""
import ast
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TS_FILE = ROOT / "i18n" / "IBTool_de.ts"
UI_FILE = ROOT / "ibtool" / "ibtool_dialog_base.ui"

# Python file -> translation context used by its tr() helper
SOURCE_CONTEXTS = {
    "ibtool/ibtool.py": "IBTool",
    "ibtool/ibtool_dialog.py": "IBToolDialog",
    "helpers/check.py": "InputValidator",
}
TR_FUNCTIONS = {"tr", "_tr"}


def _parse(rel):
    return ast.parse((ROOT / rel).read_text(encoding="utf-8-sig"), filename=rel)


def _ts_entries():
    """Return {(context, source): (translation, type)} from the .ts file."""
    entries = {}
    for ctx in ET.parse(TS_FILE).getroot().iter("context"):  # nosec B314 - repository file, not untrusted input
        name = ctx.findtext("name")
        for message in ctx.iter("message"):
            translation = message.find("translation")
            entries[(name, message.findtext("source"))] = (
                translation.text or "", translation.get("type"))
    return entries


def _literal_tr_sources():
    """Return {(context, source)} of all tr()/_tr() calls with a string literal."""
    used = set()
    for rel, context in SOURCE_CONTEXTS.items():
        for node in ast.walk(_parse(rel)):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            arg = node.args[0]
            if name in TR_FUNCTIONS and isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                used.add((context, arg.value))
    return used


def _ui_sources():
    """Return {(context, source)} of all translatable strings in the .ui file."""
    used = set()
    for prop in ET.parse(UI_FILE).getroot().iter("property"):  # nosec B314 - repository file, not untrusted input
        string = prop.find("string")
        if string is None or not string.text or string.get("notr") == "true":
            continue
        used.add(("IBToolDialogBase", string.text))
    return used


def _dynamic_sources():
    """Strings translated through a variable (``tr(name)``), maintained by hand."""
    phases = {"Load Data", "Save Output"}
    for node in ast.walk(_parse("helpers/partition_pipeline.py")):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "PHASES" for t in node.targets):
            phases |= {v.value for v in node.value.values}
    layer_names = {"Building footprints (HU)", "Road network (RN)",
                   "Partitioning (Part)", "Auxiliary layer (Aux)"}
    return ({("IBTool", p) for p in phases}
            | {("InputValidator", n) for n in layer_names})


@pytest.mark.unit
class TestTranslationCoverage:
    """The .ts file matches the strings the code actually translates."""

    def test_dynamic_sources_exist_in_code(self):
        """The hand-maintained dynamic strings are still defined in the source."""
        text = "".join((ROOT / rel).read_text(encoding="utf-8-sig") for rel in (
            "helpers/partition_pipeline.py", "ibtool/ibtool.py", "helpers/check.py"))
        missing = [src for _, src in _dynamic_sources() if f'"{src}"' not in text]
        assert not missing, f"dynamic tr() sources no longer in the code: {missing}"

    def test_every_source_string_has_a_translation(self):
        entries = _ts_entries()
        needed = _literal_tr_sources() | _ui_sources() | _dynamic_sources()
        missing = sorted(k for k in needed if k not in entries)
        unfinished = sorted(k for k in needed if k in entries
                            and (not entries[k][0] or entries[k][1] == "unfinished"))
        assert not missing, "missing in IBTool_de.ts:\n" + "\n".join(map(repr, missing))
        assert not unfinished, "untranslated in IBTool_de.ts:\n" + "\n".join(map(repr, unfinished))

    def test_no_obsolete_entries(self):
        used = _literal_tr_sources() | _ui_sources() | _dynamic_sources()
        obsolete = sorted(k for k in _ts_entries() if k not in used)
        assert not obsolete, "obsolete in IBTool_de.ts:\n" + "\n".join(map(repr, obsolete))


# Literals that are intentionally not translated (product name as dialog title)
ALLOWED_LITERALS = {"IB-Tool"}


def _is_bare_text(node):
    """True for a plain string literal or f-string (i.e. not routed through tr())."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return bool(node.value.strip()) and node.value not in ALLOWED_LITERALS
    return isinstance(node, ast.JoinedStr)


def _ui_text_args(call):
    """Return the arguments of *call* that are shown to the user as text."""
    func = call.func
    if not isinstance(func, ast.Attribute):
        return []
    owner = func.value.id if isinstance(func.value, ast.Name) else None
    if func.attr == "setText" and isinstance(func.value, ast.Attribute) \
            and func.value.attr == "phaseLabel":
        return call.args[:1]
    if func.attr == "setWindowTitle":
        return call.args[:1]
    if owner == "QMessageBox" and func.attr in {"question", "warning", "information", "critical"}:
        return call.args[1:3]  # title, text
    if owner == "QFileDialog" and func.attr in {
            "getOpenFileName", "getSaveFileName", "getExistingDirectory"}:
        return [a for i, a in enumerate(call.args) if i in (1, 3)]  # caption, filter
    return []


@pytest.mark.unit
@pytest.mark.parametrize("rel", ["ibtool/ibtool.py", "ibtool/ibtool_dialog.py"])
def test_ui_texts_are_translatable(rel):
    """Phase label, dialogs and message boxes never show a bare literal."""
    offenders = []
    for node in ast.walk(_parse(rel)):
        if isinstance(node, ast.Call):
            offenders += [f"{rel}:{a.lineno}: {ast.unparse(a)[:70]}"
                          for a in _ui_text_args(node) if _is_bare_text(a)]
    assert not offenders, "UI text not wrapped in tr():\n" + "\n".join(offenders)
