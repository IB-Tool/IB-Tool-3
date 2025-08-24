import os

from qgis.core import QgsWkbTypes, QgsVectorLayer, QgsProcessingUtils
from qgis import processing

from ..helpers.logger import Logger
from ..helpers.system_utils import save_temp_layer_to_gpkg
from ..helpers.geometry_utils import select_and_save_by_location, shp_area, shp_area2

def import_filter(filename, HU_Input):
    """
    Importiert Listen von Gebäuden aus IB-Tool2_Filter.txt und erstellt Selektionsstrings.
    :param filename: Datei mit Filterdefinitionen
    :param HU_Input: Gebäude-Shape-Layer als Polygon
    :return: Selektionsstrings für positive und negative Filter

    - Liest die Filterdatei und konvertiert sie in zwei Listen (positiv/negativ).
    - Erstellt Selektionsstrings für spätere Filterung.
    """
    if not os.path.isfile(filename):
        raise Exception(f"{filename} existiert nicht im Arbeitsverzeichnis.")

    # Überprüfen, ob der Eingabelayer das richtige Format hat
    if not HU_Input.isValid() or HU_Input.geometryType() != QgsWkbTypes.PolygonGeometry:
        raise Exception("hu_layer muss ein gültiger Polygon-Layer sein.")


    # Feldname bestimmen
    fieldname = None
    fields = HU_Input.fields()
    if fields.indexOf("fkt") != -1:
        fieldname = "fkt"
    elif fields.indexOf("funktion") != -1:
        fieldname = "funktion"
    else:
        raise Exception("Das Eingabe-Shape enthält weder ein 'fkt'- noch ein 'funktion'-Feld.")

    # Filterdatei lesen und Listen erstellen
    with open(filename, 'r', encoding='utf-8') as file:
        listpos = []
        listneg = []
        current_section = None

        for row in file:
            row = row.strip()
            if row.startswith("#Filter positive"):
                current_section = "positive"
            elif row.startswith("#Filter negative"):
                current_section = "negative"
            elif row.startswith("#") or not row:
                continue
            else:
                if current_section == "positive":
                    listpos.append(f"'{row[:10]}'")
                elif current_section == "negative":
                    listneg.append(f"'{row[:10]}'")

    # Selektionsstrings erstellen
    def create_filter_string(filter_list, fieldname):
        filter_string = ""
        for index, value in enumerate(filter_list):
            addstring = f"{fieldname} LIKE {value}"
            if index < len(filter_list) - 1:
                addstring += " OR "
            filter_string += addstring
        return filter_string

    filterpos = create_filter_string(listpos, fieldname)
    filterneg = create_filter_string(listneg, fieldname)

    return filterpos, filterneg, fieldname


