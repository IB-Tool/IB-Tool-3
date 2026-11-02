# -*- coding: utf-8 -*-
"""Integration tests: run the real worker program on sample data."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from qgis import processing  # noqa: E402  (Processing is initialised by test/__init__.py)
from qgis.core import QgsApplication, QgsCoordinateReferenceSystem  # noqa: E402

from ibtool.helpers import worker_protocol as wp  # noqa: E402
from ibtool.helpers.geometry_utils import load_to_geopackage  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "Testdaten"


def _prepare_inputs(ws):
    """Load sample data into GPKGs like IBTool does (incl. aux_line)."""
    crs = QgsCoordinateReferenceSystem("EPSG:25833")
    out = {}
    for key, name in (("hu", "A_HU"), ("rn", "A_RN"), ("part", "A_PART"), ("aux", "A_AUX")):
        out[key] = str(ws / f"layer_{key}.gpkg")
        load_to_geopackage(str(DATA / f"{name}.shp"), out[key], f"layer_{key}", crs)
    processing.run("qgis:mergevectorlayers", {"LAYERS": [out["aux"], out["rn"]], "CRS": crs,
                                              "OUTPUT": str(ws / "layer_aux_line.gpkg")})
    out["aux_line"] = str(ws / "layer_aux_line.gpkg")
    return out


def _run_worker(ws, partitions):
    inputs = _prepare_inputs(ws)
    init = wp.init_message(
        plugin_root=str(ROOT), sys_path=[p for p in sys.path if p],
        prefix_path=QgsApplication.prefixPath(),
        inputs=inputs, crs="EPSG:25833",
        params={"min_overlap_blocks": 18.0, "global_footprint_density": 0.0, "min_area": 57.0,
                "min_bdg_count": 20, "min_patch_size": 10000.0, "max_hole_size": 10000.0,
                "max_gap_size": 4900.0, "part_start": -1, "part_end": -1,
                "input_filter": str(DATA / "IB-Tool2_Filter.txt")},
        workspace=str(ws) + "/", results_dir=str(ws / "IB_Tool_Results"), debug_mode=False,
        global_density=15.701401805626455, log_level="CRITICAL", parent_pid=os.getpid())
    commands = [wp.encode_command(init)] \
        + [wp.encode_command(wp.run_message(p)) for p in partitions] \
        + [wp.encode_command(wp.exit_message())]
    proc = subprocess.run([sys.executable, "-u", str(ROOT / "ibtool" / "partition_worker.py")],
                          input=b"".join(commands), capture_output=True, timeout=600,
                          check=False)
    events = [wp.parse_line(line)
              for line in proc.stdout.decode("utf-8", "replace").splitlines()]
    return proc, [e for e in events if e]


@pytest.mark.integration
@pytest.mark.slow
def test_worker_processes_partitions(tmp_path):
    proc, events = _run_worker(tmp_path, ["PART_9", "PART_1"])
    types = [e["type"] for e in events]
    assert types and types[0] == "ready", proc.stderr.decode(errors="replace")[-2000:]
    done = {e["partition"]: e for e in events if e["type"] == "done"}
    assert done["PART_9"]["result"] == "parts/PART_9.gpkg" and done["PART_9"]["features"] >= 1
    assert done["PART_1"]["result"] is None                       # < 10 buildings -> skipped
    assert (tmp_path / "IB_Tool_Results" / "parts" / "PART_9.gpkg").is_file()
    assert any(e["type"] == "progress" and e["partition"] == "PART_9" for e in events)
    assert proc.returncode == 0


@pytest.mark.integration
@pytest.mark.slow
def test_worker_handles_path_with_space_and_umlaut(tmp_path):
    ws = tmp_path / "IB Läufe" / "Testlauf 1"
    ws.mkdir(parents=True)
    proc, events = _run_worker(ws, ["PART_9"])
    assert [e["type"] for e in events if e["type"] in ("ready", "done")] == ["ready", "done"], \
        proc.stderr.decode(errors="replace")[-2000:]


@pytest.mark.integration
def test_worker_exits_on_empty_stdin():
    proc = subprocess.run([sys.executable, "-u", str(ROOT / "ibtool" / "partition_worker.py")],
                          input=b"", capture_output=True, timeout=60, check=False)
    assert proc.returncode == 1
