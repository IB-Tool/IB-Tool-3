from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsProcessing,
    QgsProcessingFeatureSourceDefinition,
    QgsProcessingUtils,
    QgsFeatureSink,
    QgsFeatureRequest,
    QgsField,
    QgsVectorLayer,
    QgsGeometry,
    QgsFeature,
    QgsVectorFileWriter,
)
from qgis import processing

from ..helpers.system_utils import save_temp_layer_to_gpkg
from ..helpers.logger import Logger
from ..helpers.system_utils import get_feature_count
from ..helpers.message import msg
from ..helpers.geometry_utils import shp_area2, create_empty_layer, get_hole_polygons

def hole_close(input_layer, max_hole_size):
    """
    Schließt Löcher innerhalb eines Eingabe-Polygons bis zu einer bestimmten maximalen Fläche.

    :param input_layer: Eingabepolygon (QgsVectorLayer)
    :param max_hole_size: Maximal erlaubte Lochfläche (z.B. in Quadratmetern)
    :return: Geschlossene Polygonlayer (QgsVectorLayer)
    """

    input_layer_diss = processing.run("native:dissolve",
                   {'INPUT': input_layer,
                    'FIELD': [],
                    'SEPARATE_DISJOINT': False,
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                    })['OUTPUT']

    input_diss_line = processing.run("native:polygonstolines", {
        'INPUT': input_layer_diss,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    lines_poly = processing.run("native:polygonize", {
        'INPUT': input_diss_line,
        'KEEP_FIELDS': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

       # Step 4: Finde Löcher (Differenz zwischen ursprünglichen und neuen Polygonen)
    holes = get_hole_polygons(lines_poly, input_layer_diss)
    save_temp_layer_to_gpkg(holes, "holes")
    shp_area2(holes)

    # Step 5: Filtere Löcher nach maximaler Größe
    holes_filtered = processing.run("native:extractbyattribute",
                   {'INPUT': holes,
                    'FIELD': 'Area',
                    'OPERATOR': 5,
                    'VALUE': max_hole_size,
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                    })['OUTPUT']
    save_temp_layer_to_gpkg(holes_filtered, "holes_filtered")

    # Step 6: Löcher und ursprüngliche Polygone zusammenführen
    merged_result = processing.run(
        "qgis:mergevectorlayers",
        {
            "LAYERS": [holes_filtered, input_layer_diss],
            "CRS": input_layer.crs().authid(),
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
    save_temp_layer_to_gpkg(merged_result, "merged_result")


    # Step 7: Geometrie reparieren und auflösen
    dissolved_result = processing.run(
        "qgis:dissolve",
        {"INPUT": merged_result,
         'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
         })['OUTPUT']

    return dissolved_result

