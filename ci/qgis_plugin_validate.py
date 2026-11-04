#!/usr/bin/env python3
'''QGIS Plugin preflight validator (structure + metadata).

Rules follow https://plugins.qgis.org/docs/publish, /docs/approval and
/docs/migrate-qgis4: required metadata, license file, package <= 25 MB, no
binaries, no hidden or generated files, a changelog entry for the current
version, and the QGIS 4 range (qgisMaximumVersion >= 4.0, no supportsQt6).

Usage examples:
  python ci/qgis_plugin_validate.py --auto
  python ci/qgis_plugin_validate.py --plugin-dir path/to/plugin
  python ci/qgis_plugin_validate.py --zip dist/ibtool.zip
  python ci/qgis_plugin_validate.py --zip dist/ibtool.zip --release
      (--release: the version must also be newer than every git tag v*)

Exit codes:
  0 = ok
  2 = validation failed
'''
from __future__ import annotations

import argparse
import subprocess  # nosec B404 - only runs 'git tag' with fixed arguments
import re
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

# plugins.qgis.org: "The plugin package must not exceed 25MB"
MAX_ZIP_BYTES = 25 * 1024 * 1024
# plugins.qgis.org: "Do not include binaries"
BINARY_EXTENSIONS = {".exe", ".dll", ".so", ".dylib", ".pyd", ".bin", ".msi", ".jar", ".class"}
# Generated files must not be shipped (publish docs, "Tips and Tricks")
GENERATED_EXTENSIONS = {".pyc", ".pyo"}
GENERATED_DIRS = {"__pycache__", "__MACOSX"}
# Listing for QGIS 4 requires qgisMaximumVersion >= 4.0 (migrate-qgis4 docs)
MIN_QGIS_MAXIMUM = (4, 0)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(2)


def warn(msg: str) -> None:
    print(f"WARN: {msg}")


def ok(msg: str) -> None:
    print(f"OK: {msg}")


def parse_metadata_text(text: str) -> dict[str, str]:
    """Parse metadata.txt like QGIS (INI): key=value, indented lines continue the previous value.

    Sections are optional. Continuation lines are joined with newlines, so a
    multi-line ``changelog`` stays one value even if an entry contains '='.
    """
    data: dict[str, str] = {}
    last_key = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if raw[:1] in (" ", "\t") and last_key is not None:
            data[last_key] += "\n" + line
            continue
        if line.startswith("[") and line.endswith("]"):
            last_key = None
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        last_key = k.strip()
        data[last_key] = v.strip()
    return data


def _version_tuple(text: str) -> tuple:
    """Sort key for versions such as '0.2.5', 'v0.2.2-beta', '4.99'.

    Numeric parts compare numerically; a pre-release suffix ('-beta') sorts
    before the plain version.
    """
    text = text.strip().lstrip("vV")
    core, _, suffix = text.partition("-")
    numbers = tuple(int(p) for p in re.findall(r"\d+", core))
    return numbers + ((0,) if suffix else (1,))


def check_metadata_rules(meta: dict[str, str]) -> None:
    """Repository rules beyond the required keys (fails on the first violation)."""
    if "supportsQt6" in meta:
        fail("metadata.txt contains 'supportsQt6' - the flag is no longer recognised; "
             "QGIS 4 support is declared by qgisMaximumVersion (remove the key)")

    maximum = meta.get("qgisMaximumVersion", "").strip()
    if not maximum:
        fail("metadata.txt has no qgisMaximumVersion - without it the plugin is only "
             "listed for the major version of qgisMinimumVersion (set 4.99)")
    if _version_tuple(maximum)[:2] < MIN_QGIS_MAXIMUM:
        fail(f"qgisMaximumVersion={maximum} excludes QGIS 4 (needs >= 4.0, e.g. 4.99)")
    ok(f"QGIS range {meta.get('qgisMinimumVersion', '?')}-{maximum} includes QGIS 4")

    version = meta.get("version", "").strip()
    changelog = meta.get("changelog", "")
    if not changelog.strip():
        fail("metadata.txt has no changelog (required for every update)")
    if not re.search(r"(?<![\d.])" + re.escape(version) + r"(?!\.?\d)", changelog):
        fail(f"changelog has no entry for the current version {version}")
    ok(f"changelog mentions version {version}")


def check_version_is_new(version: str, tags: list[str]) -> None:
    """Fail unless *version* is newer than every released tag (``v*``)."""
    released = [t for t in tags if t.strip()]
    if not released:
        ok(f"version {version}: no earlier release tags")
        return
    latest = max(released, key=_version_tuple)
    if _version_tuple(version) <= _version_tuple(latest):
        fail(f"version {version} is not newer than the latest release tag {latest} "
             "(every upload needs a new version number)")
    ok(f"version {version} is newer than {latest}")


def git_release_tags(repo: Path) -> list[str]:
    """Release tags (``v*``) of the git repository at *repo*."""
    result = subprocess.run(  # nosec B603 B607 - fixed git command, no user input
        ["git", "tag", "--list", "v*"], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout.split()


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
    if not (plugin_dir / "LICENSE").exists() and (
        (plugin_dir / "license").exists() or list(plugin_dir.glob("LICENSE*"))
    ):
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

    check_metadata_rules(meta)


def validate_zip(zip_path: Path) -> dict[str, str]:
    if not zip_path.exists():
        fail(f"zip not found: {zip_path}")
    if zip_path.suffix.lower() != ".zip":
        warn("file does not end with .zip; continuing anyway.")

    size = zip_path.stat().st_size
    if size > MAX_ZIP_BYTES:
        fail(f"zip is {size / 1024 / 1024:.1f} MB; plugins.qgis.org accepts at most 25 MB")
    ok(f"zip size {size / 1024:.0f} KB (limit 25 MB)")

    with zipfile.ZipFile(zip_path, "r") as z:
        names = [n for n in z.namelist() if not n.endswith("/")]

        hidden = [n for n in names if any(part.startswith(".") for part in n.split("/"))]
        if hidden:
            fail(f"zip contains hidden files/folders: {hidden[:10]}")
        generated = [n for n in names
                     if Path(n).suffix.lower() in GENERATED_EXTENSIONS
                     or any(part in GENERATED_DIRS for part in n.split("/"))]
        if generated:
            fail(f"zip contains generated files: {generated[:10]}")
        binaries = [n for n in names if Path(n).suffix.lower() in BINARY_EXTENSIONS]
        if binaries:
            fail(f"zip contains binaries (not accepted by plugins.qgis.org): {binaries[:10]}")
        ok("no hidden, generated or binary files in zip")
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

        check_metadata_rules(meta)
    return meta


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
    ap.add_argument("--plugin-dir", type=Path, default=None,
                    help="Path to the plugin folder (contains metadata.txt)")
    ap.add_argument("--zip", type=Path, nargs="+", default=None, help="Path(s) to release zip(s)")
    ap.add_argument("--auto", action="store_true",
                    help="Auto-detect plugin dir in repository (default if none provided)")
    ap.add_argument("--release", action="store_true",
                    help="Release check: version must be newer than every git tag v* (use before uploading)")
    args = ap.parse_args()

    if args.zip:
        for zip_path in args.zip:
            print(f"\n--- {zip_path} ---")
            meta = validate_zip(zip_path)
            if args.release:
                check_version_is_new(meta.get("version", ""), git_release_tags(Path(".")))
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
