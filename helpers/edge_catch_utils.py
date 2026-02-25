import math
from collections import defaultdict

from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsField, QgsFields, QgsWkbTypes, QgsProject,
    QgsFeatureSink, QgsProcessingUtils, QgsCoordinateReferenceSystem,
    QgsMessageLog, Qgis, QgsProcessing,
)
from qgis.PyQt.QtCore import QVariant
from qgis import processing

from .geometry_utils import shp_area2, create_empty_layer
from .system_utils import save_temp_layer_to_gpkg
from .logger import Logger
from .debug_utils import save_debug_layer
from .safe_processing import safe_processing_run


# ── EdgeCatch algorithm constants ─────────────────────────────────────────────
DEBUG_TOOL_NAME = "03_EdgeCatch"   # Sub-folder name for debug output files

ROAD_SEGMENT_LENGTH = 20    # Maximum segment length for road splitting (meters)
ROAD_BUFFER_DISTANCE = 25   # Buffer radius for building-proximity check (meters)
LINE_EXTEND_DISTANCE = 1    # Distance by which lines are extended before polygonizing (meters)
AREA_FILTER_FACTOR = 2      # Candidate polygons larger than source_area × factor are discarded

def create_shortest_lines_to_roads(point_layer, line_layer,
                                   plugin_instance=None):
    """
    Erstellt für jeden Punkt die kürzeste Linie zum nächstgelegenen Straßensegment.

    Parameters:
    -----------
    point_layer : QgsVectorLayer
        Der Punkt-Layer mit den Ausgangspunkten
    line_layer : QgsVectorLayer
        Der Linien-Layer mit den Straßengeometrien
    plugin_instance : object, optional
        Die Plugin-Instanz für Zugriff auf iface (falls benötigt)

    Returns:
    --------
    QgsVectorLayer
        Temporärer Layer mit den kürzesten Verbindungslinien
    """

    # Validierung der Input-Layer
    if not point_layer or not line_layer:
        error_msg = "Fehler: Punkt- oder Linien-Layer fehlt!"
        QgsMessageLog.logMessage(error_msg, "ShortestLines", Qgis.Critical)
        if plugin_instance and hasattr(plugin_instance, 'iface'):
            plugin_instance.iface.messageBar().pushMessage("Fehler", error_msg,
                                                           level=Qgis.Critical)
        return None

    if not point_layer.isValid() or not line_layer.isValid():
        error_msg = "Fehler: Einer der Layer ist ungültig!"
        QgsMessageLog.logMessage(error_msg, "ShortestLines", Qgis.Critical)
        if plugin_instance and hasattr(plugin_instance, 'iface'):
            plugin_instance.iface.messageBar().pushMessage("Fehler", error_msg,
                                                           level=Qgis.Critical)
        return None

    # Prüfung der Geometrietypen
    if point_layer.geometryType() != QgsWkbTypes.PointGeometry:
        error_msg = "Fehler: Der erste Layer muss ein Punkt-Layer sein!"
        QgsMessageLog.logMessage(error_msg, "ShortestLines", Qgis.Critical)
        return None

    if line_layer.geometryType() != QgsWkbTypes.LineGeometry:
        error_msg = "Fehler: Der zweite Layer muss ein Linien-Layer sein!"
        QgsMessageLog.logMessage(error_msg, "ShortestLines", Qgis.Critical)
        return None

    # Felder für den Output-Layer definieren
    fields = QgsFields()
    fields.append(QgsField("x1", QVariant.Double))
    fields.append(QgsField("y1", QVariant.Double))
    fields.append(QgsField("x2", QVariant.Double))
    fields.append(QgsField("y2", QVariant.Double))
    fields.append(QgsField("angle", QVariant.Double))
    fields.append(QgsField("distance", QVariant.Double))
    fields.append(QgsField("point_id", QVariant.Int))
    fields.append(QgsField("line_id", QVariant.Int))

    # Temporären Layer erstellen
    crs = point_layer.crs()
    temp_layer = QgsVectorLayer(
        f"LineString?crs={crs.authid()}",
        "Kürzeste Verbindungen",
        "memory"
    )

    temp_layer_data = temp_layer.dataProvider()
    temp_layer_data.addAttributes(fields)
    temp_layer.updateFields()

    # Features sammeln
    new_features = []
    error_count = 0
    processed_count = 0

    # Alle Linien-Features in eine Liste laden für bessere Performance
    line_features = list(line_layer.getFeatures())

    # Durch alle Punkt-Features iterieren
    for point_feat in point_layer.getFeatures():
        point_geom = point_feat.geometry()

        # NULL-Geometrien prüfen
        if point_geom.isNull() or point_geom.isEmpty():
            error_count += 1
            error_msg = f"Warnung: Punkt-Feature {point_feat.id()} hat keine gültige Geometrie!"
            QgsMessageLog.logMessage(error_msg, "ShortestLines", Qgis.Warning)
            continue

        # Punkt-Koordinaten extrahieren
        point = point_geom.asPoint()

        # Nächste Linie und kürzeste Distanz finden
        min_distance = float('inf')
        closest_point = None
        closest_line_id = None

        for line_feat in line_features:
            line_geom = line_feat.geometry()

            # NULL-Geometrien prüfen
            if line_geom.isNull() or line_geom.isEmpty():
                continue

            # Nächsten Punkt auf der Linie finden
            closest_point_on_line = line_geom.nearestPoint(point_geom)

            if not closest_point_on_line.isNull():
                distance = point_geom.distance(closest_point_on_line)

                if distance < min_distance:
                    min_distance = distance
                    closest_point = closest_point_on_line.asPoint()
                    closest_line_id = line_feat.id()

        # Wenn ein nächster Punkt gefunden wurde, Verbindungslinie erstellen
        if closest_point:
            # Linie vom Punkt zum nächsten Punkt auf der Straße erstellen
            line_geom = QgsGeometry.fromPolylineXY([point, closest_point])

            # Winkel berechnen (in Grad)
            dx = closest_point.x() - point.x()
            dy = closest_point.y() - point.y()
            angle_rad = math.atan2(dy, dx)
            angle_deg = math.degrees(angle_rad)
            # Winkel normalisieren auf 0-360 Grad
            if angle_deg < 0:
                angle_deg += 360

            # Feature erstellen
            feature = QgsFeature()
            feature.setGeometry(line_geom)
            feature.setAttributes([
                point.x(),  # x1
                point.y(),  # y1
                closest_point.x(),  # x2
                closest_point.y(),  # y2
                angle_deg,  # angle
                min_distance,  # distance
                point_feat.id(),  # point_id
                closest_line_id  # line_id
            ])

            new_features.append(feature)
            processed_count += 1
        else:
            error_count += 1
            error_msg = f"Warnung: Für Punkt {point_feat.id()} konnte keine nächste Linie gefunden werden!"
            QgsMessageLog.logMessage(error_msg, "ShortestLines", Qgis.Warning)

    # Features zum Layer hinzufügen
    temp_layer_data.addFeatures(new_features)

    # Layer zum Projekt hinzufügen
    #QgsProject.instance().addMapLayer(temp_layer)

    # Erfolgsmeldung
    success_msg = f"Erfolgreich {processed_count} Verbindungslinien erstellt."
    if error_count > 0:
        success_msg += f" {error_count} Features konnten nicht verarbeitet werden (siehe Log)."

    QgsMessageLog.logMessage(success_msg, "ShortestLines", Qgis.Info)
    if plugin_instance and hasattr(plugin_instance, 'iface'):
        plugin_instance.iface.messageBar().pushMessage(
            "Erfolg",
            success_msg,
            level=Qgis.Success if error_count == 0 else Qgis.Warning
        )

    return temp_layer


