# -*- coding: utf-8 -*-
"""Per-partition result files, finish log, resume validation and final merge.

Order guarantee for resume: a part file is written under a temporary name and
renamed (atomic); only then the finish line is appended and flushed. A crash
in between leaves a file without a finish line (partition recomputed); a
finish line without a complete file cannot occur.

Copyright: (C) 2026 by Oliver Harig
License: GNU General Public License v2 or later
"""
import glob
import hashlib
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from qgis.core import (QgsCoordinateTransformContext, QgsFeatureRequest, QgsSpatialIndex,
                       QgsVectorFileWriter, QgsVectorLayer)

from .geometry_utils import merge_layers_prepending

PARTS_DIR = "parts"
"""Sub-folder of the results folder that holds one GeoPackage per partition."""

FID_COLUMN = "gpkg_fid"
"""GeoPackage row-id column of part files (keeps a ``fid`` attribute intact)."""

OLD_FORMAT = "<merge_temp>"
"""``result`` marker of finish-log lines written by versions before 0.2.5."""

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Windows device names: "AUX.gpkg" opens the device and blocks forever
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(\..*)?$", re.IGNORECASE)


@dataclass(frozen=True)
class FinishedPart:
    """One line of the finish log.

    Attributes:
        partition: Partition name (``NAME`` field).
        result: Part file relative to the results folder, ``None`` if the
            partition was skipped, :data:`OLD_FORMAT` if its result lives in
            ``IB_Tool_merge_temp.gpkg`` (written by versions before 0.2.5).
        features: Feature count of the part file (``None`` if not applicable).
    """
    partition: str
    result: Optional[str]
    features: Optional[int]


def part_file_name(partition: str) -> str:
    """File name for a partition's result, unique on case-insensitive file systems.

    Names that are file-system safe, upper case and no Windows device name
    (``PART_64``) are used as is; all others get a hash suffix of the exact
    name, so ``Teil: Nord``/``Teil/ Nord``, ``part_1``/``PART_1`` and ``AUX``
    map to distinct, openable files.
    """
    safe = _UNSAFE.sub("_", partition).strip(" .") or "part"
    if (safe == partition and partition == partition.upper()
            and not _RESERVED.match(partition)):
        return f"{safe}.gpkg"
    digest = hashlib.sha1(partition.encode("utf-8")).hexdigest()[:6]
    return f"{safe}_{digest}.gpkg"


def write_part_result(layer: QgsVectorLayer, partition: str, results_dir: str) -> Tuple[str, int]:
    """Write *layer* atomically to ``<results_dir>/parts``.

    Returns:
        ``(relative_path, feature_count)``; the path uses ``/`` separators.

    Raises:
        OSError: If writing or renaming fails (no part file is left behind).
    """
    parts = os.path.join(results_dir, PARTS_DIR)
    os.makedirs(parts, exist_ok=True)
    name = part_file_name(partition)
    final = os.path.join(parts, name)
    temp = final[:-len(".gpkg")] + ".tmp.gpkg"
    if os.path.exists(temp):
        os.remove(temp)
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = "result"
    # Dedicated row-id column: a "fid" attribute of merged layers may hold
    # duplicates (same convention as save_temp_layer_to_gpkg)
    opts.layerOptions = [f"FID={FID_COLUMN}"]
    err = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, temp, QgsCoordinateTransformContext(), opts)
    if err[0] != QgsVectorFileWriter.NoError:
        if os.path.exists(temp):
            os.remove(temp)
        raise OSError(f"Teilergebnis {partition} konnte nicht geschrieben werden: {err[1]}")
    try:
        os.replace(temp, final)
    except OSError:
        if os.path.exists(temp):
            os.remove(temp)
        raise
    return f"{PARTS_DIR}/{name}", layer.featureCount()


