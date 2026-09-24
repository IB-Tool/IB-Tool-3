"""Tests for scripts/create_release_zip.py.

Functions under test (all pure Python — no QGIS dependency):

  is_included(rel)              — apply the whitelist to a relative Path
  read_version(root)            — parse version string from metadata.txt
  collect_files(root)           — walk a directory tree and apply the whitelist
  build_zip(root, ...)          — create a ZIP with the correct internal arcnames
  run_guard(root, files, zip)   — fail on forbidden extensions/exec-bit/size/binaries
  run_import_smoke_test(root)   — verify every local import resolves on disk

Note: The module is imported directly via importlib to bypass the
side-effecting scripts/__init__.py.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import subprocess  # nosec B404 — test-only, fixed args, no shell
import zipfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Isolated import — skip scripts/__init__.py (it patches sys.modules)
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "create_release_zip.py"
_spec = importlib.util.spec_from_file_location("create_release_zip", _SCRIPT)
assert _spec is not None and _spec.loader is not None, f"could not load spec for {_SCRIPT}"
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

PLUGIN_FOLDER = _mod.PLUGIN_FOLDER
is_included = _mod.is_included
read_version = _mod.read_version
collect_files = _mod.collect_files
build_zip = _mod.build_zip
run_guard = _mod.run_guard
run_import_smoke_test = _mod.run_import_smoke_test
GuardError = _mod.GuardError


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_git_repo(repo: Path) -> None:
    """Initialize a throwaway git repo with a local identity, isolated from the user's config."""
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")


# ===========================================================================
# TestPluginFolder
# ===========================================================================

class TestPluginFolder:
    """The internal ZIP folder name must be constant, independent of checkout dir."""

    @pytest.mark.unit
    def test_plugin_folder_is_constant_ibtool(self):
        """PLUGIN_FOLDER is the fixed constant 'ibtool', not the checkout dir name."""
        assert PLUGIN_FOLDER == "ibtool"


# ===========================================================================
# TestIsIncluded
# ===========================================================================

