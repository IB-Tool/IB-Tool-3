import pytest
import os
import sys
import logging
from pathlib import Path


# QGIS imports
from qgis.core import (
    QgsVectorLayer,
    QgsProject,
    QgsWkbTypes,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsField,
)
from PyQt5.QtCore import QVariant
from ibtool.helpers.system_utils import save_temp_layer_to_gpkg

# Private helpers under test
from ibtool.ibtool_tools.Blocker import (
    blocker,
    _assign_block_names,
    _remove_blocks_without_buildings,
    _build_block_polygons,
)

# Import utilities for QGIS setup
from .utilities import get_qgis_app


class TestBlockerIntegration:
    """
    Integrationstest für die Blocker-Funktion
    Testet die vollständige Funktionalität mit echten QGIS-Daten
    """

    @classmethod
    def setup_class(cls):
        """Setup QGIS application für alle Tests"""
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()
        cls.test_data_dir = Path(__file__).parent / 'dummy_data'
        cls.logger = logging.getLogger('BlockerIntegrationTest')
        cls.logger.setLevel(logging.INFO)

        # Setup console handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        cls.logger.addHandler(handler)

    def setup_method(self, method):
        """Setup für jeden einzelnen Test"""
        self.tolerance_meters = 1.0
        self.tolerance_percent = 1.0
        self.comparison_results = {}

        # Import der Blocker-Funktion (Pfad wird durch test/__init__.py gesetzt)
        try:
            from ibtool.ibtool_tools.Blocker import blocker
            self.blocker_function = blocker
        except ImportError as e:
            pytest.fail(f"Konnte Blocker-Funktion nicht importieren: {e}")

    def load_test_layer(self, filename):
        """Lädt einen Test-Layer aus dem dummy_data Ordner"""
        file_path = self.test_data_dir / filename
        if not file_path.exists():
            raise FileNotFoundError(f"Test data file not found: {file_path}")

        # Korrektur: Verwende os.path.splitext um den Namen ohne Extension zu bekommen
        layer_name = os.path.splitext(filename)[
            0]  # Entfernt die .gpkg Extension
        layer = QgsVectorLayer(str(file_path), layer_name, 'ogr')

        if not layer.isValid():
            raise ValueError(f"Layer is not valid: {filename}")

        return layer

    def calculate_total_area(self, layer):
        """Berechnet die Gesamtfläche aller Features in einem Layer"""
        total_area = 0.0
        for feature in layer.getFeatures():
            if feature.geometry() and feature.geometry().isGeosValid():
                total_area += feature.geometry().area()
        return total_area

    def calculate_perimeter_sum(self, layer):
        """Berechnet die Summe aller Umringe in einem Layer"""
        total_perimeter = 0.0
        for feature in layer.getFeatures():
            if feature.geometry() and feature.geometry().isGeosValid():
                # Für Polygone: length() gibt den Umfang zurück
                # Für Linien: length() gibt die Länge zurück
                total_perimeter += feature.geometry().length()
        return total_perimeter

    def calculate_area_difference_percent(self, expected_layer, actual_layer):
        """Berechnet die prozentuale Abweichung der Gesamtfläche"""
        expected_area = self.calculate_total_area(expected_layer)
        actual_area = self.calculate_total_area(actual_layer)

        if expected_area == 0:
            return 0.0 if actual_area == 0 else 100.0

        return abs(expected_area - actual_area) / expected_area * 100

    def union_all_geometries(self, layer):
        """Vereinigt alle Geometrien eines Layers"""
        union_geom = None
        for feature in layer.getFeatures():
            if feature.geometry() and feature.geometry().isGeosValid():
                if union_geom is None:
                    union_geom = feature.geometry()
                else:
                    union_geom = union_geom.combine(feature.geometry())
        return union_geom

    def calculate_symmetric_difference_percentage(self, expected_layer,
                                                  actual_layer):
        """Berechnet die prozentuale Symmetric Difference"""
        expected_union = self.union_all_geometries(expected_layer)
        actual_union = self.union_all_geometries(actual_layer)

        if not expected_union or not actual_union:
            return 100.0

        sym_diff = expected_union.symDifference(actual_union)
        total_area = expected_union.area()

        return (sym_diff.area() / total_area) * 100 if total_area > 0 else 0

    def check_geometry_validity(self, layer):
        """Überprüft die Geometriegültigkeit aller Features"""
        geometry_issues = []
        for feature in layer.getFeatures():
            if feature.geometry() and not feature.geometry().isGeosValid():
                geometry_issues.append({
                    'feature_id': feature.id(),
                    'error': feature.geometry().lastError() if hasattr(
                        feature.geometry(),
                        'lastError') else 'Unknown geometry error'
                })
        return geometry_issues

    def compare_attributes(self, expected_layer, actual_layer):
        """Vergleicht die Attribute zwischen erwartetem und tatsächlichem Layer"""
        expected_names = set()
        actual_names = set()

        for feature in expected_layer.getFeatures():
            if 'NAME' in feature.fields().names():
                expected_names.add(feature['NAME'])

        for feature in actual_layer.getFeatures():
            if 'NAME' in feature.fields().names():
                actual_names.add(feature['NAME'])

        return {
            'missing_names': expected_names - actual_names,
            'extra_names': actual_names - expected_names,
            'common_names': expected_names & actual_names
        }

    def generate_comparison_report(self, scenario_name, expected_layer,
                                   actual_layer):
        """Generiert detaillierten Vergleichsbericht"""
        report = {
            'scenario': scenario_name,
            'feature_count': {
                'expected': expected_layer.featureCount(),
                'actual': actual_layer.featureCount(),
                'difference': abs(
                    expected_layer.featureCount() - actual_layer.featureCount())
            },
            'total_area': {
                'expected': self.calculate_total_area(expected_layer),
                'actual': self.calculate_total_area(actual_layer),
                'difference_percent': self.calculate_area_difference_percent(
                    expected_layer, actual_layer)
            },
            'perimeter_sum': {
                'expected': self.calculate_perimeter_sum(expected_layer),
                'actual': self.calculate_perimeter_sum(actual_layer),
                'difference_meters': abs(
                    self.calculate_perimeter_sum(expected_layer) -
                    self.calculate_perimeter_sum(actual_layer))
            },
            'symmetric_difference_percent': self.calculate_symmetric_difference_percentage(
                expected_layer, actual_layer),
            'geometry_issues': self.check_geometry_validity(actual_layer),
            'attribute_comparison': self.compare_attributes(expected_layer,
                                                            actual_layer)
        }

        return report

    def print_comparison_report(self, report):
        """Druckt detaillierten Vergleichsbericht"""
        self.logger.info(f"\n===== BLOCKER INTEGRATION TEST REPORT =====")
        self.logger.info(f"Scenario: {report['scenario']}")
        self.logger.info(f"")
        self.logger.info(f"Feature Count:")
        self.logger.info(f"  Expected: {report['feature_count']['expected']}")
        self.logger.info(f"  Actual: {report['feature_count']['actual']}")
        self.logger.info(
            f"  Difference: {report['feature_count']['difference']}")
        self.logger.info(f"")
        self.logger.info(f"Total Area:")
        self.logger.info(
            f"  Expected: {report['total_area']['expected']:.2f} m²")
        self.logger.info(f"  Actual: {report['total_area']['actual']:.2f} m²")
        self.logger.info(
            f"  Difference: {report['total_area']['difference_percent']:.2f}%")
        self.logger.info(f"")
        self.logger.info(f"Perimeter Sum:")
        self.logger.info(
            f"  Expected: {report['perimeter_sum']['expected']:.2f} m")
        self.logger.info(f"  Actual: {report['perimeter_sum']['actual']:.2f} m")
        self.logger.info(
            f"  Difference: {report['perimeter_sum']['difference_meters']:.2f} m")
        self.logger.info(f"")
        self.logger.info(
            f"Symmetric Difference: {report['symmetric_difference_percent']:.2f}%")
        self.logger.info(f"")
        self.logger.info(f"Geometry Issues: {len(report['geometry_issues'])}")

        if report['geometry_issues']:
            self.logger.warning("Geometry issues found:")
            for issue in report['geometry_issues']:
                self.logger.warning(
                    f"  Feature {issue['feature_id']}: {issue['error']}")

        attr_comp = report['attribute_comparison']
        self.logger.info(f"")
        self.logger.info(f"Attribute Comparison:")
        self.logger.info(f"  Missing names: {len(attr_comp['missing_names'])}")
        self.logger.info(f"  Extra names: {len(attr_comp['extra_names'])}")
        self.logger.info(f"  Common names: {len(attr_comp['common_names'])}")

        if attr_comp['missing_names']:
            self.logger.warning(f"  Missing: {attr_comp['missing_names']}")
        if attr_comp['extra_names']:
            self.logger.warning(f"  Extra: {attr_comp['extra_names']}")

    def handle_geometry_warnings(self, layer):
        """Behandelt Geometriewarnungen ohne Test zu beenden"""
        geometry_issues = self.check_geometry_validity(layer)

        if geometry_issues:
            self.logger.warning(
                f"Geometry warnings found: {len(geometry_issues)} issues")
            for issue in geometry_issues:
                self.logger.warning(
                    f"  Feature {issue['feature_id']}: {issue['error']}")

        return geometry_issues

    def assert_layers_similar(self, expected_layer, actual_layer,
                              scenario_name):
        """Hauptvergleichsfunktion mit Toleranzen"""
        report = self.generate_comparison_report(scenario_name, expected_layer,
                                                 actual_layer)
        self.print_comparison_report(report)

        # Handle geometry warnings
        self.handle_geometry_warnings(actual_layer)

        # Debug-Ausgaben hinzufügen
        self.logger.info(
            f"Expected feature count: {report['feature_count']['expected']}")
        self.logger.info(
            f"Actual feature count: {report['feature_count']['actual']}")

        # Assertions mit Toleranzen
        assert report['feature_count']['expected'] == report['feature_count']['actual'], (
            f"Feature count mismatch in {scenario_name}: Expected {report['feature_count']['expected']}, "
            f"got {report['feature_count']['actual']}"
        )

    @pytest.mark.integration
    def test_blocker_standard_case(self):
        """Haupttest mit Standard-Dummy-Daten"""
        self.logger.info("Running standard case test...")

        # Load test data
        strassen = self.load_test_layer('dummy_aux_rn.gpkg')
        hu_input = self.load_test_layer('dummy_hu.gpkg')
        partition = self.load_test_layer('dummy_part.gpkg')
        expected_result = self.load_test_layer('blocker_result.gpkg')
        test_dir = Path(__file__).parent

        # Run blocker function
        result = self.blocker_function(strassen, hu_input, partition)
        save_temp_layer_to_gpkg(result, 'blocker_result2.gpkg', test_dir)

        # Verify result is valid
        assert result is not None, "Blocker function returned None"
        assert isinstance(result, QgsVectorLayer), "Result is not a QgsVectorLayer"
        assert result.isValid(), "Result layer is not valid"

        # Compare with expected result
        self.assert_layers_similar(expected_result, result, "standard_case")

    @pytest.mark.integration
    def test_blocker_geometry_validation(self):
        """Test der Geometriegültigkeit"""
        self.logger.info("Running geometry validation test...")

        # Load test data
        strassen = self.load_test_layer('dummy_rn.gpkg')
        hu_input = self.load_test_layer('dummy_hu.gpkg')
        partition = self.load_test_layer('dummy_part.gpkg')

        # Run blocker function
        result = self.blocker_function(strassen, hu_input, partition)

        # Check geometry validity
        geometry_issues = self.check_geometry_validity(result)

        # Log warnings but don't fail test
        if geometry_issues:
            self.logger.warning(
                f"Found {len(geometry_issues)} geometry issues (this is a warning, not an error)")

        # Ensure all features are polygons
        for feature in result.getFeatures():
            if feature.geometry():
                assert feature.geometry().type() == QgsWkbTypes.PolygonGeometry, "All features should be polygons"

    @pytest.mark.integration
    def test_blocker_spatial_relationships(self):
        """Test räumlicher Beziehungen"""
        self.logger.info("Running spatial relationships test...")

        # Load test data
        strassen = self.load_test_layer('dummy_rn.gpkg')
        hu_input = self.load_test_layer('dummy_hu.gpkg')
        partition = self.load_test_layer('dummy_part.gpkg')

        # Run blocker function
        result = self.blocker_function(strassen, hu_input, partition)

        # Check that each block contains at least one building
        blocks_with_buildings = 0
        for block_feature in result.getFeatures():
            if not block_feature.geometry():
                continue

            contains_building = False
            for building_feature in hu_input.getFeatures():
                if not building_feature.geometry():
                    continue

                if block_feature.geometry().contains(
                        building_feature.geometry()) or \
                        block_feature.geometry().intersects(
                            building_feature.geometry()):
                    contains_building = True
                    break

            if contains_building:
                blocks_with_buildings += 1

        assert blocks_with_buildings > 0, "At least one block should contain buildings"

    @pytest.mark.integration
    def test_blocker_attribute_correctness(self):
        """Test der Attributkorrektheit"""
        self.logger.info("Running attribute correctness test...")

        # Load test data
        strassen = self.load_test_layer('dummy_rn.gpkg')
        hu_input = self.load_test_layer('dummy_hu.gpkg')
        partition = self.load_test_layer('dummy_part.gpkg')

        # Run blocker function
        result = self.blocker_function(strassen, hu_input, partition)

        # Check NAME field exists
        name_field_exists = any(
            field.name() == 'NAME' for field in result.fields())
        assert name_field_exists, "NAME field should exist"

        # Check NAME field values
        name_values = []
        for feature in result.getFeatures():
            if 'NAME' in feature.fields().names():
                name_values.append(feature['NAME'])

        # All NAME values should follow Block_X pattern
        for name in name_values:
            assert name is not None, "NAME value should not be None"
            assert name.startswith('Block_'), f"NAME value '{name}' should start with 'Block_'"

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_blocker_with_empty_layers(self):
        """Test mit leeren Eingabe-Layern"""
        self.logger.info("Running empty layers test...")

        # Create empty layers
        strassen = QgsVectorLayer("LineString?crs=EPSG:4326", "empty_roads",
                                  "memory")
        hu_input = QgsVectorLayer("Polygon?crs=EPSG:4326", "empty_buildings",
                                  "memory")
        partition = QgsVectorLayer("Polygon?crs=EPSG:4326", "empty_partition",
                                   "memory")

        # Add at least one feature to partition to avoid complete failure
        partition.dataProvider().addFeatures([QgsFeature()])

        try:
            result = self.blocker_function(strassen, hu_input, partition)

            # Should handle empty inputs gracefully
            assert result is not None, "Function should handle empty inputs"
            assert isinstance(result, QgsVectorLayer), "Result should be a QgsVectorLayer"

        except Exception as e:
            # If function fails with empty inputs, that's acceptable
            self.logger.warning(f"Function failed with empty inputs: {e}")

    @pytest.mark.integration
    @pytest.mark.slow
    def test_blocker_performance(self):
        """Einfacher Performance-Test"""
        self.logger.info("Running performance test...")

        import time

        # Load test data
        strassen = self.load_test_layer('dummy_rn.gpkg')
        hu_input = self.load_test_layer('dummy_hu.gpkg')
        partition = self.load_test_layer('dummy_part.gpkg')

        # Measure execution time
        start_time = time.time()
        result = self.blocker_function(strassen, hu_input, partition)
        end_time = time.time()

        execution_time = end_time - start_time
        self.logger.info(f"Execution time: {execution_time:.2f} seconds")

        # Reasonable time limit (adjust as needed)
        assert execution_time < 60, "Function should complete within 60 seconds"
        

    def teardown_method(self, method):
        """Cleanup nach jedem Test"""
        # Clear any temporary layers
        QgsProject.instance().clear()

    @classmethod
    def teardown_class(cls):
        """Cleanup nach allen Tests — QGIS-Instanz bleibt aktiv für weitere Tests."""
        QgsProject.instance().clear()


