"""Build the QGIS project for the documentation maps (docs/img/_src/figures.qgz).

Run with the QGIS Python interpreter, e.g. on Windows:

    "C:\\Program Files\\QGIS 3.40.0\\bin\\python-qgis.bat" docs/img/_src/make_figures_project.py

Creates the project with the Testdaten layers, styled with the QML files from
make_qml_styles.py (run that first), the debug layers of the reference run
(debug/PART_PART_31/, one hidden group per tool, styled by role) and the
partition result, and one print layout "figure_1600x1000":
a map frame on the reference extent, scale bar, north arrow and attribution.
At 96 dpi the layout exports to 1600 x 1000 px. Also writes a preview PNG of
the layout to docs/img/_src/figures_preview.png (not used in the docs).

The reference extent was chosen by the user (WGS84 corners 52.692401, 14.091019
and 52.686872, 14.110263 -> 1,293 x 631 m in EPSG:25833, partition PART_31).
It is widened symmetrically in height to the 16:10 layout ratio so that no part
of the chosen area is cut off.
"""
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsLayoutItemPicture,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsGraduatedSymbolRenderer,
    QgsMarkerSymbol,
    QgsPrintLayout,
    QgsProject,
    QgsProperty,
    QgsRectangle,
    QgsRendererRange,
    QgsSingleSymbolRenderer,
    QgsSymbolLayer,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont

from make_qml_styles import (  # same folder; palette and symbol builders
    BUILDING, LIGHT_BLUE, ORANGE, PINK, PX, TEAL, fill as qml_fill, line as qml_line,
)

SRC_DIR = Path(__file__).resolve().parent
ROOT = SRC_DIR.parents[2]
STYLES = SRC_DIR / "styles"
PROJECT_PATH = SRC_DIR / "figures.qgz"
PREVIEW_PATH = SRC_DIR / "figures_preview.png"

# Reference extent (EPSG:25833), from the user's WGS84 corners
REF_XMIN, REF_YMIN, REF_XMAX, REF_YMAX = 438566, 5837810, 439859, 5838441
LAYOUT_RATIO = 1600 / 1000

DPI = 96
PX_MM = 25.4 / DPI                    # 1 px in mm at 96 dpi
PAGE_W, PAGE_H = 1600 * PX_MM, 1000 * PX_MM

# Drawn bottom-up: first entry is the lowest layer
LAYERS = [
    ("A_PART", "Part", "ibt_partitions.qml"),
    ("A_AUX", "Aux", "ibt_aux_lines.qml"),
    ("A_RN", "RN", "ibt_roads.qml"),
    ("A_HU", "HU", "ibt_buildings.qml"),
]


def layout_extent():
    """Reference extent widened in height to the layout aspect ratio."""
    width = REF_XMAX - REF_XMIN
    height = REF_YMAX - REF_YMIN
    target_h = max(height, width / LAYOUT_RATIO)
    pad = (target_h - height) / 2
    return QgsRectangle(REF_XMIN, REF_YMIN - pad, REF_XMAX, REF_YMAX + pad)


# ---------------------------------------------------------------------------
# Debug layers of the reference run (Session 0, Step 4)
# ---------------------------------------------------------------------------

DEBUG_DIR = SRC_DIR / "debug" / "PART_PART_31"
RESULT_GPKG = SRC_DIR / "IB_Tool_Results" / "IB_Tool_merge_temp.gpkg"

