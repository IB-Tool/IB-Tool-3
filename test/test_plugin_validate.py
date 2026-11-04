"""Tests for ci/qgis_plugin_validate.py — the plugins.qgis.org preflight checks.

The rules mirror https://plugins.qgis.org/docs/publish, /docs/approval and
/docs/migrate-qgis4 (package <= 25 MB, no binaries, no hidden/generated
files, changelog for the current version, QGIS 4 range without supportsQt6).
Pure Python: no QGIS objects are created.
"""
import importlib.util
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("qgis_plugin_validate", ROOT / "ci" / "qgis_plugin_validate.py")
validate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(validate)

GOOD_META = {
    "name": "IB-Tool 3",
    "description": "Settlement delineation from building footprints",
    "version": "0.3.0",
    "qgisMinimumVersion": "3.40",
    "qgisMaximumVersion": "4.99",
    "author": "A",
    "email": "a@example.org",
    "about": "About text",
    "homepage": "https://example.org",
    "tracker": "https://example.org/issues",
    "repository": "https://example.org/repo",
    "license": "GPL-2.0-or-later",
    "changelog": "0.3.0 - QGIS 4 support. 0.2.5 - Faster.",
}


def _meta_text(meta):
    return "[general]\n" + "\n".join(f"{k}={v}" for k, v in meta.items()) + "\n"


def _make_zip(path, meta=None, extra=(), folder="ibtool"):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"{folder}/metadata.txt", _meta_text(meta or GOOD_META))
        z.writestr(f"{folder}/__init__.py", "")
        z.writestr(f"{folder}/LICENSE", "GPL")
        for name in extra:
            z.writestr(name, b"x")
    return path


def _fails(func, *args):
    with pytest.raises(SystemExit) as exc:
        func(*args)
    return exc.value.code == 2


# ── metadata rules ────────────────────────────────────────────────────────────

class TestMetadataRules:

    @pytest.mark.unit
    def test_good_metadata_passes(self):
        validate.check_metadata_rules(dict(GOOD_META))

    @pytest.mark.unit
    def test_supports_qt6_is_rejected(self):
        meta = dict(GOOD_META, supportsQt6="True")
        assert _fails(validate.check_metadata_rules, meta)

    @pytest.mark.unit
    @pytest.mark.parametrize("maximum", ["3.99", "3.50", None])
    def test_qgis4_range_is_required(self, maximum):
        meta = dict(GOOD_META)
        if maximum is None:
            del meta["qgisMaximumVersion"]
        else:
            meta["qgisMaximumVersion"] = maximum
        assert _fails(validate.check_metadata_rules, meta)

    @pytest.mark.unit
    def test_changelog_must_mention_current_version(self):
        meta = dict(GOOD_META, version="0.3.1")
        assert _fails(validate.check_metadata_rules, meta)

    @pytest.mark.unit
    def test_changelog_version_match_is_exact(self):
        """'0.3.0' must not be satisfied by '10.3.0' or '0.3.01'."""
        meta = dict(GOOD_META, changelog="10.3.0 - x. 0.3.01 - y.")
        assert _fails(validate.check_metadata_rules, meta)

    @pytest.mark.unit
    def test_missing_changelog_is_rejected(self):
        meta = dict(GOOD_META)
        del meta["changelog"]
        assert _fails(validate.check_metadata_rules, meta)

    @pytest.mark.unit
    def test_multiline_changelog_is_one_value(self):
        """Indented continuation lines belong to the previous key (INI semantics, as QGIS reads it)."""
        text = ("[general]\nversion=0.3.0\nchangelog=0.3.0 - New.\n"
                " 0.2.5 - Setting \"Workers\", 0 = automatic.\n 0.2.4 - Old.\nicon=icon.png\n")
        meta = validate.parse_metadata_text(text)
        assert meta["changelog"] == '0.3.0 - New.\n0.2.5 - Setting "Workers", 0 = automatic.\n0.2.4 - Old.'
        assert meta["icon"] == "icon.png"
        assert not any(k.startswith("0.2.5") for k in meta)

    @pytest.mark.unit
    def test_version_only_in_older_changelog_line_is_rejected(self):
        """Bumping the version without a new entry fails even if an old line mentions it."""
        meta = dict(GOOD_META, version="0.2.5", changelog="0.3.0 - New.\n0.2.5 - Old.")
        validate.check_metadata_rules(meta)  # 0.2.5 has an entry (older line) -> passes
        meta = dict(GOOD_META, version="0.3.1", changelog="0.3.0 - New.\n0.2.5 - Old.")
        assert _fails(validate.check_metadata_rules, meta)

    @pytest.mark.unit
    def test_repository_metadata_passes(self):
        """The real metadata.txt must satisfy all rules (guards every commit)."""
        meta = validate.parse_metadata_text((ROOT / "metadata.txt").read_text(encoding="utf-8"))
        validate.check_metadata_rules(meta)