class TestIsIncluded:
    """Unit tests for is_included()."""

    # --- whitelisted root files ---

    @pytest.mark.unit
    def test_whitelisted_root_file_is_included(self):
        """Every file in WHITELIST_FILES is included at the repository root."""
        for fname in ("__init__.py", "metadata.txt", "icon.png", "LICENSE", "README.md",
                      "requirements.txt", "resources.qrc"):
            assert is_included(Path(fname)), f"'{fname}' should be included"

    @pytest.mark.unit
    def test_non_whitelisted_root_file_is_excluded(self):
        """Files at the repository root not in WHITELIST_FILES are excluded."""
        for fname in ("CLAUDE.md", "requirements-dev.txt", "coverage.xml",
                      "Dockerfile", "pytest.ini", ".gitignore",
                      "IB-Tool_Icon_2HiRes.png"):
            assert not is_included(Path(fname)), f"'{fname}' should be excluded"

    # --- whitelisted directories ---

    @pytest.mark.unit
    def test_file_in_whitelisted_dir_is_included(self):
        """Files nested inside a whitelisted top-level directory are included."""
        for rel in (
            Path("helpers") / "logger.py",
            Path("i18n") / "IBTool_de.qm",
            Path("ibtool") / "ibtool.py",
            Path("ibtool_tools") / "GapClose.py",
        ):
            assert is_included(rel), f"{rel} should be included"

    @pytest.mark.unit
    def test_nested_file_two_levels_deep_is_included(self):
        """A file nested two levels inside a whitelisted directory is included."""
        rel = Path("ibtool_tools") / "mst" / "mst_calculator.py"
        assert is_included(rel)

    @pytest.mark.unit
    def test_file_in_non_whitelisted_dir_is_excluded(self):
        """Files inside a top-level directory that is not whitelisted are excluded."""
        for dirname in ("test", "Testdaten", "ai", "docs", "dist", "scripts", ".github"):
            rel = Path(dirname) / "module.py"
            assert not is_included(rel), f"{rel} should be excluded"

    @pytest.mark.unit
    def test_debug_utils_module_is_included(self):
        """helpers/debug_utils.py is a production module and must ship — it must not
        be swept up by any filename-prefix exclusion (regression guard for the
        0.2.2 incident where a 'debug_' prefix rule dropped it)."""
        rel = Path("helpers") / "debug_utils.py"
        assert is_included(rel)

    # --- __pycache__ / compiled Python ---

    @pytest.mark.unit
    def test_pycache_inside_whitelisted_dir_is_excluded(self):
        """__pycache__ directories nested inside a whitelisted dir are excluded."""
        rel = Path("helpers") / "__pycache__" / "logger.cpython-311.pyc"
        assert not is_included(rel)

    @pytest.mark.unit
    def test_pyc_inside_whitelisted_dir_is_excluded(self):
        """*.pyc files inside a whitelisted dir are excluded even outside __pycache__."""
        rel = Path("ibtool_tools") / "ImportFilter.pyc"
        assert not is_included(rel)

    @pytest.mark.unit
    def test_pyo_inside_whitelisted_dir_is_excluded(self):
        """*.pyo files inside a whitelisted dir are excluded."""
        rel = Path("helpers") / "logger.pyo"
        assert not is_included(rel)


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
        (tmp_path / "helpers").mkdir()
        (tmp_path / "helpers" / "keep.py").write_text("", encoding="utf-8")
        result = collect_files(tmp_path)
        assert isinstance(result, list)
        assert all(isinstance(p, Path) for p in result)
        assert not any(p.is_absolute() for p in result)

    @pytest.mark.unit
    def test_whitelisted_dir_file_is_collected(self):
        """A regular Python file inside a whitelisted directory is collected."""
        repo_root = Path(__file__).resolve().parent.parent
        result = collect_files(repo_root)
        assert Path("helpers") / "logger.py" in result

    @pytest.mark.unit
    def test_test_directory_is_never_collected(self, tmp_path):
        """Files inside test/ are never included, even if it exists on disk."""
        (tmp_path / "test").mkdir()
        (tmp_path / "test" / "test_something.py").write_text("", encoding="utf-8")
        (tmp_path / "metadata.txt").write_text("[general]\nversion=0.1\n", encoding="utf-8")
        result = collect_files(tmp_path)
        assert Path("metadata.txt") in result
        assert not any(Path("test") in p.parents or p == Path("test") for p in result)

    @pytest.mark.unit
    def test_pyc_files_are_excluded(self, tmp_path):
        """*.pyc compiled files are not collected even when alongside whitelisted source."""
        (tmp_path / "helpers").mkdir()
        (tmp_path / "helpers" / "module.py").write_text("", encoding="utf-8")
        (tmp_path / "helpers" / "module.pyc").write_text("", encoding="utf-8")
        result = collect_files(tmp_path)
        assert Path("helpers") / "module.py" in result
        assert Path("helpers") / "module.pyc" not in result

    @pytest.mark.unit
    def test_directories_themselves_are_not_returned(self, tmp_path):
        """Only files appear in the result — directory paths are never included."""
        (tmp_path / "helpers").mkdir()
        (tmp_path / "helpers" / "file.py").write_text("", encoding="utf-8")
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
    def test_non_whitelisted_root_dotfile_is_not_collected(self, tmp_path):
        """Dotfiles at repository root are not whitelisted."""
        (tmp_path / ".gitignore").write_text("", encoding="utf-8")
        (tmp_path / "metadata.txt").write_text("[general]\nversion=0.1\n", encoding="utf-8")
        result = collect_files(tmp_path)
        assert Path(".gitignore") not in result
        assert Path("metadata.txt") in result


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

        build_zip(src, [Path("module.py")], zip_path, "ibtool")

        assert zip_path.exists()
        assert zipfile.is_zipfile(zip_path)

    @pytest.mark.unit
    def test_arcnames_are_prefixed_with_plugin_folder(self, tmp_path):
        """Every entry inside the ZIP is prefixed with '<plugin_folder>/'."""
        src = tmp_path / "repo"
        src.mkdir()
        (src / "init.py").write_text("", encoding="utf-8")
        zip_path = tmp_path / "out.zip"

        build_zip(src, [Path("init.py")], zip_path, "ibtool")

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        assert all(n.startswith("ibtool/") for n in names)

    @pytest.mark.unit
    def test_zip_contains_all_provided_files(self, tmp_path):
        """Every file supplied in the files list appears in the ZIP archive."""
        src = tmp_path / "repo"
        src.mkdir()
        for name in ("a.py", "b.py", "c.txt"):
            (src / name).write_text("content", encoding="utf-8")
        zip_path = tmp_path / "out.zip"

        build_zip(src, [Path("a.py"), Path("b.py"), Path("c.txt")], zip_path, "ibtool")

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
        assert "ibtool/a.py" in names
        assert "ibtool/b.py" in names
        assert "ibtool/c.txt" in names

    @pytest.mark.unit
    def test_creates_missing_parent_directories(self, tmp_path):
        """The dist/ parent directory (and any intermediate dirs) is created automatically."""
        src = tmp_path / "repo"
        src.mkdir()
        (src / "f.py").write_text("", encoding="utf-8")
        zip_path = tmp_path / "new_dir" / "sub" / "out.zip"

        build_zip(src, [Path("f.py")], zip_path, "ibtool")

        assert zip_path.parent.exists()
        assert zip_path.exists()

    @pytest.mark.unit
    def test_nested_file_preserves_posix_arcname(self, tmp_path):
        """Nested files use forward slashes in the arcname regardless of OS."""
        src = tmp_path / "repo"
        (src / "helpers").mkdir(parents=True)
        (src / "helpers" / "logger.py").write_text("", encoding="utf-8")
        zip_path = tmp_path / "out.zip"

        build_zip(src, [Path("helpers") / "logger.py"], zip_path, "ibtool")

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        assert "ibtool/helpers/logger.py" in names

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_file_list_creates_empty_valid_zip(self, tmp_path):
        """An empty files list produces a valid but empty ZIP without raising."""
        src = tmp_path / "repo"
        src.mkdir()
        zip_path = tmp_path / "empty.zip"

        build_zip(src, [], zip_path, "ibtool")

        assert zip_path.exists()
        with zipfile.ZipFile(zip_path, "r") as zf:
            assert zf.namelist() == []