# Role per debug file, keyed by "<tool folder>/<step name>" (the file name
# without its NNN_ prefix: the numbers shift when a tool gains a checkpoint or
# an empty layer is skipped). Files not listed fall back to a role by geometry
# type (polygon -> settlement, line -> mst, point -> points).
DEBUG_ROLES = {
    "01_Blocker/roads_in_partition": "roads",
    "01_Blocker/blocks_raw": "blocks",
    "01_Blocker/blocks_with_buildings": "blocks",
    "02_ImportFilter/after_positive_filter": "buildings_positive",
    "02_ImportFilter/after_density_buffer": "outline_dashed",
    "02_ImportFilter/after_negative_filter": "buildings_negative",
    "02_ImportFilter/after_neg_exclusion": "buildings",
    "02_ImportFilter/after_dissolve": "buildings",
    "02_ImportFilter/after_group_filter": "buildings",
    "02_ImportFilter/after_area_filter": "buildings",
    "02_ImportFilter/after_final_dissolve": "buildings",
    "02a_FootprintDensity/local_block_overlap": "bcr",
    "02a_FootprintDensity/block_overlap": "bcr",
    "02a_FootprintDensity/dense_blocks": "dense",
    "02b_CreateMST/delaunay_triangulation": "triangulation",
    "02b_CreateMST/streets_without_dead_ends": "roads",
    "02b_CreateMST/triangulation_street_filtered": "triangulation",
    "02b_CreateMST/mst": "mst_bold",
    "03_MST_Clustering/after_hu_fid_calc": "buildings",
    "03_MST_Clustering/after_clustering": "mbr",
    "04_AddSingleBuilding/buildings_outside_cluster": "added",
    "05_EdgeCatch/road_segs_near_buildings": "accepted",
    "06_ErodeEmptyAreas/step1_sel_buildings": "buildings",
    "06_ErodeEmptyAreas/step2_building_buffers": "buffers",
    "06_ErodeEmptyAreas/step3_buffer_union": "buffers",
    "06_ErodeEmptyAreas/step4_empty_areas": "voids",
    "06_ErodeEmptyAreas/step4_filtered_empty_areas": "voids",
    "06_ErodeEmptyAreas/step4b_voids_to_remove": "removed",
    "07_GapClose/block_sym_diff": "added",
    "07_GapClose/selected_areas": "added",
    "07_GapClose/merged_gap": "added",
    "07_GapClose/initial_buffer": "buffers",
    "07_GapClose/small_removed": "added",
    "07_GapClose/final_gap1_70pct": "added",
    "07_GapClose/final_gap2_90pct": "added",
    "07_GapClose/gap_poly_max_size": "added",
    "07_GapClose/large_unselected": "voids",
    "07_GapClose/mosaik_tessellated": "triangles",
    "07_GapClose/triangles_with_edge_len": "triangles",
    "07_GapClose/narrow_large_gaps": "added",
}

# Building coverage ratio classes (%) for F09-03; the last class starts at the
# default dense-block threshold min_overlap_blocks = 18
BCR_CLASSES = [(0, 5, "#F2F8F8"), (5, 10, "#BFDCDE"), (10, 15, "#7FB9BD"),
               (15, 18, "#3F9AA0"), (18, 100, "#007D85")]


def role_renderer(role, layer):
    """Renderer for a debug-layer role."""
    if role == "bcr":
        ranges = []
        for low, high, colour in BCR_CLASSES:
            symbol = qml_fill(colour, "solid", "#FFFFFF", 2 * PX)
            label = f"≥ {low} %" if high == 100 else f"{low}–{high} %"
            ranges.append(QgsRendererRange(low, high, symbol, label))
        return QgsGraduatedSymbolRenderer("OVERLAP", ranges)
    return QgsSingleSymbolRenderer(role_symbol(role, layer.geometryType()))


