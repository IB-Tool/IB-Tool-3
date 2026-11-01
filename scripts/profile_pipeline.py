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
ap.add_argument("--no-cprofile", action="store_true", help="Only phase timings, no cProfile")
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
from ibtool.helpers.geometry_utils import load_to_geopackage, select_and_save_by_location  # noqa: E402
from ibtool.helpers.data_loader import create_partitions_list  # noqa: E402
from ibtool.ibtool_tools.FootprintDensity import calc_footprint_density, identify_dense_blocks  # noqa: E402
from ibtool.ibtool_tools.Blocker import blocker  # noqa: E402
from ibtool.ibtool_tools.ImportFilter import input_hu_filter  # noqa: E402
from ibtool.ibtool_tools.CreateMST import calculate_mst  # noqa: E402
from ibtool.ibtool_tools.MST_Clustering import mst_clustering  # noqa: E402
from ibtool.ibtool_tools.AddSingleBuilding import add_single_bdg  # noqa: E402
from ibtool.ibtool_tools.EdgeCatch import edge_catch  # noqa: E402
from ibtool.ibtool_tools.GapClose import gap_close  # noqa: E402
from ibtool.ibtool_tools.PatchRemove import patch_remove  # noqa: E402
from ibtool.ibtool_tools.ErodeEmptyAreas import erode_empty_areas  # noqa: E402

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
        'LAYERS': layers, 'CRS': crs, 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT})['OUTPUT']


def main():
    t0 = time.perf_counter()
    rn = load_to_geopackage(pick("RN"), ws + "layer_rn.gpkg", "layer_rn", crs)
    aux = load_to_geopackage(pick("AUX"), ws + "layer_aux.gpkg", "layer_aux", crs)
    part = load_to_geopackage(pick("PART"), ws + "layer_part.gpkg", "layer_part", crs)
    hu = load_to_geopackage(pick("HU"), ws + "layer_hu.gpkg", "layer_hu", crs)
    aux_line = merge([aux, rn])
    TIMES["00_load"] = time.perf_counter() - t0
    print("HU", hu.featureCount(), "RN", rn.featureCount(), "PART", part.featureCount(), flush=True)

    gfd = timed("00_global_density", calc_footprint_density, hu, rn, 100, 0, 'global', 20, part)
    parts = create_partitions_list(part, ["#"], -1, -1)
    if args.parts:
        parts = parts[:args.parts]
    results = []
    for name in parts:
        tp = time.perf_counter()
        sel_part = processing.run("native:extractbyexpression", {
            'INPUT': part, 'EXPRESSION': f"\"NAME\" = '{name}'",
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT})['OUTPUT']
        hu_l = timed("01_select", select_and_save_by_location, hu, sel_part)
        if hu_l.featureCount() < 10:
            continue
        rn_l = timed("01_select", select_and_save_by_location, rn, sel_part)
        aux_l = timed("01_select", select_and_save_by_location, aux_line, sel_part)
        lfd = timed("02_local_density", calc_footprint_density, hu_l, rn_l, 100, gfd, 'local', 20)
        sel_hu = timed("03_split", lambda: processing.run("native:splitwithlines", {
            'INPUT': hu_l, 'LINES': rn_l, 'OUTPUT': 'memory:'})['OUTPUT'])
        blocks = timed("04_blocker", blocker, aux_l, sel_hu, sel_part)
        huf = timed("05_import_filter", input_hu_filter, sel_hu, FILTER, P['min_area'], 50, 200)
        dense = timed("06_dense_blocks", identify_dense_blocks, huf, blocks, P['min_overlap_blocks'])
        huf_sel = timed("06_dense_blocks", select_and_save_by_location, huf, dense, [2], 0)
        mst = timed("07_create_mst", calculate_mst, huf_sel, rn_l, crs)
        if mst is None:
            continue
        clu = timed("08_mst_clustering", mst_clustering, huf_sel, mst, crs, lfd)
        asb = timed("09_add_single", add_single_bdg, huf_sel, clu, crs, ws)
        rect = merge([asb, clu])
        snapped = timed("10_edge_catch", edge_catch, rect, huf_sel, rn_l, blocks, crs, ws)
        bm = merge([snapped, dense])
        er = timed("11_erode", erode_empty_areas, bm, sel_hu, workspace_path=ws)
        gc = timed("12_gap_close", gap_close, er, blocks, P['max_hole_size'],
                   P['max_gap_size'], crs, gap_dist=30)
        pr = timed("13_patch_remove", patch_remove, gc, sel_hu, crs, ws,
                   min_patch_size=P['min_patch_size'], min_bdg_count=20,
                   footprint_area_sum=6000, footprint_density_threshold=18)
        results.append(pr)
        print(f"  {name}: hu={hu_l.featureCount()} rects={rect.featureCount()} "
              f"{time.perf_counter() - tp:.1f}s", flush=True)
    TIMES["99_TOTAL"] = time.perf_counter() - t0

    if results:
        final = merge(results)
        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = "GPKG"
        QgsVectorFileWriter.writeAsVectorFormatV3(
            final, str(OUT / "result.gpkg"), QgsCoordinateTransformContext(), opts)
        print(f"Result written: {OUT / 'result.gpkg'} ({final.featureCount()} features)")


if args.no_cprofile:
    main()
else:
    prof = cProfile.Profile()
    prof.enable()
    main()
    prof.disable()

print("\n=== Phase times (s) ===")
for k, v in sorted(TIMES.items()):
    print(f"{k:20s} {v:8.2f}")
if not args.no_cprofile:
    st = pstats.Stats(prof)
    st.sort_stats("cumulative").print_stats(r"ibtool", 30)
    st.sort_stats("tottime").print_stats(15)
