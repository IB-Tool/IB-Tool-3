"""Export the pipeline map series (F09) for docs/how-it-works.md.

Run with the QGIS Python interpreter after make_figures_project.py, e.g.:

    "C:\\Program Files\\QGIS 3.40.0\\bin\\python-qgis.bat" docs/img/_src/make_map_figures.py

Reads docs/img/_src/figures.qgz (sample data + the debug run of PART_31) and
writes one PNG per figure to docs/img/how-it-works/. Every figure is 1600 px
wide (shown at 800 px): single maps use the reference extent (2:1), figures
with several steps use square tiles of one focus window inside it. Each figure
has a scale bar, a north arrow, the attribution and a legend strip whose
swatches are drawn from the layer symbols themselves.

Steps whose case does not occur in the sample data get no map figure (rule of
the figures plan); their sections rely on the schematics instead.
"""
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsFeature,
    QgsGeometry,
    QgsGraduatedSymbolRenderer,
    QgsMapRendererParallelJob,
    QgsMapSettings,
    QgsProject,
    QgsRectangle,
    QgsSymbolLayerUtils,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QPointF, QRectF, QSize, Qt
from qgis.PyQt.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF

from make_figures_project import REF_XMAX, REF_XMIN, REF_YMAX, REF_YMIN, role_renderer

SRC_DIR = Path(__file__).resolve().parent
OUT_DIR = SRC_DIR.parent / "how-it-works"
PROJECT_PATH = SRC_DIR / "figures.qgz"

WIDTH = 1600                  # px, displayed at 800 px
GAP = 12                      # px between tiles
LEGEND_H = 64                 # px legend strip
DPI = 150                     # symbol scaling (mm -> px)
TEXT = QColor("#212121")
MUTED = QColor("#616161")
FRAME = QColor("#9E9E9E")

# Square focus window (500 x 500 m) on the village core, inside the reference
# extent; chosen for containing closed gaps, MST clusters and negative buildings
FOCUS = QgsRectangle(439000, 5837850, 439500, 5838350)


def reference_extent():
    """Reference extent widened in height to 2:1 (single-map figures)."""
    width = REF_XMAX - REF_XMIN
    height = width / 2
    pad = (height - (REF_YMAX - REF_YMIN)) / 2
    return QgsRectangle(REF_XMIN, REF_YMIN - pad, REF_XMAX, REF_YMAX + pad)


# Layer references: ("base", name), ("result", ""), or (tool folder, step name);
# an optional third element overrides the layer's role (style) for this tile.
B_HU, B_RN, B_AUX = ("base", "HU"), ("base", "RN"), ("base", "Aux")