def role_symbol(role, geometry_type):
    """Symbol for a debug-layer role (palette as in make_qml_styles.py)."""
    if role == "roads":
        return qml_line(TEAL, 0.6)
    if role == "accepted":
        return qml_line(TEAL, 2 * PX)
    if role == "mst":
        return qml_line(TEAL, 0.3)
    if role == "mst_bold":
        return qml_line(ORANGE, 0.5)
    if role == "triangulation":
        return qml_line("#74B0C4", 0.2)
    if role == "points":
        return QgsMarkerSymbol.createSimple({"name": "circle", "color": "#616161",
                                             "size": "1.2", "outline_style": "no"})
    if role == "blocks":
        # Pastel hue from the block centroid, so the same block keeps its colour
        # in every layer and figure; the base colour shows in legend swatches
        symbol = qml_fill("#D8EFD0", "solid", "#FFFFFF", 2 * PX)
        symbol.symbolLayer(0).setDataDefinedProperty(
            QgsSymbolLayer.PropertyFillColor,
            QgsProperty.fromExpression(
                "color_hsv((round(x(centroid($geometry))) * 7"
                " + round(y(centroid($geometry))) * 13) % 360, 22, 96)"))
        return symbol
    if role == "buildings":
        return qml_fill(BUILDING)
    if role == "buildings_positive":
        return qml_fill(TEAL)
    if role == "buildings_negative":
        return qml_fill(ORANGE)
    if role == "outline_dashed":
        return qml_fill("0,0,0,0", "dash", TEAL, 2 * PX, style="no")
    if role == "mbr":
        return qml_fill(PINK, "solid", ORANGE, 2 * PX, opacity=0.7)
    if role == "added":
        return qml_fill(ORANGE, "solid", ORANGE, 1 * PX)
    if role == "buffers":
        return qml_fill("#E4E4E4", opacity=0.75)
    if role == "voids":
        return qml_fill("0,0,0,0", "dash", BUILDING, 1.5 * PX, style="no")
    if role == "triangles":
        return qml_fill("0,0,0,0", "solid", ORANGE, 1 * PX, style="no")
    if role == "settlement":
        return qml_fill(PINK, "solid", ORANGE, 2 * PX)
    if role == "filtered":
        return qml_fill("#BDBDBD", opacity=0.5)
    if role == "edges_removed":
        # Dark and dashed, to contrast with the light solid triangulation edges
        symbol = qml_line(BUILDING, 0.25)
        dash = symbol.symbolLayer(0)
        dash.setUseCustomDashPattern(True)
        dash.setCustomDashVector([1.2, 0.8])
        dash.setCustomDashPatternUnit(QgsUnitTypes.RenderMillimeters)
        return symbol
    if role == "snapped":
        return qml_fill(LIGHT_BLUE, "solid", "#3F7F95", 2 * PX, opacity=0.6)
    if role == "dense":
        return qml_fill("0,0,0,0", "solid", BUILDING, 4 * PX, style="no")
    if role == "removed":
        return qml_fill("#FFFFFF", "dash", BUILDING, 1.5 * PX)
    raise ValueError(f"unknown role {role!r} ({geometry_type})")


def default_role(layer):
    return {QgsWkbTypes.PolygonGeometry: "settlement",
            QgsWkbTypes.LineGeometry: "mst",
            QgsWkbTypes.PointGeometry: "points"}[layer.geometryType()]


def add_debug_layers(project, root):
    """Add one hidden group per tool folder plus the visible result group."""
    result_group = root.addGroup("Result PART_31")
    result = QgsVectorLayer(str(RESULT_GPKG), "Innenbereich (result)", "ogr")
    assert result.isValid(), RESULT_GPKG
    result.setRenderer(QgsSingleSymbolRenderer(role_symbol("settlement", None)))
    project.addMapLayer(result, False)
    result_group.addLayer(result)

    debug_group = root.addGroup("Debug PART_31")
    count = 0
    unlisted = []
    for tool_dir in sorted(DEBUG_DIR.iterdir()):
        group = debug_group.addGroup(tool_dir.name)
        # Last step on top, so the layer order follows the processing order
        for gpkg in sorted(tool_dir.glob("*.gpkg"), reverse=True):
            number, _, label = gpkg.stem.partition("_")
            layer = QgsVectorLayer(str(gpkg), f"{number} {label}", "ogr")
            assert layer.isValid(), gpkg
            key = f"{tool_dir.name}/{label}"
            if key not in DEBUG_ROLES:
                unlisted.append(key)
            role = DEBUG_ROLES.get(key, default_role(layer))
            layer.setRenderer(role_renderer(role, layer))
            project.addMapLayer(layer, False)
            group.addLayer(layer)
            count += 1
        group.setItemVisibilityChecked(False)
        group.setExpanded(False)
    debug_group.setItemVisibilityChecked(False)
    print(f"added {count} debug layers; default style for: {', '.join(unlisted)}")
    return result