# ── ZIP rules ─────────────────────────────────────────────────────────────────

class TestZipRules:

    @pytest.mark.unit
    def test_good_zip_passes(self, tmp_path):
        validate.validate_zip(_make_zip(tmp_path / "ibtool.zip", extra=["ibtool/helpers/a.py"]))

    @pytest.mark.unit
    @pytest.mark.parametrize("name", [
        "ibtool/lib/tool.exe", "ibtool/lib/x.dll", "ibtool/lib/x.so",
        "ibtool/lib/x.dylib", "ibtool/lib/x.pyd",
    ])
    def test_binaries_are_rejected(self, tmp_path, name):
        assert _fails(validate.validate_zip, _make_zip(tmp_path / "p.zip", extra=[name]))

    @pytest.mark.unit
    @pytest.mark.parametrize("name", [
        "ibtool/.git/config", "ibtool/.github/ci.yml", "ibtool/.env",
        "ibtool/helpers/__pycache__/a.cpython-312.pyc", "ibtool/helpers/a.pyc",
        "__MACOSX/ibtool/._metadata.txt", "ibtool/.DS_Store",
    ])
    def test_hidden_and_generated_files_are_rejected(self, tmp_path, name):
        assert _fails(validate.validate_zip, _make_zip(tmp_path / "p.zip", extra=[name]))

    @pytest.mark.unit
    def test_zip_over_25_mb_is_rejected(self, tmp_path, monkeypatch):
        path = _make_zip(tmp_path / "p.zip")
        monkeypatch.setattr(validate, "MAX_ZIP_BYTES", path.stat().st_size - 1)
        assert _fails(validate.validate_zip, path)

    @pytest.mark.unit
    def test_size_limit_is_25_mb(self):
        assert validate.MAX_ZIP_BYTES == 25 * 1024 * 1024

    @pytest.mark.unit
    def test_metadata_rules_apply_to_zip(self, tmp_path):
        meta = dict(GOOD_META, supportsQt6="True")
        assert _fails(validate.validate_zip, _make_zip(tmp_path / "p.zip", meta=meta))


# ── release mode: version must be new ─────────────────────────────────────────

class TestReleaseVersion:

    @pytest.mark.unit
    @pytest.mark.parametrize("version,tags", [
        ("0.3.0", ["v0.2.5", "v0.2.3", "v0.2.2-beta"]),
        ("0.2.6", ["v0.2.5"]),
        ("1.0.0", ["v0.9.9"]),
        ("0.3.0", []),
    ])
    def test_newer_version_passes(self, version, tags):
        validate.check_version_is_new(version, tags)

    @pytest.mark.unit
    @pytest.mark.parametrize("version,tags", [
        ("0.2.5", ["v0.2.5", "v0.2.3"]),
        ("0.2.4", ["v0.2.5"]),
        ("0.10.0", ["v0.10.1"]),
    ])
    def test_released_or_older_version_is_rejected(self, version, tags):
        assert _fails(validate.check_version_is_new, version, tags)

    @pytest.mark.unit
    def test_numeric_not_lexical_comparison(self):
        validate.check_version_is_new("0.10.0", ["v0.9.0"])
