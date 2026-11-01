# -*- coding: utf-8 -*-
"""Overlay helpers built on QgsGeometry (grid-aware, reproducing QGIS algorithms).

``symmetrical_difference`` is a drop-in equivalent of ``qgis:symmetricaldifference``
(INPUT, OVERLAY, GRID_SIZE) that computes each overlay union only once. It is
verified bit-identical (geometry WKT, feature order, fields, attributes) against
the QGIS algorithm; see ``ai/domain/gap-close.md`` (design decision 5).

Copyright: (C) 2026 by Oliver Harig
License: GNU General Public License v2 or later
"""
from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsGeometryParameters,
    QgsMemoryProviderUtils,
    QgsProcessingUtils,
    QgsSpatialIndex,
    QgsWkbTypes,
)

from .processing_context import heartbeat


def grid_union(geometries, params):
    """Union *geometries* with the grid of *params* (separate for testability)."""
    return QgsGeometry.unaryUnion(geometries, params)


def polygon_parts(geom):
    """Return the polygon parts of *geom* as a multi-polygon, or ``None``.

    Grid (snap-rounded) differences can return a ``GeometryCollection``:
    polygons plus line/point remnants of collapsed slivers. As in
    ``qgis:symmetricaldifference``, the polygon parts are kept in their order
    (including degenerate zero-area parts) and the rest is discarded.
    (``QgsGeometry.convertToType`` returns a null geometry for such
    collections, which dropped whole blocks.)

    Args:
        geom: Result of a polygon difference.

    Returns:
        Multi-polygon geometry, or ``None`` if *geom* has no polygon part.
    """
    if QgsWkbTypes.flatType(geom.wkbType()) == QgsWkbTypes.GeometryCollection:
        parts = [part for part in geom.asGeometryCollection()
                 if part.type() == QgsWkbTypes.PolygonGeometry]
        if not parts:
            return None
        geom = QgsGeometry.collectGeometry(parts)
    geom.convertToMultiType()
    return geom


def difference_features(layer_a, layer_b, params, attrs_for):
    """Yield ``(geometry, attributes)`` of ``A − B`` per feature of *layer_a*.

    Same computation as ``QgsOverlayUtils::difference`` used by
    ``qgis:symmetricaldifference``: for each A feature, the intersecting B
    geometries are unioned on the grid and subtracted; empty results are
    dropped, geometry collections reduced to their polygon parts, results
    converted to multi-type. Difference: the union of the same set of B
    features is computed once and reused (QGIS recomputes it for every A
    feature — on the largest sample partition 284 times for one settlement
    polygon, 21 s instead of 0.5 s).
    """
    geoms_b = {f.id(): f.geometry() for f in layer_b.getFeatures()}
    index = QgsSpatialIndex()
    for fid, geom in geoms_b.items():
        index.addFeature(fid, geom.boundingBox())
    union_cache = {}

    for feature in layer_a.getFeatures():
        heartbeat()   # keep the QGIS UI responsive (Python loop, no processing.run)
        geom = feature.geometry()
        if geom.isNull():
            continue
        engine = QgsGeometry.createGeometryEngine(geom.constGet())
        engine.prepareGeometry()
        ids = tuple(sorted(fid for fid in index.intersects(geom.boundingBox())
                           if engine.intersects(geoms_b[fid].constGet())))
        if ids:
            if ids not in union_cache:
                union_cache[ids] = grid_union([geoms_b[fid] for fid in ids], params)
            geom = geom.difference(union_cache[ids], params)
        if geom.isNull() or geom.isEmpty():
            continue
        geom = polygon_parts(geom)
        if geom is None:
            continue
        yield geom, attrs_for(feature)


def symmetrical_difference(input_layer, overlay_layer, grid_size):
    """Equivalent of ``qgis:symmetricaldifference`` (INPUT, OVERLAY, GRID_SIZE).

    Produces the same features in the same order with the same fields
    (``QgsProcessingUtils.combineFields``) and attributes (INPUT features:
    own attributes + NULLs; OVERLAY features: NULLs + own attributes), but
    computes each overlay union only once (see :func:`difference_features`).
    Verified bit-identical (WKT and order) against the QGIS algorithm.

    Args:
        input_layer: INPUT polygon layer.
        overlay_layer: OVERLAY polygon layer.
        grid_size: Grid size for the overlay operations (``GRID_SIZE``).

    Returns:
        Memory layer with the symmetrical difference.
    """
    params = QgsGeometryParameters()
    params.setGridSize(grid_size)
    fields = QgsProcessingUtils.combineFields(input_layer.fields(), overlay_layer.fields())
    n_a = input_layer.fields().count()
    n_b = overlay_layer.fields().count()

    result = QgsMemoryProviderUtils.createMemoryLayer(
        "symmetrical_difference", fields, QgsWkbTypes.multiType(input_layer.wkbType()),
        input_layer.crs())
    features = []
    for geom, attrs in list(difference_features(
            input_layer, overlay_layer, params,
            lambda f: f.attributes() + [None] * n_b)) + list(difference_features(
                overlay_layer, input_layer, params,
                lambda f: [None] * n_a + f.attributes())):
        out = QgsFeature(fields)
        out.setGeometry(geom)
        out.setAttributes(attrs)
        features.append(out)
    result.dataProvider().addFeatures(features)
    result.updateExtents()
    return result