def filter_ortho_lines(hu_ortho, min_lines_to_keep=2):
    """
    Filtert die orthogonalen Linien basierend auf definierten Regeln.
    Gruppiert Linien die zu denselben 4 Eckpunkten eines Features gehören.
    """

    filtered_layer = QgsVectorLayer(
        f"LineString?crs={hu_ortho.crs().authid()}",
        "filtered_ortho_lines",
        "memory"
    )

    provider = filtered_layer.dataProvider()
    provider.addAttributes(hu_ortho.fields())
    filtered_layer.updateFields()

    total_input = 0
    total_output = 0

    # Sammle ALLE Linien erst mal
    all_lines = list(hu_ortho.getFeatures())
    total_input = len(all_lines)

    # Da wir wissen dass die Linien von 4 aufeinanderfolgenden Vertices kommen,
    # können wir sie in 4er-Gruppen aufteilen
    # ANNAHME: Die Linien kommen in der richtigen Reihenfolge aus create_shortest_lines_to_roads

    features_to_add = []

    # Verarbeite in 4er-Gruppen (oder was auch immer übrig ist)
    for i in range(0, len(all_lines), 4):
        group = all_lines[i:min(i + 4, len(all_lines))]

        if len(group) <= min_lines_to_keep:
            features_to_add.extend(group)
            total_output += len(group)
            continue

        # Erstelle line_data für apply_filter_rules
        line_data = []
        for line in group:
            line_data.append({
                'feature': line,
                'distance': float(line['distance']),
                'angle': float(line['angle']),
                'x1': float(line['x1']),
                'y1': float(line['y1']),
                'x2': float(line['x2']),
                'y2': float(line['y2'])
            })

        # Wende Filterregeln an
        filtered_lines = apply_filter_rules(line_data, min_lines_to_keep)

        # Füge gefilterte Features zur Liste hinzu
        for line_info in filtered_lines:
            features_to_add.append(line_info['feature'])
            total_output += 1

    # Features zum Layer hinzufügen
    if features_to_add:
        provider.addFeatures(features_to_add)

    filtered_layer.updateExtents()

    return filtered_layer


