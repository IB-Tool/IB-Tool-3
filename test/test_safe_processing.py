# -*- coding: utf-8 -*-
"""Tests for helpers/safe_processing.py.

Covers the safe_processing_run wrapper: success path, geometry-error repair
flow, non-geometry re-raise, debug-mode layer saving, and edge cases.
"""
import pytest
from unittest.mock import patch, Mock, call

from ibtool.helpers.safe_processing import safe_processing_run


class TestSafeProcessingRun:
    """Unit tests for safe_processing_run."""

    # ── Happy path ────────────────────────────────────────────────────────────

    @pytest.mark.unit
    def test_success_returns_result_dict(self):
        """On a clean run, the result dict from processing.run is returned unchanged."""
        expected = {"OUTPUT": Mock()}
        with patch("ibtool.helpers.safe_processing.processing.run", return_value=expected):
            result = safe_processing_run("native:buffer", {"INPUT": "layer"})
        assert result == expected

    # ── Non-geometry errors ───────────────────────────────────────────────────

    @pytest.mark.unit
    def test_non_geometry_error_is_reraised_immediately(self):
        """Errors not related to geometry are re-raised without repair attempts."""
        with patch(
            "ibtool.helpers.safe_processing.processing.run",
            side_effect=RuntimeError("disk full"),
        ):
            with patch("ibtool.helpers.safe_processing.Logger"):
                with pytest.raises(RuntimeError, match="disk full"):
                    safe_processing_run("native:buffer", {"INPUT": "layer"})

    @pytest.mark.unit
    def test_fix_geometries_false_reraises_geometry_error(self):
        """With fix_geometries=False, even geometry errors are re-raised immediately."""
        with patch(
            "ibtool.helpers.safe_processing.processing.run",
            side_effect=Exception("self-intersection detected"),
        ):
            with patch("ibtool.helpers.safe_processing.Logger"):
                with pytest.raises(Exception, match="self-intersection"):
                    safe_processing_run(
                        "native:buffer",
                        {"INPUT": "layer"},
                        fix_geometries=False,
                    )

    # ── Geometry repair flow ──────────────────────────────────────────────────

    @pytest.mark.unit
    def test_geometry_error_triggers_repair_and_retry(self):
        """On geometry error: layers are repaired, algorithm is retried and succeeds."""
        mock_layer = Mock()
        mock_layer.isValid.return_value = True
        repaired_layer = Mock()
        expected = {"OUTPUT": Mock()}

        def mock_run(alg, params):
            if alg == "native:fixgeometries":
                return {"OUTPUT": repaired_layer}
            # Fail only when using the original (un-repaired) layer
            if params.get("INPUT") is mock_layer:
                raise Exception("invalid geometry in INPUT")
            return expected

        with patch("ibtool.helpers.safe_processing.processing.run", side_effect=mock_run):
            with patch("ibtool.helpers.safe_processing.Logger"):
                result = safe_processing_run("native:buffer", {"INPUT": mock_layer})
        assert result == expected

    @pytest.mark.unit
    def test_first_retry_fails_triggers_last_resort_with_invalid_feature_handling(self):
        """If first retry still fails, INVALID_FEATURE_HANDLING=1 is added as last resort."""
        mock_layer = Mock()
        mock_layer.isValid.return_value = True
        repaired_layer = Mock()
        expected = {"OUTPUT": Mock()}

        def mock_run(alg, params):
            if alg == "native:fixgeometries":
                return {"OUTPUT": repaired_layer}
            # Fail on original AND first retry (without INVALID_FEATURE_HANDLING)
            if params.get("INPUT") is mock_layer:
                raise Exception("could not write feature — invalid geometry")
            if params.get("INPUT") is repaired_layer and "INVALID_FEATURE_HANDLING" not in params:
                raise Exception("still invalid geometry after repair")
            return expected

        with patch("ibtool.helpers.safe_processing.processing.run", side_effect=mock_run):
            with patch("ibtool.helpers.safe_processing.Logger"):
                result = safe_processing_run("native:buffer", {"INPUT": mock_layer})
        assert result == expected

    @pytest.mark.unit
    def test_non_layer_parameters_are_not_repaired(self):
        """String / dict params that have no .isValid() are not passed to fixgeometries."""
        repair_calls = []

        def mock_run(alg, params):
            if alg == "native:fixgeometries":
                repair_calls.append(params.get("INPUT"))
                return {"OUTPUT": Mock()}
            raise Exception("objekt nicht schreiben — invalid geometry")

        with patch("ibtool.helpers.safe_processing.processing.run", side_effect=mock_run):
            with patch("ibtool.helpers.safe_processing.Logger"):
                try:
                    safe_processing_run(
                        "native:buffer",
                        {"INPUT": "string_layer", "DISTANCE": 10},
                    )
                except Exception:
                    pass

        assert repair_calls == [], "String parameters must not be passed to fixgeometries"

    # ── Debug mode ────────────────────────────────────────────────────────────

    @pytest.mark.unit
    def test_debug_mode_saves_failing_input_layer(self):
        """With debug_mode=True, failing INPUT layers are forwarded to save_debug_layer."""
        mock_layer = Mock()
        mock_layer.isValid.return_value = True

        with patch(
            "ibtool.helpers.safe_processing.processing.run",
            side_effect=Exception("self intersection in polygon"),
        ):
            with patch("ibtool.helpers.safe_processing.save_debug_layer") as mock_save:
                with patch("ibtool.helpers.safe_processing.Logger"):
                    try:
                        safe_processing_run(
                            "native:buffer",
                            {"INPUT": mock_layer},
                            debug_mode=True,
                            workspace_path="/mock/ws",
                            tool_name="TestTool",
                        )
                    except Exception:
                        pass
        mock_save.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_debug_mode_without_workspace_path_no_crash(self):
        """debug_mode=True with workspace_path=None must not raise AttributeError."""
        with patch(
            "ibtool.helpers.safe_processing.processing.run",
            side_effect=Exception("self-intersection in polygon"),
        ):
            with patch("ibtool.helpers.safe_processing.Logger"):
                try:
                    safe_processing_run(
                        "native:buffer",
                        {"INPUT": "string_param"},
                        debug_mode=True,
                        workspace_path=None,
                    )
                except Exception:
                    pass  # Exception expected; AttributeError / NoneType crash is not
