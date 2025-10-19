
from qgis.core import *
from qgis.PyQt.QtCore import QMetaType
from qgis import processing

from ibtool.ibtool_tools.FootprintDensity import calc_footprint_density, identify_dense_blocks
from ibtool.helpers.system_utils import save_temp_layer_to_gpkg
from ibtool.helpers.message import msg
from ibtool.helpers.geometry_utils import shp_area2

from ibtool.helpers.logger import Logger

def patch_remove(input_poly, input_bdg, crs, workspace_path, min_patch_size=10000, min_bdg_count=20, footprint_area_sum=6000, footprint_density_threshold=18, ):
    """
    Entfernt Abgrenzungen, die zu klein sind oder zu wenige Gebäude enthalten

    :param input_poly: Eingabe-Polygon-Layer
    :param input_bdg: Gebäude-Layer
    :param min_patch_size: Minimale Flächengröße
    :param min_bdg_count: Minimale Anzahl an Gebäuden
    :param footprint_density_threshold: Schwellenwert für Gebäudedichte
    :return: Bereinigter Polygon-Layer
    """

    input_poly_sp = processing.run("native:multiparttosingleparts",
                   {'INPUT': input_poly,
                    'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

    # Feldhinzufügung
    input_poly_sp.dataProvider().addAttributes([QgsField("NAME", QMetaType.QString)])
    input_poly_sp.updateFields()

    # Berechnung des NAME-Feldes
    with edit(input_poly_sp):
        for feature in input_poly_sp.getFeatures():
            feature['NAME'] = f'Block_{feature.id()}'
            input_poly_sp.updateFeature(feature)

    # Neues Feld hinzufügen
    input_poly_sp.dataProvider().addAttributes([QgsField("join_count", QMetaType.Int)])
    input_poly_sp.updateFields()

    with edit(input_poly_sp):
        for feature in input_poly_sp.getFeatures():
            #geom = feature.geometry()
            name = feature['NAME']
            block_sel = processing.run("native:extractbyattribute",{
                'INPUT': input_poly_sp,
                            'FIELD': 'NAME',
                'OPERATOR': 0,
                'VALUE': name,
                'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

            try:
                intersect = processing.run("native:extractbylocation",
                               {
                                'INPUT': input_bdg,
                                'PREDICATE': [0],
                                'INTERSECT': block_sel,
                                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                               })['OUTPUT']

                # Anzahl der überschneidenden Features setzen
                join_count = intersect.featureCount()
                feature['join_count'] = join_count
                input_poly_sp.updateFeature(feature)
            except Exception as e:
                Logger.log(f"Fehler bei der Verarbeitung von Feature {feature.id()}: {e}",level="WARNING")
        else:
            Logger.log(f"Feature {feature.id()} hat keine gültige Geometrie.", level="WARNING")

    shp_area2(input_poly_sp)
    #save_temp_layer_to_gpkg(input_poly_sp, "input_poly_sp", workspace_path)

    input_poly_sp_sel = processing.run("native:extractbyexpression",{
                'INPUT': input_poly_sp,
                #'EXPRESSION': f' "Area" > {min_patch_size} and "join_count > {min_bdg_count}',
                'EXPRESSION': ' "Area" > {} and  "join_count" > {}'.format(str(min_patch_size), str(min_bdg_count)),
                'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']
    #save_temp_layer_to_gpkg(input_poly_sp_sel, "c_input_poly_sp_sel", workspace_path)

    dense_blocks = identify_dense_blocks(input_bdg, input_poly_sp, footprint_density_threshold)
    #save_temp_layer_to_gpkg(dense_blocks, "c_dense_blocks", workspace_path)

    dense_blocks_sel = processing.run("native:extractbyexpression",{
                'INPUT': dense_blocks,
                'EXPRESSION': ' "SHAPE_AREA" >= {} or  "FOOTPRINT_AREA_sum" >= {}'.format(str(min_patch_size), str(footprint_area_sum)),
                'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']
    #save_temp_layer_to_gpkg(dense_blocks_sel, "c_dense_blocks_sel", workspace_path)

    merge = processing.run("native:mergevectorlayers", {
        'LAYERS': [dense_blocks_sel, input_poly_sp_sel],
        'CRS': crs,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']


    return merge