"""Tests for scripts/create_release_zip.py.

Functions under test (all pure Python — no QGIS dependency):

  is_excluded(rel)       — apply exclusion rules to a relative Path
  read_version(root)     — parse version string from metadata.txt
  collect_files(root)    — walk a directory tree and apply exclusion rules
  build_zip(root, ...)   — create a ZIP with the correct internal arcnames

Note: The module is imported directly via importlib to bypass the
side-effecting scripts/__init__.py.
"""

from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Isolated import — skip scripts/__init__.py (it patches sys.modules)
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "create_release_zip.py"
_spec = importlib.util.spec_from_file_location("create_release_zip", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

is_excluded = _mod.is_excluded
read_version = _mod.read_version
collect_files = _mod.collect_files
build_zip = _mod.build_zip


# ===========================================================================
# TestIsExcluded
# ===========================================================================

class TestIsExcluded:
    """Unit tests for is_excluded()."""

    # --- excluded directories ---

    @pytest.mark.unit
    def test_file_in_top_level_excluded_dir_is_excluded(self):
        """Files inside a top-level excluded directory (e.g. test/) are excluded."""
        for dirname in ("test", "Testdaten", "ai", "docs", "dist", "scripts"):
            rel = Path(dirname) / "module.py"
            assert is_excluded(rel), f"{rel} should be excluded"

    @pytest.mark.unit
    def test_file_in_nested_excluded_dir_is_excluded(self):
        """Files inside a nested excluded directory (e.g. __pycache__) are excluded."""
        rel = Path("ibtool_tools") / "__pycache__" / "ImportFilter.cpython-39.pyc"
        assert is_excluded(rel)

    @pytest.mark.unit
    def test_file_in_hidden_directory_is_excluded(self):
        """Files inside any directory that starts with '.' are excluded."""
        rel = Path(".github") / "workflows" / "ci.yml"
        assert is_excluded(rel)

    @pytest.mark.unit
    def test_file_in_egg_info_directory_is_excluded(self):
        """Files inside a *.egg-info directory are excluded."""
        rel = Path("my_package.egg-info") / "PKG-INFO"
        assert is_excluded(rel)

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_dist_directory_excluded_prevents_self_inclusion(self):
        """The dist/ output directory itself is excluded to prevent ZIP self-inclusion."""
        rel = Path("dist") / "IB-Tool-3.0.1.3.zip"
        assert is_excluded(rel)

    # --- excluded filenames ---

    @pytest.mark.unit
    def test_excluded_filename_is_excluded(self):
        """Files whose exact name matches EXCLUDED_FILES set are excluded."""
        for fname in ("CLAUDE.md", "plugin_upload.py", "Dockerfile", "pytest.ini"):
            rel = Path(fname)
            assert is_excluded(rel), f"'{fname}' should be excluded"

    @pytest.mark.unit
    def test_excluded_filename_in_subdir_is_excluded(self):
        """An excluded filename is still excluded when nested under a regular directory."""
        rel = Path("ibtool") / "CLAUDE.md"
        assert is_excluded(rel)

    # --- excluded extensions ---

    @pytest.mark.unit
    def test_pyc_extension_is_excluded(self):
        """*.pyc files are always excluded."""
        rel = Path("ibtool_tools") / "ImportFilter.pyc"
        assert is_excluded(rel)

    @pytest.mark.unit
    def test_pyo_extension_is_excluded(self):
        """*.pyo files are always excluded."""
        rel = Path("helpers") / "logger.pyo"
        assert is_excluded(rel)

    @pytest.mark.unit
    def test_iml_extension_is_excluded(self):
        """*.iml IDE project files are always excluded."""
        rel = Path("IB-Tool-3.iml")
        assert is_excluded(rel)

    # --- dotfiles ---

    @pytest.mark.unit
    def test_dotfile_at_root_is_excluded(self):
        """A dotfile at repository root (e.g. .gitignore) is excluded."""
        for name in (".gitignore", ".gitattributes", ".flake8", ".secrets.baseline"):
            rel = Path(name)
            assert is_excluded(rel), f"'{name}' should be excluded"

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_dotfile_in_subdir_is_excluded(self):
        """Dotfiles nested in non-excluded directories are still excluded."""
        rel = Path("ibtool") / ".hidden_config"
        assert is_excluded(rel)

    # --- pycache guard ---

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_pycache_anywhere_in_path_is_excluded(self):
        """__pycache__ appearing at any depth of the path triggers exclusion."""
        rel = Path("helpers") / "__pycache__" / "logger.cpython-39.pyc"
        assert is_excluded(rel)

    # --- normal / included files ---

    @pytest.mark.unit
    def test_normal_python_file_is_not_excluded(self):
        """Regular Python source files in non-excluded directories pass through."""
        rel = Path("ibtool_tools") / "ImportFilter.py"
        assert not is_excluded(rel)

    @pytest.mark.unit
    def test_metadata_txt_is_not_excluded(self):
        """metadata.txt must not be excluded — it ships with the plugin."""
        rel = Path("metadata.txt")
        assert not is_excluded(rel)

    @pytest.mark.unit
    def test_readme_is_not_excluded(self):
        """README.md is a production file and must not be excluded."""
        rel = Path("README.md")
        assert not is_excluded(rel)

    @pytest.mark.unit
    def test_nested_source_file_is_not_excluded(self):
        """A Python file nested two levels deep in a kept directory passes through."""
        rel = Path("ibtool") / "ibtool_tools" / "GapClose.py"
        assert not is_excluded(rel)

    @pytest.mark.unit
    def test_ui_file_is_not_excluded(self):
        """Qt Designer .ui files in the ibtool/ package must not be excluded."""
        rel = Path("ibtool") / "ibtool_dialog_base.ui"
        assert not is_excluded(rel)


# ===========================================================================
# TestReadVersion
# ===========================================================================

class TestReadVersion:
    """Unit tests for read_version()."""

    @pytest.mark.unit
    def test_reads_version_from_valid_metadata(self, tmp_path):
        """Returns the version string from a well-formed metadata.txt."""
        (tmp_path / "metadata.txt").write_text(
            "[general]\nversion=1.2.3\n", encoding="utf-8"
        )
        assert read_version(tmp_path) == "1.2.3"

    @pytest.mark.unit
    def test_version_value_is_stripped_of_whitespace(self, tmp_path):
        """Leading and trailing whitespace around the version value is stripped."""
        (tmp_path / "metadata.txt").write_text(
            "[general]\nversion=  2.0.0  \n", encoding="utf-8"
        )
        assert read_version(tmp_path) == "2.0.0"

    @pytest.mark.unit
    def test_missing_metadata_raises_file_not_found(self, tmp_path):
        """FileNotFoundError is raised when metadata.txt does not exist."""
        with pytest.raises(FileNotFoundError, match="metadata.txt"):
            read_version(tmp_path)

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_missing_version_key_raises_value_error(self, tmp_path):
        """ValueError is raised when [general] section exists but has no version key."""
        (tmp_path / "metadata.txt").write_text(
            "[general]\nname=IB-Tool\n", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="version"):
            read_version(tmp_path)

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_metadata_without_general_section_raises(self, tmp_path):
        """ValueError is raised when metadata.txt has no [general] section."""
        (tmp_path / "metadata.txt").write_text(
            "[other]\nversion=1.0.0\n", encoding="utf-8"
        )
        with pytest.raises((ValueError, KeyError)):
            read_version(tmp_path)


# ===========================================================================
# TestCollectFiles
# ===========================================================================

class TestCollectFiles:
    """Unit tests for collect_files()."""

    @pytest.mark.unit
    def test_returns_list_of_relative_paths(self, tmp_path):
        """collect_files returns a list whose entries are relative Path objects."""
        (tmp_path / "keep.py").write_text("", encoding="utf-8")
        result = collect_files(tmp_path)
        assert isinstance(result, list)
        assert all(isinstance(p, Path) for p in result)
        assert not any(p.is_absolute() for p in result)

    @pytest.mark.unit
    def test_normal_file_is_collected(self, tmp_path):
        """A regular Python file in a non-excluded directory is collected."""
        (tmp_path / "helpers").mkdir()
        (tmp_path / "helpers" / "utils.py").write_text("", encoding="utf-8")
        result = collect_files(tmp_path)
        assert Path("helpers") / "utils.py" in result

    @pytest.mark.unit
    def test_test_directory_is_excluded(self, tmp_path):
        """Files inside test/ are never included in the collected list."""
        (tmp_path / "test").mkdir()
        (tmp_path / "test" / "test_something.py").write_text("", encoding="utf-8")
        (tmp_path / "keep.py").write_text("", encoding="utf-8")
        result = collect_files(tmp_path)
        assert Path("keep.py") in result
        assert not any(Path("test") in p.parents or p == Path("test") for p in result)

    @pytest.mark.unit
    def test_pyc_files_are_excluded(self, tmp_path):
        """*.pyc compiled files are not collected even when alongside source."""
        (tmp_path / "module.py").write_text("", encoding="utf-8")
        (tmp_path / "module.pyc").write_text("", encoding="utf-8")
        result = collect_files(tmp_path)
        assert Path("module.py") in result
        assert Path("module.pyc") not in result

    @pytest.mark.unit
    def test_directories_themselves_are_not_returned(self, tmp_path):
        """Only files appear in the result — directory paths are never included."""
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file.py").write_text("", encoding="utf-8")
        result = collect_files(tmp_path)
        assert all((tmp_path / p).is_file() for p in result)

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_directory_returns_empty_list(self, tmp_path):
        """An empty directory tree returns an empty list without raising."""
        result = collect_files(tmp_path)
        assert result == []

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_dotfile_is_not_collected(self, tmp_path):
        """Dotfiles at repository root are not collected."""
        (tmp_path / ".gitignore").write_text("", encoding="utf-8")
        (tmp_path / "keep.py").write_text("", encoding="utf-8")
        result = collect_files(tmp_path)
        assert Path(".gitignore") not in result
        assert Path("keep.py") in result


# ===========================================================================
# TestBuildZip
# ===========================================================================

class TestBuildZip:
    """Unit tests for build_zip()."""

    @pytest.mark.unit
    def test_creates_zip_file_at_given_path(self, tmp_path):
        """A ZIP file is created at the specified zip_path."""
        src = tmp_path / "repo"
        src.mkdir()
        (src / "module.py").write_text("# code", encoding="utf-8")
        zip_path = tmp_path / "dist" / "plugin.zip"

        build_zip(src, [Path("module.py")], zip_path, "IB-Tool-3")

        assert zip_path.exists()
        assert zipfile.is_zipfile(zip_path)

    @pytest.mark.unit
    def test_arcnames_are_prefixed_with_plugin_folder(self, tmp_path):
        """Every entry inside the ZIP is prefixed with '<plugin_folder>/'."""
        src = tmp_path / "repo"
        src.mkdir()
        (src / "init.py").write_text("", encoding="utf-8")
        zip_path = tmp_path / "out.zip"

        build_zip(src, [Path("init.py")], zip_path, "MyPlugin")

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        assert all(n.startswith("MyPlugin/") for n in names)

    @pytest.mark.unit
    def test_zip_contains_all_provided_files(self, tmp_path):
        """Every file supplied in the files list appears in the ZIP archive."""
        src = tmp_path / "repo"
        src.mkdir()
        for name in ("a.py", "b.py", "c.txt"):
            (src / name).write_text("content", encoding="utf-8")
        zip_path = tmp_path / "out.zip"

        build_zip(src, [Path("a.py"), Path("b.py"), Path("c.txt")], zip_path, "Plug")

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
        assert "Plug/a.py" in names
        assert "Plug/b.py" in names
        assert "Plug/c.txt" in names

    @pytest.mark.unit
    def test_creates_missing_parent_directories(self, tmp_path):
        """The dist/ parent directory (and any intermediate dirs) is created automatically."""
        src = tmp_path / "repo"
        src.mkdir()
        (src / "f.py").write_text("", encoding="utf-8")
        zip_path = tmp_path / "new_dir" / "sub" / "out.zip"

        build_zip(src, [Path("f.py")], zip_path, "P")

        assert zip_path.parent.exists()
        assert zip_path.exists()

    @pytest.mark.unit
    def test_nested_file_preserves_posix_arcname(self, tmp_path):
        """Nested files use forward slashes in the arcname regardless of OS."""
        src = tmp_path / "repo"
        (src / "helpers").mkdir(parents=True)
        (src / "helpers" / "logger.py").write_text("", encoding="utf-8")
        zip_path = tmp_path / "out.zip"

        build_zip(src, [Path("helpers") / "logger.py"], zip_path, "IB")

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        assert "IB/helpers/logger.py" in names

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_file_list_creates_empty_valid_zip(self, tmp_path):
        """An empty files list produces a valid but empty ZIP without raising."""
        src = tmp_path / "repo"
        src.mkdir()
        zip_path = tmp_path / "empty.zip"

        build_zip(src, [], zip_path, "P")

        assert zip_path.exists()
        with zipfile.ZipFile(zip_path, "r") as zf:
            assert zf.namelist() == []
