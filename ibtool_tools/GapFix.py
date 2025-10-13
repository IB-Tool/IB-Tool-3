import processing
from qgis.core import QgsVectorLayer, QgsProject, QgsProcessing
from ibtool.helpers.logger import Logger
from ..helpers.system_utils import save_temp_layer_to_gpkg

def gapfix(Inputpoly, InputRoadnetwork, bufferwidth=70):
    """
    :param Inputpoly: Combined boundaries from all partitions as polygon shape
    :param InputRoadnetwork: Road network
    :param bufferwidth: Threshold for buffer
    :return: Refined polygon shape

    - Closes gaps between boundaries of different partitions
    """

    logger = Logger()

    try:
        logger.log("GapFix Start", level="INFO")


        # arcpy.GetCount_management(in_rows=Inputpoly)
        if isinstance(Inputpoly, str):
            input_layer = QgsVectorLayer(Inputpoly, "input", "ogr")
        else:
            input_layer = Inputpoly

        Anz_Input = input_layer.featureCount()
        logger.log(f"Input feature count: {Anz_Input}", level="INFO")

        if Anz_Input > 0:
            # arcpy.MakeFeatureLayer_management(Inputpoly) - not needed in QGIS
            # arcpy.management.FeatureToLine(Inputpoly, ugb_line, None, "ATTRIBUTES")
            ugb_line = processing.run("native:polygonstolines", {
                'INPUT': input_layer,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']
            logger.log("Converted polygons to lines", level="INFO")

            # arcpy.analysis.Buffer(ugb_line, ugb_buff, "{} Meters".format(bufferwidth), "FULL", "ROUND", "NONE", None, "PLANAR")
            ugb_buff = processing.run("native:buffer", {
                'INPUT': ugb_line,
                'DISTANCE': bufferwidth,
                'SEGMENTS': 5,
                'END_CAP_STYLE': 0,  # Round
                'JOIN_STYLE': 0,     # Round
                'MITER_LIMIT': 2,
                'DISSOLVE': False,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']
            logger.log(f"Created buffer with width {bufferwidth} meters", level="INFO")
            # arcpy.analysis.Intersect(ugb_buff, ugb_buff_intsec1, "ALL", None, "INPUT")
            ugb_buff_intsec1 = processing.run("native:intersection", {
                'INPUT': ugb_buff,
                'OVERLAY': ugb_buff,
                'INPUT_FIELDS': [],
                'OVERLAY_FIELDS': [],
                'OVERLAY_FIELDS_PREFIX': '',
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']
            logger.log("First intersection completed", level="INFO")

            # arcpy.analysis.Intersect(ugb_buff_intsec1, ugb_buff_intsec2, "ALL", None, "INPUT")
            ugb_buff_intsec2 = processing.run("native:intersection", {
                'INPUT': ugb_buff_intsec1,
                'OVERLAY': ugb_buff_intsec1,
                'INPUT_FIELDS': [],
                'OVERLAY_FIELDS': [],
                'OVERLAY_FIELDS_PREFIX': '',
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']
            logger.log("Second intersection completed", level="INFO")
            # arcpy.management.Dissolve(ugb_buff_intsec2, ugb_buff_intsec_diss, None, None, "SINGLE_PART", "DISSOLVE_LINES")
            ugb_buff_intsec_diss = processing.run("native:dissolve", {
                'INPUT': ugb_buff_intsec2,
                'FIELD': [],
                'SEPARATE_DISJOINT': True,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']
            logger.log("Dissolve operation completed", level="INFO")
            # arcpy.analysis.SymDiff(ugb_buff_intsec_diss, Inputpoly, ugb_symdiff, "ALL", None)
            ugb_symdiff = processing.run("native:symmetricaldifference", {
                'INPUT': ugb_buff_intsec_diss,
                'OVERLAY': input_layer,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']
            logger.log("Symmetric difference calculated", level="INFO")
            # arcpy.management.SelectLayerByLocation(ugb_symdiff_FL, "WITHIN", ugb_FL, None, "NEW_SELECTION", "NOT_INVERT")
            # arcpy.DeleteFeatures_management(ugb_symdiff_FL)
            ugb_symdiff_filtered1 = processing.run("native:extractbylocation", {
                'INPUT': ugb_symdiff,
                'PREDICATE': [0],  # intersect
                'INTERSECT': input_layer,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']

            # arcpy.management.SelectLayerByLocation(ugb_symdiff_FL, "INTERSECT", ugb_FL, None, "NEW_SELECTION", "INVERT")
            # arcpy.DeleteFeatures_management(ugb_symdiff_FL)
            ugb_symdiff_filtered = processing.run("native:extractbylocation", {
                'INPUT': ugb_symdiff_filtered1,
                'PREDICATE': [2],  # within
                'INTERSECT': input_layer,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']
            logger.log("Spatial filtering completed", level="INFO")

            # arcpy.GetCount_management(in_rows=ugb_symdiff_FL)
            Anz = ugb_symdiff_filtered.featureCount()
            logger.log(f"Filtered features count: {Anz}", level="INFO")

            if Anz > 0:
                # arcpy.management.Merge([InputRoadnetwork, ugb_line], rn_merge)
                if isinstance(InputRoadnetwork, str):
                    road_layer = QgsVectorLayer(InputRoadnetwork, "roads", "ogr")
                else:
                    road_layer = InputRoadnetwork

                rn_merge = processing.run("native:mergevectorlayers", {
                    'LAYERS': [road_layer, ugb_line],
                    'CRS': input_layer.crs(),
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                })['OUTPUT']
                logger.log("Merged road network with boundary lines", level="INFO")

                # arcpy.management.FeatureToPolygon(rn_merge, rn_merge_ply, None, "ATTRIBUTES", None)
                rn_merge_ply = processing.run("native:linestopolygons", {
                    'INPUT': rn_merge,
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                })['OUTPUT']
                logger.log("Converted lines to polygons", level="INFO")
                # arcpy.AddField_management(rn_merge_ply, "Name", "TEXT")
                # arcpy.management.CalculateField(rn_merge_ply, "Name", "'RoBl_'+ str(!OID!)", "PYTHON_9.3", None)
                rn_merge_ply_named = processing.run("native:fieldcalculator", {
                    'INPUT': rn_merge_ply,
                    'FIELD_NAME': 'Name',
                    'FIELD_TYPE': 2,  # String
                    'FIELD_LENGTH': 50,
                    'FORMULA': "'RoBl_' || $id",
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                })['OUTPUT']
                logger.log("Added Name field with calculated values", level="INFO")
                # arcpy.analysis.Split(ugb_symdiff_FL, rn_merge_ply, "Name", Workspace, None)
                # Note: QGIS doesn't have direct equivalent to Split, using intersection approach
                RoBl_split = processing.run("native:intersection", {
                    'INPUT': ugb_symdiff_filtered,
                    'OVERLAY': rn_merge_ply_named,
                    'INPUT_FIELDS': [],
                    'OVERLAY_FIELDS': ['Name'],
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                })['OUTPUT']

                # arcpy.management.Merge(MergeList, RoBl_Merge) - already merged through intersection
                RoBl_Merge = RoBl_split
                logger.log("Split and merge operations completed", level="INFO")
                # arcpy.management.SelectLayerByLocation(rn_merge_ply_FL, "WITHIN", RoBl_Merge_FL, None, "NEW_SELECTION", "NOT_INVERT")
                # arcpy.CopyFeatures_management(sel, RoBl_sel)
                RoBl_sel = processing.run("native:extractbylocation", {
                    'INPUT': rn_merge_ply_named,
                    'PREDICATE': [2],  # within
                    'INTERSECT': RoBl_Merge,
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                })['OUTPUT']
                logger.log("Selected features within merged boundaries", level="INFO")

                # arcpy.management.Merge([Inputpoly, RoBl_sel], inputpoly_merge)
                inputpoly_merge = processing.run("native:mergevectorlayers", {
                    'LAYERS': [input_layer, RoBl_sel],
                    'CRS': input_layer.crs(),
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                })['OUTPUT']
                logger.log("Merged input polygons with selected features", level="INFO")

                # arcpy.management.Dissolve(inputpoly_merge, GapFix_out, None, None, "SINGLE_PART", "DISSOLVE_LINES")
                final_result = processing.run("native:dissolve", {
                    'INPUT': inputpoly_merge,
                    'FIELD': [],
                    'SEPARATE_DISJOINT': True,
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                })['OUTPUT']

                # Get feature count for logging
                result_count = final_result.featureCount() if hasattr(final_result, 'featureCount') else 0
                logger.log(f"GapFix End - Patches: {result_count}", level="INFO")
                return final_result
            else:
                logger.log("No gaps to GapFix", level="INFO")
                return Inputpoly
        else:
            logger.log("No gaps to GapFix - input empty", level="INFO")
            return Inputpoly

    except Exception as e:
        logger.log(f"Error in GapFix operation: {str(e)}", level="CRITICAL")
        raise e