def apply_filter_rules(line_data, min_lines_to_keep):
    """
    Applies specific filter rules to a group of lines.
    """

    # CONSTANTS
    MAX_DIST = 70
    ANGLE_THRESHOLD = 2
    PARALLEL_THRESHOLD = 5
    ENDPOINT_PROXIMITY_THRESHOLD = 5  # Endpoint distance threshold in meters

    # RULE 1: Absolute maximum
    filtered = [line for line in line_data if line['distance'] < MAX_DIST]

    if not filtered:
        return []

    if len(filtered) <= min_lines_to_keep:
        return filtered

    # RULE 2: Endpoints within rectangle
    def point_in_rectangle(point, corners):
        x, y = point
        min_x = min(c[0] for c in corners)
        max_x = max(c[0] for c in corners)
        min_y = min(c[1] for c in corners)
        max_y = max(c[1] for c in corners)
        tolerance = 0.001
        return (min_x - tolerance <= x <= max_x + tolerance and
                min_y - tolerance <= y <= max_y + tolerance)

    start_points = [(line['x1'], line['y1']) for line in filtered]
    lines_to_keep = []
    lines_removed = []

    for line in filtered:
        end_point = (line['x2'], line['y2'])
        if point_in_rectangle(end_point, start_points):
            lines_removed.append(line)
        else:
            lines_to_keep.append(line)

    if len(lines_to_keep) >= min_lines_to_keep:
        filtered = lines_to_keep
    else:
        lines_removed.sort(key=lambda x: x['distance'])
        needed = min_lines_to_keep - len(lines_to_keep)
        filtered = lines_to_keep + lines_removed[:needed]

    if len(filtered) <= min_lines_to_keep:
        return filtered

    # RULE 3a: Special case - Two parallel nearby lines (check ENDPOINTS)
    lines_to_remove = set()

    for i in range(len(filtered)):
        for j in range(i + 1, len(filtered)):
            line1 = filtered[i]
            line2 = filtered[j]

            # Check if angles are similar (including opposite directions)
            angle_diff = abs(line1['angle'] - line2['angle'])

            # Handle wrap-around (e.g., 359° and 1° should be close)
            if angle_diff > 180:
                angle_diff = 360 - angle_diff

            # Also check if lines are parallel in opposite directions
            opposite_angle_diff = abs(
                abs(line1['angle'] - line2['angle']) - 180)
            if opposite_angle_diff > 180:
                opposite_angle_diff = 360 - opposite_angle_diff

            # Use the smaller angle difference (parallel or anti-parallel)
            final_angle_diff = min(angle_diff, opposite_angle_diff)

            if final_angle_diff <= ANGLE_THRESHOLD:
                # Lines have similar angles - check if ENDPOINTS are close to each other
                endpoint_dist = math.sqrt(
                    (line1['x2'] - line2['x2']) ** 2 +
                    (line1['y2'] - line2['y2']) ** 2
                )

                if endpoint_dist <= ENDPOINT_PROXIMITY_THRESHOLD:
                    # Two parallel lines with nearby endpoints found - delete the longer one
                    if line1['distance'] > line2['distance']:
                        lines_to_remove.add(i)
                    else:
                        lines_to_remove.add(j)

    # Remove marked lines, but keep minimum
    if lines_to_remove and len(filtered) - len(
            lines_to_remove) >= min_lines_to_keep:
        filtered = [line for idx, line in enumerate(filtered) if
                    idx not in lines_to_remove]

    if len(filtered) <= min_lines_to_keep:
        return filtered

    # RULE 3b: Original - All 4 lines parallel
    if len(filtered) == 4:
        angles = [line['angle'] for line in filtered]
        normalized_angles = [angle % 180 for angle in angles]
        min_angle = min(normalized_angles)
        max_angle = max(normalized_angles)

        if max_angle - min_angle <= PARALLEL_THRESHOLD:
            filtered.sort(key=lambda x: x['distance'])
            return filtered[:2]

    # RULE 4: Angle group outliers - LAST (Fine-tuning)
    def group_lines_by_angle(lines):
        """Groups lines with similar angles"""
        if not lines:
            return []
        sorted_lines = sorted(lines, key=lambda x: x['angle'])
        groups = [[sorted_lines[0]]]

        for line in sorted_lines[1:]:
            if abs(line['angle'] - groups[-1][-1]['angle']) <= ANGLE_THRESHOLD:
                groups[-1].append(line)
            else:
                groups.append([line])
        return groups

    if len(filtered) > 2:  # Only if more than minimum available
        grouped_angle = group_lines_by_angle(filtered)

        # Only apply rule if we have multiple groups AND can safely remove a group
        if len(grouped_angle) > 1:
            # Calculate average distances for each group
            group_stats = []
            for i, group in enumerate(grouped_angle):
                total_distance = sum(line['distance'] for line in group)
                avg_distance = total_distance / len(group)
                group_stats.append((i, avg_distance, group))

            # Sort by average distance (descending)
            group_stats.sort(key=lambda x: x[1], reverse=True)

            # Largest and second largest average distance
            max_group_idx, max_distance, max_group = group_stats[0]
            second_max_distance = group_stats[1][1] if len(
                group_stats) > 1 else 0

            # Check if removing the group still leaves enough lines
            remaining_lines = sum(len(group) for _, _, group in group_stats[1:])

            # MORE RESTRICTIVE CONDITIONS:
            # 1. Must have at least 2 groups
            # 2. Must keep minimum lines
            # 3. Max distance must be significantly larger (2x instead of 1.5x)
            # 4. Don't remove single-line groups unless we have plenty of lines
            if (remaining_lines >= min_lines_to_keep and
                    max_distance > 2.0 * second_max_distance and
                    len(grouped_angle) >= 3):  # Need at least 3 groups to remove one

                # Keep all groups except the one with largest average distance
                filtered = []
                for idx, (_, _, group) in enumerate(group_stats[1:]):
                    filtered.extend(group)

    return filtered


