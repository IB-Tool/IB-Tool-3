from qgis.core import QgsVectorLayer, QgsProcessing
from qgis import processing

from ..helpers.logger import Logger

def safe_processing_run(algorithm_name, parameters, fix_geometries=True):
    """
    Sicherer Wrapper für processing.run mit Geometriereparatur
    
    Args:
        algorithm_name: Name des Algorithmus
        parameters: Parameter-Dictionary
        fix_geometries: Ob Geometrien vor der Verarbeitung repariert werden sollen
    
    Returns:
        Ergebnis der Verarbeitung
    """
    try:
        return processing.run(algorithm_name, parameters)
    except Exception as e:
        if fix_geometries and 'ungültige Geometrie' in str(e):
            # Versuche alle Input-Layer zu reparieren
            repaired_params = parameters.copy()
            for key, value in parameters.items():
                if key in ['INPUT', 'OVERLAY', 'INTERSECT'] and hasattr(value, 'isValid'):
                    try:
                        repaired_layer = processing.run("native:fixgeometries", {
                            'INPUT': value,
                            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                        })['OUTPUT']
                        repaired_params[key] = repaired_layer
                    except:
                        pass  # Falls Reparatur fehlschlägt, ursprünglichen Layer verwenden
            
            # Erneut versuchen mit reparierten Geometrien
            try:
                return processing.run(algorithm_name, repaired_params)
            except:
                # Letzter Versuch: Ungültige Geometrien ignorieren
                if 'INVALID_FEATURE_HANDLING' not in repaired_params:
                    repaired_params['INVALID_FEATURE_HANDLING'] = 1
                return processing.run(algorithm_name, repaired_params)
        else:
            Logger.log(str(e), level="ERROR")
            raise e


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
        input_poly_diss = safe_processing_run("qgis:dissolve", {
            'INPUT': input_poly,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Polygone in Linien umwandeln
        input_poly_lines = safe_processing_run("native:polygonstolines", {
            'INPUT': input_poly_diss,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        gap_lines = safe_processing_run("native:polygonstolines", {
            'INPUT': input_gaps,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Multipart zu Singlepart für Lückenlinien
        gap_lines_single = safe_processing_run("native:multiparttosingleparts", {
            'INPUT': gap_lines,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Felder hinzufügen und Längen berechnen
        gap_lines_with_length = safe_processing_run("qgis:fieldcalculator", {
            'INPUT': gap_lines_single,
            'FIELD_NAME': 'length_1',
            'FIELD_TYPE': 0,
            'FIELD_LENGTH': 20,
            'FIELD_PRECISION': 10,
            'NEW_FIELD': True,
            'FORMULA': '$length',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        gap_lines_with_fid_copy = safe_processing_run("native:fieldcalculator", {
            'INPUT': gap_lines_with_length,
            'FIELD_NAME': 'fid_copy',
            'FIELD_TYPE': 0,
            'FIELD_LENGTH': 0,
            'FIELD_PRECISION': 0,
            'FORMULA': '@id',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Linien an Schnittpunkten teilen
        split_lines = safe_processing_run("native:splitlinesbylength", {
            'INPUT': gap_lines_with_fid_copy,
            'LENGTH': 10,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        input_poly_lines_buff = safe_processing_run("native:buffer", {
            'INPUT': input_poly_lines,
            'DISTANCE': 0.5,
            'SEGMENTS': 5,
            'END_CAP_STYLE': 0,
            'JOIN_STYLE': 0,
            'MITER_LIMIT': 2,
            'DISSOLVE': False,
            'SEPARATE_DISJOINT': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Überlappende Segmente extrahieren
        overlapping_segments = safe_processing_run("native:extractbylocation", {
            'INPUT': split_lines,
            'PREDICATE': [0],  # intersect
            'INTERSECT': input_poly_lines_buff,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Segmente nach FID auflösen und neue Länge berechnen
        dissolved_segments = safe_processing_run("qgis:dissolve", {
            'INPUT': overlapping_segments,
            'FIELD': ['fid_copy'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        lines_with_length_2 = safe_processing_run("qgis:fieldcalculator", {
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
        final_selection = safe_processing_run("qgis:extractbyexpression", {
            'INPUT': lines_with_length_2,
            'EXPRESSION': f'("length_2" / "length_1") * 100 > {length_percentage}',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
            'KEEP_FIELDS': True
        })['OUTPUT']

        # Retrieve all values from the 'fid_copy' field in final_selection and store them in a list
        fid_copy_values = [
            feature['fid_copy']
            for feature in final_selection.getFeatures()
        ]

        if not fid_copy_values:
            # Erstelle leeres Polygon mit gleicher Struktur wie input_gaps
            empty_layer = QgsVectorLayer("Polygon", "empty", "memory")
            empty_layer.setCrs(input_gaps.crs())

            # Kopiere Felder vom input_gaps
            provider = empty_layer.dataProvider()
            provider.addAttributes(input_gaps.fields())
            empty_layer.updateFields()

            return empty_layer

        # Ansonsten normale Filterung durchführen
        filtered_features = safe_processing_run("native:extractbylocation", {
            'INPUT': input_gaps,
            'PREDICATE': [0, 4],
            'INTERSECT': final_selection,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        return filtered_features

    ############################################################

    input_diss = safe_processing_run("native:dissolve", {
        'INPUT': input_layer,
        'FIELD': [],
        'SEPARATE_DISJOINT': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Initial count of input layer
    input_layer_count = input_diss.featureCount()

    if input_layer_count > 0:
        # Close holes in the input polygons
        hole_closed = safe_processing_run("native:deleteholes", {
            'INPUT': input_diss,
            'MIN_AREA': max_hole_size,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Symmetrical difference between blocks and hole-closed polygons
        block_sym_diff = safe_processing_run("qgis:symmetricaldifference", {
            'INPUT': blocks,
            'OVERLAY': hole_closed,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Convert multipart polygons to singlepart
        block_sym_diff_single = safe_processing_run("native:multiparttosingleparts", {
            'INPUT': block_sym_diff,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Filter areas smaller than max_gap_size
        selected_areas = safe_processing_run("qgis:extractbyexpression", {
            'INPUT': block_sym_diff_single,
            'EXPRESSION': f"area($geometry) < {max_gap_size}",
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Merge selected gaps with hole_closed polygons
        merged_gap = gap_select(hole_closed, selected_areas, crs, 70)

        merged_output = safe_processing_run("native:mergevectorlayers", {
            'LAYERS': [merged_gap, hole_closed],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        dissolved_output = safe_processing_run("native:dissolve", {
            'INPUT': merged_output,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        initial_buffer = safe_processing_run("native:buffer", {
            'INPUT': dissolved_output,
            'DISTANCE': gap_dist,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        boundary_line = safe_processing_run("native:polygonstolines", {
            'INPUT': initial_buffer,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        boundary_buffer = safe_processing_run("native:buffer", {
            'INPUT': boundary_line,
            'DISTANCE': gap_dist,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        poly_cut_1 = safe_processing_run("native:difference", {
            'INPUT': initial_buffer,
            'OVERLAY': boundary_buffer,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
            'GRID_SIZE': None,
        })['OUTPUT']

        poly_cut_2 = safe_processing_run("native:difference", {
            'INPUT': poly_cut_1,
            'OVERLAY': input_layer,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
            'GRID_SIZE': None,
        })['OUTPUT']

        poly_singlepart = safe_processing_run("native:multiparttosingleparts", {
            'INPUT': poly_cut_2,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        small_removed = safe_processing_run("qgis:extractbyexpression", {
            'INPUT': poly_singlepart,
            'EXPRESSION': f'area($geometry) > {200 * gap_dist / 15}',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        final_gap = gap_select(input_layer, small_removed, crs, 70)

        gap_poly_max_size = safe_processing_run("qgis:extractbyexpression", {
            'INPUT': final_gap,
            'EXPRESSION': f'area($geometry) < {max_gap_size}',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        merged_final = safe_processing_run("native:mergevectorlayers", {
            'LAYERS': [gap_poly_max_size, merged_output],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        repaired_output = safe_processing_run("qgis:deleteduplicategeometries", {
            'INPUT': merged_final,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        dissolved_final = safe_processing_run("native:dissolve", {
            'INPUT': repaired_output,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Close holes in the input polygons
        dissolved_final_hole_closed = safe_processing_run("native:deleteholes", {
            'INPUT': dissolved_final,
            'MIN_AREA': max_hole_size,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        return dissolved_final_hole_closed
    else:
        return input_layer