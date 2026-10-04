"""
Tests for helpers/system_utils.py — compute_file_checksum.

Coverage:
- Returns a 32-character MD5 hex digest for an existing file
- Returns '' for a non-existent path
- Identical file content → identical checksum
- Different file content → different checksum
- Empty file → valid (non-empty) checksum
- Checksum changes after file content is modified
- Directory path → '' (OSError caught internally)
"""

import hashlib
import os
import pytest
from unittest.mock import patch

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from helpers.system_utils import compute_file_checksum


class TestComputeFileChecksum:
    """Tests for helpers.system_utils.compute_file_checksum."""

    # ------------------------------------------------------------------
    # Normal cases
    # ------------------------------------------------------------------

    @pytest.mark.unit
    def test_returns_32_char_hex_string_for_existing_file(self, tmp_path):
        """Returns a 32-character lowercase MD5 hex digest for a readable file."""
        f = tmp_path / "sample.shp"
        f.write_bytes(b"dummy shapefile bytes")

        result = compute_file_checksum(str(f))

        assert isinstance(result, str)
        assert len(result) == 32
        assert all(c in "0123456789abcdef" for c in result), \
            f"Expected hex string, got: {result!r}"

    @pytest.mark.unit
    def test_checksum_matches_direct_md5_of_content(self, tmp_path):
        """Checksum equals the MD5 of the exact file bytes."""
        content = b"road network binary content"
        f = tmp_path / "roads.gpkg"
        f.write_bytes(content)

        expected = hashlib.md5(content, usedforsecurity=False).hexdigest()  # nosec B324
        result = compute_file_checksum(str(f))

        assert result == expected

    @pytest.mark.unit
    def test_identical_content_yields_identical_checksum(self, tmp_path):
        """Two files with the same bytes produce the same checksum."""
        a = tmp_path / "a.shp"
        b = tmp_path / "b.shp"
        a.write_bytes(b"identical content for both files")
        b.write_bytes(b"identical content for both files")

        assert compute_file_checksum(str(a)) == compute_file_checksum(str(b))

    @pytest.mark.unit
    def test_different_content_yields_different_checksum(self, tmp_path):
        """Two files with different bytes produce different checksums."""
        a = tmp_path / "a.shp"
        b = tmp_path / "b.shp"
        a.write_bytes(b"content A")
        b.write_bytes(b"content B - not the same")

        assert compute_file_checksum(str(a)) != compute_file_checksum(str(b))

    @pytest.mark.unit
    def test_checksum_changes_after_file_is_modified(self, tmp_path):
        """Checksum differs before and after the file's content changes."""
        f = tmp_path / "changing.gpkg"
        f.write_bytes(b"original content")
        cs_before = compute_file_checksum(str(f))

        f.write_bytes(b"modified content - now different")
        cs_after = compute_file_checksum(str(f))

        assert cs_before != cs_after

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_returns_empty_string_for_nonexistent_file(self):
        """Returns '' when the file path does not exist on disk."""
        result = compute_file_checksum("/nonexistent/path/to/buildings.shp")

        assert result == ""

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_file_returns_valid_nonempty_checksum(self, tmp_path):
        """An empty file has a defined MD5 digest (not an empty string)."""
        f = tmp_path / "empty.shp"
        f.write_bytes(b"")

        result = compute_file_checksum(str(f))

        assert isinstance(result, str)
        assert len(result) == 32, \
            "Empty file must still return a 32-char MD5 digest"

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_directory_path_returns_empty_string(self, tmp_path):
        """Passing a directory (not a file) returns '' — OSError is caught internally."""
        result = compute_file_checksum(str(tmp_path))

        assert result == "", \
            "Directory path must return '' (open() raises OSError on directories)"