def project_point_to_line(point, line_geom):
    """
    Projiziert einen Punkt auf eine Liniengeometrie.

    Parameters:
    -----------
    point : QgsPointXY
        Der zu projizierende Punkt
    line_geom : QgsGeometry
        Die Liniengeometrie auf die projiziert wird

    Returns:
    --------
    tuple (QgsPointXY, float)
        (Projizierter Punkt, Distanz). Bei Fehler (None, inf).
    """
    point_geom = QgsGeometry.fromPointXY(point)
    closest = line_geom.nearestPoint(point_geom)
    if closest.isNull():
        return None, float('inf')
    projected = closest.asPoint()
    distance = point_geom.distance(closest)
    return QgsPointXY(projected.x(), projected.y()), distance


def extract_road_subline(foot_point_a, foot_point_b, road_features):
    """
    Führt Straßengeometrien zusammen und extrahiert die Teillinie zwischen
    zwei Fußpunkten. Robust gegenüber Multi-Feature-Segmenten und T-Kreuzungen.

    Parameters:
    -----------
    foot_point_a : QgsPointXY
        Erster Fußpunkt auf der Straße (Projektion von edge_start)
    foot_point_b : QgsPointXY
        Zweiter Fußpunkt auf der Straße (Projektion von edge_end)
    road_features : list oder QgsVectorLayer
        Straßen-Features im relevanten Bereich

    Returns:
    --------
    list of QgsPointXY
        Nur die ZWISCHEN-Vertices der Straße zwischen den Fußpunkten
        (ohne die Fußpunkte selbst). Kann leer sein bei gerader Straße.
        None bei Fehler.
    """
    # Straßengeometrien sammeln
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
        Logger.log("extract_road_subline: Keine gültigen Straßengeometrien", level="WARNING")
        return None

    # Zu einer Geometrie zusammenführen und Linien mergen
    collected = QgsGeometry.collectGeometry(geom_list)
    merged = collected.mergeLines()

    point_a_geom = QgsGeometry.fromPointXY(foot_point_a)
    point_b_geom = QgsGeometry.fromPointXY(foot_point_b)

    # Bei MultiLineString: den Linienteil finden der beiden Fußpunkten am nächsten ist
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
            Logger.log("extract_road_subline: Kein passender Linienteil gefunden", level="WARNING")
            return None
        merged = best_line

    # Distanzen entlang der Linie ermitteln
    dist_a = merged.lineLocatePoint(point_a_geom)
    dist_b = merged.lineLocatePoint(point_b_geom)

    # Reihenfolge: von A nach B entlang der Linie
    reversed_order = dist_a > dist_b
    start_dist = min(dist_a, dist_b)
    end_dist = max(dist_a, dist_b)

    # curveSubstring ist eine Methode von QgsAbstractGeometry, nicht QgsGeometry
    abstract_geom = merged.constGet()
    sub_curve = abstract_geom.curveSubstring(start_dist, end_dist)
    subline = QgsGeometry(sub_curve)

    if subline.isNull() or subline.isEmpty():
        Logger.log("extract_road_subline: curveSubstring ergab leere Geometrie", level="WARNING")
        return None

    # Alle Vertices der Teillinie extrahieren
    all_vertices = []
    for vertex in subline.vertices():
        all_vertices.append(QgsPointXY(vertex.x(), vertex.y()))

    # Erstes und letztes Vertex entfernen (das sind die re-projizierten Fußpunkte,
    # die leicht von den echten Fußpunkten abweichen können)
    if len(all_vertices) <= 2:
        intermediate = []  # Gerade Straße, keine Zwischenvertices
    else:
        intermediate = all_vertices[1:-1]

    # Reihenfolge korrigieren: Vertices von foot_a nach foot_b
    if reversed_order:
        intermediate.reverse()

    return intermediate


