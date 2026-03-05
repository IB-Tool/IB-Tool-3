import os
import sys
import shutil
import hashlib
from qgis.core import QgsVectorLayer, QgsProject, QgsVectorFileWriter, Qgis
from .logger import Logger

# Supported Python version range (inclusive).
MIN_PYTHON = (3, 9)
MAX_PYTHON = (3, 12)

# Supported QGIS version range (inclusive, integer format: major*10000 + minor*100).
MIN_QGIS = 34000  # QGIS 3.40
MAX_QGIS = 35000  # QGIS 3.50

# Shapefile sidecar extensions that must be copied alongside the main .shp file.
_SHAPEFILE_EXTENSIONS = ['.shp', '.shx', '.dbf', '.prj', '.cpg', '.qpj']


def compute_file_checksum(path: str, chunk_size: int = 8192) -> str:
    """Compute the MD5 checksum of a file.

    Reads the file in chunks to avoid loading large geodata files fully into
    memory. Returns an empty string if the file cannot be read.

    Args:
        path: Absolute path to the file.
        chunk_size: Read buffer size in bytes.

    Returns:
        Hex-encoded MD5 digest, or ``""`` on any I/O error.
    """
    try:
        h = hashlib.md5(usedforsecurity=False)  # nosec B324 — checksum only, not crypto
        with open(path, 'rb') as fh:
            for chunk in iter(lambda: fh.read(chunk_size), b''):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def save_temp_layer_to_gpkg(
    layer: QgsVectorLayer, filename: str, workspace_path: str
) -> str | None:
    """Save a vector layer as a GeoPackage file in the given workspace directory.

    Args:
        layer: The QgsVectorLayer to save.
        filename: Base filename (without path or extension) for the output GeoPackage.
        workspace_path: Directory in which to write the .gpkg file.
            Created if it does not exist.

    Returns:
        Path to the written .gpkg file, or None if saving failed.
    """
    if not isinstance(layer, QgsVectorLayer):
        Logger.log(
            f"Fehler: Das übergebene Objekt {layer} ist kein gültiger QgsVectorLayer.",
            level="CRITICAL",
        )
        return None

    if not layer.isValid():
        Logger.log(
            "Fehler: Der Layer {} ist ungültig.".format(layer),
            level="WARNING",
        )
        return None

    # Ensure the target directory exists
    if not os.path.exists(workspace_path):
        try:
            os.makedirs(workspace_path)
            Logger.log(f"Verzeichnis {workspace_path} wurde erstellt.", level="INFO")
        except OSError as e:
            Logger.log(
                f"Fehler beim Erstellen des Verzeichnisses {workspace_path}: {e}",
                level="CRITICAL",
            )
            return None

    # Output file path
    gpkg_file = os.path.join(workspace_path, "{}.gpkg".format(filename))

    # Determine layer name for the GeoPackage
    layer_name = layer.name()

    # Save as GeoPackage (overwrite if file already exists)
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = layer_name
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    error = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer,
        gpkg_file,
        QgsProject.instance().transformContext(),
        options
    )

    if error[0] == QgsVectorFileWriter.NoError:
        Logger.log(
            f"Layer erfolgreich als '{layer_name}' in '{gpkg_file}' gespeichert.",
            level="SUCCESS",
        )
    else:
        Logger.log(
            f"Fehler beim Speichern des Layers '{layer_name}' in '{gpkg_file}': {error[1]}",
            level="CRITICAL",
        )

    return gpkg_file


def manage_directory(workspace_path: str, del_part_log: bool) -> None:
    """Manage the output directory structure at the start of a processing run.

    Deletes 'IB_Tool_Results' and 'debug' if del_part_log is True, then
    ensures 'IB_Tool_Results' exists. The 'debug' folder is not recreated
    here — it is created on demand by the debug utilities.

    Args:
        workspace_path: Base workspace path.
        del_part_log: If True, existing output and debug folders are deleted.
    """
    directory_path = os.path.join(workspace_path, 'IB_Tool_Results')
    debug_path = os.path.join(workspace_path, 'debug')

    try:
        if del_part_log:
            if os.path.exists(directory_path):
                shutil.rmtree(directory_path)
                Logger.log(
                    f"Verzeichnis {directory_path} wurde erfolgreich gelöscht.",
                    level="SUCCESS",
                )
            if os.path.exists(debug_path):
                shutil.rmtree(debug_path)
                Logger.log(
                    f"Verzeichnis {debug_path} wurde erfolgreich gelöscht.",
                    level="SUCCESS",
                )

        # Always ensure the output folder exists
        if not os.path.exists(directory_path):
            os.makedirs(directory_path)
            Logger.log(
                f"Verzeichnis {directory_path} wurde erfolgreich neu erstellt.",
                level="SUCCESS",
            )
        else:
            Logger.log(
                f"Verzeichnis {directory_path} existiert bereits und wird verwendet.",
                level="WARNING",
            )
    except Exception as e:
        Logger.log(
            f"Fehler beim Verwalten des Verzeichnisses {directory_path}: {str(e)}",
            level="CRITICAL",
        )


def copy_shapefile(
    source_folder: str, shapefile_name: str, target_folder: str
) -> str:
    """Copy all sidecar files of a shapefile to a target directory.

    Copies every extension listed in ``_SHAPEFILE_EXTENSIONS`` that exists in
    ``source_folder`` to ``target_folder`` (created if needed).

    Args:
        source_folder: Directory containing the source shapefile.
        shapefile_name: Base name of the shapefile (without extension).
        target_folder: Directory to copy the files into.

    Returns:
        Path to the copied main .shp file.

    Raises:
        FileNotFoundError: If the main .shp file was not found in the source directory.
    """
    # Ensure the target directory exists
    os.makedirs(target_folder, exist_ok=True)

    copied_files = []  # list of copied file paths

    for ext in _SHAPEFILE_EXTENSIONS:
        source_file = os.path.join(source_folder, shapefile_name + ext)
        if os.path.exists(source_file):  # only copy files that exist
            target_file = os.path.join(target_folder, shapefile_name + ext)
            shutil.copy2(source_file, target_file)
            copied_files.append(target_file)

    # Return path to the main .shp file
    shapefile_path = os.path.join(target_folder, shapefile_name + ".shp")
    if shapefile_path in copied_files:
        return shapefile_path
    raise FileNotFoundError(
        f"The main shapefile '{shapefile_name}.shp' was not found in: {source_folder}"
    )


def get_feature_count(layer: QgsVectorLayer) -> int:
    """Return the feature count of a layer and log it.

    Args:
        layer: A valid QgsVectorLayer.

    Returns:
        Number of features in the layer.

    Raises:
        RuntimeError: If the layer is not valid.
    """
    if not layer.isValid():
        raise RuntimeError(f"Layer could not be loaded: {layer}")

    feature_count = layer.featureCount()
    Logger.log(f"No: {feature_count}", level="INFO")
    return feature_count


def version_check() -> None:
    """Check that the current Python and QGIS versions are within the supported range.

    Raises:
        RuntimeError: If Python or QGIS version is outside the supported range.
    """
    # Python check
    if not (MIN_PYTHON <= sys.version_info[:2] <= MAX_PYTHON):
        raise RuntimeError(
            f"Dieses Plugin benötigt Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} - "
            f"{MAX_PYTHON[0]}.{MAX_PYTHON[1]}"
        )
    # QGIS check
    qgis_int = Qgis.QGIS_VERSION_INT
    if not (MIN_QGIS <= qgis_int <= MAX_QGIS):
        raise RuntimeError(
            "Dieses Plugin benötigt QGIS zwischen Version 3.40 und 3.50"
        )
