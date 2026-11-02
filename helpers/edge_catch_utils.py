import math
from collections import defaultdict
from typing import List, Optional, Tuple

from qgis.core import (
    Qgis, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsField, QgsFields, QgsWkbTypes,
    QgsCoordinateReferenceSystem, QgsMemoryProviderUtils, QgsProcessing,
)
from qgis.PyQt.QtCore import QMetaType

from .geometry_utils import shp_area2
from .logger import Logger
from .ortho_line_filter import _filter_ortho_items, filter_ortho_lines
from .debug_utils import save_debug_layer
from .overlay_utils import (
    extract_intersecting,
    intersection_with,
    make_valid_polygon,
    polygonize_lines,
)
from .processing_context import heartbeat
from .safe_processing import safe_processing_run


# ── EdgeCatch algorithm constants ─────────────────────────────────────────────
DEBUG_TOOL_NAME = "05_EdgeCatch"   # Sub-folder name for debug output files

ROAD_SEGMENT_LENGTH = 20    # Maximum segment length for road splitting (meters)
ROAD_BUFFER_DISTANCE = 25   # Buffer radius for building-proximity check (meters)
LINE_EXTEND_DISTANCE = 1    # Distance by which lines are extended before polygonizing (meters)
AREA_FILTER_FACTOR = 2      # Candidate polygons larger than source_area × factor are discarded
ROAD_BLOCK_TOLERANCE = 0.1  # Roads within this distance of a block count as its roads (meters)


def create_shortest_lines_to_roads(
    point_layer: QgsVectorLayer,
    line_layer: QgsVectorLayer,
    plugin_instance=None,
) -> Optional[QgsVectorLayer]:
    """Create the shortest connection line from each point to the nearest road segment.

    Args:
        point_layer: QgsVectorLayer containing the source points.
        line_layer: QgsVectorLayer containing road line geometries.
        plugin_instance: Optional plugin instance for legacy iface access.
            Unused in the core pipeline.

    Returns:
        Temporary QgsVectorLayer with the shortest connection lines, or None
        on validation failure.
    """
    if not point_layer or not line_layer:
        Logger.log("Point or line layer is missing!", level="CRITICAL")
        return None

    if not point_layer.isValid() or not line_layer.isValid():
        Logger.log("One of the input layers is invalid!", level="CRITICAL")
        return None

    if point_layer.geometryType() != QgsWkbTypes.PointGeometry:
        Logger.log("The first layer must be a point layer!", level="CRITICAL")
        return None

    if line_layer.geometryType() != QgsWkbTypes.LineGeometry:
        Logger.log("The second layer must be a line layer!", level="CRITICAL")
        return None

    fields = QgsFields()
    fields.append(QgsField("x1", QMetaType.Double))
    fields.append(QgsField("y1", QMetaType.Double))
    fields.append(QgsField("x2", QMetaType.Double))
    fields.append(QgsField("y2", QMetaType.Double))
    fields.append(QgsField("angle", QMetaType.Double))
    fields.append(QgsField("distance", QMetaType.Double))
    fields.append(QgsField("point_id", QMetaType.Int))
    fields.append(QgsField("line_id", QMetaType.Int))

    crs = point_layer.crs()
    temp_layer = QgsVectorLayer(
        f"LineString?crs={crs.authid()}",
        "shortest_connections",
        "memory"
    )

    temp_layer_data = temp_layer.dataProvider()
    temp_layer_data.addAttributes(fields)
    temp_layer.updateFields()

    new_features = []
    for line_geom, attributes in _shortest_connections(
            [(f.id(), f.geometry()) for f in point_layer.getFeatures()],
            [(f.id(), f.geometry()) for f in line_layer.getFeatures()]):
        feature = QgsFeature()
        feature.setGeometry(line_geom)
        feature.setAttributes(attributes)
        new_features.append(feature)
    temp_layer_data.addFeatures(new_features)
    return temp_layer


