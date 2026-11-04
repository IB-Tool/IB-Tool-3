"""Headless profiling of the IB-Tool partition pipeline.

Mirrors ``IBTool._run_partition_pipeline`` (ibtool/ibtool.py) without the GUI,
prints per-step wall-clock times plus a cProfile summary, and writes the merged
result to ``<out>/result.gpkg`` so runs before/after an optimisation can be
compared geometrically.

Run with the QGIS Python (Windows example):

    "C:\\Program Files\\QGIS 3.40.0\\bin\\python-qgis.bat" scripts\\profile_pipeline.py ^
        --data Testdaten --out %TEMP%\\ibtool_prof --parts 10 > prof.txt 2>&1

Not part of the plugin package (development tool only).
"""
import argparse
import cProfile
import os
import pstats
import shutil
import sys
import time
import types
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("--data", default=str(PLUGIN / "Testdaten"),
                help="Folder with *HU*, *RN*, *AUX*, *PART* (.shp or .gpkg) and filter file")
ap.add_argument("--filter", default=None, help="Filter file (default: <data>/IB-Tool2_Filter.txt)")
ap.add_argument("--out", required=True, help="Workspace/output folder")
ap.add_argument("--crs", default="EPSG:25833")
ap.add_argument("--parts", type=int, default=0, help="Process only the first N partitions (0 = all)")
ap.add_argument("--only", default=None,
                help="Comma-separated partition names to process (e.g. PART_64)")
ap.add_argument("--no-cprofile", action="store_true", help="Only phase timings, no cProfile")
ap.add_argument("--heartbeat-stats", action="store_true",
                help="Report the longest gap between UI heartbeats (= longest time the "
                     "plugin window would not respond)")
ap.add_argument("--workers", type=int, default=1,
                help="Worker processes (1 = in this process, like the sequential plugin path)")
ap.add_argument("--resume", action="store_true",
                help="Keep part files and finish log of <out> and skip finished partitions")
args = ap.parse_args()

DATA = Path(args.data)
OUT = Path(args.out)
OUT.mkdir(parents=True, exist_ok=True)

from qgis.core import (  # noqa: E402
    QgsApplication, QgsCoordinateReferenceSystem, QgsProcessing, QgsVectorFileWriter,
    QgsCoordinateTransformContext,
)
QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", ""), True)
app = QgsApplication([], False)
app.initQgis()
sys.path.append(os.path.join(os.environ.get("QGIS_PREFIX_PATH", ""), "python", "plugins"))
from processing.core.Processing import Processing  # noqa: E402
Processing.initialize()
from qgis import processing  # noqa: E402

# Make the plugin folder importable as package 'ibtool' (same trick as test/conftest.py)
_pkg = types.ModuleType("ibtool")
_pkg.__path__ = [str(PLUGIN)]
sys.modules["ibtool"] = _pkg

from ibtool.helpers.logger import Logger  # noqa: E402
from ibtool.helpers.processing_context import (  # noqa: E402
    current_processing_context, shared_processing_context, ui_heartbeat)
from ibtool.helpers.geometry_utils import load_to_geopackage  # noqa: E402
from ibtool.helpers.data_loader import create_partitions_list  # noqa: E402
from ibtool.helpers import partition_pipeline  # noqa: E402
from ibtool.helpers import partition_results as pr  # noqa: E402
from ibtool.helpers.geometry_utils import create_empty_layer  # noqa: E402
from ibtool.helpers.system_utils import save_temp_layer_to_gpkg  # noqa: E402
from ibtool.helpers.worker_launcher import find_worker_command  # noqa: E402
from ibtool.helpers.worker_pool import WorkerPool  # noqa: E402
from ibtool.ibtool_tools.FootprintDensity import calc_footprint_density  # noqa: E402
from qgis.core import QgsVectorLayer  # noqa: E402
from qgis.PyQt.QtCore import QEventLoop  # noqa: E402

try:
    Logger.set_log_level("CRITICAL")
except Exception:  # pylint: disable=broad-except
    pass

crs = QgsCoordinateReferenceSystem(args.crs)
ws = str(OUT) + "/"
# Defaults as in CONFIG.ini / parameterization.md
P = dict(min_overlap_blocks=18.0, min_area=57.0, min_bdg_count=20, min_patch_size=10000.0,
         max_hole_size=10000.0, max_gap_size=4900.0)
FILTER = args.filter or str(DATA / "IB-Tool2_Filter.txt")

TIMES = {}
RESULTS = OUT / "IB_Tool_Results"
LOG_FIN = str(RESULTS / "IB_Tool2_Log_Fin.txt")


def timed(name, fn, *a, **k):
    t = time.perf_counter()
    r = fn(*a, **k)
    TIMES[name] = TIMES.get(name, 0) + time.perf_counter() - t
    return r