FIGURES = {
    "01_blocker.png": {
        "extent": None,
        "tiles": [
            ("Blocks from roads + Aux lines",
             [("01_Blocker", "blocks_raw", "removed"),
              ("01_Blocker", "blocks_with_buildings"), B_AUX, B_RN, B_HU]),
        ],
        "legend": [(("01_Blocker", "blocks_with_buildings"), "block (one colour each)"),
                   (("01_Blocker", "blocks_raw", "removed"), "block without buildings (dropped)"),
                   (B_RN, "road"), (B_AUX, "Aux line"), (B_HU, "building")],
    },
    "02_import_filter.png": {
        "extent": FOCUS,
        "tiles": [
            ("1  Function codes",
             [(*B_HU, "filtered"), ("02_ImportFilter", "after_negative_filter"),
              ("02_ImportFilter", "after_positive_filter"), B_RN]),
            ("2  Density zone",
             [(*B_HU, "filtered"), ("02_ImportFilter", "after_neg_exclusion"),
              ("02_ImportFilter", "after_density_buffer"), B_RN]),
            ("3  Minimum size",
             [("02_ImportFilter", "after_neg_exclusion", "filtered"),
              ("02_ImportFilter", "after_area_filter"), B_RN]),
        ],
        "legend": [(("02_ImportFilter", "after_positive_filter"), "positive list"),
                   (("02_ImportFilter", "after_negative_filter"), "negative list"),
                   (("02_ImportFilter", "after_density_buffer"), "settlement core zone"),
                   (("02_ImportFilter", "after_area_filter"), "kept"),
                   ((*B_HU, "filtered"), "removed / not listed")],
    },
    "03_footprint_density.png": {
        "extent": None,
        "tiles": [
            ("Building coverage ratio per block",
             [("02a_FootprintDensity", "block_overlap"), B_AUX, B_RN, B_HU]),
        ],
        "legend": [(("02a_FootprintDensity", "block_overlap"), None), (B_HU, "building")],
    },
    "04_create_mst.png": {
        "extent": FOCUS,
        "tiles": [
            ("1  Delaunay triangulation",
             [B_RN, ("03_MST_Clustering", "after_hu_fid_calc"),
              ("02b_CreateMST", "delaunay_triangulation")]),
            ("2  Cut edges crossing roads",
             [("03_MST_Clustering", "after_hu_fid_calc"),
              ("02b_CreateMST", "delaunay_triangulation", "edges_removed"),
              ("02b_CreateMST", "triangulation_street_filtered"),
              ("02b_CreateMST", "streets_without_dead_ends")]),
            ("3  Minimum spanning tree",
             [("02b_CreateMST", "streets_without_dead_ends"),
              ("03_MST_Clustering", "after_hu_fid_calc"), ("02b_CreateMST", "mst")]),
        ],
        "legend": [(("02b_CreateMST", "delaunay_triangulation"), "triangulation edge"),
                   (("02b_CreateMST", "delaunay_triangulation", "edges_removed"),
                    "edge removed (crosses a road)"),
                   (("02b_CreateMST", "mst"), "MST edge"),
                   (B_RN, "road")],
    },
    "05_mst_clustering.png": {
        "extent": None,
        "tiles": [
            ("Building groups and their oriented rectangles",
             [B_AUX, B_RN, ("03_MST_Clustering", "after_clustering"), B_HU]),
        ],
        "legend": [(("03_MST_Clustering", "after_clustering"), "rectangle of a building group"),
                   (B_HU, "building"), (B_RN, "road")],
    },
    "07_edge_catch.png": {
        "extent": FOCUS,
        "tiles": [
            ("1  Before: rectangles",
             [B_AUX, B_RN, ("03_MST_Clustering", "after_clustering"), B_HU]),
            ("2  After: snapped to the roads",
             [B_AUX, ("05_EdgeCatch", "polygons_merged", "snapped"), B_RN, B_HU]),
        ],
        "legend": [(("03_MST_Clustering", "after_clustering"), "rectangle"),
                   (("05_EdgeCatch", "polygons_merged", "snapped"), "settlement after EdgeCatch"),
                   (B_RN, "road"), (B_HU, "building")],
    },
    "09_gap_close.png": {
        "extent": FOCUS,
        "tiles": [
            ("1  Before",
             [B_AUX, B_RN, ("06_ErodeEmptyAreas", "step0b_dissolved"), B_HU]),
            ("2  After: holes and gaps closed",
             [B_AUX, B_RN, ("07_GapClose", "result"),
              ("computed", "gapclose_added"), B_HU]),
        ],
        "legend": [(("07_GapClose", "result"), "settlement"),
                   (("computed", "gapclose_added"), "area added by GapClose"),
                   (B_RN, "road"), (B_HU, "building")],
    },
}


# ---------------------------------------------------------------------------
# Layer lookup
# ---------------------------------------------------------------------------

def index_layers(project):
    """Map ("base"|"result"|tool folder, name) -> layer."""
    index = {}
    root = project.layerTreeRoot()
    for node in root.findLayers():
        parent = node.parent().name()
        layer = node.layer()
        if parent.startswith("Base"):
            index[("base", layer.name())] = layer
        elif parent.startswith("Result"):
            index[("result", "")] = layer
        else:
            _, _, label = layer.name().partition(" ")
            index[(parent, label)] = layer
    return index


def add_computed_layers(index, crs):
    """Layers derived from the debug data (not written by the plugin itself)."""
    before = QgsGeometry.unaryUnion(
        [f.geometry() for f in index[("06_ErodeEmptyAreas", "step0b_dissolved")].getFeatures()])
    after = QgsGeometry.unaryUnion(
        [f.geometry() for f in index[("07_GapClose", "result")].getFeatures()])
    added = QgsVectorLayer(f"Polygon?crs={crs.authid()}", "gapclose_added", "memory")
    feature = QgsFeature()
    feature.setGeometry(after.difference(before))      # everything GapClose added
    added.dataProvider().addFeatures([feature])
    added.setRenderer(role_renderer("added", added))
    index[("computed", "gapclose_added")] = added


def resolve(index, ref):
    """Layer for a reference; a third element returns a restyled clone."""
    layer = index[tuple(ref[:2])]
    if len(ref) == 3:
        clone = layer.clone()
        clone.setRenderer(role_renderer(ref[2], clone))
        return clone
    return layer


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def font(px, bold=False):
    f = QFont("Arial")
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def render_map(layers, extent, size, crs):
    settings = QgsMapSettings()
    settings.setLayers(list(reversed(layers)))          # last entry on top
    settings.setDestinationCrs(crs)
    settings.setOutputSize(size)
    settings.setOutputDpi(DPI)
    settings.setExtent(extent)
    settings.setBackgroundColor(QColor("white"))
    job = QgsMapRendererParallelJob(settings)
    job.start()
    job.waitForFinished()
    return job.renderedImage(), settings.mapUnitsPerPixel()


