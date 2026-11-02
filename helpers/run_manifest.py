# -*- coding: utf-8 -*-
"""Run manifest ``ibtool_run.json``: one working directory = one run.

Records inputs (path + checksum), parameters, CRS and versions so that a run
can be resumed safely after a restart and its settings restored in the UI.

Copyright: (C) 2026 by Oliver Harig
License: GNU General Public License v2 or later
"""
import json
import os
import time
from typing import Dict, List, Optional

from .system_utils import compute_file_checksum

MANIFEST_NAME = "ibtool_run.json"
FORMAT_VERSION = 1

# User-facing labels (German, shown in the resume dialog)
_INPUT_LABELS = {"hu": "Gebäude-Datei", "rn": "Straßen-Datei", "part": "Partitions-Datei",
                 "aux": "Hilfslinien-Datei", "filter": "Filter-Datei"}


def build_manifest(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        inputs: Dict[str, str], params: dict, crs_authid: str, plugin_version: str,
        qgis_version: str, worker_count: int) -> dict:
    """Build a manifest; computes the checksum of every input file.

    Args:
        inputs: Paths keyed ``hu``, ``rn``, ``part``, ``aux``, ``filter``
            (an empty path gets an empty checksum).
        params: Processing parameters as entered in the UI.
        crs_authid: Target CRS, e.g. ``EPSG:25833``.
        plugin_version: IB-Tool version from metadata.txt.
        qgis_version: ``Qgis.version()`` of the running QGIS.
        worker_count: Worker processes used (informational, not compared).
    """
    return {
        "format_version": FORMAT_VERSION,
        "inputs": {key: {"path": path,
                         "checksum": compute_file_checksum(path) if path else ""}
                   for key, path in inputs.items()},
        "params": dict(params),
        "crs": crs_authid,
        "plugin_version": plugin_version,
        "qgis_version": qgis_version,
        "worker_count": worker_count,
    }


def read_manifest(workspace: str) -> Optional[dict]:
    """Read ``ibtool_run.json``; ``None`` if missing, broken or of another format."""
    path = os.path.join(workspace, MANIFEST_NAME)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and data.get("format_version") == FORMAT_VERSION:
        return data
    return None


def write_manifest(workspace: str, manifest: dict, status: str) -> None:
    """Write the manifest atomically with *status*; keeps an existing ``created``."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    previous = read_manifest(workspace) or {}
    data = dict(manifest, status=status, updated=now)
    data["created"] = previous.get("created") or manifest.get("created") or now
    path = os.path.join(workspace, MANIFEST_NAME)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def compare_manifests(stored: dict, current: dict) -> List[str]:
    """User-readable differences that forbid resuming (empty list = resume allowed).

    Ignores worker count, status, timestamps and input paths (only the
    checksums of the inputs count, so moved but unchanged files are fine).
    """
    diffs = []
    for key, label in _INPUT_LABELS.items():
        old = stored.get("inputs", {}).get(key, {}).get("checksum")
        new = current.get("inputs", {}).get(key, {}).get("checksum")
        if old != new:
            diffs.append(f"{label} geändert")
    old_params, new_params = stored.get("params", {}), current.get("params", {})
    for name in sorted(set(old_params) | set(new_params)):
        if old_params.get(name) != new_params.get(name):
            diffs.append(f"Parameter {name}: {old_params.get(name)} → {new_params.get(name)}")
    for key, label in (("crs", "Koordinatensystem"), ("qgis_version", "QGIS"),
                       ("plugin_version", "IB-Tool")):
        if stored.get(key) != current.get(key):
            diffs.append(f"{label} {stored.get(key)} → {current.get(key)}")
    return diffs


def manifest_to_ui_settings(manifest: dict) -> dict:
    """Input paths, parameters and CRS of a manifest (for restoring the UI)."""
    return {"inputs": {k: v.get("path", "") for k, v in manifest.get("inputs", {}).items()},
            "params": dict(manifest.get("params", {})), "crs": manifest.get("crs")}