def build_catch_polygon(edge_start, edge_end, foot_a, foot_b, road_intermediate_vertices=None):
    """
    Baut ein Fangpolygon aus Gebäudekanten-Vertices, Fußpunkten und Straßenvertices.

    Das Polygon wird gebildet aus:
    edge_start → edge_end → foot_b → [Straßen-Zwischenvertices B→A] → foot_a → edge_start

    Parameters:
    -----------
    edge_start : QgsPointXY
        Startpunkt der Gebäudekante (auf dem Rechteck)
    edge_end : QgsPointXY
        Endpunkt der Gebäudekante (auf dem Rechteck)
    foot_a : QgsPointXY
        Fußpunkt auf der Straße bei edge_start (exakt aus Orthogonaler)
    foot_b : QgsPointXY
        Fußpunkt auf der Straße bei edge_end (exakt aus Orthogonaler)
    road_intermediate_vertices : list of QgsPointXY, optional
        Zwischen-Vertices der Straße von foot_a nach foot_b (ohne die
        Fußpunkte selbst). Kann leer/None sein bei gerader Straße.

    Returns:
    --------
    QgsGeometry oder None
        Polygon-Geometrie, oder None bei Fehler.
    """
    if road_intermediate_vertices is None:
        road_intermediate_vertices = []

    # Polygon: edge_start → edge_end → foot_b → [Straße B→A] → foot_a → schließen
    points = [edge_start, edge_end, foot_b]
    # Zwischenvertices von B nach A (umgekehrte Reihenfolge da A→B geliefert)
    points.extend(reversed(road_intermediate_vertices))
    points.append(foot_a)
    points.append(edge_start)  # Polygon schließen

    if len(points) < 4:
        return None

    polygon = QgsGeometry.fromPolygonXY([points])

    if polygon.isNull() or polygon.isEmpty():
        Logger.log("build_catch_polygon: Erzeugtes Polygon ist ungültig", level="WARNING")
        return None

    # Geometrie reparieren falls nötig
    if not polygon.isGeosValid():
        polygon = polygon.makeValid()
        if polygon.isNull() or polygon.isEmpty():
            return None

    return polygon


