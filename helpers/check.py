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

from .logger import Logger


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
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


class InputValidator:
    """Validates all IBTool input data before processing."""

    # Required fields per layer type
    HU_REQUIRED_FIELDS = ("fkt", "funktion")  # At least one must exist
    HU_FKT_PATTERN = re.compile(r"^\d{5}_\d{4}")  # ATKIS: 31001_1000
    PART_REQUIRED_FIELD = "NAME"
    PART_NAME_REGEX = re.compile(r"^PART_\d+$")  # PART_36, PART_433
    FILTER_SECTION_POSITIVE = "#Filter positive"
    FILTER_SECTION_NEGATIVE = "#Filter negative"

    # Minimum feature counts per layer
    MIN_FEATURES_HU = 50
    MIN_FEATURES_RN = 30
    MIN_FEATURES_AUX = 10

    # Maximum ratio of Part features to HU features
    MAX_PART_TO_HU_RATIO = 10000

    def validate_all(
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
            "Gebäudeumrisse (HU)": hu_path,
            "Straßennetz (RN)": rn_path,
            "Partitionierung (Part)": part_path,
            "Hilfslayer (Aux)": aux_path,
        }

        valid_layers = {}  # name -> QgsVectorLayer for layers that loaded OK

        for name, path in layer_paths.items():
            # Check path is specified
            if not path or not path.strip():
                result.add_error(f"{name}: Kein Dateipfad angegeben.")
                continue

            # Check file exists
            if not os.path.exists(path):
                result.add_error(
                    f"{name}: Datei existiert nicht: {path}"
                )
                continue

            # Check layer is valid
            layer = QgsVectorLayer(path, name, "ogr")
            if not layer.isValid():
                result.add_error(
                    f"{name}: Datei kann nicht als gültiger Layer "
                    f"geladen werden: {path}"
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
        hu_key = "Gebäudeumrisse (HU)"
        if hu_key in valid_layers:
            self._check_hu_layer(valid_layers[hu_key], result)

        rn_key = "Straßennetz (RN)"
        if rn_key in valid_layers:
            self._check_rn_layer(valid_layers[rn_key], result)

        part_key = "Partitionierung (Part)"
        if part_key in valid_layers:
            self._check_part_layer(valid_layers[part_key], result)

        # Multipart geometry check for line layers
        for key in [rn_key, "Hilfslayer (Aux)"]:
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
            actual = layer_crs.authid() or "undefiniert/unbekannt"
            result.add_error(
                f"{layer_name}: CRS stimmt nicht überein. "
                f"Erwartet: {expected_crs.authid()}, gefunden: {actual}. "
                f"Hinweis: Layer nach {expected_crs.authid()} reprojizieren."
            )

    def _check_feature_counts(
        self, valid_layers: dict, result: ValidationResult
    ) -> None:
        """Check that layers contain minimum required feature counts."""
        min_counts = {
            "Gebäudeumrisse (HU)": self.MIN_FEATURES_HU,
            "Straßennetz (RN)": self.MIN_FEATURES_RN,
            "Hilfslayer (Aux)": self.MIN_FEATURES_AUX,
        }

        for name, min_count in min_counts.items():
            if name not in valid_layers:
                continue
            layer = valid_layers[name]
            count = layer.featureCount()
            if count == 0:
                result.add_error(
                    f"{name}: Layer ist leer (0 Features). "
                    f"Hinweis: Layer mit Daten befüllen."
                )
            elif count < min_count:
                result.add_error(
                    f"{name}: Zu wenige Features ({count}), "
                    f"mindestens {min_count} erforderlich. "
                    f"Hinweis: Datensatz auf Vollständigkeit prüfen."
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
                f"{layer_name}: {null_count} Features mit NULL-Geometrie. "
                f"Hinweis: Features ohne Geometrie entfernen."
            )

        if empty_count > 0:
            result.add_error(
                f"{layer_name}: {empty_count} Features mit leerer Geometrie. "
                f"Hinweis: Features mit leerer Geometrie entfernen."
            )

        if invalid_count > 0:
            details = ""
            if invalid_reasons:
                details = " Beispiele: " + "; ".join(invalid_reasons) + "."
            result.add_warning(
                f"{layer_name}: {invalid_count} ungültige Geometrien "
                f"(isGeosValid=False).{details} "
                f"Hinweis: Geometrien reparieren "
                f"(native:fixgeometries)."
            )

    def _check_validity_processing(
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
                details = " Fehlertypen: " + "; ".join(error_messages) + "."

            result.add_warning(
                f"{layer_name}: 'qgis:checkvalidity' hat "
                f"{invalid_count} ungültige Features gefunden.{details} "
                f"Hinweis: Geometrien reparieren "
                f"(native:fixgeometries)."
            )

        except Exception as e:
            result.add_warning(
                f"{layer_name}: 'qgis:checkvalidity' konnte nicht "
                f"ausgeführt werden: {e}"
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
                f"Gebäudeumrisse (HU): Polygon-Geometrie erforderlich, "
                f"aber {geom_type} gefunden. "
                f"Hinweis: Einen Layer mit Polygon-Geometrie verwenden."
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
                f"Gebäudeumrisse (HU): Feld 'fkt' oder 'funktion' fehlt. "
                f"Vorhandene Felder: {', '.join(field_names[:15])}. "
                f"Hinweis: Ein Feld 'fkt' oder 'funktion' mit "
                f"Gebäudefunktionscodes hinzufügen."
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
            result.add_error(
                f"Gebäudeumrisse (HU): {null_count} Features mit "
                f"leerem/NULL-Wert im Feld '{fkt_field}'. "
                f"Hinweis: Alle Features brauchen einen "
                f"Gebäudefunktionscode."
            )

        if invalid_format:
            result.add_warning(
                f"Gebäudeumrisse (HU): Werte im Feld '{fkt_field}' "
                f"entsprechen nicht dem ATKIS-Format (NNNNN_NNNN, "
                f"z.B. 31001_1000). Beispiele: "
                f"{', '.join(invalid_format)}. "
                f"Hinweis: Nur die ersten 10 Zeichen werden "
                f"fuer den Filterabgleich verwendet."
            )

    def _check_rn_layer(
        self, layer: QgsVectorLayer, result: ValidationResult
    ) -> None:
        """Validate RN layer: must be LineString geometry."""
        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            geom_type = QgsWkbTypes.geometryDisplayString(layer.geometryType())
            result.add_error(
                f"Straßennetz (RN): Linien-Geometrie erforderlich, "
                f"aber {geom_type} gefunden. "
                f"Hinweis: Einen Layer mit Linien-Geometrie verwenden."
            )

    def _check_part_layer(
        self, layer: QgsVectorLayer, result: ValidationResult
    ) -> None:
        """Validate Part layer: NAME field and naming pattern."""
        field_names = [f.name() for f in layer.fields()]

        # Required field: NAME
        if self.PART_REQUIRED_FIELD not in field_names:
            result.add_error(
                f"Partitionierung (Part): Feld "
                f"'{self.PART_REQUIRED_FIELD}' fehlt. "
                f"Vorhandene Felder: {', '.join(field_names[:15])}. "
                f"Hinweis: Ein Textfeld 'NAME' mit Partitionsnamen "
                f"(z.B. PART_123) hinzufügen."
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
                f"Partitionierung (Part): {null_count} Features mit "
                f"leerem/NULL-Wert im Feld 'NAME'. "
                f"Hinweis: Alle Partitionen brauchen einen Namen "
                f"im Format PART_<Zahl>."
            )

        if non_matching:
            result.add_error(
                f"Partitionierung (Part): NAME-Werte entsprechen "
                f"nicht dem Format PART_<Zahl>. "
                f"Beispiele: {', '.join(non_matching)}. "
                f"Hinweis: NAME-Werte muessen exakt dem Muster "
                f"PART_123 folgen (z.B. PART_36, PART_433)."
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
                f"{layer_name}: {multiline_count} Features enthalten "
                f"mehrere Linienzuege (MultiLineString mit >1 Teil). "
                f"Jedes Feature darf nur einen Linienzug enthalten. "
                f"Hinweis: Sketcher auflösen "
                f"(native:multiparttosingleparts)."
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
                f"Verhältnis Part:HU = 1:{ratio:.0f} "
                f"(Schwellenwert: 1:{self.MAX_PART_TO_HU_RATIO}). "
                f"Part hat {part_count} Features, HU hat "
                f"{hu_count} Features. "
                f"Hinweis: Feinere Partitionierung verwenden, um die "
                f"Verarbeitungszeit pro Partition zu reduzieren."
            )

    # ------------------------------------------------------------------
    # Filter file and output paths
    # ------------------------------------------------------------------

    def _check_filter_file(
        self, filter_path: str, result: ValidationResult
    ) -> None:
        """Validate filter file existence, format, and content.

        Expected format:
            #Filter positive
            31001_1000, Wohngeb
            31001_1010, Wohnhaus
            ...

            #Filter negative
            31001_1310, Freizeit
            31001_2600, Entsorgung
            ...

        Rules:
        - Sections '#Filter positive' and '#Filter negative' required
        - '#Filter positive' must appear before '#Filter negative'
        - Each section must contain at least one entry
        - Entries should start with ATKIS code (NNNNN_NNNN)
        - Lines starting with '#' are comments, empty lines ignored
        - Only first 10 characters per entry used for matching
        """
        if not filter_path or not filter_path.strip():
            result.add_error("Filterdatei: Kein Dateipfad angegeben.")
            return

        if not os.path.exists(filter_path):
            result.add_error(
                f"Filterdatei: Datei existiert nicht: {filter_path}"
            )
            return

        try:
            with open(filter_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as e:
            result.add_error(
                f"Filterdatei: Datei kann nicht gelesen werden: {e}. "
                f"Hinweis: Datei muss UTF-8-kodiert und lesbar sein."
            )
            return

        # Parse structure: find sections and their entries
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
                continue
            elif line.startswith(self.FILTER_SECTION_NEGATIVE):
                current_section = "negative"
                neg_line = i
                continue
            elif line.startswith("#") or not line:
                continue

            # Content line
            if current_section == "positive":
                entries_positive.append((i, line))
            elif current_section == "negative":
                entries_negative.append((i, line))
            else:
                orphan_lines.append((i, line))

        # Check sections exist
        if pos_line is None:
            result.add_error(
                f"Filterdatei: Abschnitt "
                f"'{self.FILTER_SECTION_POSITIVE}' fehlt. "
                f"Hinweis: Zeile '{self.FILTER_SECTION_POSITIVE}' "
                f"in der Datei ergänzen."
            )
        if neg_line is None:
            result.add_error(
                f"Filterdatei: Abschnitt "
                f"'{self.FILTER_SECTION_NEGATIVE}' fehlt. "
                f"Hinweis: Zeile '{self.FILTER_SECTION_NEGATIVE}' "
                f"in der Datei ergänzen."
            )

        # Check section order
        if pos_line is not None and neg_line is not None:
            if pos_line > neg_line:
                result.add_error(
                    f"Filterdatei: '{self.FILTER_SECTION_POSITIVE}' "
                    f"(Zeile {pos_line}) muss vor "
                    f"'{self.FILTER_SECTION_NEGATIVE}' "
                    f"(Zeile {neg_line}) stehen."
                )

        # Check orphan lines (before any section header)
        if orphan_lines:
            samples = [f"Zeile {n}: {t[:30]}" for n, t in orphan_lines[:3]]
            result.add_warning(
                f"Filterdatei: {len(orphan_lines)} Zeilen stehen vor "
                f"dem ersten Abschnittsheader und werden ignoriert. "
                f"Beispiele: {'; '.join(samples)}."
            )

        # Check minimum entries per section
        if pos_line is not None and len(entries_positive) == 0:
            result.add_error(
                f"Filterdatei: Abschnitt "
                f"'{self.FILTER_SECTION_POSITIVE}' enthält keine "
                f"Einträge. Hinweis: Mindestens einen "
                f"Funktionscode hinzufügen."
            )
        if neg_line is not None and len(entries_negative) == 0:
            result.add_error(
                f"Filterdatei: Abschnitt "
                f"'{self.FILTER_SECTION_NEGATIVE}' enthält keine "
                f"Einträge. Hinweis: Mindestens einen "
                f"Funktionscode hinzufügen."
            )

        # Check entry format (ATKIS code in first 10 chars)
        invalid_entries = []
        for line_nr, entry in entries_positive + entries_negative:
            code = entry[:10].strip().rstrip(",")
            if not self.HU_FKT_PATTERN.match(code):
                if len(invalid_entries) < 5:
                    invalid_entries.append(
                        f"Zeile {line_nr}: {entry[:30]}"
                    )

        if invalid_entries:
            result.add_warning(
                f"Filterdatei: Einträge entsprechen nicht dem "
                f"ATKIS-Format (NNNNN_NNNN). Beispiele: "
                f"{'; '.join(invalid_entries)}. "
                f"Hinweis: Nur die ersten 10 Zeichen werden "
                f"für den Filterabgleich verwendet."
            )

    def _check_output_paths(
        self, output_path: str, workspace_path: str,
        result: ValidationResult
    ) -> None:
        """Validate output and workspace paths."""
        if not output_path or not output_path.strip():
            result.add_error("Ausgabedatei: Kein Pfad angegeben.")
        else:
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                result.add_error(
                    f"Ausgabedatei: Verzeichnis existiert nicht: "
                    f"{output_dir}. "
                    f"Hinweis: Verzeichnis anlegen oder anderen "
                    f"Pfad wählen."
                )

        if not workspace_path or not workspace_path.strip():
            result.add_error("Arbeitsverzeichnis: Kein Pfad angegeben.")

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
        # Numeric parameters: (key, label, type, min, max)
        numeric_checks = [
            ("min_overlap_blocks", "Min. Overlap Blocks (%)",
             float, 0, 100),
            ("global_footprint_density", "Globale Footprint-Dichte (%)",
             float, 0, 100),
            ("min_area", "Min. Gebaeude-Grundflaeche (qm)",
             float, 10, 500),
            ("min_bdg_count", "Min. Gebaeudeanzahl",
             int, 1, 100),
            ("min_patch_size", "Min. Patchgroesse (qm)",
             float, 100, 100000),
            ("max_hole_size", "Max. Lochgroesse (qm)",
             float, 0, 100000),
            ("max_gap_size", "Max. Lueckengroesse (qm)",
             float, 0, 100000),
        ]

        parsed = {}
        for key, label, num_type, min_val, max_val in numeric_checks:
            raw = params.get(key)
            if raw is None:
                continue

            raw_str = str(raw).strip()
            if not raw_str:
                result.add_error(
                    f"Parameter '{label}': Kein Wert angegeben."
                )
                continue

            try:
                value = num_type(raw_str)
            except (ValueError, TypeError):
                expected = "Ganzzahl" if num_type == int else "Zahl"
                result.add_error(
                    f"Parameter '{label}': '{raw_str}' ist keine "
                    f"gueltige {expected}."
                )
                continue

            parsed[key] = value

            if min_val is not None and value < min_val:
                result.add_error(
                    f"Parameter '{label}': Wert {value} ist kleiner "
                    f"als das Minimum ({min_val})."
                )
            if max_val is not None and value > max_val:
                result.add_error(
                    f"Parameter '{label}': Wert {value} ist groesser "
                    f"als das Maximum ({max_val})."
                )

        # Spatial reference check
        sr_text = params.get("spatial_reference_text", "").strip()
        if sr_text:
            crs = QgsCoordinateReferenceSystem(sr_text)
            if not crs.isValid():
                result.add_error(
                    f"Parameter 'CRS': '{sr_text}' ist "
                    f"kein gueltiges CRS. "
                    f"Hinweis: z.B. EPSG:25832 verwenden."
                )
            elif crs.isGeographic():
                result.add_warning(
                    f"Parameter 'CRS': '{sr_text}' ist "
                    f"ein geographisches CRS (Grad). "
                    f"Hinweis: Ein projiziertes CRS (Meter) wie "
                    f"EPSG:25832 wird empfohlen."
                )

        # Partition range check
        part_start = params.get("part_start", "").strip()
        part_end = params.get("part_end", "").strip()
        if part_start and part_end:
            try:
                ps = int(part_start)
                pe = int(part_end)
                if ps != -1 and pe != -1:
                    if ps < 0:
                        result.add_error(
                            f"Parameter 'Partition Start': "
                            f"Wert {ps} ist ungueltig. "
                            f"Hinweis: -1 (alle) oder >= 0."
                        )
                    if pe < 0:
                        result.add_error(
                            f"Parameter 'Partition End': "
                            f"Wert {pe} ist ungueltig. "
                            f"Hinweis: -1 (alle) oder >= 0."
                        )
                    if ps >= 0 and pe >= 0 and ps >= pe:
                        result.add_error(
                            f"Parameter: Partition Start ({ps}) >= "
                            f"Partition End ({pe}). "
                            f"Hinweis: Start muss kleiner als "
                            f"End sein."
                        )
            except ValueError:
                result.add_error(
                    f"Parameter 'Partition Start/End': "
                    f"'{part_start}'/'{part_end}' sind keine "
                    f"gueltigen Ganzzahlen."
                )
