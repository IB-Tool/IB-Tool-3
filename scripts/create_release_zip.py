#!/usr/bin/env python3
"""Create a QGIS plugin release ZIP.

Usage:
    python scripts/create_release_zip.py

Output:
    dist/ibtool.zip

The script reads the version from metadata.txt (for the printed summary only —
the version is not part of the ZIP filename or the internal folder name),
collects every file listed in the whitelist below, packages them under the
constant folder name ibtool/ inside the ZIP, and runs a guard that fails the
build on anything the plugins.qgis.org security scan would reject. The ZIP
filename and internal folder name never change between versions, so the
download link and install steps stay identical release to release.

Run from the repository root.
"""
from __future__ import annotations

import ast
import configparser
import stat
import subprocess  # nosec B404 — used only for `git ls-files` with fixed args, no shell
import sys
import tempfile
import zipfile
from pathlib import Path

PLUGIN_FOLDER = "ibtool"

# ---------------------------------------------------------------------------
# Whitelist — the authoritative source of truth for what ships in the release
# ---------------------------------------------------------------------------
# Root-level files shipped as-is.
WHITELIST_FILES = {
    "__init__.py",
    "metadata.txt",
    "icon.png",
    "LICENSE",
    "README.md",
    "requirements.txt",
    "resources.qrc",
}

# Top-level directories shipped wholesale (minus __pycache__/*.pyc, see below).
WHITELIST_DIRS = {
    "helpers",
    "i18n",
    "ibtool",
    "ibtool_tools",
}

_COMPILED_PY_EXTENSIONS = {".pyc", ".pyo"}


def is_included(rel: Path) -> bool:
    """Decide whether a repository-relative path ships in the release ZIP.

    Args:
        rel: Path relative to the repository root.

    Returns:
        True if the file is part of the whitelist and not a compiled-Python
        byproduct.
    """
    parts = rel.parts

    if len(parts) == 1:
        return parts[0] in WHITELIST_FILES

    if parts[0] not in WHITELIST_DIRS:
        return False

    if "__pycache__" in parts:
        return False

    if rel.suffix.lower() in _COMPILED_PY_EXTENSIONS:
        return False

    return True


def read_version(repo_root: Path) -> str:
    meta_path = repo_root / "metadata.txt"
    if not meta_path.exists():
        raise FileNotFoundError(f"metadata.txt not found at {meta_path}")
    parser = configparser.ConfigParser()
    # metadata.txt has a [general] section
    parser.read(str(meta_path), encoding="utf-8")
    try:
        return parser["general"]["version"].strip()
    except KeyError:
        raise ValueError("version key not found in metadata.txt [general]")


def collect_files(repo_root: Path) -> list[Path]:
    collected = []
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(repo_root)
        except ValueError:
            continue
        if is_included(rel):
            collected.append(rel)
    return collected


def build_zip(repo_root: Path, files: list[Path], zip_path: Path, plugin_folder: str) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            arcname = f"{plugin_folder}/{rel.as_posix()}"
            zf.write(repo_root / rel, arcname)
            print(f"  + {arcname}")


# ---------------------------------------------------------------------------
# Guard — fails the build on anything the server security scan would reject
# ---------------------------------------------------------------------------

MAX_ZIP_SIZE_BYTES = 25 * 1024 * 1024

FORBIDDEN_EXTENSIONS = {".exe", ".dll", ".so", ".dylib", ".sh", ".bat", ".cmd"}

# Binary files that are intentionally shipped: the plugin icon and compiled
# Qt translations. Any other binary file is treated as a build error.
ALLOWED_BINARY_EXTENSIONS = {".png", ".qm"}


class GuardError(RuntimeError):
    """Raised when the release ZIP fails a packaging safety check."""


def _is_binary(path: Path) -> bool:
    """Heuristically detect binary content via a null-byte scan."""
    with open(path, "rb") as fh:
        chunk = fh.read(8192)
    return b"\x00" in chunk


