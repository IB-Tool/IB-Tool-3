from qgis.core import QgsVectorLayer, QgsProcessing
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
        #save_temp_layer_to_gpkg(input_poly_lines, "b_input_poly_lines")

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
        '''
        gap_lines_with_fid_copy = processing.run("qgis:fieldcalculator", {
            'INPUT': gap_lines_with_length,
            'FIELD_NAME': 'fid_copy',
            'FIELD_TYPE': 1,  # Integer field
            'FIELD_LENGTH': 10,
            'NEW_FIELD': True,
            'FORMULA': 'attribute($currentfeature, \'fid\')',  # Korrekten Feldwert kopieren
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        '''
        gap_lines_with_fid_copy= processing.run("native:fieldcalculator",
                                   {'INPUT': gap_lines_with_length,
                                    'FIELD_NAME': 'fid_copy',
                                    'FIELD_TYPE': 0,
                                    'FIELD_LENGTH': 0,
                                    'FIELD_PRECISION': 0,
                                    'FORMULA': '@id',
                                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                                    })['OUTPUT']

        # Linien an Schnittpunkten teilen
        split_lines = processing.run("native:splitlinesbylength",
                       {'INPUT': gap_lines_with_fid_copy,
                        'LENGTH': 10,
                        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                        })['OUTPUT']
        #save_temp_layer_to_gpkg(split_lines, "b_split_lines")

        input_poly_lines_buff = processing.run("native:buffer",
                       {'INPUT': input_poly_lines,
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
        overlapping_segments = processing.run("native:extractbylocation", {
            'INPUT': split_lines,
            'PREDICATE': [0],  # intersect
            'INTERSECT': input_poly_lines_buff,
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
        #save_temp_layer_to_gpkg(lines_with_length_2, "b_lines_with_length_2")

        # Längenverhältnis berechnen und filtern
        final_selection = processing.run("qgis:extractbyexpression", {
            'INPUT': lines_with_length_2,
            'EXPRESSION': f'("length_2" / "length_1") * 100 > {length_percentage}',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
            'KEEP_FIELDS': True
             })['OUTPUT']
        #save_temp_layer_to_gpkg(final_selection, "b_final_selection")

        # Retrieve all values from the 'fid_copy' field in final_selection and store them in a list
        fid_copy_values = [
            feature['fid_copy']
            for feature in final_selection.getFeatures()
        ]  # TODO das geht auch anders
        #small_removed_count = small_removed.featureCount()


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
        filtered_features = processing.run("native:extractbylocation",
                       {'INPUT': input_gaps,
                        'PREDICATE': [0, 4],
                        'INTERSECT': final_selection,
                        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                         })['OUTPUT']

        #save_temp_layer_to_gpkg(filtered_features, "b_filtered_features")

        return filtered_features


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
        #save_temp_layer_to_gpkg(hole_closed, "a_hole_closed")

        # Symmetrical difference between blocks and hole-closed polygons
        block_sym_diff = processing.run("qgis:symmetricaldifference", {
            'INPUT': blocks,
            'OVERLAY': hole_closed,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        #save_temp_layer_to_gpkg(block_sym_diff, "a_block_sym_diff")

        # Convert multipart polygons to singlepart
        block_sym_diff_single = processing.run("native:multiparttosingleparts", {
            'INPUT': block_sym_diff,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        #save_temp_layer_to_gpkg(block_sym_diff_single, "a_block_sym_diff_single")

        # Filter areas smaller than max_gap_size
        selected_areas = processing.run("qgis:extractbyexpression", {
            'INPUT': block_sym_diff_single,
            'EXPRESSION': f"area($geometry) < {max_gap_size}",
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        #save_temp_layer_to_gpkg(selected_areas, "a_selected_areas")

        # Merge selected gaps with hole_closed polygons
        merged_gap = gap_select(hole_closed, selected_areas, crs, 70)
        #save_temp_layer_to_gpkg(merged_gap, "a_merged_gap")
        #TODO prüfen ob der erste Teil so Sinn ergibt

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
        #save_temp_layer_to_gpkg(initial_buffer, "a_initial_buffer")

        boundary_line = processing.run("native:polygonstolines", {
            'INPUT': initial_buffer,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        boundary_buffer = processing.run("native:buffer", {
            'INPUT': boundary_line,
            'DISTANCE': gap_dist,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        #save_temp_layer_to_gpkg(boundary_buffer, "a_boundary_buffer")

        poly_cut_1 = processing.run("native:difference",
                       {'INPUT': initial_buffer,
                        'OVERLAY': boundary_buffer,
                        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
                        'GRID_SIZE': None,
                        })['OUTPUT']

        poly_cut_2 = processing.run("native:difference",
                       {'INPUT': poly_cut_1,
                        'OVERLAY': input_layer,
                        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
                        'GRID_SIZE': None,
                        })['OUTPUT']
        #save_temp_layer_to_gpkg(poly_cut_2, "a_poly_cut_2")

        poly_singlepart = processing.run("native:multiparttosingleparts",
                       {'INPUT': poly_cut_2,
                        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                        })['OUTPUT']


        small_removed = processing.run("qgis:extractbyexpression", {
            'INPUT': poly_singlepart,
            'EXPRESSION': f'area($geometry) > {200 * gap_dist / 15}',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        #save_temp_layer_to_gpkg(small_removed, "a_small_removed")


        final_gap = gap_select(input_layer, small_removed, crs, 70)

        gap_poly_max_size = processing.run("qgis:extractbyexpression", {
            'INPUT': final_gap,
            'EXPRESSION': f'area($geometry) < {max_gap_size}',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        #shp_area2(gap_poly_max_size)
        #save_temp_layer_to_gpkg(gap_poly_max_size, "a_gap_poly_max_size")

        merged_final = processing.run("native:mergevectorlayers", {
            'LAYERS': [gap_poly_max_size, merged_output],
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

        # Close holes in the input polygons
        dissolved_final_hole_colsed = processing.run("native:deleteholes", {
            'INPUT': dissolved_final,
            'MIN_AREA': max_hole_size,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']


        return dissolved_final_hole_colsed
    else:
        #("Input layer is empty.")
        return input_layer