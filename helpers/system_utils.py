import os
import sys
import shutil
from qgis.core import QgsVectorLayer, QgsProject, QgsVectorFileWriter, Qgis
from .logger import Logger

MIN_PYTHON = (3, 9)
MAX_PYTHON = (3, 12)
MIN_QGIS = 34000  # QGIS Version 3.40
MAX_QGIS = 35000  # QGIS Version 3.50

Logger = Logger()

def save_temp_layer_to_gpkg(layer, filename, workspace_path):
    """
    Speichert einen temporären Layer in ein GeoPackage (GPKG) unter 'L:\\Test_data\\workspace'.

    :param layer: QgsVectorLayer - Der zu speichernde Layer
    :param layer: str - Der Dateiname (ohne Pfad) für das GeoPackage
    """

    if not isinstance(layer, QgsVectorLayer):
        Logger.log(
            f"Fehler: Das übergebene Objekt {layer} ist kein gültiger QgsVectorLayer.",
            "CRITICAL"
        )
        return

    if not layer.isValid():
        Logger.log("Fehler: Der Layer {} ist ungültig.".format(layer))
        return

    # Ausgabe-Dateipfad
    gpkg_file = os.path.join(workspace_path, "{}.gpkg".format(filename))

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
        Logger.log(
            f"Layer erfolgreich als '{layer_name}' in '{gpkg_file}' gespeichert.",
            'SUCCESS'
        )
    else:
        Logger.log(
            f"Fehler beim Speichern des Layers '{layer_name}' in '{gpkg_file}': {error[1]}",
            'CRITICAL'
        )

    return gpkg_file


def manage_directory(workspace_path, del_part_log):
    """
    Löscht den Ordner 'IB_Tool_Results', wenn del_part_log True ist,
    und stellt sicher, dass der Ordner neu erstellt wird.

    Parameter:
        path_common_workspace (str): Der Basis-Pfad, in dem der Ordner verwaltet wird.
        del_part_log (bool): Gibt an, ob der Ordner gelöscht werden soll.
    """
    # Verzeichnispfad zusammensetzen
    #path_common_workspace = r"{}".format(workspace_path)
    #directory_path = f'"{os.path.join(path_common_workspace, "IB_Tool_Results")}"'
    directory_path = os.path.join(workspace_path, 'IB_Tool_Results')

    try:
        # Wenn del_part_log True ist und der Ordner existiert, löschen
        if del_part_log and os.path.exists(directory_path):
            shutil.rmtree(directory_path)
            Logger.log(
                f"Verzeichnis {directory_path} wurde erfolgreich gelöscht.",
                "SUCCESS"
            )

        # In jedem Fall den Ordner neu erstellen
        if not os.path.exists(directory_path):
            os.makedirs(directory_path)
            Logger.log(
                f"Verzeichnis {directory_path} wurde erfolgreich neu erstellt.",
                "SUCCESS"
            )
        else:
            Logger.log(
                f"Verzeichnis {directory_path} existiert bereits und wird verwendet.",
                "WARNING"
            )
    except Exception as e:
        Logger.log(
            f"Fehler beim Verwalten des Verzeichnisses {directory_path}: {str(e)}",
            'CRITICAL'
        )

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

def get_feature_count(layer):

    """
    Gibt die Anzahl der Features einer Datei aus (zur Überprüfung geeignet).
    :param layer: str - Der Pfad zur Vektordatei.
    :return: str - Text mit der Anzahl der Features.
    """

    if not layer.isValid():
        raise RuntimeError(f"Layer konnte nicht geladen werden: {layer}")

    # Anzahl der Features abrufen
    feature_count = layer.featureCount()
    printtext = f"No: {feature_count}"

    Logger.log(printtext, level="INFO")

    return feature_count

def version_check():
    # Python check
    if not (MIN_PYTHON <= sys.version_info[:2] <= MAX_PYTHON):
        raise RuntimeError(
            (
                f"Dieses Plugin benötigt Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} - "
                f"{MAX_PYTHON[0]}.{MAX_PYTHON[1]}"
            )
        )
    # QGIS check
    qgis_int = Qgis.QGIS_VERSION_INT
    if not (MIN_QGIS <= qgis_int <= MAX_QGIS):
        raise RuntimeError(
            "Dieses Plugin benötigt QGIS zwischen Version 3.40 und 3.50"
        )
