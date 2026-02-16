from qgis.core import (
    QgsVectorLayer,
    QgsProcessing
)

from qgis import processing

def add_single_bdg(input_hu: QgsVectorLayer, 
                   rect_merge: QgsVectorLayer, 
                   crs, 
                   threshold=300) -> QgsVectorLayer:
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
    :return: A merged QgsVectorLayer containing both the rectangular geometries 
             derived from buildings and the original rectangular geometries 
             from the `rect_merge` parameter.
    :rtype: QgsVectorLayer
    """

    processed_input_hu = processing.run("qgis:fixgeometries", {
        'INPUT': input_hu,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    processed_rect_merge = processing.run("qgis:fixgeometries", {
        'INPUT': rect_merge,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Gebäude außerhalb von rect_merge extrahieren (Disjoint)
    hu_centroids = processing.run("native:centroids", {
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

    # Erzeuge rechteckige Geometrien
    hu_rect = processing.run("qgis:minimumboundinggeometry", {
        'INPUT': hu_huge,
        'FIELD': 'node',
        'TYPE': 1,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    return hu_rect