def delete_first_point(layer):
    from qgis.core import QgsVectorLayer, QgsFeature

    features = list(layer.getFeatures())
    if len(features) <= 1:
        return layer

    # Neuen Layer erstellen ohne das erste Feature
    new_layer = QgsVectorLayer(
        f"{layer.geometryType().name}?crs={layer.crs().authid()}", "filtered",
        "memory")
    new_layer.dataProvider().addAttributes(layer.fields())
    new_layer.updateFields()

    # Alle Features außer dem ersten hinzufügen
    new_layer.dataProvider().addFeatures(features[1:])

    return new_layer


# ── Road network preprocessing ────────────────────────────────────────────────

def _normalize_node(point):
    """Create a hashable node key with limited coordinate precision."""
    return (round(point.x(), 8), round(point.y(), 8))


def _build_minimized_lines_from_selection(road_network_sel, crs):
    """Reduce a selected road network to the minimum number of line features.

    Decomposes all polylines into vertex-to-vertex segments, removes duplicates,
    builds an adjacency graph, and reassembles the segments into chains running
    from one intersection/endpoint to the next.  Straight sequences of degree-2
    nodes are merged into a single feature; closed rings with no dedicated
    endpoint are handled in a second pass.

    Args:
        road_network_sel: QgsVectorLayer - pre-selected road line layer.
        crs: QgsCoordinateReferenceSystem - CRS for the output layer.

    Returns:
        QgsVectorLayer - road lines reassembled as minimal chains.
    """
    if road_network_sel.featureCount() == 0:
        return road_network_sel

    unique_segments = {}
    adjacency = defaultdict(set)

    for feature in road_network_sel.getFeatures():
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
        return road_network_sel

    visited_segments = set()
    result_layer = QgsVectorLayer(f"LineString?crs={crs.authid()}", "road_network_reduced", "memory")
    result_provider = result_layer.dataProvider()
    result_provider.addAttributes([QgsField("src_count", QVariant.Int)])
    result_layer.updateFields()

    def traverse_chain(start_node, next_node):
        chain = [start_node, next_node]
        prev_node = start_node
        curr_node = next_node

        while len(adjacency[curr_node]) == 2:
            candidates = [node for node in adjacency[curr_node] if node != prev_node]
            if not candidates:
                break
            forward_node = candidates[0]
            segment = tuple(sorted([curr_node, forward_node]))
            if segment in visited_segments:
                break
            chain.append(forward_node)
            prev_node = curr_node
            curr_node = forward_node

        return chain

    start_nodes = [node for node, neighbors in adjacency.items() if len(neighbors) != 2]
    if not start_nodes:
        start_nodes = [next(iter(adjacency.keys()))]

    features_to_add = []
    for start_node in start_nodes:
        for neighbor in adjacency[start_node]:
            segment = tuple(sorted([start_node, neighbor]))
            if segment in visited_segments:
                continue

            chain = traverse_chain(start_node, neighbor)
            for a, b in zip(chain[:-1], chain[1:]):
                visited_segments.add(tuple(sorted([a, b])))

            new_feature = QgsFeature(result_layer.fields())
            new_feature.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in chain]))
            new_feature["src_count"] = len(chain) - 1
            features_to_add.append(new_feature)

    # Handle closed rings that have no start/end node with degree != 2
    for segment in unique_segments:
        if segment in visited_segments:
            continue
        start_node, next_node = segment
        chain = traverse_chain(start_node, next_node)
        for a, b in zip(chain[:-1], chain[1:]):
            visited_segments.add(tuple(sorted([a, b])))

        new_feature = QgsFeature(result_layer.fields())
        new_feature.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in chain]))
        new_feature["src_count"] = len(chain) - 1
        features_to_add.append(new_feature)

    result_provider.addFeatures(features_to_add)
    return result_layer


