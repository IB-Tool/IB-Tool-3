"""
Input data validation for IBTool.

Validates all input layers, fields, geometry types, CRS, and filter files
before processing starts.
"""

import os
from dataclasses import dataclass, field
from typing import List

from qgis.core import (
    QgsVectorLayer,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
)

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
    PART_REQUIRED_FIELD = "NAME"
    PART_NAME_PATTERN = "PART_"
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
                    f"{name}: Datei kann nicht als gültiger Layer geladen werden: {path}"
                )
                continue

            valid_layers[name] = layer

            # Check CRS
            self._check_crs(layer, name, spatial_reference, result)

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

        # Feature count checks
        self._check_feature_counts(valid_layers, result)

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

        return result

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
        has_field = any(f in field_names for f in self.HU_REQUIRED_FIELDS)
        if not has_field:
            result.add_error(
                f"Gebäudeumrisse (HU): Feld 'fkt' oder 'funktion' fehlt. "
                f"Vorhandene Felder: {', '.join(field_names[:15])}. "
                f"Hinweis: Ein Feld 'fkt' oder 'funktion' mit Gebäudefunktionscodes hinzufügen."
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
                f"Partitionierung (Part): Feld '{self.PART_REQUIRED_FIELD}' fehlt. "
                f"Vorhandene Felder: {', '.join(field_names[:15])}. "
                f"Hinweis: Ein Textfeld 'NAME' mit Partitionsnamen (z.B. PART_123) hinzufügen."
            )
            return

        # Check NAME values match PART_ pattern (warning only)
        name_idx = layer.fields().indexFromName(self.PART_REQUIRED_FIELD)
        non_matching = []
        for feature in layer.getFeatures():
            name_val = str(feature[name_idx])
            if not name_val.startswith(self.PART_NAME_PATTERN):
                non_matching.append(name_val)

        if non_matching:
            sample = non_matching[:5]
            result.add_warning(
                f"Partitionierung (Part): {len(non_matching)} NAME-Werte entsprechen "
                f"nicht dem '{self.PART_NAME_PATTERN}'-Muster. "
                f"Beispiele: {', '.join(sample)}. "
                f"Hinweis: NAME-Werte sollten dem Format PART_123 entsprechen."
            )

    def _check_filter_file(
        self, filter_path: str, result: ValidationResult
    ) -> None:
        """Validate filter file existence and format."""
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
                content = f.read()
        except Exception as e:
            result.add_error(
                f"Filterdatei: Datei kann nicht gelesen werden: {e}. "
                f"Hinweis: Datei muss UTF-8-kodiert und lesbar sein."
            )
            return

        if self.FILTER_SECTION_POSITIVE not in content:
            result.add_error(
                f"Filterdatei: Abschnitt '{self.FILTER_SECTION_POSITIVE}' fehlt. "
                f"Hinweis: Zeile '{self.FILTER_SECTION_POSITIVE}' in der Datei ergänzen."
            )
        if self.FILTER_SECTION_NEGATIVE not in content:
            result.add_error(
                f"Filterdatei: Abschnitt '{self.FILTER_SECTION_NEGATIVE}' fehlt. "
                f"Hinweis: Zeile '{self.FILTER_SECTION_NEGATIVE}' in der Datei ergänzen."
            )

    def _check_output_paths(
        self, output_path: str, workspace_path: str, result: ValidationResult
    ) -> None:
        """Validate output and workspace paths."""
        if not output_path or not output_path.strip():
            result.add_error("Ausgabedatei: Kein Pfad angegeben.")
        else:
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                result.add_error(
                    f"Ausgabedatei: Verzeichnis existiert nicht: {output_dir}. "
                    f"Hinweis: Verzeichnis anlegen oder anderen Pfad wählen."
                )

        if not workspace_path or not workspace_path.strip():
            result.add_error("Arbeitsverzeichnis: Kein Pfad angegeben.")

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

    def _check_multipart_lines(
        self, layer: QgsVectorLayer, layer_name: str,
        result: ValidationResult
    ) -> None:
        """Warn if line layer contains multipart geometries."""
        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            return

        multipart_count = 0
        for feature in layer.getFeatures():
            geom = feature.geometry()
            if geom.isNull():
                continue
            if geom.isMultipart():
                multipart_count += 1

        if multipart_count > 0:
            result.add_warning(
                f"{layer_name}: {multipart_count} Multipart-Geometrien gefunden. "
                f"Hinweis: Sketcher vor der Verarbeitung auflösen "
                f"(sketcher: native:multiparttosingleparts)."
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
                f"Part hat {part_count} Features, HU hat {hu_count} Features. "
                f"Hinweis: Feinere Partitionierung verwenden, um die "
                f"Verarbeitungszeit pro Partition zu reduzieren."
            )
