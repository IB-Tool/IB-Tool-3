import processing
from qgis.core import QgsVectorLayer, QgsProcessing
from ibtool.helpers.logger import Logger
from ibtool.helpers.geometry_utils import intersect_polygons
from ibtool.helpers.system_utils import save_temp_layer_to_gpkg

def gap_fix(Inputpoly, InputRoadnetwork, workspace_path, bufferwidth=70):
    """
    :param Inputpoly: Combined boundaries from all partitions as polygon shape
    :param InputRoadnetwork: Road network
    :param bufferwidth: Threshold for buffer
    :return: Refined polygon shape

    - Closes gaps between boundaries of different partitions
    """

    try:
        Logger.log("GapFix Start", level="INFO")

        if isinstance(Inputpoly, str):
            input_layer = QgsVectorLayer(Inputpoly, "input", "ogr")
        else:
            input_layer = Inputpoly

        Anz_Input = input_layer.featureCount()

        save_temp_layer_to_gpkg(Inputpoly, "D_Inputpoly", workspace_path)

        if Anz_Input > 0:

            ugb_intersect1 = intersect_polygons(Inputpoly)

            ugb_intersect2 = intersect_polygons(ugb_intersect1)

            save_temp_layer_to_gpkg(ugb_intersect1, "D_ugb_intersect1", workspace_path)

            # arcpy.management.Dissolve(ugb_buff_intsec2, ugb_buff_intsec_diss, None, None, "SINGLE_PART", "DISSOLVE_LINES")
            ugb_buff_intsec_diss = processing.run("native:dissolve", {
                'INPUT': ugb_intersect2,
                'FIELD': [],
                'SEPARATE_DISJOINT': True,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']

            ugb_symdiff = processing.run("native:symmetricaldifference", {
                'INPUT': ugb_buff_intsec_diss,
                'OVERLAY': input_layer,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']

            processing.run("native:selectbylocation", {
                'INPUT': ugb_symdiff,
                'PREDICATE': [2],
                'INTERSECT': input_layer,
                'METHOD': 0})

            ugb_symdiff.invertSelection()

            ugb_symdiff_del1 = processing.run("native:saveselectedfeatures", {
                'INPUT': ugb_symdiff,
                'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

            processing.run("native:selectbylocation", {
                'INPUT': ugb_symdiff_del1,
                'PREDICATE': [0],
                'INTERSECT': input_layer,
                'METHOD': 0})

            ugb_symdiff_del1.invertSelection()

            ugb_symdiff_del2 = processing.run("native:saveselectedfeatures", {
                'INPUT': ugb_symdiff_del1,
                'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

            Anz = ugb_symdiff_del2.featureCount()
            Logger.log(f"Filtered features count: {Anz}", level="INFO")

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

                rn_merge_ply = processing.run("native:polygonize", {
                    'INPUT': rn_merge,
                    'KEEP_FIELDS': False,
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
                })['OUTPUT']

                rn_merge_ply_named = processing.run("native:fieldcalculator", {
                    'INPUT': rn_merge_ply,
                    'FIELD_NAME': 'Name',
                    'FIELD_TYPE': 2,  # String
                    'FIELD_LENGTH': 50,
                    'FORMULA': "'RoBl_' || $id",
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                })['OUTPUT']

                RoBl_split = processing.run("native:intersection", {
                    'INPUT': ugb_symdiff,
                    'OVERLAY': rn_merge_ply_named,
                    'INPUT_FIELDS': [],
                    'OVERLAY_FIELDS': ['Name'],
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                })['OUTPUT']

                RoBl_Merge = RoBl_split

                RoBl_sel = processing.run("native:extractbylocation", {
                    'INPUT': rn_merge_ply_named,
                    'PREDICATE': [2],  # within
                    'INTERSECT': RoBl_Merge,
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                })['OUTPUT']

                inputpoly_merge = processing.run("native:mergevectorlayers", {
                    'LAYERS': [input_layer, RoBl_sel],
                    'CRS': input_layer.crs(),
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                })['OUTPUT']

                final_result = processing.run("native:dissolve", {
                    'INPUT': inputpoly_merge,
                    'FIELD': [],
                    'SEPARATE_DISJOINT': True,
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                })['OUTPUT']

                # Get feature count for logging
                result_count = final_result.featureCount() if hasattr(final_result, 'featureCount') else 0
                Logger.log(f"GapFix End - Patches: {result_count}", level="INFO")
                return final_result
            else:
                Logger.log("No gaps to GapFix", level="INFO")
                return Inputpoly
        else:
            Logger.log("No gaps to GapFix - input empty", level="INFO")
            return Inputpoly

    except Exception as e:
        Logger.log(f"Error in GapFix operation: {str(e)}", level="CRITICAL")
        raise e