# ===========================================================================
# TestRunGuard
# ===========================================================================

class TestRunGuard:
    """Unit tests for run_guard()."""

    @pytest.mark.unit
    def test_passes_for_clean_files(self, tmp_path):
        """No violation is raised for ordinary text files well under the size limit."""
        (tmp_path / "module.py").write_text("print('hi')", encoding="utf-8")
        zip_path = tmp_path / "out.zip"
        zip_path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)  # minimal empty-zip EOCD

        run_guard(tmp_path, [Path("module.py")], zip_path)  # must not raise

    @pytest.mark.unit
    def test_forbidden_extension_raises(self, tmp_path):
        """A forbidden extension (.exe) fails the guard."""
        (tmp_path / "tool.exe").write_bytes(b"MZ")
        with pytest.raises(GuardError, match=r"\.exe"):
            run_guard(tmp_path, [Path("tool.exe")], tmp_path / "out.zip")

    @pytest.mark.unit
    @pytest.mark.parametrize("ext", [".dll", ".so", ".dylib", ".sh", ".bat", ".cmd"])
    def test_all_forbidden_extensions_raise(self, tmp_path, ext):
        """Every extension on the critical server blocklist fails the guard."""
        f = tmp_path / f"tool{ext}"
        f.write_bytes(b"x")
        with pytest.raises(GuardError):
            run_guard(tmp_path, [Path(f.name)], tmp_path / "out.zip")

    @pytest.mark.unit
    @pytest.mark.skipif(os.name == "nt", reason="executable bit is POSIX-only")
    def test_executable_bit_raises(self, tmp_path):
        """A file with the executable bit set fails the guard."""
        f = tmp_path / "script.py"
        f.write_text("print(1)", encoding="utf-8")
        f.chmod(f.stat().st_mode | stat.S_IXUSR)
        with pytest.raises(GuardError, match="executable bit"):
            run_guard(tmp_path, [Path("script.py")], tmp_path / "out.zip")

    @pytest.mark.unit
    def test_unexpected_binary_file_raises(self, tmp_path):
        """A binary file with a non-whitelisted extension fails the guard."""
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01\x02\x03")
        with pytest.raises(GuardError, match="binary"):
            run_guard(tmp_path, [Path("data.bin")], tmp_path / "out.zip")

    @pytest.mark.unit
    def test_allowed_binary_extensions_do_not_raise(self, tmp_path):
        """A binary .png/.qm file (the whitelisted icon/translation types) passes."""
        for name in ("icon.png", "translation.qm"):
            (tmp_path / name).write_bytes(b"\x00\x01\x02\x03")
        run_guard(tmp_path, [Path("icon.png"), Path("translation.qm")], tmp_path / "out.zip")

    @pytest.mark.unit
    def test_oversized_zip_raises(self, tmp_path):
        """A ZIP larger than the 25 MB limit fails the guard."""
        zip_path = tmp_path / "out.zip"
        with zip_path.open("wb") as fh:
            fh.seek(26 * 1024 * 1024 - 1)
            fh.write(b"\x00")
        with pytest.raises(GuardError, match="25"):
            run_guard(tmp_path, [], zip_path)

    @pytest.mark.unit
    def test_untracked_file_in_git_repo_raises(self, tmp_path):
        """A file not committed to git fails the guard.

        Regression guard for a local, gitignored CONFIG.ini (containing the
        developer's real local file paths) that the whitelist otherwise
        packaged silently, because it walks the filesystem rather than the
        git index.
        """
        _init_git_repo(tmp_path)
        (tmp_path / "tracked.py").write_text("print(1)", encoding="utf-8")
        _git(tmp_path, "add", "tracked.py")
        _git(tmp_path, "commit", "-m", "add tracked.py")
        (tmp_path / "untracked_local.ini").write_text("secret=local", encoding="utf-8")

        with pytest.raises(GuardError, match="untracked_local.ini"):
            run_guard(
                tmp_path,
                [Path("tracked.py"), Path("untracked_local.ini")],
                tmp_path / "out.zip",
            )

    @pytest.mark.unit
    def test_tracked_file_in_git_repo_passes(self, tmp_path):
        """A file committed to git does not trip the tracked-file check."""
        _init_git_repo(tmp_path)
        (tmp_path / "tracked.py").write_text("print(1)", encoding="utf-8")
        _git(tmp_path, "add", "tracked.py")
        _git(tmp_path, "commit", "-m", "add tracked.py")

        run_guard(tmp_path, [Path("tracked.py")], tmp_path / "out.zip")  # must not raise

    @pytest.mark.unit
    def test_non_git_directory_skips_tracked_file_check(self, tmp_path):
        """Outside a git repository, the tracked-file check is silently skipped."""
        (tmp_path / "module.py").write_text("print(1)", encoding="utf-8")

        run_guard(tmp_path, [Path("module.py")], tmp_path / "out.zip")  # must not raise