def _shortest_connections(points: list, lines: list) -> list:
    """Core of :func:`create_shortest_lines_to_roads` on plain lists.

    Args:
        points: ``(point_id, point geometry)`` in order.
        lines: ``(line_id, line geometry)`` in order; on equal distance the
            first line wins.

    Returns:
        List of ``(connection line geometry, attributes)`` with attributes
        ``[x1, y1, x2, y2, angle, distance, point_id, line_id]``.
    """
    result = []
    error_count = 0
    for point_id, point_geom in points:
        if point_geom.isNull() or point_geom.isEmpty():
            error_count += 1
            Logger.log(f"Point feature {point_id} has no valid geometry.", level="WARNING")
            continue

        point = point_geom.asPoint()
        min_distance = float('inf')
        closest_point = None
        closest_line_id = None

        for line_id, line_geom in lines:
            if line_geom.isNull() or line_geom.isEmpty():
                continue
            closest_point_on_line = line_geom.nearestPoint(point_geom)
            if not closest_point_on_line.isNull():
                distance = point_geom.distance(closest_point_on_line)
                if distance < min_distance:
                    min_distance = distance
                    closest_point = closest_point_on_line.asPoint()
                    closest_line_id = line_id

        if closest_point:
            dx = closest_point.x() - point.x()
            dy = closest_point.y() - point.y()
            angle_deg = math.degrees(math.atan2(dy, dx))
            if angle_deg < 0:
                angle_deg += 360
            result.append((QgsGeometry.fromPolylineXY([point, closest_point]),
                           [point.x(), point.y(), closest_point.x(), closest_point.y(),
                            angle_deg, min_distance, point_id, closest_line_id]))
        else:
            error_count += 1
            Logger.log(f"No nearest line found for point {point_id}.", level="WARNING")

    if error_count > 0:
        Logger.log(
            f"Created {len(result)} connection lines. {error_count} features could not be processed (see log).",
            level="WARNING",
        )
    return result


def project_point_to_line(
    point: QgsPointXY,
    line_geom: QgsGeometry,
) -> Tuple[Optional[QgsPointXY], float]:
    """Project a point onto a line geometry.

    Args:
        point: QgsPointXY to project.
        line_geom: QgsGeometry to project onto.

    Returns:
        Tuple of (projected QgsPointXY, distance). Returns (None, inf) on failure.
    """
    point_geom = QgsGeometry.fromPointXY(point)
    closest = line_geom.nearestPoint(point_geom)
    if closest.isNull():
        return None, float('inf')
    projected = closest.asPoint()
    distance = point_geom.distance(closest)
    return QgsPointXY(projected.x(), projected.y()), distance


