"""Compare two IB-Tool result GeoPackages geometrically.

Reports feature counts, total (dissolved) area, whether the per-feature
signatures (area + centroid, rounded to 1 cm) are identical, the area of the
symmetric difference of both dissolved results and — optionally — which
partitions differ. Used to verify that an optimisation does not change the
result (target: symmetric difference 0 m²) and that runs are deterministic.

Run with the QGIS Python (Windows example):

    "C:\\Program Files\\QGIS 3.40.0\\bin\\python-qgis.bat" scripts\\compare_results.py ^
        reference.gpkg candidate.gpkg --parts Testdaten\\A_PART.shp

Exit code: 0 if identical (symmetric difference <= --tolerance), 1 otherwise.
Not part of the plugin package (development tool only).
"""
import argparse
import os
import sys

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("reference", help="Reference result GeoPackage")
ap.add_argument("candidate", help="Candidate result GeoPackage")
ap.add_argument("--parts", default=None,
                help="Partition layer (NAME field) for a per-partition breakdown")
ap.add_argument("--tolerance", type=float, default=0.001,
                help="Max. symmetric difference area (m²) still counted as identical "
                     "(default 0.001: absorbs floating-point noise of the union/difference "
                     "computation itself)")
args = ap.parse_args()

from qgis.core import QgsApplication, QgsGeometry, QgsVectorLayer  # noqa: E402

QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", ""), True)
app = QgsApplication([], False)
app.initQgis()


def load(path):
    layer = QgsVectorLayer(path, os.path.basename(path), "ogr")
    if not layer.isValid():
        sys.exit(f"Cannot open {path}")
    geoms = [f.geometry() for f in layer.getFeatures()]
    signature = sorted(
        (round(g.area(), 2),
         round(g.centroid().asPoint().x(), 2),
         round(g.centroid().asPoint().y(), 2))
        for g in geoms)
    return signature, QgsGeometry.unaryUnion(geoms)


sig_a, union_a = load(args.reference)
sig_b, union_b = load(args.candidate)
sym_diff = union_a.symDifference(union_b)

print(f"reference: n={len(sig_a)} area={union_a.area():.3f} m2")
print(f"candidate: n={len(sig_b)} area={union_b.area():.3f} m2")
print(f"identical feature signatures: {sig_a == sig_b}")
print(f"symmetric difference area: {sym_diff.area():.6f} m2")

if args.parts:
    parts = QgsVectorLayer(args.parts, "parts", "ogr")
    differing = 0
    for part in parts.getFeatures():
        diff = sym_diff.intersection(part.geometry()).area()
        if diff > max(args.tolerance, 0.01):
            differing += 1
            print(f"  {part['NAME']}: diff={diff:.2f} m2 "
                  f"(ref {union_a.intersection(part.geometry()).area():.1f}, "
                  f"cand {union_b.intersection(part.geometry()).area():.1f})")
    print(f"partitions with differences: {differing}")

identical = sym_diff.area() <= args.tolerance
print("RESULT:", "IDENTICAL" if identical else "DIFFERENT")
sys.exit(0 if identical else 1)
