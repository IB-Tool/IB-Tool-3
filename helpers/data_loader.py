"""File-dialog helpers and partition-list builder for the IBTool plugin.

Provides thin wrappers around Qt file/directory dialogs that write the selected
path directly into the matching QLineEdit widget of IBToolDialog, plus a utility
function that constructs the ordered list of partition names to process.

Constants:
    COMMENT_MARKER: Sentinel string (``'#'``) used as the first element of
        ``part_list`` to signal "load all partitions from the layer".
"""

from PyQt5.QtWidgets import QFileDialog  # pylint: disable=no-name-in-module

# Sentinel value indicating "use all partitions from the layer" in partition list config.
COMMENT_MARKER = '#'


def _select_vector_file(dlg: object, field_name: str) -> None:
    """Open a file dialog for vector files and write the selected path to a dialog text field.

    Args:
        dlg: The dialog instance whose text field will be updated.
        field_name: Attribute name of the QLineEdit on ``dlg`` to receive the path.
    """
    filename, _ = QFileDialog.getOpenFileName(
        dlg, "Select input file", "",
        "Vector files (*.shp *.gpkg);;Shapefiles (*.shp);;GeoPackage (*.gpkg);;All Files (*)"
    )
    getattr(dlg, field_name).setText(filename)


def select_HU_file(dlg: object) -> None:  # pylint: disable=invalid-name
    """Open a file dialog and set the selected vector-file path as the HU input path.

    Args:
        dlg: The plugin dialog instance.
    """
    _select_vector_file(dlg, "HuPath")


def select_RN_file(dlg: object) -> None:  # pylint: disable=invalid-name
    """Open a file dialog and set the selected vector-file path as the RN input path.

    Args:
        dlg: The plugin dialog instance.
    """
    _select_vector_file(dlg, "RnPath")


def select_PART_file(dlg: object) -> None:  # pylint: disable=invalid-name
    """Open a file dialog and set the selected vector-file path as the partition input path.

    Args:
        dlg: The plugin dialog instance.
    """
    _select_vector_file(dlg, "PartPath")


def select_AUX_file(dlg: object) -> None:  # pylint: disable=invalid-name
    """Open a file dialog and set the selected vector-file path as the auxiliary input path.

    Args:
        dlg: The plugin dialog instance.
    """
    _select_vector_file(dlg, "AuxPath")


def select_output_file(dlg: object) -> None:
    """Open a save dialog and set the selected .gpkg path as the output path.

    Args:
        dlg: The plugin dialog instance.
    """
    filename, _ = QFileDialog.getSaveFileName(dlg, "Select output file", "", "*.gpkg")
    dlg.OutputPath.setText(filename)


def select_workspace_file(dlg: object) -> None:
    """Open a directory dialog and set the selected path as the workspace directory.

    Args:
        dlg: The plugin dialog instance.
    """
    directory = QFileDialog.getExistingDirectory(
        dlg,
        "Open Directory",
        "",
        QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
    )
    dlg.WorkspacePath.setText(directory)


def create_partitions_list(
    partition_layer: object,
    part_list: list,
    part_start: int,
    part_end: int,
) -> list:
    """Build a list of partition names from a layer, applying optional range filtering.

    If ``part_list`` starts with ``COMMENT_MARKER`` ('#'), all partition names are
    read from ``partition_layer``. When ``part_start`` and ``part_end`` are both
    non-negative, only features in that index range are included. Otherwise
    ``part_list`` is used directly after stripping embedded newlines.

    Args:
        partition_layer: QgsVectorLayer containing partition features with a ``NAME`` field.
        part_list: List of explicit partition names, or ``['#']`` to use all partitions.
        part_start: Start index for slicing (inclusive). Pass ``-1`` to use all.
        part_end: End index for slicing (exclusive). Pass ``-1`` to use all.

    Returns:
        List of partition name strings.

    Raises:
        ValueError: If ``partition_layer`` is not a valid layer.
    """
    if not partition_layer.isValid():
        raise ValueError("Invalid partition layer. Check the path to the partition table.")

    if str(part_list[0]) == COMMENT_MARKER:
        all_names = [feature["NAME"] for feature in partition_layer.getFeatures()]
        if part_start == -1 or part_end == -1:
            part_list = all_names
        else:
            part_list = all_names[part_start:part_end]
    else:
        part_list = [name.replace('\n', '') for name in part_list]

    return part_list
