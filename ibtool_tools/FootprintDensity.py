from qgis.core import (
    QgsProcessingFeatureSourceDefinition,
    QgsVectorLayer,
    QgsProcessing,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsVectorLayerUtils,
    QgsFeature,
    QgsProject,
    QgsExpression,
    QgsField,
    QgsFeatureRequest,
    QgsVectorLayerJoinInfo,
    edit,
    QgsGeometry,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsProcessingOutputLayerDefinition,
    QgsVectorFileWriter
)

from qgis import processing
import os
import sys
from qgis.PyQt.QtCore import QVariant, QMetaType


# Absoluten Pfad des benachbarten Ordners berechnen
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
utils_dir = os.path.join(parent_dir, 'helpers')

# Den Ordner zu sys.path hinzufügen
sys.path.append(utils_dir)
from ..helpers.system_utils import save_temp_layer_to_gpkg
from ..helpers.message import msg
from ..helpers.logger import Logger

def calc_footprint_density(InputBdg, InputStrNetwork, Buffer=100, GlobalThreshold=18, Ext='local',
                           MinBdgCount=20, Partition=None):
    """
    Calculates the degree of overlap of the given building footprints on the city blocks
    constructed of the given road network.

    :param InputBdg: QgsVectorLayer with building footprints
    :param InputStrNetwork: QgsVectorLayer with road network
    :param Buffer: Buffer distance to determine dense settlement areas
    :param GlobalThreshold: fallback value of GlobalThreshold
    :param Ext: Extent of area to calculate ('local' or 'global')
    :param MinBdgCount: Minimum building count to consider
    :param Partition: Partition layer for 'global' extent
    :return: Global overlap value in percent
    """

    def select_block(InputStrNetwork, InputBdg, Buffer):

        # Convert the street network to polygons
        InputStrNetwork_Poly = processing.run("native:polygonize", {
            'INPUT': InputStrNetwork,
            'OUTPUT': 'TEMPORARY_OUTPUT'
        })['OUTPUT']
        #save_temp_layer_to_gpkg(InputStrNetwork_Poly, "InputStrNetwork_Poly")


        # Create a spatial index for the polygonized street network
        processing.run("native:createspatialindex", {
            'INPUT': InputStrNetwork_Poly
        })

        # Buffer buildings and dissolve them
        InputBdg_Buff = processing.run("native:buffer", {
            'INPUT': InputBdg,
            'DISTANCE': Buffer,
            'SEGMENTS': 5,
            'END_CAP_STYLE': 0,  # Round
            'JOIN_STYLE': 0,  # Round
            'MITER_LIMIT': 2,
            'DISSOLVE': True,
            'OUTPUT': 'TEMPORARY_OUTPUT'
        })['OUTPUT']
        #save_temp_layer_to_gpkg(InputBdg_Buff, "InputBdg_Buff")

        # Create a spatial index for the polygonized street network
        processing.run("native:createspatialindex", {
            'INPUT': InputBdg_Buff
        })

        InputBdg_Buff_Line = processing.run("native:polygonstolines", {
            'INPUT': InputBdg_Buff,
            'OUTPUT': 'TEMPORARY_OUTPUT'
        })['OUTPUT']
        #save_temp_layer_to_gpkg(InputBdg_Buff_Line, "InputBdg_Buff_Line")

        # Erste Auswahl basierend auf räumlicher Beziehung
        processing.run("native:selectbylocation", {
            'INPUT': InputStrNetwork_Poly,
            'PREDICATE': [0],  # Überschneidet
            'INTERSECT': InputBdg_Buff_Line,
            'METHOD': 0  # Neue Auswahl erstellen
        })

        # IDs der ausgewählten Features holen
        selected_ids = InputStrNetwork_Poly.selectedFeatureIds()

        # Invertierung: Wähle alle Features, die nicht in der aktuellen Auswahl sind
        all_ids = [f.id() for f in InputStrNetwork_Poly.getFeatures()]
        inverted_ids = [fid for fid in all_ids if fid not in selected_ids]


        # Auswahl mit invertierten IDs setzen
        InputStrNetwork_Poly.selectByIds(inverted_ids)

        InputStrNetwork_Poly_Sel = processing.run("native:saveselectedfeatures",
                       {'INPUT': InputStrNetwork_Poly,
                        'OUTPUT': 'TEMPORARY_OUTPUT'
                        })['OUTPUT']

        # Zweite Auswahl basierend auf der invertierten Auswahl
        BlocksInside = processing.run("native:selectbylocation", {
            'INPUT': InputStrNetwork_Poly_Sel,
            'PREDICATE': [0],  # Überschneidet
            'INTERSECT': InputBdg,
            'METHOD': 2  # Auswahl verfeinern (auf bestehender Auswahl aufbauen)
        })['OUTPUT']
        #save_temp_layer_to_gpkg(BlocksInside, "BlocksInside")

        InputBdg_Diss = processing.run("native:dissolve",
                       {'INPUT': InputBdg,
                        'FIELD': [],
                        'SEPARATE_DISJOINT': True,
                        'OUTPUT': 'TEMPORARY_OUTPUT'
                        })['OUTPUT']

        # Spatial join between building buffer and street polygons
        Blocks_join = processing.run("native:joinbylocationsummary", {
            'INPUT': BlocksInside,
            'JOIN': InputBdg_Diss,
            'PREDICATE': [0],  # Intersects
            'JOIN_FIELDS': [],
            'SUMMARIES': [0],
            'DISCARD_NONMATCHING': False,
            'OUTPUT': 'TEMPORARY_OUTPUT'
        })['OUTPUT']
        #save_temp_layer_to_gpkg(Blocks_join, "Blocks_join")

        # Filter blocks with enough buildings
        Blocks_filtered = processing.run("native:extractbyattribute", {
            'INPUT': Blocks_join,
            'FIELD': 'oid_1_count',
            'OPERATOR': 2,  # Greater than
            'VALUE': MinBdgCount,
            'OUTPUT': 'TEMPORARY_OUTPUT'
        })['OUTPUT']
        #save_temp_layer_to_gpkg(Blocks_filtered, "Blocks_filtered")

        return Blocks_filtered


    if Ext == 'global':
        Logger.log("Start calc footprint global", 'SUCCESS')
        if not Partition:
            raise ValueError("Partition layer is required for global extent.")

        Merge_Dummy = None

        for feature in Partition.getFeatures():
            where_clause = f'"NAME" = \'{feature["NAME"]}\''
            filtered_partition = processing.run("native:extractbyexpression", {
                'INPUT': Partition,
                'EXPRESSION': where_clause,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            })['OUTPUT']
            #save_temp_layer_to_gpkg(filtered_partition,"filtered_partition")

            # Filter buildings and streets by partition
            SelHU = processing.run("native:extractbylocation", {
                'INPUT': InputBdg,
                'PREDICATE': [0],  # Intersects
                'INTERSECT': filtered_partition,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            })['OUTPUT']
            #save_temp_layer_to_gpkg(SelHU, "SelHU")

            SelStrassen = processing.run("native:extractbylocation", {
                'INPUT': InputStrNetwork,
                'PREDICATE': [0],  # Intersects
                'INTERSECT': filtered_partition,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            })['OUTPUT']

            Inner_BlocksPart = select_block(SelStrassen, SelHU, Buffer)

            if Merge_Dummy:
                Merge_Dummy = processing.run("native:mergevectorlayers", {
                    'LAYERS': [Merge_Dummy, Inner_BlocksPart],
                    'OUTPUT': 'TEMPORARY_OUTPUT'
                })['OUTPUT']
            else:
                Merge_Dummy = Inner_BlocksPart

        Inner_Blocks = Merge_Dummy


    else:  # Local extent
        Inner_Blocks = select_block(InputStrNetwork, InputBdg, Buffer)


    # Calculate block names
    Inner_Blocks = processing.run("native:addautoincrementalfield", {
        'INPUT': Inner_Blocks,
        'FIELD_NAME': 'NAME',
        'START': 1,
        'GROUP_FIELDS': [],
        'SORT_EXPRESSION': '',
        'OUTPUT': 'TEMPORARY_OUTPUT'
    })['OUTPUT']

    # Calculate the overlap
    result = Inner_Blocks.featureCount()
    Logger.log("Inner blocks count: {}".format(result),'SUCCESS')

    if result > 5:
        overlap_sum = 0
        Blocks_red = footprint_density(InputBdg, Inner_Blocks, 0)

        for feature in Blocks_red.getFeatures():
            overlap_sum += feature["OVERLAP"]  # Assuming OVERLAP field exists

        global_overlap = overlap_sum / result
    else:
        global_overlap = GlobalThreshold

    return global_overlap


