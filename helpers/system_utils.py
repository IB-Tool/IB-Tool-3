import logging
import time
import os
import shutil
#from qgis.PyQt.QtWidgets import QAction, QFileDialog, QDialog
from qgis.core import Qgis, QgsVectorLayer, QgsProject, QgsVectorFileWriter, QgsProcessingFeatureSourceDefinition
from qgis.utils import QgsMessageLog
from .logger import Logger



def msg(message, level=Qgis.Info):
    if not isinstance(message, str):
        message = str(message)
    QgsMessageLog.logMessage(message, 'Meldungen', level=level)


def save_temp_layer_to_gpkg(layer, filename):
    """
    Speichert einen temporären Layer in ein GeoPackage (GPKG) unter 'L:\\Test_data\\workspace'.

    :param layer: QgsVectorLayer - Der zu speichernde Layer
    :param filename: str - Der Dateiname (ohne Pfad) für das GeoPackage
    """

    if not isinstance(layer, QgsVectorLayer):
        Logger.log("Fehler: Das übergebene Objekt {} ist kein gültiger QgsVectorLayer.".format(layer), "CRITICAL")
        return

    if not layer.isValid():
        Logger.log("Fehler: Der Layer {} ist ungültig.".format(layer))
        return

    # Standardpfad
    base_path = r'L:\Test_data\workspace'

    # Ausgabe-Dateipfad
    gpkg_file = os.path.join(base_path, "{}.gpkg".format(filename))

    # Layer-Name für GPKG bestimmen
    layer_name = layer.name()

    # GeoPackage speichern
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = layer_name

    error = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer,
        gpkg_file,
        QgsProject.instance().transformContext(),
        options
    )

    if error[0] == QgsVectorFileWriter.NoError:
        Logger.log("Layer erfolgreich als '{}' in '{}' gespeichert.".format(layer_name, gpkg_file), 'DEBUG')
    else:
        Logger.log("Fehler beim Speichern des Layers '{}' in '{}': {}".format(layer_name, gpkg_file, error[1]), 'CRITICAL')

    return gpkg_file



def manage_directory(PathCommonWorkspace, DelPartLog):
    """
    Löscht den Ordner 'IB_Tool_Results', wenn DelPartLog True ist,
    und stellt sicher, dass der Ordner neu erstellt wird.

    Parameter:
        PathCommonWorkspace (str): Der Basis-Pfad, in dem der Ordner verwaltet wird.
        DelPartLog (bool): Gibt an, ob der Ordner gelöscht werden soll.
    """
    # Verzeichnispfad zusammensetzen
    directory_path = os.path.join(PathCommonWorkspace, 'IB_Tool_Results')

    try:
        # Wenn DelPartLog True ist und der Ordner existiert, löschen
        if DelPartLog and os.path.exists(directory_path):
            shutil.rmtree(directory_path)
            Logger.log("Verzeichnis {} wurde erfolgreich gelöscht.".format(directory_path), "DEBUG")

        # In jedem Fall den Ordner neu erstellen
        if not os.path.exists(directory_path):
            os.makedirs(directory_path)
            Logger.log("Verzeichnis {} wurde erfolgreich neu erstellt.".format(directory_path), "DEBUG")
        else:
            Logger.log("Verzeichnis {} existiert bereits und wird verwendet.".format(directory_path), "DEBUG")
    except Exception as e:
        Logger.log("Fehler beim Verwalten des Verzeichnisses {}: {}".format(directory_path, str(e)), 'CRITICAL')

# Beispielaufruf
# manage_directory(r"L:\Test_data\workspace", True)

def copy_shapefile(source_folder, shapefile_name, target_folder):
    # Liste aller Shapefile-Erweiterungen
    extensions = ['.shp', '.shx', '.dbf', '.prj', '.cpg', '.qpj']

    # Sicherstellen, dass das Zielverzeichnis existiert
    os.makedirs(target_folder, exist_ok=True)

    copied_files = []  # Liste der kopierten Dateien

    for ext in extensions:
        source_file = os.path.join(source_folder, shapefile_name + ext)
        if os.path.exists(source_file):  # Nur vorhandene Dateien kopieren
            target_file = os.path.join(target_folder, shapefile_name + ext)
            shutil.copy2(source_file, target_file)
            copied_files.append(target_file)

    # Gib den Pfad zur Hauptdatei (.shp) zurück
    shapefile_path = os.path.join(target_folder, shapefile_name + ".shp")
    if shapefile_path in copied_files:
        return shapefile_path
    else:
        raise FileNotFoundError("Die Shapefile-Hauptdatei (.shp) wurde nicht kopiert!")

    # Beispielaufruf
    # output = copy_shapefile("C:/pfad/zur/quelle", "mein_shapefile", "C:/pfad/zum/ziel")