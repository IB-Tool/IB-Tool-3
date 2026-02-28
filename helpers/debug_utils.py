"""Debug utilities for saving erroneous features when debug mode is active."""

import os
from typing import List, Optional
from qgis.core import QgsVectorLayer, QgsFeature, QgsFields, QgsCoordinateReferenceSystem
from .system_utils import save_temp_layer_to_gpkg
from .logger import Logger

# Maps WKB type codes to geometry type strings for memory-layer creation
_WKB_TYPE_MAP = {
    1: "Point",
    2: "LineString",
    3: "Polygon",
    4: "MultiPoint",
    5: "MultiLineString",
    6: "MultiPolygon",
}


def _next_debug_index(debug_dir: str) -> int:
    """Determine the next sequential index for debug files in the target folder.

    Counts all existing ``.gpkg`` files in the folder so that saved files are
    numbered consecutively and reflect the processing order when sorted by name
    in a GIS.

    Args:
        debug_dir: Path to the tool-specific debug sub-folder.

    Returns:
        Next available index (int, starting at 1).
    """
    if not os.path.isdir(debug_dir):
        return 1
    existing = [f for f in os.listdir(debug_dir) if f.lower().endswith(".gpkg")]
    return len(existing) + 1


def save_debug_layer(
    layer: QgsVectorLayer,
    tool_name: str,
    step_name: str,
    workspace_path: str,
    is_error: bool = False,
) -> Optional[str]:
    """Save a layer as a numbered debug file in the tool sub-folder.

    Creates ``workspace/debug/{tool_name}/`` and writes the layer as a
    GeoPackage. The filename receives an auto-incremented numeric prefix and —
    for error snapshots — an ``_err`` suffix:

    - Checkpoint:    ``001_after_dissolve.gpkg``
    - Failed step:   ``002_failed_buffer_err.gpkg``

    Args:
        layer: QgsVectorLayer containing the features to save.
        tool_name: Name of the tool (e.g. ``"GapClose"``); becomes the sub-folder.
        step_name: Descriptive step name (e.g. ``"after_dissolve"``).
        workspace_path: Base workspace path.
        is_error: If True, the file receives the ``_err`` suffix (failed step).

    Returns:
        Path to the saved GeoPackage file, or None on error or empty layer.
    """
    if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
        Logger.log(f"Debug: invalid layer, skipping save for {tool_name}/{step_name}", level="WARNING")
        return None

    if layer.featureCount() == 0:
        Logger.log(f"Debug: no features to save for {tool_name}/{step_name}", level="INFO")
        return None

    debug_dir = os.path.join(workspace_path, "debug", tool_name)
    idx = _next_debug_index(debug_dir)
    suffix = "_err" if is_error else ""
    filename = f"{idx:03d}_{step_name}{suffix}"

    path = save_temp_layer_to_gpkg(layer, filename, debug_dir)
    if path:
        Logger.log(f"Debug layer saved: {path}", level="INFO")
    return path


def save_debug_features(
    features: List[QgsFeature],
    crs: QgsCoordinateReferenceSystem,
    tool_name: str,
    step_name: str,
    workspace_path: str,
    fields: Optional[QgsFields] = None,
    is_error: bool = False,
) -> Optional[str]:
    """Save a list of QgsFeature objects as a numbered debug file.

    Constructs a temporary QgsVectorLayer from the feature list and delegates
    to :func:`save_debug_layer`. Filename convention is identical.

    Args:
        features: List of QgsFeature objects to save.
        crs: Coordinate reference system of the layer.
        tool_name: Name of the tool; becomes the sub-folder.
        step_name: Descriptive step name.
        workspace_path: Base workspace path.
        fields: Optional QgsFields definition. Taken from the first feature if
            not provided.
        is_error: If True, the file receives the ``_err`` suffix (failed step).

    Returns:
        Path to the saved GeoPackage file, or None on error or empty list.
    """
    if not features:
        Logger.log(f"Debug: no features to save for {tool_name}/{step_name}", level="INFO")
        return None

    if fields is None:
        fields = features[0].fields()

    geom_type = "Polygon"
    first_geom = features[0].geometry()
    if not first_geom.isNull():
        wkb = first_geom.wkbType()
        geom_type = _WKB_TYPE_MAP.get(wkb, "Polygon")

    mem_layer = QgsVectorLayer(f"{geom_type}?crs={crs.authid()}", step_name, "memory")
    provider = mem_layer.dataProvider()
    provider.addAttributes(fields)
    mem_layer.updateFields()
    provider.addFeatures(features)

    return save_debug_layer(mem_layer, tool_name, step_name, workspace_path, is_error=is_error)