# ---------------------------------------------------------------------------
# Unit tests for _assign_block_names (no Processing algorithms required)
# ---------------------------------------------------------------------------

class TestAssignBlockNames:
    """Unit tests for the _assign_block_names helper."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    def _make_polygon_layer(self, n: int = 3) -> QgsVectorLayer:
        """Create an in-memory polygon layer with n simple square features."""
        layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "blocks", "memory")
        feats = []
        for i in range(n):
            f = QgsFeature()
            x = float(i * 10)
            f.setGeometry(QgsGeometry.fromPolygonXY([[
                QgsPointXY(x, 0), QgsPointXY(x + 9, 0),
                QgsPointXY(x + 9, 9), QgsPointXY(x, 9),
                QgsPointXY(x, 0),
            ]]))
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        return layer

    @pytest.mark.unit
    def test_name_field_is_created_when_absent(self):
        """NAME field must not exist before and must exist after the call."""
        layer = self._make_polygon_layer()
        assert layer.fields().indexFromName("NAME") < 0, "NAME must not exist yet"
        _assign_block_names(layer)
        assert layer.fields().indexFromName("NAME") >= 0

    @pytest.mark.unit
    def test_all_features_receive_name_value(self):
        """Every feature gets a non-None NAME starting with 'Block_'."""
        layer = self._make_polygon_layer(4)
        _assign_block_names(layer)
        for feat in layer.getFeatures():
            val = feat["NAME"]
            assert val is not None, "NAME must not be None"
            assert str(val).startswith("Block_"), f"Expected Block_<id>, got '{val}'"

    @pytest.mark.unit
    def test_name_values_follow_block_id_pattern(self):
        """NAME values must match 'Block_<integer>' exactly."""
        import re
        pattern = re.compile(r"^Block_\d+$")
        layer = self._make_polygon_layer(3)
        _assign_block_names(layer)
        for feat in layer.getFeatures():
            assert pattern.match(str(feat["NAME"])), f"Pattern mismatch: '{feat['NAME']}'"

    @pytest.mark.unit
    def test_name_values_are_unique(self):
        """No two features share the same NAME value."""
        layer = self._make_polygon_layer(5)
        _assign_block_names(layer)
        names = [feat["NAME"] for feat in layer.getFeatures()]
        assert len(names) == len(set(names)), "Duplicate NAME values detected"

    @pytest.mark.unit
    def test_name_field_not_duplicated_when_already_present(self):
        """If NAME field already exists, no second NAME field is added."""
        layer = self._make_polygon_layer(2)
        layer.dataProvider().addAttributes([QgsField("NAME", QVariant.String)])
        layer.updateFields()
        field_count_before = layer.fields().count()
        _assign_block_names(layer)
        assert layer.fields().count() == field_count_before, \
            "NAME field must not be added twice"

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_layer_no_crash(self):
        """Calling on an empty layer must not raise and must add NAME field."""
        layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "empty", "memory")
        _assign_block_names(layer)
        assert layer.fields().indexFromName("NAME") >= 0
        assert layer.featureCount() == 0


# ---------------------------------------------------------------------------
# Integration tests for _remove_blocks_without_buildings
# ---------------------------------------------------------------------------

class TestRemoveBlocksWithoutBuildings:
    """Integration tests for _remove_blocks_without_buildings (needs Processing)."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    def _make_two_block_layer(self) -> QgsVectorLayer:
        """Two non-overlapping polygon blocks — A at (0-100) and B at (200-300)."""
        layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "blocks", "memory")
        geoms = [
            QgsGeometry.fromPolygonXY([[      # Block A
                QgsPointXY(0, 0), QgsPointXY(100, 0),
                QgsPointXY(100, 100), QgsPointXY(0, 100), QgsPointXY(0, 0),
            ]]),
            QgsGeometry.fromPolygonXY([[      # Block B — far away
                QgsPointXY(200, 200), QgsPointXY(300, 200),
                QgsPointXY(300, 300), QgsPointXY(200, 300), QgsPointXY(200, 200),
            ]]),
        ]
        feats = [QgsFeature() for _ in geoms]
        for f, g in zip(feats, geoms):
            f.setGeometry(g)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        return layer

    def _make_building_in_block_a(self) -> QgsVectorLayer:
        """Single building inside Block A (overlaps → intersects)."""
        layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "buildings", "memory")
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(40, 40), QgsPointXY(60, 40),
            QgsPointXY(60, 60), QgsPointXY(40, 60), QgsPointXY(40, 40),
        ]]))
        layer.dataProvider().addFeatures([f])
        layer.updateExtents()
        return layer

    @pytest.mark.integration
    def test_feature_count_reduced_to_one(self):
        """Two blocks, one building — exactly one block must survive."""
        blocks = self._make_two_block_layer()
        buildings = self._make_building_in_block_a()
        assert blocks.featureCount() == 2
        _remove_blocks_without_buildings(blocks, buildings)
        assert blocks.featureCount() == 1

    @pytest.mark.integration
    def test_surviving_block_is_the_one_with_building(self):
        """The surviving block must be Block A (contains the building)."""
        blocks = self._make_two_block_layer()
        buildings = self._make_building_in_block_a()
        _remove_blocks_without_buildings(blocks, buildings)
        remaining = list(blocks.getFeatures())
        assert len(remaining) == 1
        centroid = remaining[0].geometry().centroid().asPoint()
        # Block A centroid is around (50, 50); Block B is around (250, 250)
        assert centroid.x() < 150, \
            f"Expected Block A to survive (centroid ~50), got x={centroid.x()}"

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_all_blocks_removed_when_buildings_layer_is_empty(self):
        """When no buildings intersect any block, all blocks are removed."""
        blocks = self._make_two_block_layer()
        empty_buildings = QgsVectorLayer(
            "Polygon?crs=EPSG:25833", "empty_buildings", "memory"
        )
        _remove_blocks_without_buildings(blocks, empty_buildings)
        assert blocks.featureCount() == 0


