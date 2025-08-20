"""
Das helpers-Modul enthält verschiedene Hilfsfunktionen für das Plugin.
Module:

"""

# Gezielte Importe aus Untermodulen
from ibtool.helpers.geometry_utils import (
    polyline2,
    check_projection,
    load_to_geopackage,
    split_layer_by_attribute,
    select_and_save_by_location,
    create_polygons_from_lines,
    extract_polygons_from_lines,
    shp_area,
    shp_area2,
    shp_length,
    create_empty_layer,
    create_linestring_layer_from_array,
    nodes_detect,
    get_hole_polygons

)
from ibtool.helpers.data_loader import (
    select_HU_file,
    select_RN_file,
    select_AUX_file,
    select_PART_file,
    select_output_file,
    select_workspace_file,
    create_partitions_list
)
from ibtool.helpers.system_utils import (
    save_temp_layer_to_gpkg,
    manage_directory,
    copy_shapefile,
    get_feature_count,
    version_check
)

from ibtool.helpers.logger import Logger

from ibtool.helpers.message import msg

# Exportierte Symbole für den einfachen Zugriff
__all__ = [
    "polyline2",
    "check_projection",
    "load_to_geopackage",
    "select_HU_file",
    "select_RN_file",
    "select_AUX_file",
    "select_PART_file",
    "select_output_file",
    "select_workspace_file",
    "save_temp_layer_to_gpkg",
    "split_layer_by_attribute",
    "manage_directory",
    "create_partitions_list",
    "Logger",
    "extract_polygons_from_lines",
    "msg",
    "get_feature_count",
    "shp_area2",
    "shp_area",
    "get_hole_polygons",
    "version_check"
]