def _git_tracked_files(repo_root: Path) -> set[Path] | None:
    """Return the set of git-tracked files (repo-relative), or None if git is unavailable.

    None means "could not determine" (no git, or repo_root is not a git
    repository) — callers must skip the tracked-file check in that case
    rather than fail the whole build over a missing secondary safety net.
    """
    try:
        result = subprocess.run(  # nosec B603, B607 — fixed args, no shell, git is a build-time dependency
            ["git", "ls-files"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return {Path(line) for line in result.stdout.splitlines() if line}


def run_guard(repo_root: Path, files: list[Path], zip_path: Path) -> None:
    """Fail the build if the packaged content would trip the server scan.

    Checks forbidden extensions, the executable bit, unexpected binary
    files, the overall ZIP size limit, and — whenever repo_root is a git
    checkout — that every packaged file is actually committed. The last
    check exists because the whitelist walks the real filesystem: a local,
    gitignored file sitting inside a whitelisted directory (e.g. a
    developer's untracked CONFIG.ini) would otherwise ship silently.

    Raises:
        GuardError: Listing every violation found.
    """
    violations = []
    tracked = _git_tracked_files(repo_root)

    for rel in files:
        suffix = rel.suffix.lower()
        if suffix in FORBIDDEN_EXTENSIONS:
            violations.append(f"forbidden extension {suffix}: {rel.as_posix()}")

        abs_path = repo_root / rel
        mode = abs_path.stat().st_mode
        if mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            violations.append(f"executable bit set: {rel.as_posix()}")

        if suffix not in ALLOWED_BINARY_EXTENSIONS and _is_binary(abs_path):
            violations.append(f"unexpected binary file: {rel.as_posix()}")

        if tracked is not None and rel not in tracked:
            violations.append(f"untracked file would ship (not committed to git): {rel.as_posix()}")

    if zip_path.exists():
        size = zip_path.stat().st_size
        if size > MAX_ZIP_SIZE_BYTES:
            violations.append(
                f"ZIP exceeds {MAX_ZIP_SIZE_BYTES / 1024 / 1024:.0f} MB limit: "
                f"{size / 1024 / 1024:.2f} MB"
            )

    if violations:
        details = "\n".join(f"  - {v}" for v in violations)
        raise GuardError(f"Release guard failed:\n{details}")


# ---------------------------------------------------------------------------
# Smoke test — statically verifies every local import resolves inside the ZIP
# ---------------------------------------------------------------------------

def _resolve_local_import(
    module: str, level: int, importing_file: Path, extracted_root: Path, plugin_folder: str
) -> Path | None:
    """Resolve a from-import to a file path inside the extracted ZIP.

    Returns:
        The resolved path if the import targets the plugin package (absolute
        `ibtool.x.y` or any relative import), or None if it targets an
        external package (e.g. `qgis`, `scipy`) and should be skipped.
    """
    if level > 0:
        # Relative import: resolve against the importing file's package dir.
        base = importing_file.parent
        for _ in range(level - 1):
            base = base.parent
        target = base if not module else base / Path(*module.split("."))
    elif module == plugin_folder or module.startswith(f"{plugin_folder}."):
        parts = module.split(".")[1:]  # drop the leading "ibtool"
        target = extracted_root if not parts else extracted_root / Path(*parts)
    else:
        return None  # external package (qgis, scipy, networkx, ...)

    if target.with_suffix(".py").is_file():
        return target.with_suffix(".py")
    if (target / "__init__.py").is_file():
        return target / "__init__.py"
    return target  # unresolved — caller reports as missing


def run_import_smoke_test(extracted_root: Path, plugin_folder: str) -> None:
    """Statically verify that every local import in the extracted ZIP resolves.

    Parses every .py file with ast (no runtime import — qgis is not available
    outside QGIS) and checks that each `from ibtool...` / relative import
    target exists on disk. Guards against a repeat of the 0.2.2 incident,
    where the exclusion list silently dropped helpers/debug_utils.py.

    Raises:
        GuardError: Listing every unresolved local import found.
    """
    missing = []
    for py_file in sorted(extracted_root.rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8-sig"), filename=str(py_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            resolved = _resolve_local_import(module, node.level, py_file, extracted_root, plugin_folder)
            if resolved is None:
                continue
            if not resolved.exists():
                rel_importer = py_file.relative_to(extracted_root)
                missing.append(f"{rel_importer.as_posix()}: from {'.' * node.level}{module} import ... -> {resolved}")

    if missing:
        details = "\n".join(f"  - {m}" for m in missing)
        raise GuardError(f"Unresolved local imports in release ZIP:\n{details}")


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent

    version = read_version(repo_root)
    zip_name = f"{PLUGIN_FOLDER}.zip"
    zip_path = repo_root / "dist" / zip_name

    print(f"Plugin:  {PLUGIN_FOLDER}")
    print(f"Version: {version}")
    print(f"Output:  {zip_path}")
    print()

    files = collect_files(repo_root)
    print(f"Packaging {len(files)} files:")
    build_zip(repo_root, files, zip_path, PLUGIN_FOLDER)

    print()
    print("Running release guard...")
    try:
        run_guard(repo_root, files, zip_path)
    except GuardError as exc:
        zip_path.unlink(missing_ok=True)
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    print("Guard passed.")

    print()
    print("Running import smoke test...")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp_path)
        try:
            run_import_smoke_test(tmp_path / PLUGIN_FOLDER, PLUGIN_FOLDER)
        except GuardError as exc:
            zip_path.unlink(missing_ok=True)
            print(str(exc), file=sys.stderr)
            sys.exit(1)
    print("Smoke test passed.")

    print()
    print(f"Created {zip_path}")


if __name__ == "__main__":
    main()