def input_hu_filter(HU_Input, filter_file, MinAreaAllBdgs=56.8, PointDensCellSize=50, PointDensNbh=100, ):
    """
    :param HU_Input: input building footprints (QgsVectorLayer)
    :param MinAreaAllBdgs: minimum area of all filtered buildings
    :param PointDensCellSize: cell size parameter in meters of density function
    :param PointDensNbh: search radius parameter in meters of density function
    :return: filtered buildings (QgsVectorLayer)

    - Select residential buildings (filterpos list) and create density-based selecting polygon
    - Delete negative buildings (filterneg list) within residential selecting polygon
    - Delete small buildings
    """
    # Check if the input layer is valid
    if not HU_Input.isValid() or HU_Input.geometryType() != QgsWkbTypes.PolygonGeometry:
        raise Exception("hu_layer must be a valid polygon layer.")

    anz_hu = HU_Input.featureCount()

    if anz_hu > MinAreaAllBdgs:

        HU_Input = shp_area(HU_Input)

        filterpos, filterneg, fieldname = import_filter(filter_file, HU_Input)

        # Step 1: Select residential buildings (positive filter)
        residential_layer = processing.run("native:extractbyexpression", {
            'INPUT': HU_Input,
            'EXPRESSION': filterpos,
            'OUTPUT': 'memory:'
        })['OUTPUT']
        if not isinstance(residential_layer, QgsVectorLayer):
            raise Exception("Failed to create residential_layer")

        # Feature-to-Point
        res_cent = processing.run("native:centroids", {
            'INPUT': residential_layer,
            'ALL_PARTS': False,
            'OUTPUT': 'memory:'
        })['OUTPUT']
        if not isinstance(res_cent, QgsVectorLayer):
            raise Exception("Failed to create res_cent")

        # Create point density
        hu_raster = QgsProcessingUtils.generateTempFilename("hu_raster.tif")
        processing.run("qgis:heatmapkerneldensityestimation", {
            'INPUT': res_cent,
            'RADIUS': PointDensNbh,
            'PIXEL_SIZE': PointDensCellSize,
            'DECAY': 0,
            'OUTPUT': hu_raster
        })

        # Raster-to-Point
        res_density_points = processing.run("native:pixelstopoints", {
            'INPUT_RASTER': hu_raster,
            'RASTER_BAND': 1,
            'FIELD_NAME': 'VALUE',
            'OUTPUT': 'memory:'
        })['OUTPUT']
        if not isinstance(res_density_points, QgsVectorLayer):
            raise Exception("Failed to create res_density_points")

        # Filter points by density value
        filtered_points = processing.run("native:extractbyexpression", {
            'INPUT': res_density_points,
            'EXPRESSION': f"value >= 4",
            'OUTPUT': 'memory:'
        })['OUTPUT']
        if not isinstance(filtered_points, QgsVectorLayer):
            raise Exception("Failed to create filtered_points")

        # Buffer around filtered points
        points_buffer = processing.run("native:buffer", {
            'INPUT': filtered_points,
            'DISTANCE': PointDensCellSize / 1.5,
            'SEGMENTS': 5,
            'END_CAP_STYLE': 0,
            'JOIN_STYLE': 0,
            'MITER_LIMIT': 1,
            'DISSOLVE': True,
            'SEPARATE_DISJOINT': False,
            'OUTPUT': 'memory:'
        })['OUTPUT']
        if not isinstance(points_buffer, QgsVectorLayer):
            raise Exception("Failed to create points_buffer")

        # Step 2: Exclude buildings (negative filter)
        negative_layer = processing.run("native:extractbyexpression", {
            'INPUT': HU_Input,
            'EXPRESSION': filterneg,
            'OUTPUT': 'memory:'
        })['OUTPUT']
        if not isinstance(negative_layer, QgsVectorLayer):
            raise Exception("Failed to create negative_layer")

        # Exclude negative buildings within residential area
        hu_neg_sel = select_and_save_by_location(negative_layer, points_buffer, predicate=2)
        hu_final = select_and_save_by_location(HU_Input, hu_neg_sel, predicate=2)

        # Step 3: Delete small buildings
        hu_diss = processing.run("native:dissolve",{
            'INPUT': hu_final,
            'FIELD': [],
            'SEPARATE_DISJOINT': True,
            'OUTPUT': 'memory:'
        })['OUTPUT']
        shp_area2(hu_diss, "Area")

        diss_del = processing.run("native:extractbyattribute", {
            'INPUT': hu_diss,
            'FIELD': 'Area',
            'OPERATOR': 2,
            'VALUE': MinAreaAllBdgs,
            'OUTPUT': 'memory:'
        })['OUTPUT']
        if not isinstance(diss_del, QgsVectorLayer):
            raise Exception("Failed to create final_layer")

        hu_final_sel = select_and_save_by_location(hu_final, diss_del, predicate=0)

        final_layer = processing.run("native:extractbyattribute", {
            'INPUT': hu_final_sel,
            'FIELD': 'Area',
            'OPERATOR': 2,
            'VALUE': 35,
            'OUTPUT': 'memory:'
        })['OUTPUT']


        return final_layer

    else:
        Logger.log(f"Anzahl der Gebäude für Filterung zu gering: {anz_hu}", level="WARNING")
        return HU_Input