def boxed_text(painter, x, y, text, px, bold=False, colour=TEXT, align_right=False):
    painter.setFont(font(px, bold))
    metrics = painter.fontMetrics()
    w, h = metrics.horizontalAdvance(text), metrics.height()
    left = x - w if align_right else x
    painter.fillRect(QRectF(left - 8, y - h + 2, w + 16, h + 6), QColor(255, 255, 255, 225))
    painter.setPen(colour)
    painter.drawText(QPointF(left, y), text)


def scale_bar(painter, x, y, metres_per_px):
    target = 220 * metres_per_px
    length = max(v for v in (25, 50, 100, 200, 250, 500, 1000) if v <= target)
    bar = length / metres_per_px
    painter.fillRect(QRectF(x - 10, y - 34, bar + 90, 50), QColor(255, 255, 255, 225))
    painter.fillRect(QRectF(x, y, bar, 7), QColor("#3C3C3C"))
    painter.setFont(font(20))
    painter.setPen(TEXT)
    painter.drawText(QPointF(x - 5, y - 8), "0")
    painter.drawText(QPointF(x + bar - 12, y - 8), f"{length} m")


def north_arrow(painter, x, y):
    painter.setBrush(QColor("#3C3C3C"))
    painter.setPen(Qt.NoPen)
    painter.drawPolygon(QPolygonF([QPointF(x, y), QPointF(x - 11, y + 32),
                                   QPointF(x, y + 25), QPointF(x + 11, y + 32)]))
    painter.setFont(font(20, True))
    painter.setPen(TEXT)
    painter.drawText(QPointF(x - 7, y + 56), "N")


def legend_entries(index, legend):
    """Yield (pixmap, label) for each legend entry."""
    size = QSize(44, 26)
    for ref, label in legend:
        layer = resolve(index, ref)
        renderer = layer.renderer()
        if isinstance(renderer, QgsGraduatedSymbolRenderer):
            yield None, "Building coverage ratio:"
            for rng in renderer.ranges():
                yield QgsSymbolLayerUtils.symbolPreviewPixmap(rng.symbol(), size), rng.label()
        else:
            yield QgsSymbolLayerUtils.symbolPreviewPixmap(renderer.symbol(), size), label


def draw_legend(painter, index, legend, y0):
    x = 16
    painter.setFont(font(22))
    for pixmap, label in legend_entries(index, legend):
        if pixmap is not None:
            painter.drawPixmap(int(x), int(y0 + 18), pixmap)
            x += 52
        painter.setPen(TEXT)
        painter.drawText(QPointF(x, y0 + 39), label)
        x += painter.fontMetrics().horizontalAdvance(label) + 30
    assert x <= WIDTH + 30, f"legend too wide ({x:.0f} px)"


def make_figure(name, spec, index, crs):
    tiles = spec["tiles"]
    n = len(tiles)
    if spec["extent"] is None:
        extent, tile_w, tile_h = reference_extent(), WIDTH, WIDTH // 2
    else:
        extent = spec["extent"]
        tile_w = (WIDTH - (n - 1) * GAP) // n
        tile_h = tile_w
    image = QImage(WIDTH, tile_h + LEGEND_H, QImage.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    for i, (title, refs) in enumerate(tiles):
        layers = [resolve(index, ref) for ref in refs]
        tile, metres_per_px = render_map(layers, extent, QSize(tile_w, tile_h), crs)
        x0 = i * (tile_w + GAP)
        painter.drawImage(int(x0), 0, tile)
        # Thin frame, so maps on white do not run into each other or the page
        painter.setPen(QPen(FRAME, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(x0 + 1, 1, tile_w - 2, tile_h - 2))
        boxed_text(painter, x0 + 16, 40, title, 26, bold=True)
        if i == 0:
            scale_bar(painter, x0 + 24, tile_h - 22, metres_per_px)
        if i == n - 1:
            north_arrow(painter, x0 + tile_w - 34, 16)
            boxed_text(painter, x0 + tile_w - 14, tile_h - 14, "© GeoBasis-DE/LGB", 18,
                       colour=MUTED, align_right=True)
    draw_legend(painter, index, spec["legend"], tile_h)
    painter.end()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    assert image.save(str(path)), path
    size_kb = path.stat().st_size / 1024
    print(f"wrote {name} ({image.width()} x {image.height()}, {size_kb:.0f} KB)")
    assert size_kb < 500, f"{name} exceeds the 500 KB budget"


def main(only=None):
    project = QgsProject.instance()
    assert project.read(str(PROJECT_PATH)), PROJECT_PATH
    index = index_layers(project)
    add_computed_layers(index, project.crs())
    for name, spec in FIGURES.items():
        if only and name not in only:
            continue
        make_figure(name, spec, index, project.crs())


if __name__ == "__main__":
    import sys
    app = QgsApplication([], False)
    app.initQgis()
    main(sys.argv[1:])
    app.exitQgis()
