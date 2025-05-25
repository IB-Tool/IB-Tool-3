from qgis.core import (
    QgsVectorLayer,
    QgsField,
    QgsFeatureRequest,
    QgsProject,
    QgsProcessingAlgorithm,
    QgsProcessingUtils,
    QgsWkbTypes,
    QgsProcessing
)
from qgis import processing


def gap_close(input_layer, blocks, max_hole_size, max_gap_size, crs, gap_dist=30):
    """
    :param input_layer: Input polygon layer as QgsVectorLayer
    :param blocks: Street blocks polygon layer as QgsVectorLayer
    :param max_hole_size: Threshold value for holes
    :param max_gap_size: Threshold value for gaps
    :param gap_dist: Distance for double buffer
    :return: QgsVectorLayer containing refined polygons
    """

    def gap_select(input_poly, input_gaps, crs, length_percentage):
        """
        Wählt Lücken basierend auf dem prozentualen Anteil der überlappenden Kanten aus.
        
        Args:
            input_poly: Eingabe-Polygon Layer
            input_gaps: Lücken-Polygon Layer
            length_percentage: Schwellwert für den prozentualen Längenanteil
        
        Returns:
            QgsVectorLayer mit ausgewählten Lücken
        """
        # Input Polygon auflösen
        input_poly_diss = processing.run("qgis:dissolve", {
            'INPUT': input_poly,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
    
        # Polygone in Linien umwandeln
        input_poly_lines = processing.run("native:polygonstolines", {
            'INPUT': input_poly_diss,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
    
        gap_lines = processing.run("native:polygonstolines", {
            'INPUT': input_gaps,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
    
        # Multipart zu Singlepart für Lückenlinien
        gap_lines_single = processing.run("native:multiparttosingleparts", {
            'INPUT': gap_lines,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
    
        # Felder hinzufügen und Längen berechnen
        gap_lines_with_length = processing.run("qgis:fieldcalculator", {
            'INPUT': gap_lines_single,
            'FIELD_NAME': 'length_1',
            'FIELD_TYPE': 0,
            'FIELD_LENGTH': 20,
            'FIELD_PRECISION': 10,
            'NEW_FIELD': True,
            'FORMULA': '$length',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Feld 'fid_copy' hinzufügen als Kopie des Feldes 'fid'
        gap_lines_with_fid_copy = processing.run("qgis:fieldcalculator", {
            'INPUT': gap_lines_with_length,
            'FIELD_NAME': 'fid_copy',
            'FIELD_TYPE': 1,  # Integer field
            'FIELD_LENGTH': 10,
            'NEW_FIELD': True,
            'FORMULA': 'fid',  # Kopiert den Wert des Feldes 'fid'
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
    
        # Linien an Schnittpunkten teilen
        split_lines = processing.run("native:splitwithlines", {
            'INPUT': gap_lines_with_fid_copy,
            'LINES': input_poly_lines,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
    
        # Überlappende Segmente extrahieren
        overlapping_segments = processing.run("native:extractbylocation", {
            'INPUT': split_lines,
            'PREDICATE': [0],  # intersect
            'INTERSECT': input_poly_lines,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
    
        # Segmente nach FID auflösen und neue Länge berechnen
        dissolved_segments = processing.run("qgis:dissolve", {
            'INPUT': overlapping_segments,
            'FIELD': ['fid_copy'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        lines_with_length_2 = processing.run("qgis:fieldcalculator", {
            'INPUT': dissolved_segments,
            'FIELD_NAME': 'length_2',
            'FIELD_TYPE': 0,
            'FIELD_LENGTH': 20,
            'FIELD_PRECISION': 10,
            'NEW_FIELD': True,
            'FORMULA': '$length',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
            
    
        # Längenverhältnis berechnen und filtern
        final_selection = processing.run("qgis:extractbyexpression", {
            'INPUT': lines_with_length_2,
            'EXPRESSION': f'("length_2" / "length_1") * 100 > {length_percentage}',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
               
    
        return final_selection
    
    ############################################################

    input_diss = processing.run("native:dissolve",
                   {'INPUT': input_layer,
                    'FIELD': [],
                    'SEPARATE_DISJOINT': False,
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                     })['OUTPUT']

    # Initial count of input layer
    input_layer_count = input_diss.featureCount()

    if input_layer_count > 0:
        # Close holes in the input polygons
        hole_closed = processing.run("native:deleteholes", {
            'INPUT': input_diss,
            'MIN_AREA': max_hole_size,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Symmetrical difference between blocks and hole-closed polygons
        block_sym_diff = processing.run("qgis:symmetricaldifference", {
            'INPUT': blocks,
            'OVERLAY': hole_closed,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Convert multipart polygons to singlepart
        block_sym_diff_single = processing.run("native:multiparttosingleparts", {
            'INPUT': block_sym_diff,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Filter areas smaller than max_gap_size
        selected_areas = processing.run("qgis:extractbyexpression", {
            'INPUT': block_sym_diff_single,
            'EXPRESSION': f"area($geometry) < {max_gap_size}",
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Merge selected gaps with hole_closed polygons
        merged_gap = gap_select(hole_closed, selected_areas, crs, 70)

        merged_output = processing.run("native:mergevectorlayers", {
            'LAYERS': [merged_gap, hole_closed],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        dissolved_output = processing.run("native:dissolve", {
            'INPUT': merged_output,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        initial_buffer = processing.run("native:buffer", {
            'INPUT': dissolved_output,
            'DISTANCE': gap_dist,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        boundary_line = processing.run("native:polygonstolines", {
            'INPUT': initial_buffer,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        boundary_buffer = processing.run("native:buffer", {
            'INPUT': boundary_line,
            'DISTANCE': gap_dist,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        erased_areas = processing.run("native:erase", {
            'INPUT': initial_buffer,
            'OVERLAY': boundary_buffer,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        small_removed = processing.run("qgis:extractbyexpression", {
            'INPUT': erased_areas,
            'EXPRESSION': f'area($geometry) > {200 * gap_dist / 15}',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        final_gap = gap_select(input_layer, small_removed, 70)

        merged_final = processing.run("native:mergevectorlayers", {
            'LAYERS': [final_gap, merged_output],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        repaired_output = processing.run("qgis:deleteduplicategeometries", {
            'INPUT': merged_final,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        dissolved_final = processing.run("native:dissolve", {
            'INPUT': repaired_output,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        return dissolved_final
    else:
        #("Input layer is empty.")
        return input_layer