def pick(key):
    for ext in ("shp", "gpkg"):
        hits = sorted(DATA.glob(f"*{key}*.{ext}"))
        if hits:
            return str(hits[0])
    raise FileNotFoundError(f"No *{key}*.shp/.gpkg in {DATA}")


def merge(layers):
    return processing.run("qgis:mergevectorlayers", {
        'LAYERS': layers, 'CRS': crs, 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT},
        context=current_processing_context())['OUTPUT']


def main():
    t0 = time.perf_counter()
    # Shared processing contexts as in IBTool.start_processing(): load, global
    # density, and one per partition.
    with shared_processing_context():
        rn = load_to_geopackage(pick("RN"), ws + "layer_rn.gpkg", "layer_rn", crs)
        aux = load_to_geopackage(pick("AUX"), ws + "layer_aux.gpkg", "layer_aux", crs)
        part = load_to_geopackage(pick("PART"), ws + "layer_part.gpkg", "layer_part", crs)
        hu = load_to_geopackage(pick("HU"), ws + "layer_hu.gpkg", "layer_hu", crs)
        aux_line_file = save_temp_layer_to_gpkg(merge([aux, rn]), "layer_aux_line", ws)
        aux_line = QgsVectorLayer(aux_line_file, "aux_layers_line", "ogr")   # as the plugin
    TIMES["00_load"] = time.perf_counter() - t0
    print("HU", hu.featureCount(), "RN", rn.featureCount(), "PART", part.featureCount(), flush=True)

    with shared_processing_context():
        gfd = timed("00_global_density", calc_footprint_density, hu, rn, 100, 0, 'global', 20, part)
    parts = [str(n) for n in create_partitions_list(part, ["#"], -1, -1)]
    if args.parts:
        parts = parts[:args.parts]
    if args.only:
        wanted = [n.strip() for n in args.only.split(",")]
        parts = [n for n in parts if n in wanted]

    if not args.resume and RESULTS.exists():
        shutil.rmtree(RESULTS)
    RESULTS.mkdir(parents=True, exist_ok=True)
    pr.cleanup_temporary(str(RESULTS))
    valid, recompute = pr.validate_finished(str(RESULTS), pr.read_finished(LOG_FIN))
    todo = [n for n in parts if n not in valid]
    print(f"to do: {len(todo)} of {len(parts)} partitions (recompute: {recompute})", flush=True)

    if args.workers > 1 and len(todo) > 1:
        todo = run_parallel(todo, part, hu, rn, aux_line_file, gfd)    # returns recompute list
    for name in todo:
        with shared_processing_context():
            run_partition(name, part, hu, rn, aux_line, gfd)
    TIMES["99_TOTAL"] = time.perf_counter() - t0
    finished = pr.read_finished(LOG_FIN)
    order = [n for n in finished if n not in set(parts)] + parts
    base = create_empty_layer("global_merge_layer", "Polygon", crs.authid())
    return pr.merge_results(str(RESULTS), order, finished, base, crs)


def run_parallel(todo, part, hu, rn, aux_line_file, gfd):
    """Compute *todo* in worker processes like the plugin; return the recompute list."""
    command = find_worker_command(str(PLUGIN))
    if command is None:
        sys.exit("No worker command on this system")
    init_fields = {
        "plugin_root": str(PLUGIN), "sys_path": list(sys.path),
        "prefix_path": QgsApplication.prefixPath(),
        "inputs": {"hu": ws + "layer_hu.gpkg", "rn": ws + "layer_rn.gpkg",
                   "part": ws + "layer_part.gpkg", "aux_line": aux_line_file},
        "crs": crs.authid(), "params": PARAMS, "workspace": ws, "results_dir": str(RESULTS),
        "debug_mode": False, "global_density": gfd, "log_level": "CRITICAL",
        "parent_pid": os.getpid()}
    pool = WorkerPool(command, min(args.workers, len(todo)), init_fields)
    if not pool.selftest():
        print("\n".join(pool.stderr_tail(50)), file=sys.stderr)
        sys.exit(2)
    estimates = pr.estimate_buildings(hu, part, todo)
    order = sorted(todo, key=lambda n: -estimates.get(n, 0))

    def on_done(event):
        pr.append_finished(LOG_FIN, pr.FinishedPart(
            event["partition"], event["result"],
            event["features"] if event["result"] else None))
        print(f"  {event['partition']}: hu={event['buildings']} {event['seconds']:.1f}s",
              flush=True)

    pool.partition_done.connect(on_done)
    pool.log.connect(lambda level, message: print(f"  [{level}] {message}", flush=True)
                     if level in ("WARNING", "CRITICAL") else None)
    done = []
    loop = QEventLoop()
    pool.finished.connect(lambda: done.append(True))
    pool.finished.connect(loop.quit)
    tp = time.perf_counter()
    pool.run(order)
    if not done:
        loop.exec()
    TIMES["50_parallel"] = time.perf_counter() - tp
    failed = set(pool.recompute)
    return [n for n in todo if n in failed]


