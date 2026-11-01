# -*- coding: utf-8 -*-
"""Overlay helpers built on QgsGeometry (grid-aware, reproducing QGIS algorithms).

Each function reproduces a QGIS processing algorithm with direct ``QgsGeometry``
operations (no per-call processing overhead) and was verified against the
algorithm on the sample data:

- ``symmetrical_difference`` — ``qgis:symmetricaldifference`` (INPUT, OVERLAY,
  GRID_SIZE), computing each overlay union only once (bit-identical; see
  ``ai/domain/gap-close.md``, design decision 5).
- ``make_valid_polygon`` — ``native:fixgeometries`` (METHOD 1 = structure) for a
  polygon feature.
- ``extract_intersecting`` — ``native:extractbylocation`` (PREDICATE intersects)
  including its output order.
- ``polygonize_lines`` — ``native:extendlines`` → ``native:fixgeometries`` →
  ``native:polygonize``.
- ``intersection_with`` — ``native:intersection`` (no grid) incl. result sanitising.

A GEOS operation that fails (null result *with* an error message) raises
:class:`GeometryOperationError`; callers fall back to the processing algorithms,
which have their own error handling (``safe_processing_run``).

Copyright: (C) 2026 by Oliver Harig
License: GNU General Public License v2 or later
"""
from qgis.core import (
    Qgis,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsGeometryParameters,
    QgsMemoryProviderUtils,
    QgsProcessingUtils,
    QgsSpatialIndex,
    QgsWkbTypes,
)

from .processing_context import heartbeat


class GeometryOperationError(RuntimeError):
    """A GEOS operation failed (null result with an error message)."""


def checked(geom, operation):
    """Return *geom*, or raise :class:`GeometryOperationError` if *operation* failed.

    QgsGeometry operations do not raise; a failure shows up as a null geometry
    with ``lastError()`` set. The processing algorithms report such failures as
    errors, so they must not be silently treated as "empty result" here.
    """
    if geom.isNull() and geom.lastError():
        raise GeometryOperationError(f"{operation} failed: {geom.lastError()}")
    return geom


def grid_union(geometries, params):
    """Union *geometries* with the grid of *params* (separate for testability)."""
    return checked(QgsGeometry.unaryUnion(geometries, params), "unaryUnion")


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
            geom = checked(geom.difference(union_cache[ids], params), "difference")
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


def make_valid_polygon(geom):
    """``native:fixgeometries`` (METHOD 1, structure) for one polygon geometry.

    Returns:
        Repaired multi-polygon, or ``None`` if nothing polygonal remains.
    """
    fixed = checked(geom.makeValid(Qgis.MakeValidMethod.Structure, False), "makeValid")
    if fixed.isNull() or fixed.isEmpty():
        return None
    fixed = polygon_parts(fixed)
    if fixed is None or fixed.type() != QgsWkbTypes.PolygonGeometry:
        return None
    return fixed


def extract_intersecting(target_layer, intersect_geoms):
    """``native:extractbylocation`` (PREDICATE intersects), same features and order.

    Mirrors ``QgsLocationBasedAlgorithm``: if the target has fewer features
    than there are intersect geometries, the target is iterated in its order;
    otherwise each intersect geometry is processed in turn and the target
    features within its bounding box are taken in provider order, skipping
    features already found. Using the same provider request keeps the output
    order identical to the algorithm for memory and file layers alike.

    Args:
        target_layer: Layer to extract from (INPUT).
        intersect_geoms: Geometries to test against (INTERSECT), in order.

    Returns:
        List of matching target features.
    """
    n_target = target_layer.featureCount()
    n_intersect = len(intersect_geoms)
    result = []
    if 0 < n_target < n_intersect:
        index = QgsSpatialIndex()
        for k, geom in enumerate(intersect_geoms):
            index.addFeature(k, geom.boundingBox())
        for feature in target_layer.getFeatures():
            target_geom = feature.geometry()
            for k in index.intersects(target_geom.boundingBox()):
                if intersect_geoms[k].intersects(target_geom):
                    result.append(feature)
                    break
        return result

    found = set()
    for geom in intersect_geoms:
        if geom.isNull():
            continue
        engine = None
        request = QgsFeatureRequest().setFilterRect(geom.boundingBox())
        for feature in target_layer.getFeatures(request):
            if feature.id() in found:
                continue
            if engine is None:
                engine = QgsGeometry.createGeometryEngine(geom.constGet())
                engine.prepareGeometry()
            if engine.intersects(feature.geometry().constGet()):
                found.add(feature.id())
                result.append(feature)
    return result


def polygonize_lines(lines, extend_distance):
    """``native:extendlines`` → ``native:fixgeometries`` (structure) → ``native:polygonize``.

    Args:
        lines: Line geometries in the order the merged layer would hold them.
        extend_distance: Extension at start and end of every line (map units).

    Returns:
        List of polygon geometries in the order produced by the algorithm.
    """
    prepared = []
    for line in lines:
        extended = line.extendLine(extend_distance, extend_distance)
        fixed = checked(extended.makeValid(Qgis.MakeValidMethod.Structure, False), "makeValid")
        if fixed.isNull() or fixed.isEmpty():
            continue
        prepared.append(fixed)
    if not prepared:
        return []
    noded = checked(QgsGeometry.unaryUnion(prepared), "unaryUnion")
    polygons = checked(QgsGeometry.polygonize([noded]), "polygonize")
    if polygons.isNull() or polygons.isEmpty():
        return []
    return list(polygons.asGeometryCollection())


def intersection_with(geom, overlay_features):
    """``native:intersection`` (no grid) of one input geometry with overlay features.

    Args:
        geom: Input polygon geometry.
        overlay_features: Overlay features (geometry + attributes), in layer order.

    Returns:
        List of ``(multi-polygon geometry, overlay feature)`` for every
        non-empty polygonal intersection, in overlay order. (The algorithm
        itself returns the same features in an undefined order: it fetches
        the candidates via ``setFilterFids`` on a hash set of IDs.)
    """
    result = []
    engine = None
    bbox = geom.boundingBox()
    for overlay in overlay_features:
        overlay_geom = overlay.geometry()
        if not overlay_geom.boundingBox().intersects(bbox):
            continue
        if engine is None:
            engine = QgsGeometry.createGeometryEngine(geom.constGet())
            engine.prepareGeometry()
        if not engine.intersects(overlay_geom.constGet()):
            continue
        inter = checked(geom.intersection(overlay_geom), "intersection")
        if inter.isNull() or inter.isEmpty():
            continue
        inter = polygon_parts(inter)
        if inter is None or inter.type() != QgsWkbTypes.PolygonGeometry:
            continue
        result.append((inter, overlay))
    return result