def footprint_density(HU_Input, Bloecke, footprint_density_threshold):
    """
    Berechnet den Flächenanteil kleiner Polygone an großen Polygonen in QGIS.

    :param small_polygons_layer: Name oder Pfad zum Layer mit kleinen Polygonen
    :param large_polygons_layer: Name oder Pfad zum Layer mit großen Polygonen
    :param output_path: Pfad zur Ausgabe-Shape-Datei
    """
    # Lade die Eingabe-Layer
    #small_layer = QgsProject.instance().mapLayersByName(small_polygons_layer)[0]
    #large_layer = QgsProject.instance().mapLayersByName(large_polygons_layer)[0]

    # Geoverarbeitung: Intersektion
    intersection_result = processing.run(
        "native:intersection",
        {
            'INPUT': HU_Input,
            'OVERLAY': Bloecke,
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }
        )
    intersected_layer = intersection_result['OUTPUT']

    # Fläche der Intersektion berechnen
    intersected_layer.startEditing()
    provider = intersected_layer.dataProvider()

    # Sicherstellen, dass das Feld 'area_intersect' existiert
    if provider.fieldNameIndex('area_intersect') == -1:
        provider.addAttributes([QgsField("area_intersect", QMetaType.Double)])
        intersected_layer.updateFields()

    for feature in intersected_layer.getFeatures():
        geom = feature.geometry()
        area = geom.area()
        feature['area_intersect'] = area
        intersected_layer.updateFeature(feature)
    intersected_layer.commitChanges()
    #save_temp_layer_to_gpkg(intersected_layer, "intersected_layer")

    # Summierung der Flächenanteile für jedes große Polygon
    sum_result = processing.run(
        "native:aggregate",
        {
            'INPUT': intersected_layer,
            'GROUP_BY': 'NAME',  # Ersetze "large_id" durch das Feld, das die IDs der großen Polygone enthält
            'AGGREGATES': [
                {'aggregate': 'sum', 'delimiter': ',', 'input': 'area_intersect', 'length': 10,
                 'name': 'sum_area_intersect', 'precision': 3, 'type': 6},
                {'aggregate': 'median', 'delimiter': ',', 'input': '"NAME"', 'length': 0, 'name': 'NAME_SUM',
                 'precision': 0, 'sub_type': 0, 'type': 4, 'type_name': 'int8'}
            ],
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }
    )['OUTPUT']

    # Fläche der großen Polygone hinzufügen
    joined_layer = processing.run(
        "native:joinattributestable",
        {
            'INPUT': Bloecke,
            'FIELD': 'NAME',  # Ersetze "large_id" durch das ID-Feld der großen Polygone
            'INPUT_2': sum_result,
            'FIELD_2': 'NAME_SUM',
            'FIELDS_TO_COPY': ['sum_area_intersect'],
            'METHOD': 1,  # Take attributes of the first matching feature only
            'DISCARD_NONMATCHING': True,
            'PREFIX': '',
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }
    )['OUTPUT']

    # Berechnung des Flächenanteils
    joined_layer.startEditing()
    provider = joined_layer.dataProvider()

    # Ensure the 'OVERLAP' field exists
    if provider.fieldNameIndex('OVERLAP') == -1:
        provider.addAttributes([QgsField("OVERLAP", QMetaType.Double)])
    joined_layer.updateFields()
    joined_layer.commitChanges()

    joined_layer.startEditing()
    for feature in joined_layer.getFeatures():
        total_intersect_area = feature['sum_area_intersect']
        large_polygon_area = feature.geometry().area()
        if large_polygon_area > 0:
            feature['OVERLAP'] = (total_intersect_area / large_polygon_area) * 100
        else:
            feature['OVERLAP'] = 0
        joined_layer.updateFeature(feature)
    joined_layer.commitChanges()


    return joined_layer


