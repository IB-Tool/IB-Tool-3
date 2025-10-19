from PyQt5.QtWidgets import QFileDialog

from .logger import Logger


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