def filter_roads_near_buildings(road_network, hu_input, segment_length, buffer_distance,
                                debug_mode=False, workspace_path=None):
    """Filter road segments to only those adjacent to building footprints.

    Splits the road network into segments of ``segment_length`` meters, stamps a
    stable ``seg_id`` attribute onto each segment, creates a symmetric buffer of
    ``buffer_distance`` around each segment, and retains only segments whose
    buffer intersects at least one building footprint.  The match is done via
    the ``seg_id`` attribute (not spatial overlap of the segments themselves) so
    that neighbouring segments outside a qualifying buffer are never accidentally
    included.

    Debug checkpoint (when ``debug_mode`` is active):

    - ``road_segs_near_buildings`` — road segments whose buffer touches a building

    Args:
        road_network: QgsVectorLayer - input road line layer.
        hu_input: QgsVectorLayer - building footprints layer.
        segment_length: float - maximum segment length in map units (meters).
        buffer_distance: float - buffer radius in map units (meters) applied
            symmetrically on both sides of each road segment.
        debug_mode: If True, saves intermediate results as numbered GeoPackages.
        workspace_path: Base path for debug output files.

    Returns:
        QgsVectorLayer - road segments that are adjacent to buildings.
    """
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name=DEBUG_TOOL_NAME)

    # Split road network into fixed-length segments
    road_segs = safe_processing_run("native:splitlinesbylength", {
        'INPUT': road_network,
        'LENGTH': segment_length,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Stamp a stable integer ID onto each segment before buffering.
    # native:buffer does not guarantee FID preservation, so a dedicated
    # attribute field is the only reliable way to join buffers back to segments.
    road_segs = safe_processing_run("native:fieldcalculator", {
        'INPUT': road_segs,
        'FIELD_NAME': 'seg_id',
        'FIELD_TYPE': 1,       # Integer
        'FIELD_LENGTH': 10,
        'FORMULA': '$id',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Create a symmetric buffer around each segment.
    # The buffer inherits the seg_id field from its source segment.
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

    # Keep only buffers that intersect at least one building footprint
    road_segs_buf_near_bdgs = safe_processing_run("native:extractbylocation", {
        'INPUT': road_segs_buf,
        'PREDICATE': [0],  # intersects
        'INTERSECT': hu_input,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Collect the seg_id values of the qualifying buffers.
    # Using the dedicated attribute field (not $id) makes the join independent
    # of any internal FID handling by the Processing framework.
    near_bdg_seg_ids = {f['seg_id'] for f in road_segs_buf_near_bdgs.getFeatures()}

    if not near_bdg_seg_ids:
        return road_segs_buf_near_bdgs  # empty layer with correct schema

    # Select exactly the matching road segments by seg_id.
    # This avoids any spatial bleed-over from the larger buffer geometry.
    id_list = ", ".join(str(sid) for sid in near_bdg_seg_ids)
    road_segs_near_bdgs = safe_processing_run("native:extractbyexpression", {
        'INPUT': road_segs,
        'EXPRESSION': f'"seg_id" IN ({id_list})',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    if debug_mode and workspace_path:
        save_debug_layer(road_segs_near_bdgs, DEBUG_TOOL_NAME, "road_segs_near_buildings", workspace_path)

    return road_segs_near_bdgs


def process_single_feature(feature, road_network, bloecke, crs,
                           debug_mode=False, workspace_path=None):
    """Run the edge-catch pipeline for one grouped building feature.

    Creates a temporary single-feature layer, projects the building outline onto
    the adjacent road network via orthogonal lines, polygonizes the combined line
    geometry, clips the result to the relevant city block, and returns only
    polygons no larger than ``AREA_FILTER_FACTOR`` times the source area.

    Args:
        feature: QgsFeature - a single grouped building polygon; must already
            have an ``Area`` attribute populated by ``shp_area2``.
        road_network: QgsVectorLayer - pre-filtered road segment layer.
        bloecke: QgsVectorLayer - city block polygon layer.
        crs: QgsCoordinateReferenceSystem - CRS used for all temporary layers.
        debug_mode: If True, saves intermediate results as numbered GeoPackages.
        workspace_path: Base path for debug output files.

    Returns:
        QgsVectorLayer with candidate polygons, or None if the feature is skipped.
    """
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name=DEBUG_TOOL_NAME)

    fid = feature.id()
    area = feature['Area']
    if area is None or area == 0:
        Logger.log(f"Feature {fid}: Area is None or 0, skipping", level="WARNING")
        return None

    # Create a temporary single-feature layer and repair its geometry
    temp_layer = QgsVectorLayer(f"Polygon?crs={crs.authid()}", f"temp_feature_{fid}", "memory")
    temp_layer.dataProvider().addFeatures([QgsFeature(feature)])
    temp_layer = safe_processing_run("native:fixgeometries", {
        'INPUT': temp_layer,
        'METHOD': 1,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Extract outline vertices (first point removed to avoid closure duplication)
    outline_points = safe_processing_run("native:extractvertices", {
        'INPUT': temp_layer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    outline_points = delete_first_point(outline_points)

    # Find the city block(s) and road segments relevant to this feature
    block_sel = safe_processing_run("native:extractbylocation", {
        'INPUT': bloecke,
        'PREDICATE': [0],  # intersects
        'INTERSECT': outline_points,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    road_network_sel = safe_processing_run("native:extractbylocation", {
        'INPUT': road_network,
        'PREDICATE': [0],  # intersects
        'INTERSECT': block_sel,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    road_network_sel = _build_minimized_lines_from_selection(road_network_sel, crs)

    # Build orthogonal projection lines from the building outline to the roads
    hu_ortho = create_shortest_lines_to_roads(outline_points, road_network_sel)
    hu_ortho_filter = filter_ortho_lines(hu_ortho)

    # Decompose the building polygon boundary into individual line segments
    group_outline = safe_processing_run("native:polygonstolines", {
        'INPUT': temp_layer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    group_outline_split = safe_processing_run("native:explodelines", {
        'INPUT': group_outline,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Merge all line inputs, extend slightly, repair geometry, then polygonize
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

    # Keep only polygons overlapping the source feature and the city block
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

    # Discard polygons larger than AREA_FILTER_FACTOR × source area
    shp_area2(polygons_in_block)
    polygons_small = safe_processing_run("native:extractbyexpression", {
        'INPUT': polygons_in_block,
        'EXPRESSION': f'"Area" < {area * AREA_FILTER_FACTOR}',  # TODO: verify operator direction
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    return polygons_small