def build_layout(project, layers):
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName("figure_1600x1000")
    page = layout.pageCollection().page(0)
    page.setPageSize(QgsLayoutSize(PAGE_W, PAGE_H, QgsUnitTypes.LayoutMillimeters))

    map_item = QgsLayoutItemMap(layout)
    map_item.attemptMove(QgsLayoutPoint(0, 0, QgsUnitTypes.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(PAGE_W, PAGE_H, QgsUnitTypes.LayoutMillimeters))
    map_item.setLayers(list(reversed(layers)))
    map_item.setKeepLayerSet(True)
    map_item.setExtent(layout_extent())
    map_item.setBackgroundColor(QColor("white"))
    map_item.setFrameEnabled(False)
    layout.addLayoutItem(map_item)

    scale_bar = QgsLayoutItemScaleBar(layout)
    scale_bar.setStyle("Single Box")
    scale_bar.setLinkedMap(map_item)
    scale_bar.setUnits(QgsUnitTypes.DistanceMeters)
    scale_bar.setUnitLabel("m")
    scale_bar.setNumberOfSegments(2)
    scale_bar.setNumberOfSegmentsLeft(0)
    scale_bar.setUnitsPerSegment(100)
    scale_bar.setHeight(1.5)
    scale_bar.fillSymbol().setColor(QColor("#3C3C3C"))
    fmt = scale_bar.textFormat()
    fmt.setFont(QFont("Arial"))
    fmt.setSize(9)
    scale_bar.setTextFormat(fmt)
    scale_bar.setBackgroundEnabled(True)
    scale_bar.setBackgroundColor(QColor(255, 255, 255, 220))
    scale_bar.attemptMove(QgsLayoutPoint(8, PAGE_H - 16, QgsUnitTypes.LayoutMillimeters))
    scale_bar.update()
    layout.addLayoutItem(scale_bar)

    arrow = QgsLayoutItemPicture(layout)
    arrow.setPicturePath(":/images/north_arrows/layout_default_north_arrow.svg")
    arrow.setLinkedMap(map_item)
    arrow.setNorthMode(QgsLayoutItemPicture.GridNorth)
    arrow.attemptResize(QgsLayoutSize(8, 12, QgsUnitTypes.LayoutMillimeters))
    arrow.attemptMove(QgsLayoutPoint(PAGE_W - 16, 6, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(arrow)

    label = QgsLayoutItemLabel(layout)
    label.setText("© GeoBasis-DE/LGB")
    label_fmt = label.textFormat()
    label_fmt.setFont(QFont("Arial"))
    label_fmt.setSize(8)
    label_fmt.setColor(QColor("#616161"))
    label.setTextFormat(label_fmt)
    label.setHAlign(Qt.AlignRight)
    label.setBackgroundEnabled(True)
    label.setBackgroundColor(QColor(255, 255, 255, 220))
    label.attemptResize(QgsLayoutSize(40, 5, QgsUnitTypes.LayoutMillimeters))
    label.attemptMove(QgsLayoutPoint(PAGE_W - 44, PAGE_H - 8, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(label)

    project.layoutManager().addLayout(layout)
    return layout


def main():
    project = QgsProject.instance()
    project.clear()
    project.setCrs(QgsVectorLayer(str(ROOT / "Testdaten" / "A_HU.shp"), "", "ogr").crs())
    project.writeEntryBool("Paths", "/Absolute", False)       # portable project

    root = project.layerTreeRoot()
    base = root.addGroup("Base (Testdaten)")
    layers = []
    for shp, name, qml in LAYERS:
        layer = QgsVectorLayer(str(ROOT / "Testdaten" / f"{shp}.shp"), name, "ogr")
        assert layer.isValid(), shp
        _, ok = layer.loadNamedStyle(str(STYLES / qml))
        assert ok, qml
        project.addMapLayer(layer, False)
        base.insertLayer(0, layer)            # later entries on top
        layers.append(layer)
    add_debug_layers(project, root)

    layout = build_layout(project, layers)
    assert project.write(str(PROJECT_PATH)), "could not write project"
    print(f"wrote {PROJECT_PATH.name}")

    settings = QgsLayoutExporter.ImageExportSettings()
    settings.dpi = DPI
    result = QgsLayoutExporter(layout).exportToImage(str(PREVIEW_PATH), settings)
    assert result == QgsLayoutExporter.Success, result
    print(f"wrote {PREVIEW_PATH.name}")


if __name__ == "__main__":
    app = QgsApplication([], False)
    app.initQgis()
    main()
    app.exitQgis()
