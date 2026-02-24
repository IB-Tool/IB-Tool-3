"""AddSingleBuilding: Filter large isolated buildings and convert them to bounding rectangles."""

from qgis.core import (
    QgsVectorLayer,
    QgsProcessing
)

from ..helpers.geometry_utils import shp_area2
from ..helpers.debug_utils import save_debug_layer
from ..helpers.safe_processing import safe_processing_run

# ---------------------------------------------------------------------------
# Debug folder name — prefix reflects call order in the main pipeline
# ---------------------------------------------------------------------------
_DEBUG_TOOL_NAME = "02_AddSingleBuilding"

# ---------------------------------------------------------------------------
# QGIS predicate codes (used in native:extractbylocation)
# ---------------------------------------------------------------------------
_PREDICATE_INTERSECTS = 0   # keep features that intersect the reference layer
_PREDICATE_DISJOINT = 2     # keep features that are disjoint from the reference layer

# QGIS attribute filter operator code (used in native:extractbyattribute)
_OPERATOR_GREATER_THAN = 2

# native:pointonsurface — skip invalid geometries instead of raising an error
_INVALID_GEOMETRY_SKIP = 1

# native:addautoincrementalfield — first value of the auto-increment sequence
_AUTOINCREMENT_START = 1

# qgis:minimumboundinggeometry — type 1 produces an oriented bounding rectangle
_BOUNDING_TYPE_RECTANGLE = 1

# Default minimum area (m²) for a building to be considered "large"
DEFAULT_AREA_THRESHOLD = 300


def add_single_bdg(
    input_hu: QgsVectorLayer,
    rect_merge: QgsVectorLayer,
    crs,
    workspace_path=None,
    threshold: int = DEFAULT_AREA_THRESHOLD,
    debug_mode: bool = False,
) -> QgsVectorLayer:
    """Filter large isolated buildings and convert them to bounding rectangles.

    Identifies buildings whose centroid lies outside *rect_merge* cluster
    polygons and whose area exceeds *threshold*, then converts each such
    building to its oriented bounding rectangle.

    The result is intended to be merged with *rect_merge* by the caller.

    Debug checkpoints written to ``workspace/debug/AddSingleBuilding/``:

    1. ``centroids_outside_cluster`` — representative points outside cluster polygons
    2. ``buildings_outside_cluster`` — full building footprints outside cluster
    3. ``buildings_large`` — footprints that also exceed the area threshold
    4. ``bounding_rects`` — final oriented bounding rectangles

    Args:
        input_hu: Input layer containing building footprint polygons.
        rect_merge: Layer containing existing cluster polygons used as
            the spatial reference for the disjoint filter.
        crs: Coordinate reference system for the output layer.
        workspace_path: Base path for debug output files. Required when
            ``debug_mode`` is True. Defaults to ``None``.
        threshold: Minimum area (m²) a building must exceed to be included.
            Defaults to ``DEFAULT_AREA_THRESHOLD`` (300 m²).
        debug_mode: If True, saves intermediate results as numbered GeoPackages
            under ``workspace/debug/AddSingleBuilding/``. Defaults to False.

    Returns:
        A QgsVectorLayer containing one oriented bounding rectangle per
        qualifying building.
    """
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name=_DEBUG_TOOL_NAME)

    # Repair geometries in both input layers before any spatial operation
    processed_input_hu = safe_processing_run("qgis:fixgeometries", {
        'INPUT': input_hu,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    }, **_dbg)['OUTPUT']

    shp_area2(processed_input_hu)

    processed_rect_merge = safe_processing_run("qgis:fixgeometries", {
        'INPUT': rect_merge,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    }, **_dbg)['OUTPUT']

    # Derive one representative point per building for the spatial filter
    hu_centroids = safe_processing_run("native:pointonsurface", {
        'INPUT': processed_input_hu,
        'ALL_PARTS': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        'INVALID_HANDLING': _INVALID_GEOMETRY_SKIP,
    }, **_dbg)['OUTPUT']

    # Select only the centroids that lie outside all cluster polygons
    hu_centroids_outside = safe_processing_run("native:extractbylocation", {
        'INPUT': hu_centroids,
        'PREDICATE': [_PREDICATE_DISJOINT],
        'INTERSECT': processed_rect_merge,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    }, **_dbg)['OUTPUT']

    if debug_mode and workspace_path:
        save_debug_layer(hu_centroids_outside, _DEBUG_TOOL_NAME, "centroids_outside_cluster", workspace_path)

    # Retrieve the corresponding full building polygons
    hu_outside = safe_processing_run("native:extractbylocation", {
        'INPUT': processed_input_hu,
        'PREDICATE': [_PREDICATE_INTERSECTS],
        'INTERSECT': hu_centroids_outside,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    }, **_dbg)['OUTPUT']

    if debug_mode and workspace_path:
        save_debug_layer(hu_outside, _DEBUG_TOOL_NAME, "buildings_outside_cluster", workspace_path)

    # Keep only buildings whose area exceeds the threshold
    hu_large = safe_processing_run("native:extractbyattribute", {
        'INPUT': hu_outside,
        'FIELD': 'Area',
        'OPERATOR': _OPERATOR_GREATER_THAN,
        'VALUE': threshold,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    }, **_dbg)['OUTPUT']

    if debug_mode and workspace_path:
        save_debug_layer(hu_large, _DEBUG_TOOL_NAME, "buildings_large", workspace_path)

    # Assign a unique ID per feature so each gets its own bounding rectangle
    hu_large_with_id = safe_processing_run("native:addautoincrementalfield", {
        'INPUT': hu_large,
        'FIELD_NAME': 'unique_id',
        'START': _AUTOINCREMENT_START,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    }, **_dbg)['OUTPUT']

    # Create one oriented bounding rectangle per feature
    hu_rect_raw = safe_processing_run("qgis:minimumboundinggeometry", {
        'INPUT': hu_large_with_id,
        'FIELD': 'unique_id',
        'TYPE': _BOUNDING_TYPE_RECTANGLE,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    }, **_dbg)['OUTPUT']

    # Remove any null or empty geometries produced by the bounding step
    hu_rect = safe_processing_run("native:removenullgeometries", {
        'INPUT': hu_rect_raw,
        'REMOVE_EMPTY': True,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    }, **_dbg)['OUTPUT']

    if debug_mode and workspace_path:
        save_debug_layer(hu_rect, _DEBUG_TOOL_NAME, "bounding_rects", workspace_path)

    return hu_rect
