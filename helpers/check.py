"""
Input data validation for IBTool.

Validates all input layers, fields, geometry types, CRS, and filter files
before processing starts.
"""

import os
import re
from dataclasses import dataclass, field
from typing import List

from qgis.core import (
    QgsVectorLayer,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsProcessing,
)
from qgis import processing
from qgis.PyQt.QtCore import QCoreApplication


def _tr(text: str) -> str:
    """Translate a string using QGIS translation system."""
    return QCoreApplication.translate('InputValidator', text)


@dataclass
class ValidationResult:
    """Aggregated result of input data validation."""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True if no critical errors found."""
        return len(self.errors) == 0

    def add_error(self, message: str) -> None:
        """Append a critical error message."""
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        """Append a non-critical warning message."""
        self.warnings.append(message)


class InputValidator:
    """Validates all IBTool input data before processing."""

    def quick_path_check(self, path: str, is_dir: bool = False) -> tuple:
        """Fast filesystem check without QGIS layer instantiation.

        Suitable for real-time textChanged feedback in the UI.

        Args:
            path: Filesystem path to check.
            is_dir: If True, also verify the path is a directory.

        Returns:
            Tuple (ok: bool, message: str).  ok=True means the path exists
            (and is a directory when is_dir=True).
        """
        if not path or not path.strip():
            return False, _tr("No path specified")
        if not os.path.exists(path):
            return False, _tr("File or directory does not exist")
        if is_dir and not os.path.isdir(path):
            return False, _tr("Not a directory")
        return True, ""

    # Required fields per layer type
    HU_REQUIRED_FIELDS = ("fkt", "gfkzshh", "funktion")  # At least one must exist
    HU_FKT_PATTERN = re.compile(r"^\d{5}_\d{4}")  # ATKIS: 31001_1000
    PART_REQUIRED_FIELD = "NAME"
    PART_NAME_REGEX = re.compile(r"^PART_\d+$")  # PART_36, PART_433
    FILTER_SECTION_POSITIVE = "#Filter positive"
    FILTER_SECTION_NEGATIVE = "#Filter negative"

    # Minimum feature counts per layer
    MIN_FEATURES_HU = 50
    MIN_FEATURES_RN = 30
    MIN_FEATURES_PART = 1
    MIN_FEATURES_AUX = 10

    # Maximum ratio of Part features to HU features
    MAX_PART_TO_HU_RATIO = 10000

    def validate_all(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches
        self,
        hu_path: str,
        rn_path: str,
        part_path: str,
        aux_path: str,
        filter_path: str,
        output_path: str,
        workspace_path: str,
        spatial_reference: QgsCoordinateReferenceSystem,
        params: dict = None,
    ) -> ValidationResult:
        """Run all validation checks and return aggregated result.

        Args:
            hu_path: Path to building footprints layer.
            rn_path: Path to road network layer.
            part_path: Path to partitioning layer.
            aux_path: Path to auxiliary layer.
            filter_path: Path to filter text file.
            output_path: Path for output file.
            workspace_path: Path for workspace directory.
            spatial_reference: Expected CRS for all layers.
            params: Optional dict with UI parameter values, keys:
                min_overlap_blocks, global_footprint_density,
                min_area, min_bdg_count, min_patch_size,
                max_hole_size, max_gap_size, spatial_reference_text,
                part_start, part_end, part_list.

        Returns:
            ValidationResult with errors and warnings.
        """
        result = ValidationResult()

        # Layer paths and display names
        layer_paths = {
            "Building footprints (HU)": hu_path,
            "Road network (RN)": rn_path,
            "Partitioning (Part)": part_path,
            "Auxiliary layer (Aux)": aux_path,
        }

        valid_layers = {}  # name -> QgsVectorLayer for layers that loaded OK

        for name, path in layer_paths.items():
            # Check path is specified
            if not path or not path.strip():
                result.add_error(
                    _tr("{layer}: No file path specified.").format(layer=_tr(name))
                )
                continue

            # Check file exists
            if not os.path.exists(path):
                result.add_error(
                    _tr("{layer}: File does not exist: {path}").format(
                        layer=_tr(name), path=path)
                )
                continue

            # Check layer is valid
            layer = QgsVectorLayer(path, name, "ogr")
            if not layer.isValid():
                result.add_error(
                    _tr("{layer}: File cannot be loaded as a valid layer: {path}").format(
                        layer=_tr(name), path=path)
                )
                continue

            valid_layers[name] = layer

            # Check CRS
            self._check_crs(layer, name, spatial_reference, result)

        # Feature count checks (includes empty layer check)
        self._check_feature_counts(valid_layers, result)

        # Geometry checks for all layers: null, empty, isGeosValid
        for name, layer in valid_layers.items():
            self._check_geometries(layer, name, result)

        # Detailed geometry validation via qgis:checkvalidity
        for name, layer in valid_layers.items():
            self._check_validity_processing(layer, name, result)

        # Layer-specific checks
        hu_key = "Building footprints (HU)"
        if hu_key in valid_layers:
            self._check_hu_layer(valid_layers[hu_key], result)

        rn_key = "Road network (RN)"
        if rn_key in valid_layers:
            self._check_rn_layer(valid_layers[rn_key], result)

        aux_key = "Auxiliary layer (Aux)"
        if aux_key in valid_layers:
            self._check_aux_layer(valid_layers[aux_key], result)

        part_key = "Partitioning (Part)"
        if part_key in valid_layers:
            self._check_part_layer(valid_layers[part_key], result)

        # Multipart geometry check for line layers
        for key in [rn_key, aux_key]:
            if key in valid_layers:
                self._check_multipart_lines(valid_layers[key], key, result)

        # Part-to-HU ratio check
        if hu_key in valid_layers and part_key in valid_layers:
            self._check_part_hu_ratio(
                valid_layers[part_key], valid_layers[hu_key], result
            )

        # Filter file
        self._check_filter_file(filter_path, result)

        # Output and workspace paths
        self._check_output_paths(output_path, workspace_path, result)

        # UI parameter validation
        if params:
            self._check_params(params, result)

        return result

    # ------------------------------------------------------------------
    # General checks
    # ------------------------------------------------------------------

    def _check_crs(
        self,
        layer: QgsVectorLayer,
        layer_name: str,
        expected_crs: QgsCoordinateReferenceSystem,
        result: ValidationResult,
    ) -> None:
        """Check that layer CRS matches the expected spatial reference."""
        layer_crs = layer.crs()
        if layer_crs.authid() != expected_crs.authid():
            actual = layer_crs.authid() or "undefined/unknown"
            result.add_error(
                _tr("{layer}: CRS mismatch. Expected: {expected}, found: {actual}. "
                    "Hint: Reproject the layer to {expected}.").format(
                    layer=_tr(layer_name), expected=expected_crs.authid(), actual=actual)
            )

    def _check_feature_counts(
        self, valid_layers: dict, result: ValidationResult
    ) -> None:
        """Check that layers contain minimum required feature counts."""
        min_counts = {
            "Building footprints (HU)": self.MIN_FEATURES_HU,
            "Road network (RN)": self.MIN_FEATURES_RN,
            "Partitioning (Part)": self.MIN_FEATURES_PART,
            "Auxiliary layer (Aux)": self.MIN_FEATURES_AUX,
        }

        for name, min_count in min_counts.items():
            if name not in valid_layers:
                continue
            layer = valid_layers[name]
            count = layer.featureCount()
            if count == 0:
                result.add_error(
                    _tr("{layer}: Layer is empty (0 features). "
                        "Hint: Populate the layer with data.").format(layer=_tr(name))
                )
            elif count < min_count:
                result.add_error(
                    _tr("{layer}: Too few features ({count}), at least {min_count} required. "
                        "Hint: Check the dataset for completeness.").format(
                        layer=_tr(name), count=count, min_count=min_count)
                )

    # ------------------------------------------------------------------
    # Geometry checks
    # ------------------------------------------------------------------

    def _check_geometries(
        self, layer: QgsVectorLayer, layer_name: str,
        result: ValidationResult,
    ) -> None:
        """Check all features for null, empty, and invalid geometries."""
        null_count = 0
        empty_count = 0
        invalid_count = 0
        invalid_reasons = []

        for feature in layer.getFeatures():
            geom = feature.geometry()

            if geom.isNull():
                null_count += 1
                continue

            if geom.isEmpty():
                empty_count += 1
                continue

            if not geom.isGeosValid():
                invalid_count += 1
                if len(invalid_reasons) < 3:
                    error = geom.validateGeometry()
                    if error:
                        invalid_reasons.append(
                            f"FID {feature.id()}: {error[0].what()}"
                        )

        if null_count > 0:
            result.add_error(
                _tr("{layer}: {null_count} features with NULL geometry. "
                    "Hint: Remove features without geometry.").format(
                    layer=_tr(layer_name), null_count=null_count)
            )

        if empty_count > 0:
            result.add_error(
                _tr("{layer}: {empty_count} features with empty geometry. "
                    "Hint: Remove features with empty geometry.").format(
                    layer=_tr(layer_name), empty_count=empty_count)
            )

        if invalid_count > 0:
            details = ""
            if invalid_reasons:
                details = " Examples: " + "; ".join(invalid_reasons) + "."
            result.add_warning(
                _tr("{layer}: {invalid_count} invalid geometries (isGeosValid=False)."
                    "{details} Hint: Fix geometries (native:fixgeometries).").format(
                    layer=_tr(layer_name), invalid_count=invalid_count, details=details)
            )

    def _check_validity_processing(  # pylint: disable=too-many-locals,too-many-branches
        self, layer: QgsVectorLayer, layer_name: str,
        result: ValidationResult,
    ) -> None:
        """Run qgis:checkvalidity for detailed geometry validation."""
        try:
            check_result = processing.run("qgis:checkvalidity", {
                'INPUT_LAYER': layer,
                'METHOD': 2,  # GEOS
                'IGNORE_RING_SELF_INTERSECTION': False,
                'VALID_OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
                'INVALID_OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
                'ERROR_OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
            })

            invalid_layer = check_result.get('INVALID_OUTPUT')
            error_layer = check_result.get('ERROR_OUTPUT')

            # Count invalid features
            invalid_count = 0
            if isinstance(invalid_layer, QgsVectorLayer) and invalid_layer.isValid():
                invalid_count = invalid_layer.featureCount()
            elif isinstance(invalid_layer, str):
                tmp = QgsVectorLayer(invalid_layer, "invalid", "ogr")
                if tmp.isValid():
                    invalid_count = tmp.featureCount()

            if invalid_count == 0:
                return

            # Collect error details from error layer
            error_messages = []
            error_source = None
            if isinstance(error_layer, QgsVectorLayer) and error_layer.isValid():
                error_source = error_layer
            elif isinstance(error_layer, str):
                tmp = QgsVectorLayer(error_layer, "errors", "ogr")
                if tmp.isValid():
                    error_source = tmp

            if error_source:
                for i, feat in enumerate(error_source.getFeatures()):
                    if i >= 5:
                        break
                    msg = feat.attribute("message") if feat.fields().indexFromName("message") >= 0 else ""
                    if msg:
                        error_messages.append(str(msg))

            details = ""
            if error_messages:
                details = " Error types: " + "; ".join(error_messages) + "."

            result.add_warning(
                _tr("{layer}: 'qgis:checkvalidity' found {invalid_count} invalid features."
                    "{details} Hint: Fix geometries (native:fixgeometries).").format(
                    layer=_tr(layer_name), invalid_count=invalid_count, details=details)
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            result.add_warning(
                _tr("{layer}: 'qgis:checkvalidity' could not be executed: {error}").format(
                    layer=_tr(layer_name), error=e)
            )

    # ------------------------------------------------------------------
    # Layer-specific checks
    # ------------------------------------------------------------------

    def _check_hu_layer(
        self, layer: QgsVectorLayer, result: ValidationResult
    ) -> None:
        """Validate HU layer: polygon geometry and required fields."""
        # Geometry type
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            geom_type = QgsWkbTypes.geometryDisplayString(layer.geometryType())
            result.add_error(
                _tr("Building footprints (HU): Polygon geometry required, but {geom_type} found. "
                    "Hint: Use a layer with polygon geometry.").format(geom_type=geom_type)
            )

        # Required field: fkt or funktion
        field_names = [f.name() for f in layer.fields()]
        fkt_field = None
        for f in self.HU_REQUIRED_FIELDS:
            if f in field_names:
                fkt_field = f
                break

        if not fkt_field:
            result.add_error(
                _tr("Building footprints (HU): Field 'fkt', 'gfkzshh' or 'funktion' missing. "
                    "Available fields: {fields}. "
                    "Hint: Add a field 'fkt', 'gfkzshh' or 'funktion' containing "
                    "building function codes.").format(fields=', '.join(field_names[:15]))
            )
            return

        # Check field values: not empty, ATKIS format
        null_count = 0
        invalid_format = []

        for feature in layer.getFeatures():
            val = feature[fkt_field]
            if val is None or str(val).strip() in ("", "NULL"):
                null_count += 1
                continue
            # "0" means no function code assigned — valid for uncategorised buildings, skip silently
            if str(val).strip() == "0":
                continue
            if not self.HU_FKT_PATTERN.match(str(val)):
                if len(invalid_format) < 5:
                    invalid_format.append(str(val)[:20])

        if null_count > 0:
            result.add_warning(
                _tr("Building footprints (HU): {null_count} features with "
                    "empty/NULL value in field '{field}'. "
                    "Hint: All features require a building function code.").format(
                    null_count=null_count, field=fkt_field)
            )

        if invalid_format:
            result.add_warning(
                _tr("Building footprints (HU): Values in field '{field}' do not match "
                    "the ATKIS format (NNNNN_NNNN, e.g. 31001_1000). Examples: {examples}. "
                    "Hint: Only the first 10 characters are used for filter matching.").format(
                    field=fkt_field, examples=', '.join(invalid_format))
            )

    def _check_rn_layer(
        self, layer: QgsVectorLayer, result: ValidationResult
    ) -> None:
        """Validate RN layer: must be LineString geometry."""
        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            geom_type = QgsWkbTypes.geometryDisplayString(layer.geometryType())
            result.add_error(
                _tr("Road network (RN): Line geometry required, but {geom_type} found. "
                    "Hint: Use a layer with line geometry.").format(geom_type=geom_type)
            )

    def _check_aux_layer(
        self, layer: QgsVectorLayer, result: ValidationResult
    ) -> None:
        """Validate Aux layer: must be LineString geometry."""
        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            geom_type = QgsWkbTypes.geometryDisplayString(layer.geometryType())
            result.add_error(
                _tr("Auxiliary layer (Aux): Line geometry required, but {geom_type} found. "
                    "Hint: Use a layer with line geometry.").format(geom_type=geom_type)
            )

    def _check_part_layer(
        self, layer: QgsVectorLayer, result: ValidationResult
    ) -> None:
        """Validate Part layer: polygon geometry, NAME field and naming pattern."""
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            geom_type = QgsWkbTypes.geometryDisplayString(layer.geometryType())
            result.add_error(
                _tr("Partitioning (Part): Polygon geometry required, but {geom_type} found. "
                    "Hint: Use a layer with polygon geometry.").format(geom_type=geom_type)
            )

        field_names = [f.name() for f in layer.fields()]

        # Required field: NAME
        if self.PART_REQUIRED_FIELD not in field_names:
            result.add_error(
                _tr("Partitioning (Part): Field '{field}' missing. "
                    "Available fields: {fields}. "
                    "Hint: Add a text field 'NAME' with partition names "
                    "(e.g. PART_123).").format(
                    field=self.PART_REQUIRED_FIELD,
                    fields=', '.join(field_names[:15]))
            )
            return

        # Check NAME values: not empty, must match PART_<number>
        name_idx = layer.fields().indexFromName(self.PART_REQUIRED_FIELD)
        null_count = 0
        non_matching = []

        for feature in layer.getFeatures():
            val = feature[name_idx]
            if val is None or str(val).strip() == "" or str(val) == "NULL":
                null_count += 1
                continue
            name_val = str(val).strip()
            if not self.PART_NAME_REGEX.match(name_val):
                if len(non_matching) < 5:
                    non_matching.append(name_val)

        if null_count > 0:
            result.add_error(
                _tr("Partitioning (Part): {null_count} features with empty/NULL value "
                    "in field 'NAME'. Hint: All partitions require a name in the format "
                    "PART_<number>.").format(null_count=null_count)
            )

        if non_matching:
            result.add_error(
                _tr("Partitioning (Part): NAME values do not match the format "
                    "PART_<number>. Examples: {examples}. Hint: NAME values must exactly "
                    "follow the pattern PART_123 (e.g. PART_36, PART_433).").format(
                    examples=', '.join(non_matching))
            )

    # ------------------------------------------------------------------
    # Multipart and ratio checks
    # ------------------------------------------------------------------

    def _check_multipart_lines(
        self, layer: QgsVectorLayer, layer_name: str,
        result: ValidationResult
    ) -> None:
        """Check that each line feature contains exactly one line string.

        OGC Simple Feature structure check:
        - LineString -> OK
        - MultiLineString with exactly 1 part -> OK
        - MultiLineString with >1 parts -> Error
        """
        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            return

        multiline_count = 0
        for feature in layer.getFeatures():
            geom = feature.geometry()
            if geom.isNull():
                continue
            if geom.isMultipart():
                parts = geom.asMultiPolyline()
                if len(parts) > 1:
                    multiline_count += 1

        if multiline_count > 0:
            result.add_error(
                _tr("{layer}: {count} features contain multiple line strings "
                    "(MultiLineString with >1 part). Each feature may only contain one "
                    "line string. Hint: Explode multipart features "
                    "(native:multiparttosingleparts).").format(
                    layer=_tr(layer_name), count=multiline_count)
            )

    def _check_part_hu_ratio(
        self, part_layer: QgsVectorLayer, hu_layer: QgsVectorLayer,
        result: ValidationResult
    ) -> None:
        """Warn if ratio of Part features to HU features exceeds threshold."""
        part_count = part_layer.featureCount()
        hu_count = hu_layer.featureCount()

        if part_count == 0 or hu_count == 0:
            return

        ratio = hu_count / part_count
        if ratio > self.MAX_PART_TO_HU_RATIO:
            result.add_warning(
                _tr("Part:HU ratio = 1:{ratio} (threshold: 1:{threshold}). "
                    "Part has {part_count} features, HU has {hu_count} features. "
                    "Hint: Use a finer partitioning to reduce processing time "
                    "per partition.").format(
                    ratio=f"{ratio:.0f}", threshold=self.MAX_PART_TO_HU_RATIO,
                    part_count=part_count, hu_count=hu_count)
            )

    # ------------------------------------------------------------------
    # Filter file and output paths
    # ------------------------------------------------------------------

    def _check_filter_file(
        self, filter_path: str, result: ValidationResult
    ) -> None:
        """Validate filter file existence, format, and content.

        Expected format::

            #Filter positive
            31001_1000, Wohngeb
            31001_1010, Wohnhaus
            ...

            #Filter negative
            31001_1310, Freizeit
            31001_2600, Entsorgung
            ...

        Rules:

        - Sections '#Filter positive' and '#Filter negative' required.
        - '#Filter positive' must appear before '#Filter negative'.
        - Each section must contain at least one entry.
        - Entries should start with an ATKIS code (NNNNN_NNNN).
        - Lines starting with '#' are comments; empty lines are ignored.
        - Only the first 10 characters per entry are used for matching.

        Args:
            filter_path: Path to the filter text file.
            result: Validation result to append errors/warnings to.
        """
        lines = self._read_filter_file(filter_path, result)
        if lines is None:
            return
        parsed = self._parse_filter_sections(lines)
        self._validate_filter_structure(parsed, result)
        self._validate_filter_entries(parsed, result)

    def _read_filter_file(
        self, filter_path: str, result: ValidationResult
    ) -> list | None:
        """Check that the filter file exists and is readable; return its lines.

        Args:
            filter_path: Path to the filter text file.
            result: Validation result to append errors to.

        Returns:
            List of raw lines from the file, or None if it could not be read.
        """
        if not filter_path or not filter_path.strip():
            result.add_error(_tr("Filter file: No file path specified."))
            return None

        if not os.path.exists(filter_path):
            result.add_error(
                _tr("Filter file: File does not exist: {path}").format(path=filter_path)
            )
            return None

        try:
            with open(filter_path, 'r', encoding='utf-8') as f:
                return f.readlines()
        except Exception as e:  # pylint: disable=broad-exception-caught
            result.add_error(
                _tr("Filter file: File cannot be read: {error}. "
                    "Hint: File must be UTF-8 encoded and readable.").format(error=e)
            )
            return None

    def _parse_filter_sections(self, lines: list) -> dict:
        """Parse filter file lines into sections and entry lists.

        Args:
            lines: Raw lines from the filter file.

        Returns:
            Dict with keys ``pos_line``, ``neg_line``,
            ``entries_positive``, ``entries_negative``, ``orphan_lines``.
        """
        current_section = None
        pos_line = None
        neg_line = None
        entries_positive = []
        entries_negative = []
        orphan_lines = []

        for i, raw_line in enumerate(lines, 1):
            line = raw_line.strip()
            if line.startswith(self.FILTER_SECTION_POSITIVE):
                current_section = "positive"
                pos_line = i
            elif line.startswith(self.FILTER_SECTION_NEGATIVE):
                current_section = "negative"
                neg_line = i
            elif line.startswith("#") or not line:
                continue
            elif current_section == "positive":
                entries_positive.append((i, line))
            elif current_section == "negative":
                entries_negative.append((i, line))
            else:
                orphan_lines.append((i, line))

        return {
            "pos_line": pos_line,
            "neg_line": neg_line,
            "entries_positive": entries_positive,
            "entries_negative": entries_negative,
            "orphan_lines": orphan_lines,
        }

    def _validate_filter_structure(
        self, parsed: dict, result: ValidationResult
    ) -> None:
        """Validate that required section headers are present and correctly ordered.

        Args:
            parsed: Output of :meth:`_parse_filter_sections`.
            result: Validation result to append errors/warnings to.
        """
        pos_line = parsed["pos_line"]
        neg_line = parsed["neg_line"]
        orphan_lines = parsed["orphan_lines"]

        if pos_line is None:
            result.add_error(
                _tr("Filter file: Section '{section}' missing. "
                    "Hint: Add the line '{section}' to the file.").format(
                    section=self.FILTER_SECTION_POSITIVE)
            )
        if neg_line is None:
            result.add_error(
                _tr("Filter file: Section '{section}' missing. "
                    "Hint: Add the line '{section}' to the file.").format(
                    section=self.FILTER_SECTION_NEGATIVE)
            )
        if pos_line is not None and neg_line is not None and pos_line > neg_line:
            result.add_error(
                _tr("Filter file: '{pos}' (line {pos_line}) must appear before "
                    "'{neg}' (line {neg_line}).").format(
                    pos=self.FILTER_SECTION_POSITIVE, pos_line=pos_line,
                    neg=self.FILTER_SECTION_NEGATIVE, neg_line=neg_line)
            )
        if orphan_lines:
            samples = [f"line {n}: {t[:30]}" for n, t in orphan_lines[:3]]
            result.add_warning(
                _tr("Filter file: {count} lines appear before the first section header "
                    "and will be ignored. Examples: {examples}.").format(
                    count=len(orphan_lines), examples='; '.join(samples))
            )

    def _validate_filter_entries(
        self, parsed: dict, result: ValidationResult
    ) -> None:
        """Validate filter entry counts and ATKIS code format.

        Args:
            parsed: Output of :meth:`_parse_filter_sections`.
            result: Validation result to append errors/warnings to.
        """
        pos_line = parsed["pos_line"]
        neg_line = parsed["neg_line"]
        entries_positive = parsed["entries_positive"]
        entries_negative = parsed["entries_negative"]

        if pos_line is not None and len(entries_positive) == 0:
            result.add_error(
                _tr("Filter file: Section '{section}' contains no entries. "
                    "Hint: Add at least one function code.").format(
                    section=self.FILTER_SECTION_POSITIVE)
            )
        if neg_line is not None and len(entries_negative) == 0:
            result.add_error(
                _tr("Filter file: Section '{section}' contains no entries. "
                    "Hint: Add at least one function code.").format(
                    section=self.FILTER_SECTION_NEGATIVE)
            )

        invalid_entries = []
        for line_nr, entry in entries_positive + entries_negative:
            code = entry[:10].strip().rstrip(",")
            if not self.HU_FKT_PATTERN.match(code):
                if len(invalid_entries) < 5:
                    invalid_entries.append(f"line {line_nr}: {entry[:30]}")

        if invalid_entries:
            result.add_warning(
                _tr("Filter file: Entries do not match the ATKIS format (NNNNN_NNNN). "
                    "Examples: {examples}. "
                    "Hint: Only the first 10 characters are used for filter matching.").format(
                    examples='; '.join(invalid_entries))
            )

    def _check_output_paths(
        self, output_path: str, workspace_path: str,
        result: ValidationResult
    ) -> None:
        """Validate output path format and workspace-path presence."""
        if not output_path or not output_path.strip():
            result.add_error(_tr("Output file: No path specified."))
        else:
            if not output_path.lower().endswith(".gpkg"):
                result.add_error(
                    _tr("Output file: GeoPackage (.gpkg) required, but got: {path}. "
                        "Hint: Choose a .gpkg output file.").format(path=output_path)
                )
            output_dir = os.path.dirname(output_path)
            if not output_dir:
                result.add_error(
                    _tr("Output file: Path must include a directory: {path}. "
                        "Hint: Choose a full output path such as "
                        "C:/data/result.gpkg.").format(path=output_path)
                )

        if not workspace_path or not workspace_path.strip():
            result.add_error(_tr("Workspace directory: No path specified."))

    # ------------------------------------------------------------------
    # Parameter validation
    # ------------------------------------------------------------------

    def _check_params(
        self, params: dict, result: ValidationResult
    ) -> None:
        """Validate UI parameter values for type, range, and consistency.

        Args:
            params: Dict with raw string values from UI widgets.
        """
        self._check_numeric_params(params, result)
        self._check_spatial_reference_param(params, result)
        self._check_partition_range_params(params, result)

    def _check_numeric_params(
        self, params: dict, result: ValidationResult
    ) -> None:
        """Validate numeric UI parameters for type and value range.

        Args:
            params: Dict with raw string values from UI widgets.
            result: Validation result to append errors to.
        """
        numeric_checks = [
            ("min_overlap_blocks", _tr("Min. Overlap Blocks (%)"), float, 0, 100),
            ("global_footprint_density", _tr("Global Footprint Density (%)"), float, 0, 100),
            ("min_area", _tr("Min. Building Area (sqm)"), float, 10, 500),
            ("min_bdg_count", _tr("Min. Building Count"), int, 1, 100),
            ("min_patch_size", _tr("Min. Patch Size (sqm)"), float, 100, 100000),
            ("max_hole_size", _tr("Max. Hole Size (sqm)"), float, 0, 100000),
            ("max_gap_size", _tr("Max. Gap Size (sqm)"), float, 0, 100000),
        ]

        for key, label, num_type, min_val, max_val in numeric_checks:
            raw = params.get(key)
            if raw is None:
                continue

            raw_str = str(raw).strip()
            if not raw_str:
                result.add_error(
                    _tr("Parameter '{label}': No value specified.").format(label=label)
                )
                continue

            try:
                value = num_type(raw_str)
            except (ValueError, TypeError):
                kind = _tr("integer") if num_type == int else _tr("number")
                result.add_error(
                    _tr("Parameter '{label}': '{value}' is not a valid {kind}.").format(
                        label=label, value=raw_str, kind=kind)
                )
                continue

            if min_val is not None and value < min_val:
                result.add_error(
                    _tr("Parameter '{label}': Value {value} is less than the "
                        "minimum ({min_val}).").format(
                        label=label, value=value, min_val=min_val)
                )
            if max_val is not None and value > max_val:
                result.add_error(
                    _tr("Parameter '{label}': Value {value} is greater than the "
                        "maximum ({max_val}).").format(
                        label=label, value=value, max_val=max_val)
                )

    def _check_spatial_reference_param(
        self, params: dict, result: ValidationResult
    ) -> None:
        """Validate the spatial reference (CRS) parameter.

        Args:
            params: Dict with raw string values from UI widgets.
            result: Validation result to append errors/warnings to.
        """
        sr_text = params.get("spatial_reference_text", "").strip()
        if not sr_text:
            return

        crs = QgsCoordinateReferenceSystem(sr_text)
        if not crs.isValid():
            result.add_error(
                _tr("Parameter 'CRS': '{crs}' is not a valid CRS. "
                    "Hint: Use e.g. EPSG:25832.").format(crs=sr_text)
            )
        elif crs.isGeographic():
            result.add_warning(
                _tr("Parameter 'CRS': '{crs}' is a geographic CRS (degrees). "
                    "Hint: A projected CRS (metres) such as EPSG:25832 "
                    "is recommended.").format(crs=sr_text)
            )

    def _check_partition_range_params(
        self, params: dict, result: ValidationResult
    ) -> None:
        """Validate the partition start/end range parameters.

        Args:
            params: Dict with raw string values from UI widgets.
            result: Validation result to append errors to.
        """
        part_start = params.get("part_start", "").strip()
        part_end = params.get("part_end", "").strip()
        if not part_start or not part_end:
            return

        try:
            start_val = int(part_start)
            end_val = int(part_end)
            if start_val != -1 and end_val != -1:
                if start_val < 0:
                    result.add_error(
                        _tr("Parameter 'Partition Start': Value {value} is invalid. "
                            "Hint: -1 (all) or >= 0.").format(value=start_val)
                    )
                if end_val < 0:
                    result.add_error(
                        _tr("Parameter 'Partition End': Value {value} is invalid. "
                            "Hint: -1 (all) or >= 0.").format(value=end_val)
                    )
                if 0 <= end_val <= start_val:
                    result.add_error(
                        _tr("Parameter: Partition Start ({start}) >= Partition End ({end}). "
                            "Hint: Start must be less than End.").format(
                            start=start_val, end=end_val)
                    )
        except ValueError:
            result.add_error(
                _tr("Parameter 'Partition Start/End': '{start}'/'{end}' are not "
                    "valid integers.").format(start=part_start, end=part_end)
            )
