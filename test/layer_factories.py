"""
Shared layer and geometry factory helpers for IBTool tests.

Import this module AFTER calling get_qgis_app() in your test file so that
qgis.core is fully initialised when the module-level imports run.

Usage in test files:
    from .utilities import get_qgis_app
    QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
    from .layer_factories import (
        make_polygon_layer, make_line_layer, make_square_geom, add_feature_to_layer
    )
"""

from qgis.core import QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY


def make_polygon_layer(crs: str = "EPSG:25833", name: str = "test_poly") -> QgsVectorLayer:
    """Return an empty in-memory polygon layer with the given CRS."""
    layer = QgsVectorLayer(f"Polygon?crs={crs}", name, "memory")
    layer.updateFields()
    return layer


def make_line_layer(crs: str = "EPSG:25833", name: str = "test_line") -> QgsVectorLayer:
    """Return an empty in-memory line layer with the given CRS."""
    layer = QgsVectorLayer(f"LineString?crs={crs}", name, "memory")
    layer.updateFields()
    return layer


def make_square_geom(x0: float, y0: float, size: float) -> QgsGeometry:
    """Return an axis-aligned square QgsGeometry with bottom-left corner at (x0, y0)."""
    return QgsGeometry.fromPolygonXY([[
        QgsPointXY(x0,        y0),
        QgsPointXY(x0 + size, y0),
        QgsPointXY(x0 + size, y0 + size),
        QgsPointXY(x0,        y0 + size),
        QgsPointXY(x0,        y0),
    ]])


def add_feature_to_layer(layer: QgsVectorLayer, geom: QgsGeometry) -> QgsFeature:
    """Add a QgsFeature with the given geometry to layer and return it."""
    feat = QgsFeature(layer.fields())
    feat.setGeometry(geom)
    layer.dataProvider().addFeatures([feat])
    layer.updateExtents()
    return feat
