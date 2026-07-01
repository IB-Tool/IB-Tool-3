#!/usr/bin/env python3
"""Create a QGIS plugin release ZIP.

Usage:
    python scripts/create_release_zip.py

Output:
    dist/IB-Tool-3.<version>.zip

The script reads the version from metadata.txt, collects all productive plugin
files (applying the exclusion list), and packages them under the folder name
IB-Tool-3/ inside the ZIP.

Run from the repository root.
"""
from __future__ import annotations

import configparser
import os
import zipfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Exclusion rules
# ---------------------------------------------------------------------------

EXCLUDED_DIRS = {
    "test",
    "Testdaten",
    "ai",
    "ci",
    "docs",
    ".github",
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    "dist",
    "venv",
    ".venv",
    "env",
    ".eggs",
    "logs",
    "scripts",
    "help",
    "build",
    "htmlcov",
}

EXCLUDED_FILES = {
    "CLAUDE.md",
    "plugin_upload.py",
    "pytest.ini",
    "codecov.yml",
    "Dockerfile",
    "Makefile",
    "compile.bat",
    "pb_tool.cfg",
    "test_import_mst.py",
    "IB-Tool2.py",
    ".gitignore",
    ".gitattributes",
    ".secrets.baseline",
    ".flake8",
    ".bandit",
    "CONFIG.ini",
    ".DS_Store",
    "Thumbs.db",
    "Desktop.ini",
    "nul",
}

EXCLUDED_FILE_PATTERNS = (
    "- Kopie",
    "_kopie",
    "_original_backup",
)

EXCLUDED_FILE_PREFIXES = (
    "debug_",
)

EXCLUDED_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".iml",
    ".iws",
    ".ipr",
    ".egg-info",
    ".egg",
    ".so",
    ".log",
}


def is_excluded(rel: Path) -> bool:
    parts = rel.parts

    # Any path component is an excluded directory
    for part in parts[:-1]:
        if part in EXCLUDED_DIRS:
            return True
        if part.startswith("."):
            return True
        if part.endswith(".egg-info"):
            return True

    filename = parts[-1]

    # Excluded by exact filename
    if filename in EXCLUDED_FILES:
        return True

    # Excluded by filename prefix (e.g. debug_*.py)
    if filename.startswith(EXCLUDED_FILE_PREFIXES):
        return True

    # Excluded by filename substring (e.g. backup/copy files)
    if any(pattern in filename for pattern in EXCLUDED_FILE_PATTERNS):
        return True

    # Excluded by extension
    suffix = Path(filename).suffix.lower()
    if suffix in EXCLUDED_EXTENSIONS:
        return True

    # Hidden files (dotfiles) other than those explicitly included
    if filename.startswith("."):
        return True

    # __pycache__ directories (caught above, but also as file path component)
    if "__pycache__" in parts:
        return True

    return False


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
        if not is_excluded(rel):
            collected.append(rel)
    return collected


def build_zip(repo_root: Path, files: list[Path], zip_path: Path, plugin_folder: str) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            arcname = f"{plugin_folder}/{rel.as_posix()}"
            zf.write(repo_root / rel, arcname)
            print(f"  + {arcname}")


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    plugin_folder = repo_root.name  # IB-Tool-3

    version = read_version(repo_root)
    zip_name = f"{plugin_folder}.{version}.zip"
    zip_path = repo_root / "dist" / zip_name

    print(f"Plugin:  {plugin_folder}")
    print(f"Version: {version}")
    print(f"Output:  {zip_path}")
    print()

    files = collect_files(repo_root)
    print(f"Packaging {len(files)} files:")
    build_zip(repo_root, files, zip_path, plugin_folder)

    print()
    print(f"Created {zip_path}")


if __name__ == "__main__":
    main()
