"""Generate the shared QGIS layer styles (QML) for the documentation maps.

Run with the QGIS Python interpreter (needs qgis.core), e.g. on Windows:

    "C:\\Program Files\\QGIS 3.40.0\\bin\\python-qgis.bat" docs/img/_src/make_qml_styles.py

Writes one .qml per map element to docs/img/_src/styles/. The colours and
line styles follow the "Map style" table in
docs/superpowers/plans/2026-09-24-documentation-figures.md (palette from the
plugin icon). Load a style in QGIS via Layer Properties -> Style -> Load Style.

Widths given in pixels in the style table are converted at 96 dpi
(1 px = 0.2646 mm), so the print layout export at 96 dpi matches the table.
"""
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsPalLayerSettings,
    QgsSimpleLineSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtGui import QColor, QFont

OUT_DIR = Path(__file__).resolve().parent / "styles"
PX = 0.2646          # mm per pixel at 96 dpi

TEAL = "#007D85"
ORANGE = "#F7561A"
PINK = "#FFBCB0"
LIGHT_BLUE = "#74B0C4"
BUILDING = "#3C3C3C"
FILTERED = "#BDBDBD"
BOUNDARY = "#616161"
TEXT = "#212121"


def fill(colour, stroke="no", stroke_colour="0,0,0,0", stroke_mm=0.0, style="solid",
         opacity=1.0):
    symbol = QgsFillSymbol.createSimple({
        "color": colour,
        "style": style,
        "outline_style": "solid" if stroke == "solid" else "no",
        "outline_color": stroke_colour,
        "outline_width": str(stroke_mm),
        "outline_width_unit": "MM",
        "joinstyle": "miter",
    })
    if stroke == "dash":
        # Dashed outline as a separate line layer with a fixed dash pattern:
        # the built-in "dash" pen scales with the width and looks solid at 1 px.
        symbol.appendSymbolLayer(QgsSimpleLineSymbolLayer.create({
            "line_color": stroke_colour,
            "line_width": str(stroke_mm),
            "line_width_unit": "MM",
            "use_custom_dash": "1",
            "customdash": "3;2",
            "customdash_unit": "MM",
            "joinstyle": "miter",
        }))
    symbol.setOpacity(opacity)
    return symbol


def line(colour, width_mm, pen="solid"):
    return QgsLineSymbol.createSimple({
        "line_color": colour,
        "line_width": str(width_mm),
        "line_width_unit": "MM",
        "line_style": pen,
        "capstyle": "round",
        "joinstyle": "round",
    })


def partition_labels():
    fmt = QgsTextFormat()
    fmt.setFont(QFont("Arial"))
    fmt.setSize(9)
    fmt.setColor(QColor(BOUNDARY))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(0.8)
    buffer.setColor(QColor("#FFFFFF"))
    fmt.setBuffer(buffer)
    settings = QgsPalLayerSettings()
    settings.fieldName = "NAME"
    settings.setFormat(fmt)
    return QgsVectorLayerSimpleLabeling(settings)


# name -> (geometry type, symbol, labeling or None)
STYLES = {
    "buildings": ("Polygon", lambda: fill(BUILDING), None),
    "buildings_filtered": ("Polygon", lambda: fill(FILTERED, opacity=0.5), None),
    "roads": ("LineString", lambda: line(TEAL, 0.6), None),
    "aux_lines": ("LineString", lambda: line(LIGHT_BLUE, 0.5), None),
    "partitions": ("Polygon",
                   lambda: fill("0,0,0,0", "dash", BOUNDARY, 1 * PX, style="no"),
                   partition_labels),
    "innenbereich": ("Polygon", lambda: fill(PINK, "solid", ORANGE, 2 * PX), None),
    "added_area": ("Polygon", lambda: fill(ORANGE, "solid", ORANGE, 1 * PX), None),
    "removed_area": ("Polygon", lambda: fill("#FFFFFF", "dash", BUILDING, 1.5 * PX), None),
    "accepted_step": ("LineString", lambda: line(TEAL, 2 * PX), None),
}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, (geom_type, make_symbol, make_labels) in STYLES.items():
        layer = QgsVectorLayer(f"{geom_type}?crs=EPSG:25833&field=NAME:string",
                               name, "memory")
        layer.setRenderer(QgsSingleSymbolRenderer(make_symbol()))
        if make_labels is not None:
            layer.setLabeling(make_labels())
            layer.setLabelsEnabled(True)
        path = OUT_DIR / f"ibt_{name}.qml"
        message, ok = layer.saveNamedStyle(str(path))
        assert ok, f"{path.name}: {message}"
        print(f"wrote {path.name}")


if __name__ == "__main__":
    app = QgsApplication([], False)
    app.initQgis()
    main()
    app.exitQgis()
