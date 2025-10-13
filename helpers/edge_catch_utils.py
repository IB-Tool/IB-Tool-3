from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsField, QgsFields, QgsWkbTypes, QgsProject,
    QgsFeatureSink, QgsProcessingUtils, QgsCoordinateReferenceSystem,
    QgsMessageLog, Qgis
)
from PyQt5.QtCore import QVariant
import math

from qgis.core import QgsVectorLayer, QgsProcessing
from qgis import processing


from collections import defaultdict

from .system_utils import save_temp_layer_to_gpkg
from .logger import Logger

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
    import math
    from collections import defaultdict

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