# Per-step timing: wrap the tool functions as seen by the partition pipeline
# (same step names as before, so timings stay comparable with earlier runs).
_STEP_NAMES = {
    "select_and_save_by_location": "01_select", "calc_footprint_density": "02_local_density",
    "blocker": "04_blocker", "input_hu_filter": "05_import_filter",
    "identify_dense_blocks": "06_dense_blocks", "calculate_mst": "07_create_mst",
    "mst_clustering": "08_mst_clustering", "add_single_bdg": "09_add_single",
    "edge_catch": "10_edge_catch", "erode_empty_areas": "11_erode",
    "gap_close": "12_gap_close", "patch_remove": "13_patch_remove",
}


def _timed_tool(step, fn):
    def wrapper(*a, **k):
        if "HEARTBEATS" in globals():
            HEARTBEATS["step"] = step
        return timed(step, fn, *a, **k)
    return wrapper


for _attr, _step in _STEP_NAMES.items():
    setattr(partition_pipeline, _attr, _timed_tool(_step, getattr(partition_pipeline, _attr)))

# Same parameters as the plugin passes (CONFIG.ini defaults, see parameterization.md)
PARAMS = {"min_overlap_blocks": P["min_overlap_blocks"], "global_footprint_density": 0.0,
          "min_area": P["min_area"], "min_bdg_count": P["min_bdg_count"],
          "min_patch_size": P["min_patch_size"], "max_hole_size": P["max_hole_size"],
          "max_gap_size": P["max_gap_size"], "part_start": -1, "part_end": -1,
          "input_filter": FILTER}


def run_partition(name, part, hu, rn, aux_line, gfd):
    """One partition in this process via the plugin's pipeline, written as part file."""
    tp = time.perf_counter()
    layers = {"layer_part": part, "layer_hu": hu, "layer_rn": rn, "aux_layers_line": aux_line}
    counts = []
    result, _count = partition_pipeline.run_partition(
        name, layers, crs, ws, False, gfd, PARAMS, on_selected=counts.append)
    rel, features = (None, 0) if result is None else \
        pr.write_part_result(result, name, str(RESULTS))
    pr.append_finished(LOG_FIN, pr.FinishedPart(name, rel, features if rel else None))
    if result is not None:
        print(f"  {name}: hu={counts[0] if counts else '?'} {time.perf_counter() - tp:.1f}s",
              flush=True)


def save_result(final):
    """Write the merged result to <out>/result.gpkg."""
    if final is None or final.featureCount() == 0:
        return
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    QgsVectorFileWriter.writeAsVectorFormatV3(
        final, str(OUT / "result.gpkg"), QgsCoordinateTransformContext(), opts)
    print(f"Result written: {OUT / 'result.gpkg'} ({final.featureCount()} features)")


HEARTBEATS = {"last": None, "max_gap": 0.0, "max_gap_at": "", "count": 0, "step": ""}


def _record_heartbeat():
    """Heartbeat callback: track the longest gap between two UI heartbeats."""
    now = time.perf_counter()
    if HEARTBEATS["last"] is not None:
        gap = now - HEARTBEATS["last"]
        if gap > HEARTBEATS["max_gap"]:
            HEARTBEATS["max_gap"] = gap
            HEARTBEATS["max_gap_at"] = HEARTBEATS["step"]
    HEARTBEATS["last"] = now
    HEARTBEATS["count"] += 1


if args.heartbeat_stats:
    _orig_timed = timed

    def timed(name, fn, *a, **k):  # noqa: F811  (wraps timed to label the current step)
        HEARTBEATS["step"] = name
        return _orig_timed(name, fn, *a, **k)

if args.heartbeat_stats:
    with ui_heartbeat(_record_heartbeat, min_interval=0):
        save_result(main())
    print(f"\n=== UI heartbeat ===\nheartbeats: {HEARTBEATS['count']}, longest gap: "
          f"{HEARTBEATS['max_gap']:.2f} s (during {HEARTBEATS['max_gap_at'] or '?'})")
elif args.no_cprofile:
    save_result(main())
else:
    prof = cProfile.Profile()
    prof.enable()
    merged = main()
    prof.disable()
    save_result(merged)

print("\n=== Phase times (s) ===")
for k, v in sorted(TIMES.items()):
    print(f"{k:20s} {v:8.2f}")
if not (args.no_cprofile or args.heartbeat_stats):
    st = pstats.Stats(prof)
    st.sort_stats("cumulative").print_stats(r"ibtool", 30)
    st.sort_stats("tottime").print_stats(15)
