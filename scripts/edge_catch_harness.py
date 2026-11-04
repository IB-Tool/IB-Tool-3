"""Golden-data harness for EdgeCatch.process_single_feature (Phase 3 refactoring).

Records the exact output of ``process_single_feature`` for every rectangle of
selected partitions and checks a modified implementation against it
(bit-identical: geometry WKT with 17 digits, attributes, feature order).

Commands (run with the QGIS Python, e.g. ``python-qgis-ltr.bat``):

    dump    --cases DIR [--data Testdaten] [--only PART_64,PART_56,...]
            Runs the pipeline up to EdgeCatch for the given partitions and saves
            the inputs of every process_single_feature call to DIR/<PART>.gpkg
            (layers: rects, roads, blocks).
    record  --cases DIR      Runs the CURRENT code on the dumped inputs and writes
                             DIR/golden.json (+ timing).
    check   --cases DIR      Runs the current code and compares with golden.json;
                             prints per-algorithm timings. Exit code 0 = identical.

Not part of the plugin package (development tool only).
"""
import argparse
import json
import os
import sys
import time
import types
from collections import defaultdict
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("command", choices=["dump", "record", "check"])
ap.add_argument("--cases", required=True, help="Directory for dumped inputs and golden data")
ap.add_argument("--data", default=str(PLUGIN / "Testdaten"))
ap.add_argument("--only", default="PART_64,PART_43,PART_25,PART_56,PART_33,PART_7,PART_49",
                help="Partitions to dump (comma-separated)")
ap.add_argument("--limit", type=int, default=0, help="check/record: max rectangles per partition")
args = ap.parse_args()
CASES = Path(args.cases)
CASES.mkdir(parents=True, exist_ok=True)

from qgis.core import (  # noqa: E402
    QgsApplication, QgsCoordinateReferenceSystem, QgsVectorFileWriter, QgsVectorLayer,
    QgsCoordinateTransformContext,
)
QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", ""), True)
app = QgsApplication([], False)
app.initQgis()
sys.path.append(os.path.join(os.environ.get("QGIS_PREFIX_PATH", ""), "python", "plugins"))
from processing.core.Processing import Processing  # noqa: E402
Processing.initialize()

_pkg = types.ModuleType("ibtool")
_pkg.__path__ = [str(PLUGIN)]
sys.modules["ibtool"] = _pkg
from ibtool.helpers.logger import Logger  # noqa: E402
from ibtool.helpers import safe_processing  # noqa: E402
from ibtool.helpers import edge_catch_utils  # noqa: E402
from ibtool.helpers.processing_context import shared_processing_context  # noqa: E402

try:
    Logger.set_log_level("CRITICAL")
except Exception:  # pylint: disable=broad-except
    pass

CRS = QgsCoordinateReferenceSystem("EPSG:25833")


def _write(layer, path, name, append):
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = name
    if append:
        opts.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
    err = QgsVectorFileWriter.writeAsVectorFormatV3(layer, str(path), QgsCoordinateTransformContext(), opts)
    if err[0] != QgsVectorFileWriter.WriterError.NoError:
        raise RuntimeError(f"write {path}:{name} failed: {err}")


