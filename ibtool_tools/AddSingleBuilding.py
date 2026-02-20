from qgis.core import (
    QgsVectorLayer,
    QgsProcessing
)

from qgis import processing
from ..helpers.geometry_utils import shp_area2

def add_single_bdg(input_hu: QgsVectorLayer, 
                   rect_merge: QgsVectorLayer, 
                   crs, workspace_path,
                   threshold=300, ) -> QgsVectorLayer:
    """
    Processes building data and merges it with rectangular geometries after 
    filtering based on specific criteria.

    The function takes a layer containing building polygons and another layer 
    with rectangular geometries. It then identifies buildings that do not 
    intersect with the provided rectangular geometries, filters large buildings 
    above a specified area threshold, and transforms the large buildings into 
    rectangular bounding geometries. These rectangular geometries are finally 
    merged with the original rectangular geometries.

    :param input_hu: The input layer containing building polygons to process.
    :type input_hu: QgsVectorLayer
    :param rect_merge: The input layer containing rectangular geometries to
    merge.
    :type rect_merge: QgsVectorLayer
    :param crs: The coordinate reference system for merging the layers. 
                The type is left generic as it can vary depending on the 
                software or library.
    :param threshold: The area threshold value above which buildings are 
                      considered large and their geometries are transformed 
                      into rectangles. Default is 300.
    :type threshold: int, optional
    :return: A QgsVectorLayer containing rectangular bounding geometries derived
             from large buildings outside of existing cluster polygons. The
             merge with `rect_merge` is performed by the caller.
    :rtype: QgsVectorLayer
    """

    processed_input_hu = processing.run("qgis:fixgeometries", {
        'INPUT': input_hu,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    shp_area2(processed_input_hu)

    processed_rect_merge = processing.run("qgis:fixgeometries", {
        'INPUT': rect_merge,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Gebäude außerhalb von rect_merge extrahieren (Disjoint)
    hu_centroids = processing.run("native:pointonsurface", {
        'INPUT': processed_input_hu,
        'ALL_PARTS': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        'INVALID_HANDLING': 1  # 1 für ignorieren
    })['OUTPUT']

    hu_centroids_sel = processing.run("native:extractbylocation", {
        'INPUT': hu_centroids,
        'PREDICATE': [2],  # getrennt
        'INTERSECT': processed_rect_merge,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    hu_sel = processing.run("native:extractbylocation", {
        'INPUT': processed_input_hu,
        'PREDICATE': [0],  # schneidet
        'INTERSECT': hu_centroids_sel,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Filtere große Gebäude (Fläche > threshold)
    hu_huge = processing.run("native:extractbyattribute", {
        'INPUT': hu_sel,
        'FIELD': 'Area',
        'OPERATOR': 2,
        'VALUE': threshold,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Eindeutige ID pro Feature hinzufügen (für Gruppierung in minimumboundinggeometry)
    hu_huge_with_id = processing.run("native:addautoincrementalfield", {
        'INPUT': hu_huge,
        'FIELD_NAME': 'unique_id',
        'START': 1,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Erzeuge rechteckige Geometrien (je eine pro Feature)
    hu_rect_raw = processing.run("qgis:minimumboundinggeometry", {
        'INPUT': hu_huge_with_id,
        'FIELD': 'unique_id',
        'TYPE': 1,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Filtere leere/null Geometrien aus dem Ergebnis
    hu_rect = processing.run("native:removenullgeometries", {
        'INPUT': hu_rect_raw,
        'REMOVE_EMPTY': True,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    return hu_rect