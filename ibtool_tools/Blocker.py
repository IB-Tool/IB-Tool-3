from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsProcessingFeatureSourceDefinition,
    QgsProcessing,
    QgsProcessingUtils
)
from qgis.PyQt.QtCore import QMetaType
import processing
from ..helpers.logger import Logger
from ..helpers.geometry_utils import create_polygons_from_lines, extract_polygons_from_lines


def blocker(strassen, hu_input, partition):

    """
    :param strassen: road network as polyline (QGIS layer)
    :param hu_input: building footprints as polygon (QGIS layer)
    :param partition: part of study area for that city block is calculated (QGIS layer)
    :return: city block (QGIS layer)

    - create city blocks of partition outline and road network
    """

    # Create partition outline as lines
    partition_outline = processing.run("native:polygonstolines", {
        'INPUT': partition,
        'OUTPUT': 'TEMPORARY_OUTPUT'
        })['OUTPUT']

    # Intersect roads with partition
    strassen_intersect = processing.run("native:intersection", {
        'INPUT': strassen,
        'OVERLAY': partition,
        'OUTPUT':'TEMPORARY_OUTPUT'
        })['OUTPUT']

    # Merge outlines and road intersections
    strassen_merge = processing.run("native:mergevectorlayers", {
        'LAYERS': [partition_outline, strassen_intersect],
        'OUTPUT':'TEMPORARY_OUTPUT'
        })['OUTPUT']

    blocks_layer = processing.run("native:polygonize", {
        'INPUT':strassen_merge,
        'KEEP_FIELDS':False,
        'OUTPUT':'TEMPORARY_OUTPUT'
        })['OUTPUT']

    # Select blocks containing buildings
    processing.run("native:selectbylocation", {
        'INPUT': blocks_layer,
        'PREDICATE': [0],  # Contains
        'INTERSECT': hu_input,
        'METHOD': 0  # Create new selection
    })

    # Delete empty blocks (not selected)
    blocks_layer.startEditing()
    selected_ids = blocks_layer.selectedFeatureIds()
    for feature in blocks_layer.getFeatures():
        if feature.id() not in selected_ids:
            blocks_layer.deleteFeature(feature.id())
    blocks_layer.commitChanges()

    # Add NAME field
    blocks_layer.startEditing()
    if not blocks_layer.dataProvider().fieldNameIndex("NAME") >= 0:
        blocks_layer.dataProvider().addAttributes([QgsField("NAME", QMetaType.QString)])
        blocks_layer.updateFields()

    # Calculate NAME field values
    for feature in blocks_layer.getFeatures():
        feature["NAME"] = f"Block_{feature.id()}"
        blocks_layer.updateFeature(feature)

    blocks_layer.commitChanges()
    Logger.log("Blocker End - blocks", "SUCCESS")

    return blocks_layer
