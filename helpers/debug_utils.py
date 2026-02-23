"""Debug-Utilities zum Speichern fehlerhafter Features bei aktiviertem Debug-Modus."""

import os
from qgis.core import QgsVectorLayer, QgsFeature, QgsFields, QgsCoordinateReferenceSystem
from .system_utils import save_temp_layer_to_gpkg
from .logger import Logger


def _next_debug_index(debug_dir):
    """Ermittelt den nächsten laufenden Index für Debug-Dateien im Zielordner.

    Zählt alle bereits vorhandenen .gpkg-Dateien im Ordner. So entstehen
    durchnummerierte Dateien, die im GIS nach Nummer sortiert den
    Verarbeitungsablauf widerspiegeln.

    Args:
        debug_dir: Pfad zum Tool-spezifischen Debug-Unterordner.

    Returns:
        Nächster freier Index (int, beginnend bei 1).
    """
    if not os.path.isdir(debug_dir):
        return 1
    existing = [f for f in os.listdir(debug_dir) if f.lower().endswith(".gpkg")]
    return len(existing) + 1


def save_debug_layer(layer, tool_name, step_name, workspace_path, is_error=False):
    """Speichert einen Layer als nummerierte Debug-Datei in den Tool-Unterordner.

    Erstellt workspace/debug/{tool_name}/ und speichert den Layer als GeoPackage.
    Der Dateiname erhält automatisch ein laufendes Nummernpräfix sowie – bei
    Fehler-Snapshots – das Suffix ``_err``:

    - Checkpoint:   ``001_after_dissolve.gpkg``
    - Fehlerschritt: ``002_failed_buffer_err.gpkg``

    Args:
        layer: QgsVectorLayer mit den zu speichernden Features.
        tool_name: Name des Tools (z.B. "GapClose") — wird zum Unterordner.
        step_name: Beschreibender Schrittname (z.B. "after_dissolve").
        workspace_path: Workspace-Basispfad.
        is_error: True → Datei erhält Suffix ``_err`` (fehlgeschlagener Schritt).

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
    idx = _next_debug_index(debug_dir)
    suffix = "_err" if is_error else ""
    filename = f"{idx:03d}_{step_name}{suffix}"

    path = save_temp_layer_to_gpkg(layer, filename, debug_dir)
    if path:
        Logger.log(f"Debug-Layer gespeichert: {path}", "INFO")
    return path


def save_debug_features(features, crs, tool_name, step_name, workspace_path, fields=None, is_error=False):
    """Speichert eine Liste von QgsFeature-Objekten als nummerierte Debug-Datei.

    Erstellt einen temporären QgsVectorLayer aus den Features und speichert ihn.
    Dateinamen-Konvention identisch zu ``save_debug_layer``.

    Args:
        features: Liste von QgsFeature-Objekten.
        crs: QgsCoordinateReferenceSystem des Layers.
        tool_name: Name des Tools — wird zum Unterordner.
        step_name: Beschreibender Schrittname.
        workspace_path: Workspace-Basispfad.
        fields: Optionale QgsFields-Definition. Wird aus dem ersten Feature übernommen,
                falls nicht angegeben.
        is_error: True → Datei erhält Suffix ``_err`` (fehlgeschlagener Schritt).

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

    return save_debug_layer(mem_layer, tool_name, step_name, workspace_path, is_error=is_error)
