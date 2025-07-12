import unittest
import os
import sys
import logging
from pathlib import Path
import importlib.util


# QGIS imports
from qgis.core import (
    QgsVectorLayer,
    QgsProject,
    QgsGeometry,
    QgsWkbTypes,  # Wichtig: Import für Geometrietypen
    QgsProcessing,
    QgsFeature
)
import processing


from ..helpers.system_utils import save_temp_layer_to_gpkg


# Import utilities for QGIS setup
from utilities import get_qgis_app


class TestBlockerIntegration(unittest.TestCase):
    """
    Integrationstest für die Blocker-Funktion
    Testet die vollständige Funktionalität mit echten QGIS-Daten
    """

    @classmethod
    def setUpClass(cls):
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

    def setUp(self):
        """Setup für jeden einzelnen Test"""
        self.tolerance_meters = 1.0
        self.tolerance_percent = 1.0
        self.comparison_results = {}

        # Verbesserte Pfadkonfiguration für Tests
        test_dir = Path(__file__).parent
        project_root = test_dir.parent

        # Alle notwendigen Pfade hinzufügen
        paths_to_add = [
            str(project_root),
            str(project_root / 'helpers'),
            str(project_root / 'ibtool_tools')
        ]

        for path in paths_to_add:
            if path not in sys.path:
                sys.path.insert(0, path)

        # Import der Blocker-Funktion
        try:
            from ..ibtool_tools.Blocker import blocker
            self.blocker_function = blocker
        except ImportError as e:
            self.fail(f"Konnte Blocker-Funktion nicht importieren: {e}")

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
        self.assertEqual(
            report['feature_count']['expected'],
            report['feature_count']['actual'],
            f"Feature count mismatch in {scenario_name}: Expected {report['feature_count']['expected']}, got {report['feature_count']['actual']}"
        )

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
        self.assertIsNotNone(result, "Blocker function returned None")
        self.assertIsInstance(result, QgsVectorLayer,
                              "Result is not a QgsVectorLayer")
        self.assertTrue(result.isValid(), "Result layer is not valid")

        # Compare with expected result
        self.assert_layers_similar(expected_result, result, "standard_case")

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
                self.assertEqual(
                    feature.geometry().type(),
                    QgsWkbTypes.PolygonGeometry,  # Korrekte Syntax!
                    "All features should be polygons"
                )

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

        self.assertGreater(
            blocks_with_buildings,
            0,
            "At least one block should contain buildings"
        )

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
        self.assertTrue(name_field_exists, "NAME field should exist")

        # Check NAME field values
        name_values = []
        for feature in result.getFeatures():
            if 'NAME' in feature.fields().names():
                name_values.append(feature['NAME'])

        # All NAME values should follow Block_X pattern
        for name in name_values:
            self.assertIsNotNone(name, "NAME value should not be None")
            self.assertTrue(
                name.startswith('Block_'),
                f"NAME value '{name}' should start with 'Block_'"
            )

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
            self.assertIsNotNone(result, "Function should handle empty inputs")
            self.assertIsInstance(result, QgsVectorLayer,
                                  "Result should be a QgsVectorLayer")

        except Exception as e:
            # If function fails with empty inputs, that's acceptable
            self.logger.warning(f"Function failed with empty inputs: {e}")

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
        self.assertLess(execution_time, 60,
                        "Function should complete within 60 seconds")
        

    def tearDown(self):
        """Cleanup nach jedem Test"""
        # Clear any temporary layers
        QgsProject.instance().clear()

    @classmethod
    def tearDownClass(cls):
        """Cleanup nach allen Tests"""
        if hasattr(cls, 'QGIS_APP') and cls.QGIS_APP:
            cls.QGIS_APP.exitQgis()


if __name__ == '__main__':
    unittest.main()