def extract_road_subline(
    foot_point_a: QgsPointXY,
    foot_point_b: QgsPointXY,
    road_features,
) -> Optional[List[QgsPointXY]]:
    """Extract the intermediate road vertices between two foot points.

    Merges road geometries in the relevant area and extracts the sub-curve
    between ``foot_point_a`` and ``foot_point_b``. Robust against multi-feature
    segments and T-junctions.

    Args:
        foot_point_a: First foot point on the road (projection of edge_start).
        foot_point_b: Second foot point on the road (projection of edge_end).
        road_features: Road features (QgsVectorLayer or iterable of QgsFeature)
            in the relevant area.

    Returns:
        List of intermediate QgsPointXY vertices between the two foot points
        (excluding the foot points themselves). Returns an empty list for a
        straight road, or None on failure.
    """
    geom_list = []
    if hasattr(road_features, 'getFeatures'):
        features = road_features.getFeatures()
    else:
        features = road_features

    for feat in features:
        geom = feat.geometry()
        if not geom.isNull() and not geom.isEmpty():
            geom_list.append(geom)

    if not geom_list:
        Logger.log("extract_road_subline: No valid road geometries found.", level="WARNING")
        return None

    collected = QgsGeometry.collectGeometry(geom_list)
    merged = collected.mergeLines()

    point_a_geom = QgsGeometry.fromPointXY(foot_point_a)
    point_b_geom = QgsGeometry.fromPointXY(foot_point_b)

    if merged.isMultipart():
        best_line = None
        best_total_dist = float('inf')
        for part in merged.asGeometryCollection():
            if part.isNull() or part.isEmpty():
                continue
            dist_a = part.distance(point_a_geom)
            dist_b = part.distance(point_b_geom)
            total = dist_a + dist_b
            if total < best_total_dist:
                best_total_dist = total
                best_line = part
        if best_line is None:
            Logger.log("extract_road_subline: No matching line part found.", level="WARNING")
            return None
        merged = best_line

    dist_a = merged.lineLocatePoint(point_a_geom)
    dist_b = merged.lineLocatePoint(point_b_geom)

    reversed_order = dist_a > dist_b
    start_dist = min(dist_a, dist_b)
    end_dist = max(dist_a, dist_b)

    abstract_geom = merged.constGet()
    sub_curve = abstract_geom.curveSubstring(start_dist, end_dist)
    subline = QgsGeometry(sub_curve)

    if subline.isNull() or subline.isEmpty():
        Logger.log("extract_road_subline: curveSubstring returned empty geometry.", level="WARNING")
        return None

    all_vertices = [QgsPointXY(v.x(), v.y()) for v in subline.vertices()]

    # Strip the re-projected foot points (first and last vertex)
    intermediate = [] if len(all_vertices) <= 2 else all_vertices[1:-1]

    if reversed_order:
        intermediate.reverse()

    return intermediate


def build_catch_polygon(
    edge_start: QgsPointXY,
    edge_end: QgsPointXY,
    foot_a: QgsPointXY,
    foot_b: QgsPointXY,
    road_intermediate_vertices: Optional[List[QgsPointXY]] = None,
) -> Optional[QgsGeometry]:
    """Build a catch polygon from building edge vertices, foot points, and road vertices.

    The polygon ring follows:
    edge_start → edge_end → foot_b → [road vertices B→A] → foot_a → edge_start

    Args:
        edge_start: Start vertex of the building edge (on the bounding rectangle).
        edge_end: End vertex of the building edge (on the bounding rectangle).
        foot_a: Foot point on the road at edge_start (from orthogonal projection).
        foot_b: Foot point on the road at edge_end (from orthogonal projection).
        road_intermediate_vertices: Intermediate road vertices from foot_a to
            foot_b (excluding foot points). Pass None or [] for a straight road.

    Returns:
        QgsGeometry polygon, or None on failure.
    """
    if road_intermediate_vertices is None:
        road_intermediate_vertices = []

    points = [edge_start, edge_end, foot_b]
    points.extend(reversed(road_intermediate_vertices))
    points.append(foot_a)
    points.append(edge_start)

    if len(points) < 4:
        return None

    polygon = QgsGeometry.fromPolygonXY([points])

    if polygon.isNull() or polygon.isEmpty():
        Logger.log("build_catch_polygon: Created polygon is invalid.", level="WARNING")
        return None

    if not polygon.isGeosValid():
        polygon = polygon.makeValid()
        if polygon.isNull() or polygon.isEmpty():
            return None

    return polygon


def delete_first_point(layer: QgsVectorLayer) -> QgsVectorLayer:
    """Return a copy of the layer with its first feature removed.

    Args:
        layer: QgsVectorLayer to process.

    Returns:
        New QgsVectorLayer without the first feature. Returns the original
        layer unchanged if it has one or fewer features.
    """
    from qgis.core import QgsVectorLayer

    features = list(layer.getFeatures())
    if len(features) <= 1:
        return layer

    new_layer = QgsVectorLayer(
        f"{layer.geometryType().name}?crs={layer.crs().authid()}", "filtered",
        "memory")
    new_layer.dataProvider().addAttributes(layer.fields())
    new_layer.updateFields()

    new_layer.dataProvider().addFeatures(features[1:])

    return new_layer


# ── Road network preprocessing ────────────────────────────────────────────────