def dump():
    """Run the pipeline up to EdgeCatch for --only partitions and save exactly what
    edge_catch() passes to process_single_feature (rects with Area, filtered roads, blocks).
    Mirrors scripts/profile_pipeline.py (same parameters as CONFIG.ini defaults)."""
    # pylint: disable=import-outside-toplevel
    from qgis import processing
    from qgis.core import QgsProcessing
    from ibtool.helpers.processing_context import current_processing_context
    from ibtool.helpers.geometry_utils import (
        load_to_geopackage, select_and_save_by_location, shp_area2)
    from ibtool.ibtool_tools.FootprintDensity import calc_footprint_density, identify_dense_blocks
    from ibtool.ibtool_tools.Blocker import blocker
    from ibtool.ibtool_tools.ImportFilter import input_hu_filter
    from ibtool.ibtool_tools.CreateMST import calculate_mst
    from ibtool.ibtool_tools.MST_Clustering import mst_clustering
    from ibtool.ibtool_tools.AddSingleBuilding import add_single_bdg

    data = Path(args.data)
    ws = str(CASES / "_ws") + "/"
    os.makedirs(ws, exist_ok=True)

    def pick(key):
        return str(sorted(data.glob(f"*{key}*.shp"))[0])

    def run(alg, params):
        return processing.run(alg, params, context=current_processing_context())['OUTPUT']

    with shared_processing_context():
        rn = load_to_geopackage(pick("RN"), ws + "layer_rn.gpkg", "layer_rn", CRS)
        aux = load_to_geopackage(pick("AUX"), ws + "layer_aux.gpkg", "layer_aux", CRS)
        part = load_to_geopackage(pick("PART"), ws + "layer_part.gpkg", "layer_part", CRS)
        hu = load_to_geopackage(pick("HU"), ws + "layer_hu.gpkg", "layer_hu", CRS)
        aux_line = run("qgis:mergevectorlayers", {'LAYERS': [aux, rn], 'CRS': CRS,
                                                  'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT})
    with shared_processing_context():
        gfd = calc_footprint_density(hu, rn, 100, 0, 'global', 20, part)
    wanted = [n.strip() for n in args.only.split(",")]
    for name in [f["NAME"] for f in part.getFeatures() if f["NAME"] in wanted]:
        with shared_processing_context():
            sel_part = run("native:extractbyexpression", {
                'INPUT': part, 'EXPRESSION': f"\"NAME\" = '{name}'",
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT})
            hu_l = select_and_save_by_location(hu, sel_part)
            rn_l = select_and_save_by_location(rn, sel_part)
            aux_l = select_and_save_by_location(aux_line, sel_part)
            lfd = calc_footprint_density(hu_l, rn_l, 100, gfd, 'local', 20)
            sel_hu = run("native:splitwithlines", {'INPUT': hu_l, 'LINES': rn_l, 'OUTPUT': 'memory:'})
            blocks = blocker(aux_l, sel_hu, sel_part)
            huf = input_hu_filter(sel_hu, str(data / "IB-Tool2_Filter.txt"), 57.0, 50, 200)
            dense = identify_dense_blocks(huf, blocks, 18.0)
            huf_sel = select_and_save_by_location(huf, dense, [2], 0)
            mst = calculate_mst(huf_sel, rn_l, CRS)
            clu = mst_clustering(huf_sel, mst, CRS, lfd)
            asb = add_single_bdg(huf_sel, clu, CRS, ws)
            rect = run("qgis:mergevectorlayers", {'LAYERS': [asb, clu], 'CRS': CRS,
                                                  'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT})
            # exactly as in EdgeCatch.edge_catch before the per-feature loop
            roads = edge_catch_utils.filter_roads_near_buildings(
                rn_l, huf_sel, edge_catch_utils.ROAD_SEGMENT_LENGTH,
                edge_catch_utils.ROAD_BUFFER_DISTANCE)
            shp_area2(rect)
        path = CASES / f"{name}.gpkg"
        if path.exists():
            path.unlink()
        _write(rect, path, "rects", False)
        _write(roads, path, "roads", True)
        _write(blocks, path, "blocks", True)
        print(f"dumped {name}: {rect.featureCount()} rects, {roads.featureCount()} roads, "
              f"{blocks.featureCount()} blocks", flush=True)


def _load_cases():
    for path in sorted(CASES.glob("PART_*.gpkg")):
        layers = {n: QgsVectorLayer(f"{path}|layername={n}", n, "ogr") for n in ("rects", "roads", "blocks")}
        yield path.stem, layers


TIMING = defaultdict(float)
_real_run = safe_processing.processing.run


def _timed_run(alg, params, *a, **k):
    t = time.perf_counter()
    try:
        return _real_run(alg, params, *a, **k)
    finally:
        TIMING[alg] += time.perf_counter() - t


def _norm(value):
    if value is None or (hasattr(value, "isNull") and value.isNull()):
        return None
    return value if isinstance(value, (int, float, str)) else str(value)


def run_all():
    """Run process_single_feature on all dumped rectangles; return {case: [[rows], ...]}."""
    safe_processing.processing.run = _timed_run
    out = {}
    t0 = time.perf_counter()
    for name, layers in _load_cases():
        results = []
        with shared_processing_context():
            for i, feat in enumerate(layers["rects"].getFeatures()):
                if args.limit and i >= args.limit:
                    break
                res = edge_catch_utils.process_single_feature(feat, layers["roads"], layers["blocks"], CRS)
                results.append(None if res is None else
                               [[f.geometry().asWkt(17), [_norm(v) for v in f.attributes()]]
                                for f in res.getFeatures()])
        out[name] = results
    return out, time.perf_counter() - t0


if args.command == "dump":
    dump()
elif args.command == "record":
    data, total = run_all()
    (CASES / "golden.json").write_text(json.dumps(data), encoding="utf-8")
    print(f"recorded {sum(len(v) for v in data.values())} rectangles in {total:.1f} s")
else:
    golden = json.loads((CASES / "golden.json").read_text(encoding="utf-8"))
    data, total = run_all()
    data = json.loads(json.dumps(data))   # same normalisation as the stored golden data
    # Criterion: same multiset of (WKT, attributes) per rectangle. The feature
    # ORDER within one rectangle's result already varies between QGIS processes
    # with the original code (downstream steps union the polygons), so it is
    # reported separately and not counted as a difference.
    n_diff = 0
    n_order_only = 0
    for name, results in data.items():
        for i, (got, exp) in enumerate(zip(results, golden[name])):
            if got == exp:
                continue
            if got and exp and sorted(map(str, got)) == sorted(map(str, exp)):
                n_order_only += 1
                continue
            n_diff += 1
            if n_diff <= 5:
                print(f"DIFF {name} rect #{i}: got {None if got is None else len(got)} features, "
                      f"expected {None if exp is None else len(exp)}")
                only_got = sorted(set(map(str, got or [])) - set(map(str, exp or [])))
                only_exp = sorted(set(map(str, exp or [])) - set(map(str, got or [])))
                if only_got:
                    print(f"   only in new:    {only_got[0][:160]}")
                if only_exp:
                    print(f"   only in golden: {only_exp[0][:160]}")
    n = sum(len(v) for v in data.values())
    print(f"checked {n} rectangles in {total:.1f} s: {'IDENTICAL' if n_diff == 0 else f'{n_diff} DIFFERENT'}"
          f" ({n_order_only} with identical features in different order — not counted)")
    for alg, t in sorted(TIMING.items(), key=lambda x: -x[1])[:15]:
        print(f"  {t:7.2f} s  {alg}")
    sys.exit(0 if n_diff == 0 else 1)