@pytest.mark.unit
class TestUserConfigDir:
    def test_returns_ibtool_subdir_and_creates_it(self, tmp_path):
        from helpers.system_utils import get_user_config_dir
        result = get_user_config_dir(str(tmp_path))
        assert result == os.path.join(str(tmp_path), "ibtool")
        assert os.path.isdir(result)

    @pytest.mark.parametrize("bad", ["", None])
    def test_empty_settings_dir_raises_oserror(self, bad):
        from helpers.system_utils import get_user_config_dir
        fake = type("QA", (), {"qgisSettingsDirPath": staticmethod(lambda: "")})
        with patch.dict("sys.modules", {"qgis.core": type("M", (), {"QgsApplication": fake})}):
            with pytest.raises(OSError):
                get_user_config_dir(bad)

    def test_migrates_legacy_config_once(self, tmp_path):
        from helpers.system_utils import migrate_legacy_config
        legacy, target = tmp_path / "legacy", tmp_path / "target"
        legacy.mkdir()
        target.mkdir()
        content = "[paths]\nx=1\n"
        (legacy / "CONFIG.ini").write_text(content, encoding="utf-8")

        assert migrate_legacy_config(str(legacy), str(target)) is True
        assert (target / "CONFIG.ini").read_text(encoding="utf-8") == content
        assert (legacy / "CONFIG.ini").exists()

    def test_does_not_overwrite_existing_target(self, tmp_path):
        from helpers.system_utils import migrate_legacy_config
        legacy, target = tmp_path / "legacy", tmp_path / "target"
        legacy.mkdir()
        target.mkdir()
        (legacy / "CONFIG.ini").write_text("old", encoding="utf-8")
        (target / "CONFIG.ini").write_text("new", encoding="utf-8")

        assert migrate_legacy_config(str(legacy), str(target)) is False
        assert (target / "CONFIG.ini").read_text(encoding="utf-8") == "new"

    def test_no_legacy_file_is_noop(self, tmp_path):
        from helpers.system_utils import migrate_legacy_config
        assert migrate_legacy_config(str(tmp_path / "nope"), str(tmp_path)) is False

    def test_copy_failure_returns_false(self, tmp_path):
        from unittest.mock import patch
        from helpers.system_utils import migrate_legacy_config
        legacy, target = tmp_path / "legacy", tmp_path / "target"
        legacy.mkdir()
        target.mkdir()
        (legacy / "CONFIG.ini").write_text("[UI]", encoding="utf-8")
        with patch("helpers.system_utils.shutil.copy2", side_effect=OSError("denied")):
            assert migrate_legacy_config(str(legacy), str(target)) is False
        assert not (target / "CONFIG.ini").exists()

    def test_legacy_default_log_dir_is_blanked(self, tmp_path):
        import configparser
        from helpers.system_utils import migrate_legacy_config
        legacy, target = tmp_path / "legacy", tmp_path / "target"
        legacy.mkdir()
        target.mkdir()
        legacy_logs = os.path.join(str(legacy), "logs")
        (legacy / "CONFIG.ini").write_text(
            f"[UI]\nlog_directory = {legacy_logs}\n", encoding="utf-8")
        assert migrate_legacy_config(str(legacy), str(target)) is True
        parser = configparser.ConfigParser()
        parser.read(str(target / "CONFIG.ini"), encoding="utf-8")
        assert parser.get("UI", "log_directory") == ""

    def test_custom_log_dir_is_preserved(self, tmp_path):
        import configparser
        from helpers.system_utils import migrate_legacy_config
        legacy, target = tmp_path / "legacy", tmp_path / "target"
        legacy.mkdir()
        target.mkdir()
        (legacy / "CONFIG.ini").write_text(
            "[UI]\nlog_directory = C:/somewhere/logs\n", encoding="utf-8")
        assert migrate_legacy_config(str(legacy), str(target)) is True
        parser = configparser.ConfigParser()
        parser.read(str(target / "CONFIG.ini"), encoding="utf-8")
        assert parser.get("UI", "log_directory") == "C:/somewhere/logs"
