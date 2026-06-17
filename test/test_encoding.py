# coding=utf-8
"""Regression test: detect broken (multi-encoded) UTF-8 characters in source files.

Broken patterns arise when UTF-8 text is decoded as Windows-1252 / Latin-1 and
then re-encoded as UTF-8 -- once (double-encoding) or twice (triple-encoding).
This produces recognisable garbage sequences that are caught here before reaching
production.  No QGIS dependency.
"""

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Broken patterns: (human label, broken Unicode sequence)
# The source file itself is excluded from the scan so these literals are safe.
# ---------------------------------------------------------------------------
_BROKEN_PATTERNS = [
    # triple-encoded (UTF-8 -> cp1252 mis-read -> UTF-8, done twice)
    ('triple-encoded ü (ue)', 'ÃƒÂ¼'),   # ue
    ('triple-encoded ö (oe)', 'ÃƒÂ¶'),   # oe
    ('triple-encoded ä (ae)', 'ÃƒÂ¤'),   # ae
    ('triple-encoded ß (ss)', 'ÃƒÅ¸'),   # ss
    ('triple-encoded — (em-dash)',                            # --
     'Ã¢â‚¬â€'),
    # double-encoded (UTF-8 -> cp1252 mis-read -> UTF-8, done once)
    ('double-encoded ü (ue)', 'Ã¼'),
    ('double-encoded ö (oe)', 'Ã¶'),
    ('double-encoded ä (ae)', 'Ã¤'),
    ('double-encoded Ü (Ue)', 'Ãœ'),
    ('double-encoded Ö (Oe)', 'Ã–'),
    ('double-encoded Ä (Ae)', 'Ã„'),
    ('double-encoded ß (ss)', 'ÃŸ'),
    ('double-encoded — (em-dash)', 'â€\x22'),  # ends with ASCII "
]

_COMBINED_RE = re.compile(
    '|'.join(re.escape(pat) for _, pat in _BROKEN_PATTERNS)
)

_SKIP_DIRS = {'.git', '__pycache__', '.pytest_cache', 'node_modules'}


def _python_sources(root, exclude=None):
    for path in root.rglob('*.py'):
        if exclude and path.resolve() == exclude:
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        yield path


class TestSourceEncoding:
    """Pure filesystem check -- no QGIS dependency."""

    def test_no_broken_encoding_in_python_sources(self):
        root = Path(__file__).resolve().parent.parent
        this_file = Path(__file__).resolve()
        findings = []

        for py_file in _python_sources(root, exclude=this_file):
            try:
                text = py_file.read_text(encoding='utf-8')
            except UnicodeDecodeError as exc:
                findings.append(
                    '{}: cannot decode as UTF-8 -- {}'.format(
                        py_file.relative_to(root), exc))
                continue

            for lineno, line in enumerate(text.splitlines(), start=1):
                if _COMBINED_RE.search(line):
                    rel = py_file.relative_to(root)
                    findings.append('{}:{}: {!r}'.format(rel, lineno, line.strip()))

        assert not findings, (
            'Found {} line(s) with broken encoding patterns:\n'.format(len(findings))
            + '\n'.join(findings)
        )