# ===========================================================================
# TestRunImportSmokeTest
# ===========================================================================

class TestRunImportSmokeTest:
    """Unit tests for run_import_smoke_test()."""

    @pytest.mark.unit
    def test_resolvable_absolute_import_passes(self, tmp_path):
        """An absolute `from ibtool.x import y` that resolves on disk does not raise."""
        root = tmp_path / "ibtool"
        (root / "helpers").mkdir(parents=True)
        (root / "helpers" / "logger.py").write_text("class Logger: pass", encoding="utf-8")
        (root / "ibtool_tools").mkdir()
        (root / "ibtool_tools" / "Blocker.py").write_text(
            "from ibtool.helpers.logger import Logger\n", encoding="utf-8"
        )

        run_import_smoke_test(root, "ibtool")  # must not raise

    @pytest.mark.unit
    def test_resolvable_relative_import_passes(self, tmp_path):
        """A relative `from .logger import Logger` that resolves on disk does not raise."""
        root = tmp_path / "ibtool"
        (root / "helpers").mkdir(parents=True)
        (root / "helpers" / "logger.py").write_text("class Logger: pass", encoding="utf-8")
        (root / "helpers" / "message.py").write_text(
            "from .logger import Logger\n", encoding="utf-8"
        )

        run_import_smoke_test(root, "ibtool")  # must not raise

    @pytest.mark.unit
    def test_missing_local_module_raises(self, tmp_path):
        """A local import targeting a file absent from the ZIP fails the smoke test.

        Regression guard for the 0.2.2 incident: the release exclusion list
        silently dropped helpers/debug_utils.py, breaking every tool that
        imported it, and this went unnoticed until users installed the ZIP.
        """
        root = tmp_path / "ibtool"
        (root / "ibtool_tools").mkdir(parents=True)
        (root / "ibtool_tools" / "GapClose.py").write_text(
            "from ibtool.helpers.debug_utils import save_debug_layer\n", encoding="utf-8"
        )
        # Note: helpers/debug_utils.py is intentionally NOT created.

        with pytest.raises(GuardError, match="debug_utils"):
            run_import_smoke_test(root, "ibtool")

    @pytest.mark.unit
    def test_external_package_import_is_ignored(self, tmp_path):
        """Imports of external packages (qgis, scipy, networkx) are not resolved locally."""
        root = tmp_path / "ibtool"
        (root / "helpers").mkdir(parents=True)
        (root / "helpers" / "system_utils.py").write_text(
            "from qgis.core import QgsVectorLayer\nimport scipy.spatial\n", encoding="utf-8"
        )

        run_import_smoke_test(root, "ibtool")  # must not raise
