# -*- coding: utf-8 -*-
"""
Unit tests for CreateMST.py

Tests the main calculate_mst function and integration scenarios.
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# QGIS imports
from qgis.core import (
    QgsVectorLayer, QgsCoordinateReferenceSystem, QgsWkbTypes,
    QgsFeature, QgsGeometry, QgsPointXY, QgsProject
)

# Import utilities for QGIS setup
from .utilities import get_qgis_app
from .test_fixtures_mst import MSTTestFixtures

# Import the function to test
from ibtool.ibtool_tools.CreateMST import calculate_mst, CreateMST



class TestCreateMST:
    """Test suite for CreateMST.py main functionality."""

    @classmethod
    def setup_class(cls):
        """Setup QGIS application for all tests."""
        cls.qgis_app, cls.canvas, cls.iface, cls.parent = get_qgis_app()
        cls.fixtures = MSTTestFixtures()

    def test_calculate_mst_with_simple_buildings(self):
        """Test MST calculation with simple building layout."""
        # Create test layers
        building_layer = self.fixtures.create_simple_building_layer()
        street_layer = self.fixtures.create_simple_street_layer()
        crs = self.fixtures.create_test_crs()

        print(f"\nDEBUG: Building layer valid: {building_layer.isValid()}")
        print(f"DEBUG: Building layer features: {building_layer.featureCount()}")
        print(f"DEBUG: Street layer valid: {street_layer.isValid()}")
        print(f"DEBUG: Street layer features: {street_layer.featureCount()}")
        print(f"DEBUG: CRS: {crs.authid()}")

        # Detaillierte Debugging der MST-Berechnung
        mst_calculator = CreateMST()

        try:
            # Step 1: Test building centroids
            print("DEBUG: Step 1 - Extracting building centroids...")
            centroids_result = mst_calculator.delaunay_processor.extract_building_centroids(building_layer)
            print(f"DEBUG: Found {len(centroids_result.centroids)} centroids")

            if len(centroids_result.centroids) == 0:
                pytest.fail("No building centroids found!")

            # Step 2: Test triangulation
            print("DEBUG: Step 2 - Creating triangulation...")
            triangulation_edges = mst_calculator.delaunay_processor.create_triangulation(centroids_result)
            print(f"DEBUG: Created {len(triangulation_edges)} triangulation edges")

            # Step 3: Test street processing
            print("DEBUG: Step 3 - Processing streets...")
            street_result = mst_calculator.street_processor.process_streets(street_layer)
            print(f"DEBUG: Street processing complete. Removed {street_result.removed_street_count} streets")

            # Step 4: Test triangulation layer creation
            print("DEBUG: Step 4 - Creating triangulation layer...")
            triangulation_layer = mst_calculator.delaunay_processor.create_triangulation_layer(
                triangulation_edges, crs
            )
            print(f"DEBUG: Triangulation layer created with {triangulation_layer.featureCount()} features")

            # Step 5: Test edge filtering
            print("DEBUG: Step 5 - Filtering edges by streets...")
            filtered_edges = mst_calculator.delaunay_processor.filter_edges_by_streets(
                triangulation_layer, street_result.filtered_streets
            )
            print(f"DEBUG: {len(filtered_edges)} edges remaining after filtering")

            if len(filtered_edges) == 0:
                pytest.fail(
                    f"No triangulation edges remaining after street filtering. "
                    f"Triangulation features: {triangulation_layer.featureCount()}, "
                    f"Street features: {street_result.filtered_streets.featureCount()}"
                )

        except Exception as e:
            import traceback
            pytest.fail(f"Unexpected error during MST step-by-step debug: {e}\n{traceback.format_exc()}")

        # Execute MST calculation
        result = calculate_mst(building_layer, street_layer, crs)

        # Show detailed failure info if None
        if result is None:
            print("ERROR: calculate_mst returned None - check debug logs above")

        # Validate result - tests must fail properly, not skip
        assert result is not None, "calculate_mst should not return None - check debug output above"
        assert result.isValid(), "Returned layer should be valid"

        is_valid, message = self.fixtures.validate_mst_layer(result)
        assert is_valid, f"MST layer validation failed: {message}"

        # Check geometry type
        assert result.wkbType() == QgsWkbTypes.LineString, "MST should return LineString layer"

        # Check feature count (for 4 buildings, expect 3 MST edges)
        feature_count = result.featureCount()
        assert feature_count == 3, f"Expected 3 MST edges for 4 buildings, got {feature_count}"

        # Verify layer has weight field
        field_names = [field.name() for field in result.fields()]
        assert "weight" in field_names, "MST layer should have 'weight' field"

    def test_calculate_mst_with_empty_buildings(self):
        """Test MST calculation with empty building layer."""
        empty_building_layer = self.fixtures.create_empty_layer("Polygon")
        street_layer = self.fixtures.create_simple_street_layer()
        crs = self.fixtures.create_test_crs()

        # Should handle empty input gracefully
        result = calculate_mst(empty_building_layer, street_layer, crs)

        # Result could be None or empty layer - both are acceptable
        if result is not None:
            assert result.featureCount() == 0, "Empty input should produce empty or no MST"

    def test_calculate_mst_with_empty_streets(self):
        """Test MST calculation with empty street layer."""
        building_layer = self.fixtures.create_simple_building_layer()
        empty_street_layer = self.fixtures.create_empty_layer("LineString")
        crs = self.fixtures.create_test_crs()

        # Should still generate MST based on building positions
        result = calculate_mst(building_layer, empty_street_layer, crs)

        if result is not None:
            assert result.isValid(), "Returned layer should be valid"

    def test_calculate_mst_invalid_inputs(self):
        """Test MST calculation with invalid inputs."""
        building_layer = self.fixtures.create_simple_building_layer()
        street_layer = self.fixtures.create_simple_street_layer()
        crs = self.fixtures.create_test_crs()

        # Test with None inputs - should handle gracefully without crashing
        calculate_mst(None, street_layer, crs)
        calculate_mst(building_layer, None, crs)
        calculate_mst(building_layer, street_layer, None)

    def test_calculate_mst_single_building(self):
        """Test MST calculation with only one building."""
        crs = self.fixtures.create_test_crs()

        single_building_layer = QgsVectorLayer(f"Polygon?crs={crs.toWkt()}", "single", "memory")
        provider = single_building_layer.dataProvider()

        from qgis.PyQt.QtCore import QVariant
        from qgis.core import QgsField
        provider.addAttributes([QgsField("id", QVariant.Int)])
        single_building_layer.updateFields()

        feature = QgsFeature(single_building_layer.fields())
        points = [QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)]
        geometry = QgsGeometry.fromPolygonXY([points])
        feature.setGeometry(geometry)
        feature.setAttributes([1])
        provider.addFeatures([feature])

        street_layer = self.fixtures.create_simple_street_layer()
        result = calculate_mst(single_building_layer, street_layer, crs)

        # Single building should produce no MST edges
        if result is not None and result.isValid():
            assert result.featureCount() == 0, "Single building should produce no MST edges"

    @patch('ibtool.ibtool_tools.CreateMST.Logger')
    def test_calculate_mst_logging(self, mock_logger):
        """Logger.log is called with the correct warning when buildings layer is empty."""
        empty_building_layer = self.fixtures.create_empty_layer("Polygon")
        street_layer = self.fixtures.create_simple_street_layer()
        crs = self.fixtures.create_test_crs()

        result = calculate_mst(empty_building_layer, street_layer, crs)

        assert result is None, "Empty buildings should produce no MST"
        mock_logger.log.assert_called_once_with(
            "No building centroids found", level="WARNING"
        )

    # ------------------------------------------------------------------
    # Extended tests (STEP 9 — test-plan.md)
    # ------------------------------------------------------------------

    @pytest.mark.integration
    def test_mst_produces_n_minus_1_edges(self):
        """MST edge count equals number of buildings minus one (fundamental MST property)."""
        building_layer = self.fixtures.create_simple_building_layer()
        street_layer = self.fixtures.create_simple_street_layer()
        crs = self.fixtures.create_test_crs()

        result = calculate_mst(building_layer, street_layer, crs)

        assert result is not None, (
            "calculate_mst returned None — street filter removed all triangulation edges. "
            "Check test_calculate_mst_with_simple_buildings for a step-by-step diagnosis."
        )
        assert result.isValid(), "Returned layer must be valid"

        expected_edges = building_layer.featureCount() - 1
        assert result.featureCount() == expected_edges, (
            f"MST must have exactly n-1 edges. "
            f"Got {result.featureCount()}, expected {expected_edges} "
            f"(n={building_layer.featureCount()} buildings)"
        )

    @pytest.mark.integration
    def test_all_edge_weights_are_positive(self):
        """All edges in the MST layer carry a positive weight value."""
        building_layer = self.fixtures.create_simple_building_layer()
        street_layer = self.fixtures.create_simple_street_layer()
        crs = self.fixtures.create_test_crs()

        result = calculate_mst(building_layer, street_layer, crs)

        assert result is not None, (
            "calculate_mst returned None — street filter removed all triangulation edges"
        )

        field_names = [field.name() for field in result.fields()]
        assert "weight" in field_names, "MST layer must contain a 'weight' field"

        for feat in result.getFeatures():
            weight = feat["weight"]
            assert weight is not None, "weight field must not be NULL"
            assert weight > 0, (
                f"Every MST edge weight must be positive, got {weight}"
            )

    @pytest.mark.integration
    def test_output_layer_crs_matches_input(self):
        """Output layer CRS matches the CRS passed to calculate_mst."""
        building_layer = self.fixtures.create_simple_building_layer()
        street_layer = self.fixtures.create_simple_street_layer()
        crs = self.fixtures.create_test_crs()

        result = calculate_mst(building_layer, street_layer, crs)

        assert result is not None, (
            "calculate_mst returned None — street filter removed all triangulation edges"
        )
        assert result.crs().authid() == crs.authid(), (
            f"Output CRS must match input CRS. "
            f"Expected {crs.authid()}, got {result.crs().authid()}"
        )

    @pytest.mark.integration
    def test_with_complex_building_layout(self):
        """Handles a complex building layout with irregular shapes and sizes."""
        building_layer = self.fixtures.create_complex_building_layer()
        street_layer = self.fixtures.create_simple_street_layer()
        crs = self.fixtures.create_test_crs()

        result = calculate_mst(building_layer, street_layer, crs)

        assert result is not None, \
            "calculate_mst must not return None for the complex 4-building layout"
        assert result.isValid(), "Result layer must be valid"
        assert result.featureCount() > 0, \
            "Result layer must contain at least one edge"

        for feat in result.getFeatures():
            geom = feat.geometry()
            assert not geom.isNull(), "Edge geometry must not be null"
            assert not geom.isEmpty(), "Edge geometry must not be empty"
            assert geom.isGeosValid(), "Edge geometry must be GEOS-valid"

    @pytest.mark.integration
    def test_get_detailed_result_returns_mst_result_object(self):
        """get_detailed_result() returns a populated MSTResult with a valid mst_layer."""
        from ibtool.ibtool_tools.mst import MSTResult

        building_layer = self.fixtures.create_simple_building_layer()
        street_layer = self.fixtures.create_simple_street_layer()
        crs = self.fixtures.create_test_crs()

        creator = CreateMST()
        detailed = creator.get_detailed_result(building_layer, street_layer, crs)

        assert detailed is not None, (
            "get_detailed_result() returned None — street filter removed all triangulation edges"
        )
        assert isinstance(detailed, MSTResult), \
            f"get_detailed_result() must return an MSTResult, got {type(detailed)}"
        assert detailed.mst_layer is not None, \
            "MSTResult.mst_layer must not be None"
        assert detailed.mst_layer.isValid(), \
            "MSTResult.mst_layer must be a valid QgsVectorLayer"

    @pytest.mark.integration
    def test_output_geometries_are_geos_valid(self):
        """Every geometry in the MST output layer passes the GEOS validity check."""
        building_layer = self.fixtures.create_simple_building_layer()
        street_layer = self.fixtures.create_simple_street_layer()
        crs = self.fixtures.create_test_crs()

        result = calculate_mst(building_layer, street_layer, crs)

        assert result is not None, (
            "calculate_mst returned None — street filter removed all triangulation edges"
        )
        assert result.featureCount() > 0, \
            "Result layer must contain at least one edge"

        for feat in result.getFeatures():
            geom = feat.geometry()
            assert not geom.isNull(), \
                f"Feature {feat.id()}: geometry must not be null"
            assert not geom.isEmpty(), \
                f"Feature {feat.id()}: geometry must not be empty"
            assert geom.isGeosValid(), \
                f"Feature {feat.id()}: geometry must be GEOS-valid"
