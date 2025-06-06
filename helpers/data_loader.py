from PyQt5.QtWidgets import QFileDialog

from qgis.core import QgsVectorLayer, QgsWkbTypes, QgsProcessingFeedback, QgsProcessingException
from qgis import processing
from .logger import Logger
from .system_utils import save_temp_layer_to_gpkg

Logger = Logger()


# Function to select the HU input file
def select_HU_file(dlg):
    filename, _filter = QFileDialog.getOpenFileName(
        dlg, "Select input file", "", "*.shp"
    )
    dlg.HuPath.setText(filename)

# Function to select the RN input file
def select_RN_file(dlg):
    filename, _filter = QFileDialog.getOpenFileName(
        dlg, "Select input file", "", "*.shp"
    )
    dlg.RnPath.setText(filename)

# Function to select the PART input file
def select_PART_file(dlg):
    filename, _filter = QFileDialog.getOpenFileName(
        dlg, "Select input file", "", "*.shp"
    )
    dlg.PartPath.setText(filename)

# Function to select the AUX input file
def select_AUX_file(dlg):
    filename, _filter = QFileDialog.getOpenFileName(
        dlg, "Select input file", "", "*.shp"
    )
    dlg.AuxPath.setText(filename)

# Function to select the output GeoPackage file
def select_output_file(dlg):
    filename, _filter = QFileDialog.getSaveFileName(
        dlg, "Select output file", "", "*.gpkg"
    )
    dlg.OutputPath.setText(filename)

# Function to select a workspace directory
def select_workspace_file(dlg):
    directory = QFileDialog.getExistingDirectory(
        dlg,
        "Open Directory",  # Dialog title
        "",  # Default path, empty for current directory
        QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
    )
    dlg.WorkspacePath.setText(directory)


def create_partitions_list(Partition_layer, partlist, partstart, partend):
    # Laden des Layers
    #Partition_layer = QgsVectorLayer(Partition_layer_path, "Partition Layer", "ogr")

    if not Partition_layer.isValid():
        raise ValueError("Ungültiger Layer. Überprüfen Sie den Pfad zur Partition-Tabelle.")

    # Überprüfen, ob partlist den Wert '#' enthält
    if str(partlist[0]) == str('#'):
        if partstart == -1 or partend == -1:
            # partlist und partstart ohne Werte
            partlist = []
            for feature in Partition_layer.getFeatures():
                partlist.append(feature["NAME"])
        else:
            # partstart und partend mit Werten
            partlist = []
            for feature in Partition_layer.getFeatures():
                partlist.append(feature["NAME"])
            partlist = partlist[partstart:partend]

    else:
        # Bearbeitung von partlist mit Werten
        partlist = [j.replace('\n', '') for j in partlist]

    return partlist

def create_auxiliary_data(veg_layer, strassen, workspace_path):
    """
    Creates auxiliary data by converting vegetation layers to lines if needed, merging them with roads,
    and converting the result to polygons.

    :param veg_layer: Vegetation layer (QGIS layer)
    :param strassen: Roads layer (QGIS layer)
    :return: Auxiliary polygons layer
    """
    feedback = QgsProcessingFeedback()
    AuxFileList = []
    AuxLayers = [veg_layer]

    for idx, layer in enumerate(AuxLayers, start=1):
        filename = f"memory:AuxFile_{idx}"
        if layer.wkbType() not in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString]:
            # Convert non-line layers to lines
            result = processing.run("native:polygonstolines", {
                'INPUT': layer,
                'OUTPUT': filename
            }, feedback=feedback)
            if not result['OUTPUT']:
                raise QgsProcessingException(f"Layer {filename} could not be created")
            AuxFileList.append(filename)
        else:
            # Add line layers directly
            AuxFileList.append(layer.source())

    # Add roads layer
    AuxFileList.append(strassen.source())
    Logger.log(f"Auxiliary layers: {AuxFileList}")

    # Merge all layers into a single line layer
    AuxLayers_Line = processing.run("native:mergevectorlayers", {
        'LAYERS': AuxFileList,
        'OUTPUT': 'memory:AuxLayers_Line'
    }, feedback=feedback)['OUTPUT']

    # Convert lines to polygons
    AuxLayers_Poly = processing.run("qgis:linestopolygons", {
        'INPUT': AuxLayers_Line,
        'OUTPUT': 'memory:AuxLayers_Poly'
    }, feedback=feedback)['OUTPUT']

    AuxiliaryData_Poly = save_temp_layer_to_gpkg(AuxLayers_Poly, "AuxiliaryData_Poly", workspace_path)
    AuxiliaryData_Line = save_temp_layer_to_gpkg(AuxLayers_Line, "AuxiliaryData_Line", workspace_path)

    return AuxiliaryData_Poly, AuxiliaryData_Line