def identify_dense_blocks(HU_Input, Bloecke, footprintdensitythreshold):
    """
    :param HU_Input: Input layer of building footprints (QGIS vector layer)
    :param Bloecke: Input layer of city blocks (QGIS vector layer)
    :param footprintdensitythreshold: Threshold for footprint density
    :return: City blocks and related buildings below given footprintdensitythreshold

    - Calculates the overlap ratio of the sum of building footprint areas to the area of each city block
    - Returns buildings and city blocks below the given footprintdensitythreshold
    """

    # Ensure input layers are loaded
    if not isinstance(HU_Input, QgsVectorLayer) or not isinstance(Bloecke, QgsVectorLayer):
        raise ValueError("Both hu_layer and Bloecke must be valid QgsVectorLayer objects.")

    bloecke_singlepart = processing.run("native:multiparttosingleparts",
                   {'INPUT': Bloecke,
                    'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

    # Add area fields for both buildings and blocks
    bloecke_singlepart.startEditing()
    if "SHAPE_AREA" not in [field.name() for field in bloecke_singlepart.fields()]:
        bloecke_singlepart.dataProvider().addAttributes([QgsField("SHAPE_AREA", QMetaType.Double)])
    bloecke_singlepart.commitChanges()

    HU_Input.startEditing()
    if "FOOTPRINT_AREA" not in [field.name() for field in HU_Input.fields()]:
        HU_Input.dataProvider().addAttributes([QgsField("FOOTPRINT_AREA", QMetaType.Double)])
    HU_Input.commitChanges()

    # Calculate areas
    expr_blk_area = QgsExpression("$area")
    expr_ftprt_area = QgsExpression("$area")
    with edit(bloecke_singlepart):
        for feature in bloecke_singlepart.getFeatures():
            context = QgsExpressionContext()
            context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(bloecke_singlepart))
            context.setFeature(feature)
            feature["SHAPE_AREA"] = expr_blk_area.evaluate(context)
            bloecke_singlepart.updateFeature(feature)

    with edit(HU_Input):
        for feature in HU_Input.getFeatures():
            context = QgsExpressionContext()
            context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(HU_Input))
            context.setFeature(feature)
            feature["FOOTPRINT_AREA"] = expr_ftprt_area.evaluate(context)
            HU_Input.updateFeature(feature)

    # Perform a spatial join to associate building footprints with city blocks
    dissolved_layer = processing.run("native:joinbylocationsummary",
                   {'INPUT': bloecke_singlepart,
                    'PREDICATE': [0],
                    'JOIN': HU_Input,
                    'JOIN_FIELDS': ['FOOTPRINT_AREA'],
                    'SUMMARIES': [5],
                    'DISCARD_NONMATCHING': True,
                    'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

    # Calculate overlap
    diss_overlap = processing.run("native:fieldcalculator",
                   {'INPUT': dissolved_layer,
                    'FIELD_NAME': 'OVERLAP',
                    'FIELD_TYPE': 0,
                    'FIELD_LENGTH': 0,
                    'FIELD_PRECISION': 0,
                    'FORMULA': ' "FOOTPRINT_AREA_sum" / "SHAPE_AREA" * 100',
                    'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

    # Filter blocks below the footprint density threshold
    filtered_layer = processing.run(
        "native:extractbyexpression",
        {
            "INPUT": diss_overlap,
            "EXPRESSION": '\"OVERLAP\" >= {}'.format(footprintdensitythreshold),
            'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

    return filtered_layer