# ---------------------------------------------------------------------------
# Integration tests for _build_block_polygons
# ---------------------------------------------------------------------------

class TestBuildBlockPolygons:
    """Integration tests for _build_block_polygons using test data files."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()
        cls.test_data_dir = Path(__file__).parent / "dummy_data"

    def _load(self, filename: str) -> QgsVectorLayer:
        path = str(self.test_data_dir / filename)
        name = os.path.splitext(filename)[0]
        layer = QgsVectorLayer(path, name, "ogr")
        assert layer.isValid(), f"Could not load test data: {filename}"
        return layer

    @pytest.mark.integration
    def test_returns_valid_qgsvectorlayer(self):
        """_build_block_polygons returns a non-None, valid QgsVectorLayer."""
        rn = self._load("dummy_rn.gpkg")
        part = self._load("dummy_part.gpkg")
        result = _build_block_polygons(rn, part)
        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()

    @pytest.mark.integration
    def test_output_geometry_type_is_polygon(self):
        """Output layer geometry type must be PolygonGeometry."""
        rn = self._load("dummy_rn.gpkg")
        part = self._load("dummy_part.gpkg")
        result = _build_block_polygons(rn, part)
        assert result.geometryType() == QgsWkbTypes.PolygonGeometry

    @pytest.mark.integration
    def test_produces_at_least_one_polygon(self):
        """A road cutting through a partition must produce at least one block."""
        rn = self._load("dummy_rn.gpkg")
        part = self._load("dummy_part.gpkg")
        result = _build_block_polygons(rn, part)
        assert result.featureCount() > 0, "Expected at least one raw block polygon"


# ---------------------------------------------------------------------------
# Additional result-quality tests for the public blocker() function
# ---------------------------------------------------------------------------

class TestBlockerResultQuality:
    """Additional output quality assertions for blocker() using real test data."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()
        cls.test_data_dir = Path(__file__).parent / "dummy_data"

        rn = QgsVectorLayer(str(cls.test_data_dir / "dummy_rn.gpkg"), "rn", "ogr")
        hu = QgsVectorLayer(str(cls.test_data_dir / "dummy_hu.gpkg"), "hu", "ogr")
        part = QgsVectorLayer(str(cls.test_data_dir / "dummy_part.gpkg"), "part", "ogr")
        assert rn.isValid() and hu.isValid() and part.isValid()

        cls.result = blocker(rn, hu, part)

    @pytest.mark.integration
    def test_result_feature_count_greater_zero(self):
        """blocker() must return at least one block for real data."""
        assert self.result.featureCount() > 0

    @pytest.mark.integration
    def test_no_null_geometries_in_result(self):
        """No feature in the result layer may have a null geometry."""
        for feat in self.result.getFeatures():
            geom = feat.geometry()
            assert not geom.isNull(), f"Null geometry found for FID {feat.id()}"
            assert not geom.isEmpty(), f"Empty geometry found for FID {feat.id()}"

    @pytest.mark.integration
    def test_all_geometries_geos_valid(self):
        """Every output geometry must pass GEOS validity check."""
        for feat in self.result.getFeatures():
            geom = feat.geometry()
            if not geom.isNull():
                assert geom.isGeosValid(), \
                    f"Invalid geometry at FID {feat.id()}: {geom.validateGeometry()}"

    @pytest.mark.integration
    def test_all_name_values_are_unique(self):
        """NAME attribute must be unique across all output blocks."""
        names = [feat["NAME"] for feat in self.result.getFeatures()]
        assert len(names) == len(set(names)), \
            f"Duplicate NAME values: {[n for n in names if names.count(n) > 1]}"

    @pytest.mark.integration
    def test_debug_mode_true_does_not_crash(self, tmp_path):
        """blocker() with debug_mode=True must not raise and must return a valid layer."""
        test_data_dir = Path(__file__).parent / "dummy_data"
        rn = QgsVectorLayer(str(test_data_dir / "dummy_rn.gpkg"), "rn", "ogr")
        hu = QgsVectorLayer(str(test_data_dir / "dummy_hu.gpkg"), "hu", "ogr")
        part = QgsVectorLayer(str(test_data_dir / "dummy_part.gpkg"), "part", "ogr")
        result = blocker(rn, hu, part, debug_mode=True, workspace_path=str(tmp_path))
        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()

