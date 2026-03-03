#!/usr/bin/env python3
'''QGIS Plugin preflight validator (structure + metadata).

Usage examples:
  python ci/qgis_plugin_validate.py --plugin-dir path/to/plugin
  python ci/qgis_plugin_validate.py --zip dist/MyPlugin.1.2.3.zip

Exit codes:
  0 = ok
  2 = validation failed
'''
from __future__ import annotations

import argparse
import configparser
import io
import os
import re
import sys
import zipfile
from pathlib import Path


FOLDER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")

REQUIRED_FILES = [
    "metadata.txt",
    "__init__.py",
    "LICENSE",
]

REQUIRED_METADATA_KEYS = [
    "name",
    "description",
    "version",
    "qgisMinimumVersion",
    "author",
    "email",
    "about",
    "homepage",
    "tracker",
    "repository",
    "license",
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(2)


def warn(msg: str) -> None:
    print(f"WARN: {msg}")


def ok(msg: str) -> None:
    print(f"OK: {msg}")


def parse_metadata_text(text: str) -> dict[str, str]:
    # metadata.txt uses INI-like format, but often without sections.
    # QGIS accepts it as a simple key=value file.
    # We'll parse with a fallback approach.
    data: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip()
    return data


def validate_plugin_dir(plugin_dir: Path) -> None:
    if not plugin_dir.exists() or not plugin_dir.is_dir():
        fail(f"plugin-dir not found or not a directory: {plugin_dir}")

    folder = plugin_dir.name
    if not FOLDER_RE.match(folder):
        fail(f"invalid plugin folder name '{folder}'. Must match: {FOLDER_RE.pattern}")
    ok(f"folder name valid: {folder}")

    for fname in REQUIRED_FILES:
        p = plugin_dir / fname
        if not p.exists():
            fail(f"missing required file: {p}")
    ok("required files present")

    # LICENSE filename exact check already by existence.
    if (plugin_dir / "LICENSE").exists() or (plugin_dir / "license").exists():
        warn("found LICENSE-like files; repository expects file named exactly 'LICENSE' (no extension).")

    meta_path = plugin_dir / "metadata.txt"
    meta_text = meta_path.read_text(encoding="utf-8", errors="replace")
    meta = parse_metadata_text(meta_text)

    missing = [k for k in REQUIRED_METADATA_KEYS if k not in meta or not meta[k].strip()]
    if missing:
        fail(f"metadata.txt missing/empty keys: {', '.join(missing)}")
    ok("metadata.txt required keys present")

    # Basic URL sanity checks (not strict)
    for k in ("homepage", "tracker", "repository"):
        v = meta.get(k, "")
        if v and not (v.startswith("http://") or v.startswith("https://")):
            warn(f"metadata key '{k}' does not look like a URL: {v}")

    # Version sanity
    version = meta.get("version", "")
    if version and not re.match(r"^[0-9A-Za-z.\-_+]+$", version):
        warn(f"version contains unusual characters: {version}")

    # Optional but useful
    if "icon" not in meta:
        warn("metadata.txt has no 'icon' key (best practice).")
    if len(meta.get("description", "")) < 10:
        warn("description is very short; consider a clearer English description.")


def validate_zip(zip_path: Path) -> None:
    if not zip_path.exists():
        fail(f"zip not found: {zip_path}")
    if zip_path.suffix.lower() != ".zip":
        warn("file does not end with .zip; continuing anyway.")

    with zipfile.ZipFile(zip_path, "r") as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        top_levels = set(n.split("/", 1)[0] for n in names if "/" in n)
        if len(top_levels) != 1:
            fail(f"zip must contain exactly one top-level plugin folder. Found: {sorted(top_levels)}")

        plugin_folder = next(iter(top_levels))
        if not FOLDER_RE.match(plugin_folder):
            fail(f"invalid plugin folder name in zip '{plugin_folder}'")

        ok(f"zip top-level folder: {plugin_folder}")

        def has(path: str) -> bool:
            return path in names

        for fname in REQUIRED_FILES:
            inner = f"{plugin_folder}/{fname}"
            if not has(inner):
                fail(f"missing required file in zip: {inner}")
        ok("required files present in zip")

        # Read metadata.txt
        meta_bytes = z.read(f"{plugin_folder}/metadata.txt")
        meta_text = meta_bytes.decode("utf-8", errors="replace")
        meta = parse_metadata_text(meta_text)

        missing = [k for k in REQUIRED_METADATA_KEYS if k not in meta or not meta[k].strip()]
        if missing:
            fail(f"metadata.txt missing/empty keys: {', '.join(missing)}")
        ok("metadata.txt required keys present (zip)")

        # Warn on suspicious filetypes (very simple heuristic)
        suspicious_ext = {".exe", ".dll", ".so", ".dylib"}
        found_susp = [n for n in names if Path(n).suffix.lower() in suspicious_ext]
        if found_susp:
            warn(f"zip contains binary-looking files: {found_susp[:10]}{'...' if len(found_susp)>10 else ''}")


def auto_detect_plugin_dir(repo_root: Path) -> Path | None:
    # Look for a directory that contains metadata.txt at depth <= 3, excluding common dirs
    skip = {".git", ".github", "__pycache__", "venv", ".venv", "dist", "build"}
    for p in repo_root.rglob("metadata.txt"):
        try:
            rel = p.relative_to(repo_root)
        except ValueError:
            continue
        parts = rel.parts
        if any(part in skip for part in parts):
            continue
        # plugin folder is parent of metadata.txt
        plugin_dir = p.parent
        # avoid nested metadata in docs
        if plugin_dir.is_dir() and (plugin_dir / "__init__.py").exists():
            return plugin_dir
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugin-dir", type=Path, default=None, help="Path to the plugin folder (contains metadata.txt)")
    ap.add_argument("--zip", type=Path, nargs="+", default=None, help="Path(s) to release zip(s)")
    ap.add_argument("--auto", action="store_true", help="Auto-detect plugin dir in repository (default if none provided)")
    args = ap.parse_args()

    if args.zip:
        for zip_path in args.zip:
            print(f"\n--- {zip_path} ---")
            validate_zip(zip_path)
            ok("validation finished")
        return

    plugin_dir = args.plugin_dir
    if plugin_dir is None:
        repo_root = Path(".").resolve()
        plugin_dir = auto_detect_plugin_dir(repo_root)
        if plugin_dir is None:
            fail("could not auto-detect plugin dir. Provide --plugin-dir explicitly.")
        ok(f"auto-detected plugin dir: {plugin_dir}")

    validate_plugin_dir(Path(plugin_dir))
    ok("validation finished")


if __name__ == "__main__":
    main()