def append_finished(log_path: str, part: FinishedPart) -> None:
    """Append one finish line and force it to disk."""
    if part.result is None:
        line = f"{part.partition}\tskipped\n"
    else:
        line = f"{part.partition}\t{part.result}\t{part.features}\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def read_finished(log_path: str) -> Dict[str, FinishedPart]:
    """Parse the finish log (new and old format).

    The old format (<= 0.2.4) wrote ``"\\n" + name``, so its last line has no
    trailing newline but is complete. New-format lines always end with
    ``\\n``; a new-format line without it is incomplete (crash while writing)
    and ignored.
    """
    if not os.path.isfile(log_path):
        return {}
    with open(log_path, "r", encoding="utf-8") as f:
        content = f.read()
    lines = content.split("\n")
    complete = lines if content.endswith("\n") else lines[:-1]
    result = {}
    for raw in complete:
        cols = raw.strip("\r").split("\t")
        name = cols[0].strip()
        if not name:
            continue
        if len(cols) == 1:
            result[name] = FinishedPart(name, OLD_FORMAT, None)
        elif len(cols) == 2 and cols[1] == "skipped":
            result[name] = FinishedPart(name, None, None)
        elif len(cols) == 3 and cols[2].isdigit():
            result[name] = FinishedPart(name, cols[1], int(cols[2]))
    tail = "" if content.endswith("\n") else lines[-1].strip("\r").strip()
    if tail and "\t" not in tail:
        result[tail] = FinishedPart(tail, OLD_FORMAT, None)
    return result


def validate_finished(results_dir: str,
                      finished: Dict[str, FinishedPart]) -> Tuple[Dict[str, FinishedPart], List[str]]:
    """Split finished partitions into ``valid`` ones and names to ``recompute``.

    A part file is valid if it opens and has the logged feature count.
    """
    valid, recompute = {}, []
    for name, part in finished.items():
        if part.result is None or part.result == OLD_FORMAT:
            valid[name] = part
            continue
        path = os.path.join(results_dir, part.result)
        layer = (QgsVectorLayer(f"{path}|layername=result", name, "ogr")
                 if os.path.isfile(path) else None)
        if layer is not None and layer.isValid() and layer.featureCount() == part.features:
            valid[name] = part
        else:
            recompute.append(name)
    return valid, recompute


def cleanup_temporary(results_dir: str) -> None:
    """Remove leftover ``*.tmp.gpkg`` files of an interrupted run."""
    for path in glob.glob(os.path.join(results_dir, PARTS_DIR, "*.tmp.gpkg")):
        os.remove(path)


def estimate_buildings(layer_hu: QgsVectorLayer, layer_part: QgsVectorLayer,
                       names: List[str]) -> Dict[str, int]:
    """Buildings per partition, estimated from bounding boxes (spatial index).

    Used only for the processing order (largest first) and the progress bar;
    the exact count comes from the pipeline.
    """
    index = QgsSpatialIndex(layer_hu.getFeatures(QgsFeatureRequest().setNoAttributes()))
    wanted = set(names)
    estimates = {name: 0 for name in names}
    for feature in layer_part.getFeatures():
        name = str(feature["NAME"])
        if name in wanted:
            estimates[name] += len(index.intersects(feature.geometry().boundingBox()))
    return estimates


def merge_results(results_dir: str, order: List[str], finished: Dict[str, FinishedPart],
                  base_layer: QgsVectorLayer, crs) -> QgsVectorLayer:
    """Merge part files in partition order, like the former incremental merge.

    Each part is copied into memory and the GeoPackage row-id column
    (:data:`FID_COLUMN`) is dropped, so the merged layer has exactly the
    attributes of the partition results.
    """
    layers = []
    for name in order:
        part = finished.get(name)
        if part is None or part.result in (None, OLD_FORMAT):
            continue
        path = os.path.join(results_dir, part.result)
        source = QgsVectorLayer(f"{path}|layername=result", name, "ogr")
        memory = source.materialize(QgsFeatureRequest())
        fid_index = memory.fields().lookupField(FID_COLUMN)
        if fid_index >= 0:
            memory.dataProvider().deleteAttributes([fid_index])
            memory.updateFields()
        layers.append(memory)
    return merge_layers_prepending(layers, base_layer, crs)