def _normalize_node(point: QgsPointXY) -> Tuple[float, float]:
    """Create a hashable node key with limited coordinate precision."""
    return (round(point.x(), 8), round(point.y(), 8))


def _build_minimized_lines_from_selection(
    road_network_sel: QgsVectorLayer,
    crs: QgsCoordinateReferenceSystem,
) -> QgsVectorLayer:
    """Reduce a selected road network to the minimum number of line features.

    Decomposes all polylines into vertex-to-vertex segments, removes duplicates,
    builds an adjacency graph, and reassembles the segments into chains running
    from one intersection/endpoint to the next. Straight sequences of degree-2
    nodes are merged into a single feature; closed rings with no dedicated
    endpoint are handled in a second pass.

    Args:
        road_network_sel: QgsVectorLayer — pre-selected road line layer.
        crs: QgsCoordinateReferenceSystem — CRS for the output layer.

    Returns:
        QgsVectorLayer — road lines reassembled as minimal chains.
    """
    if road_network_sel.featureCount() == 0:
        return road_network_sel

    chains = _minimized_chains(road_network_sel.getFeatures())
    if chains is None:
        return road_network_sel

    result_layer = QgsVectorLayer(f"LineString?crs={crs.authid()}", "road_network_reduced", "memory")
    result_provider = result_layer.dataProvider()
    result_provider.addAttributes([QgsField("src_count", QMetaType.Int)])
    result_layer.updateFields()
    features_to_add = []
    for chain in chains:
        new_feature = QgsFeature(result_layer.fields())
        new_feature.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in chain]))
        new_feature["src_count"] = len(chain) - 1
        features_to_add.append(new_feature)
    result_provider.addFeatures(features_to_add)
    return result_layer


def _minimized_chains(features) -> Optional[list]:
    """Core of :func:`_build_minimized_lines_from_selection` on an iterable of features.

    Returns:
        List of node chains (lists of ``(x, y)``) in output order, or ``None``
        if no usable segment exists (the caller then keeps the input lines).
    """
    unique_segments = {}
    adjacency = defaultdict(set)

    for feature in features:
        geometry = feature.geometry()
        if not geometry or geometry.isEmpty():
            continue

        parts = geometry.asMultiPolyline() if geometry.isMultipart() else [geometry.asPolyline()]

        for part in parts:
            if len(part) < 2:
                continue
            for start, end in zip(part[:-1], part[1:]):
                start_key = _normalize_node(start)
                end_key = _normalize_node(end)
                if start_key == end_key:
                    continue

                segment_key = tuple(sorted([start_key, end_key]))
                if segment_key in unique_segments:
                    continue

                unique_segments[segment_key] = (start_key, end_key)
                adjacency[start_key].add(end_key)
                adjacency[end_key].add(start_key)

    if not unique_segments:
        return None

    visited_segments = set()

    def _traverse_chain(start_node, next_node):
        """Follow a chain of degree-2 nodes from start_node through next_node."""
        chain = [start_node, next_node]
        prev_node = start_node
        curr_node = next_node
        local_visited = {tuple(sorted([start_node, next_node]))}

        while len(adjacency[curr_node]) == 2:
            candidates = [node for node in adjacency[curr_node] if node != prev_node]
            if not candidates:
                break
            forward_node = candidates[0]
            segment = tuple(sorted([curr_node, forward_node]))
            if segment in visited_segments or segment in local_visited:
                break
            local_visited.add(segment)
            chain.append(forward_node)
            prev_node = curr_node
            curr_node = forward_node

        return chain

    start_nodes = [node for node, neighbors in adjacency.items() if len(neighbors) != 2]
    if not start_nodes:
        start_nodes = [next(iter(adjacency.keys()))]

    chains = []
    for start_node in start_nodes:
        for neighbor in adjacency[start_node]:
            segment = tuple(sorted([start_node, neighbor]))
            if segment in visited_segments:
                continue

            chain = _traverse_chain(start_node, neighbor)
            for a, b in zip(chain[:-1], chain[1:]):
                visited_segments.add(tuple(sorted([a, b])))
            chains.append(chain)

    # Handle closed rings that have no start/end node with degree != 2
    for segment in unique_segments:
        if segment in visited_segments:
            continue
        start_node, next_node = segment
        chain = _traverse_chain(start_node, next_node)
        for a, b in zip(chain[:-1], chain[1:]):
            visited_segments.add(tuple(sorted([a, b])))
        chains.append(chain)

    return chains


