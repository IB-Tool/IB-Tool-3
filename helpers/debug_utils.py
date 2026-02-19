"""Debug-Utilities zum Speichern fehlerhafter Features bei aktiviertem Debug-Modus."""

import os
from qgis.core import QgsVectorLayer, QgsFeature, QgsFields, QgsCoordinateReferenceSystem
from .system_utils import save_temp_layer_to_gpkg
from .logger import Logger


def save_debug_layer(layer, tool_name, step_name, workspace_path):
    """Speichert einen Layer mit fehlerhaften Features in den Debug-Ordner.

    Erstellt workspace/debug/{tool_name}/ und speichert den Layer als GeoPackage.

    Args:
        layer: QgsVectorLayer mit den zu speichernden Features.
        tool_name: Name des Tools (z.B. "GapClose") — wird zum Unterordner.
        step_name: Beschreibender Name des Schritts (z.B. "invalid_after_dissolve").
        workspace_path: Workspace-Basispfad.

    Returns:
        Pfad zur gespeicherten GeoPackage-Datei oder None bei Fehler/leerem Layer.
    """
    if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
        Logger.log(f"Debug: Layer ungültig, überspringe Speichern für {tool_name}/{step_name}", "WARNING")
        return None

    if layer.featureCount() == 0:
        Logger.log(f"Debug: Keine Features zum Speichern für {tool_name}/{step_name}", "INFO")
        return None

    debug_dir = os.path.join(workspace_path, "debug", tool_name)
    path = save_temp_layer_to_gpkg(layer, step_name, debug_dir)
    if path:
        Logger.log(f"Debug-Layer gespeichert: {path}", "INFO")
    return path


def save_debug_features(features, crs, tool_name, step_name, workspace_path, fields=None):
    """Speichert eine Liste von QgsFeature-Objekten als Debug-Layer.

    Erstellt einen temporären QgsVectorLayer aus den Features und speichert ihn.

    Args:
        features: Liste von QgsFeature-Objekten.
        crs: QgsCoordinateReferenceSystem des Layers.
        tool_name: Name des Tools — wird zum Unterordner.
        step_name: Beschreibender Name des Schritts.
        workspace_path: Workspace-Basispfad.
        fields: Optionale QgsFields-Definition. Wird aus dem ersten Feature übernommen,
                falls nicht angegeben.

    Returns:
        Pfad zur gespeicherten GeoPackage-Datei oder None bei Fehler/leerer Liste.
    """
    if not features:
        Logger.log(f"Debug: Keine Features zum Speichern für {tool_name}/{step_name}", "INFO")
        return None

    if fields is None:
        fields = features[0].fields()

    geom_type = "Polygon"
    first_geom = features[0].geometry()
    if not first_geom.isNull():
        wkb = first_geom.wkbType()
        # Einfache Zuordnung der häufigsten Typen
        type_map = {1: "Point", 2: "LineString", 3: "Polygon",
                    4: "MultiPoint", 5: "MultiLineString", 6: "MultiPolygon"}
        geom_type = type_map.get(wkb, "Polygon")

    mem_layer = QgsVectorLayer(f"{geom_type}?crs={crs.authid()}", step_name, "memory")
    provider = mem_layer.dataProvider()
    provider.addAttributes(fields)
    mem_layer.updateFields()
    provider.addFeatures(features)

    return save_debug_layer(mem_layer, tool_name, step_name, workspace_path)