def filter_roads_near_buildings(
    road_network: QgsVectorLayer,
    hu_input: QgsVectorLayer,
    segment_length: float,
    buffer_distance: float,
    debug_mode: bool = False,
    workspace_path: Optional[str] = None,
) -> QgsVectorLayer:
    """Filter road segments to only those adjacent to building footprints.

    Splits the road network into segments of ``segment_length`` meters, stamps a
    stable ``seg_id`` attribute onto each segment, creates a symmetric buffer of
    ``buffer_distance`` around each segment, and retains only segments whose
    buffer intersects at least one building footprint. The match is done via
    the ``seg_id`` attribute (not spatial overlap of the segments themselves) so
    that neighbouring segments outside a qualifying buffer are never accidentally
    included.

    Debug checkpoint (when ``debug_mode`` is active):

    - ``road_segs_near_buildings`` — road segments whose buffer touches a building

    Args:
        road_network: QgsVectorLayer — input road line layer.
        hu_input: QgsVectorLayer — building footprints layer.
        segment_length: Maximum segment length in map units (meters).
        buffer_distance: Buffer radius in map units (meters) applied
            symmetrically on both sides of each road segment.
        debug_mode: If True, saves intermediate results as numbered GeoPackages.
        workspace_path: Base path for debug output files.

    Returns:
        QgsVectorLayer — road segments that are adjacent to buildings.
    """
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name=DEBUG_TOOL_NAME)

    road_segs = safe_processing_run("native:splitlinesbylength", {
        'INPUT': road_network,
        'LENGTH': segment_length,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    road_segs = safe_processing_run("native:fieldcalculator", {
        'INPUT': road_segs,
        'FIELD_NAME': 'seg_id',
        'FIELD_TYPE': 1,
        'FIELD_LENGTH': 10,
        'FORMULA': '$id',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    road_segs_buf = safe_processing_run("native:buffer", {
        'INPUT': road_segs,
        'DISTANCE': buffer_distance,
        'SEGMENTS': 5,
        'END_CAP_STYLE': 0,
        'JOIN_STYLE': 0,
        'MITER_LIMIT': 2,
        'DISSOLVE': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    road_segs_buf_near_bdgs = safe_processing_run("native:extractbylocation", {
        'INPUT': road_segs_buf,
        'PREDICATE': [0],  # intersects
        'INTERSECT': hu_input,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    near_bdg_seg_ids = {f['seg_id'] for f in road_segs_buf_near_bdgs.getFeatures()}

    if not near_bdg_seg_ids:
        return road_segs_buf_near_bdgs

    # Same result as native:extractbyexpression '"seg_id" IN (...)' (segments
    # in source order, new ids 1..n), but a set lookup instead of evaluating an
    # IN list of thousands of ids per segment (3 s on the largest sample partition).
    road_segs_near_bdgs = _copy_features_where(
        road_segs, lambda f: f['seg_id'] in near_bdg_seg_ids, "road_segs_near_bdgs")

    if debug_mode and workspace_path:
        save_debug_layer(road_segs_near_bdgs, DEBUG_TOOL_NAME, "road_segs_near_buildings", workspace_path)

    return road_segs_near_bdgs


def _copy_features_where(layer: QgsVectorLayer, keep, name: str) -> QgsVectorLayer:
    """Memory copy of the features of *layer* for which ``keep(feature)`` is true.

    Keeps source order, fields, geometry type and CRS; the copies get new ids
    1..n like a processing ``TEMPORARY_OUTPUT``.
    """
    out = QgsMemoryProviderUtils.createMemoryLayer(name, layer.fields(), layer.wkbType(),
                                                   layer.crs())
    kept = [f for f in layer.getFeatures() if keep(f)]
    if kept and not out.dataProvider().addFeatures(kept):
        raise RuntimeError(f"{name}: features could not be written")
    out.updateExtents()
    return out


def select_roads_near_blocks(
    road_network: QgsVectorLayer,
    blocks: QgsVectorLayer,
    dbg: Optional[dict] = None,
) -> QgsVectorLayer:
    """Select the road segments of the given blocks, with a small tolerance.

    A road counts as a road of the block if it lies within
    ``ROAD_BLOCK_TOLERANCE`` of the block. Block vertices come from
    polygonize/noding and carry floating-point noise (< 1e-9 m), so an exact
    ``intersects`` test flips for roads that end on the block boundary. The
    blocks are buffered by the tolerance for the selection only; the
    clipping to the block later in ``process_single_feature`` stays exact.

    ``native:extractbylocation`` with ``intersects`` keeps the input order,
    which matters because ``_build_minimized_lines_from_selection`` chains
    segments in iteration order.

    Args:
        road_network: Road segment line layer.
        blocks: Block polygon layer (usually the blocks touched by one rectangle).
        dbg: Optional debug kwargs for ``safe_processing_run``.

    Returns:
        QgsVectorLayer with the selected road segments in input order.
    """
    dbg = dbg or {}
    blocks_buffered = safe_processing_run("native:buffer", {
        'INPUT': blocks,
        'DISTANCE': ROAD_BLOCK_TOLERANCE,
        'SEGMENTS': 5,
        'END_CAP_STYLE': 0,
        'JOIN_STYLE': 0,
        'MITER_LIMIT': 2,
        'DISSOLVE': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **dbg)['OUTPUT']
    return safe_processing_run("native:extractbylocation", {
        'INPUT': road_network,
        'PREDICATE': [0],  # intersects
        'INTERSECT': blocks_buffered,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **dbg)['OUTPUT']


def process_single_feature(
    feature: QgsFeature,
    road_network: QgsVectorLayer,
    bloecke: QgsVectorLayer,
    crs: QgsCoordinateReferenceSystem,
    debug_mode: bool = False,
    workspace_path: Optional[str] = None,
) -> Optional[QgsVectorLayer]:
    """Run the edge-catch pipeline for one grouped building feature.

    Creates a temporary single-feature layer, projects the building outline onto
    the adjacent road network via orthogonal lines, polygonizes the combined line
    geometry, clips the result to the relevant city block, and returns only
    polygons no larger than ``AREA_FILTER_FACTOR`` times the source area.

    Args:
        feature: QgsFeature — a single grouped building polygon; must already
            have an ``Area`` attribute populated by ``shp_area2``.
        road_network: QgsVectorLayer — pre-filtered road segment layer.
        bloecke: QgsVectorLayer — city block polygon layer.
        crs: QgsCoordinateReferenceSystem — CRS used for all temporary layers.
        debug_mode: If True, saves intermediate results as numbered GeoPackages.
        workspace_path: Base path for debug output files.

    Returns:
        QgsVectorLayer with candidate polygons, or None if the feature is skipped.
    """
    fid = feature.id()
    area = feature['Area']
    # A missing value is None or a NULL QVariant, depending on QGIS version and
    # data provider (shp_area2 leaves Area empty for invalid geometries)
    if area is None or (hasattr(area, "isNull") and area.isNull()) or area == 0:
        Logger.log(f"Feature {fid}: Area is None or 0, skipping", level="WARNING")
        return None

    heartbeat()   # keep the QGIS UI responsive (no processing.run on the fast path)
    try:
        return _process_single_feature_geometry(feature, area, road_network, bloecke, crs)
    except Exception as e:  # pylint: disable=broad-exception-caught
        Logger.log(f"Feature {fid}: geometry-based EdgeCatch failed ({e}); "
                   f"using the processing algorithms", level="WARNING")
        return _process_single_feature_processing(
            feature, area, road_network, bloecke, crs, debug_mode, workspace_path)


def _outline_points(fixed: QgsGeometry) -> list:
    """``native:extractvertices`` + ``delete_first_point``: ring vertices without the first."""
    points = [QgsGeometry.fromPointXY(QgsPointXY(v.x(), v.y())) for v in fixed.vertices()]
    return points[1:] if len(points) > 1 else points


def _outline_segments(fixed: QgsGeometry) -> list:
    """``native:polygonstolines`` + ``native:explodelines``: every ring segment in order."""
    segments = []
    for polygon in fixed.asGeometryCollection():
        for ring in polygon.asPolygon():
            for start, end in zip(ring[:-1], ring[1:]):
                segments.append(QgsGeometry.fromPolylineXY([start, end]))
    return segments


def _process_single_feature_geometry(
    feature: QgsFeature,
    area: float,
    road_network: QgsVectorLayer,
    bloecke: QgsVectorLayer,
    crs: QgsCoordinateReferenceSystem,
) -> Optional[QgsVectorLayer]:
    """Geometry-based implementation of :func:`process_single_feature`.

    Same steps as the processing version, each replaced by its QgsGeometry
    equivalent from ``overlay_utils`` (verified per step on 1,926 sample
    rectangles: identical features; see ``scripts/edge_catch_harness.py``).
    Avoids ~16 processing calls per rectangle (≈4 ms overhead each).

    Raises:
        GeometryOperationError: if a GEOS operation fails (caller falls back).
    """
    fixed = make_valid_polygon(feature.geometry())
    if fixed is None:
        raise ValueError("rectangle geometry could not be repaired")
    outline_points = _outline_points(fixed)

    # blocks touched by the rectangle's vertices, roads of these blocks (10 cm tolerance)
    block_features = extract_intersecting(bloecke, outline_points)
    block_buffers = [
        f.geometry().buffer(ROAD_BLOCK_TOLERANCE, 5, Qgis.EndCapStyle.Round, Qgis.JoinStyle.Round, 2)
        for f in block_features
    ]
    selected_roads = extract_intersecting(road_network, block_buffers)
    chains = _minimized_chains(selected_roads) if selected_roads else None
    if chains is None:      # no usable segment: the selected road lines are used as they are
        road_lines = [f.geometry() for f in selected_roads]
    else:
        road_lines = [QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in chain])
                      for chain in chains]

    # memory-layer feature IDs start at 1 → same point_id / line_id as the layer version
    connections = _shortest_connections(list(enumerate(outline_points, start=1)),
                                        list(enumerate(road_lines, start=1)))
    ortho_lines = _filter_ortho_items(connections)     # kept connection line geometries

    lines = road_lines + ortho_lines + _outline_segments(fixed)
    polygons = polygonize_lines(lines, LINE_EXTEND_DISTANCE)

    # polygons touching the rectangle (extractbylocation with one intersect geometry)
    engine = QgsGeometry.createGeometryEngine(fixed.constGet())
    engine.prepareGeometry()
    rect_bbox = fixed.boundingBox()
    polygons_in_feature = [p for p in polygons
                           if p.boundingBox().intersects(rect_bbox) and engine.intersects(p.constGet())]

    # clip to the blocks, repair, keep pieces smaller than AREA_FILTER_FACTOR × rectangle
    fields = QgsFields(bloecke.fields())
    existing = {f.name().lower(): i for i, f in enumerate(fields)}
    if "area" in existing:          # shp_area2 writes into an existing (case-insensitive) field
        area_index = existing["area"]
    else:
        fields.append(QgsField("Area", QMetaType.Double))
        area_index = fields.count() - 1
    result = QgsVectorLayer(f"MultiPolygon?crs={crs.authid()}", "polygons_small", "memory")
    result.dataProvider().addAttributes(fields.toList())
    result.updateFields()

    out_features = []
    max_area = area * AREA_FILTER_FACTOR
    for polygon in polygons_in_feature:
        for piece, block in intersection_with(polygon, block_features):
            piece = make_valid_polygon(piece)
            if piece is None or not piece.isGeosValid():
                continue        # shp_area2 leaves Area NULL → excluded by the area filter
            piece_area = piece.area()
            if not piece_area < max_area:
                continue
            attributes = list(block.attributes())
            if area_index < len(attributes):
                attributes[area_index] = piece_area
            else:
                attributes.append(piece_area)
            out = QgsFeature(result.fields())
            out.setGeometry(piece)
            out.setAttributes(attributes)
            out_features.append(out)
    result.dataProvider().addFeatures(out_features)
    return result


def _process_single_feature_processing(
    feature: QgsFeature,
    area: float,
    road_network: QgsVectorLayer,
    bloecke: QgsVectorLayer,
    crs: QgsCoordinateReferenceSystem,
    debug_mode: bool = False,
    workspace_path: Optional[str] = None,
) -> Optional[QgsVectorLayer]:
    """Original processing-based implementation (fallback of :func:`process_single_feature`)."""
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name=DEBUG_TOOL_NAME)
    fid = feature.id()

    temp_layer = QgsVectorLayer(f"Polygon?crs={crs.authid()}", f"temp_feature_{fid}", "memory")
    temp_layer.dataProvider().addFeatures([QgsFeature(feature)])
    temp_layer = safe_processing_run("native:fixgeometries", {
        'INPUT': temp_layer,
        'METHOD': 1,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    outline_points = safe_processing_run("native:extractvertices", {
        'INPUT': temp_layer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    outline_points = delete_first_point(outline_points)

    block_sel = safe_processing_run("native:extractbylocation", {
        'INPUT': bloecke,
        'PREDICATE': [0],  # intersects
        'INTERSECT': outline_points,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    road_network_sel = select_roads_near_blocks(road_network, block_sel, _dbg)
    road_network_sel = _build_minimized_lines_from_selection(road_network_sel, crs)

    hu_ortho = create_shortest_lines_to_roads(outline_points, road_network_sel)
    hu_ortho_filter = filter_ortho_lines(hu_ortho)

    group_outline = safe_processing_run("native:polygonstolines", {
        'INPUT': temp_layer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    group_outline_split = safe_processing_run("native:explodelines", {
        'INPUT': group_outline,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    lines_merged = safe_processing_run("native:mergevectorlayers", {
        'LAYERS': [road_network_sel, hu_ortho_filter, group_outline_split],
        'CRS': crs,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    lines_extended = safe_processing_run("native:extendlines", {
        'INPUT': lines_merged,
        'START_DISTANCE': LINE_EXTEND_DISTANCE,
        'END_DISTANCE': LINE_EXTEND_DISTANCE,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    lines_fixed = safe_processing_run("native:fixgeometries", {
        'INPUT': lines_extended,
        'METHOD': 1,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    polygons = safe_processing_run("native:polygonize", {
        'INPUT': lines_fixed,
        'KEEP_FIELDS': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    polygons_in_feature = safe_processing_run("native:extractbylocation", {
        'INPUT': polygons,
        'PREDICATE': [0],  # intersects
        'INTERSECT': temp_layer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    polygons_in_block = safe_processing_run("native:intersection", {
        'INPUT': polygons_in_feature,
        'OVERLAY': block_sel,
        'INPUT_FIELDS': [],
        'OVERLAY_FIELDS': [],
        'OVERLAY_FIELDS_PREFIX': '',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        'GRID_SIZE': None
    }, **_dbg)['OUTPUT']
    polygons_in_block = safe_processing_run("native:fixgeometries", {
        'INPUT': polygons_in_block,
        'METHOD': 1,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    shp_area2(polygons_in_block)
    polygons_small = safe_processing_run("native:extractbyexpression", {
        'INPUT': polygons_in_block,
        'EXPRESSION': f'"Area" < {area * AREA_FILTER_FACTOR}',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    return polygons_small
