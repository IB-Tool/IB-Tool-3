# -*- coding: utf-8 -*-
"""Tests for helpers/processing_context.py.

The module provides one shared QgsProcessingContext per pipeline section
(e.g. per partition) so that processing.run() does not rebuild the context —
expression scopes, encoding, settings — for every call (~3 ms each, ~24 % of
the total runtime on the sample data).
"""
from unittest.mock import patch

import pytest
from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingContext,
    QgsVectorLayer,
)

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from qgis import processing  # noqa: E402

from ibtool.helpers.processing_context import (  # noqa: E402
    current_processing_context,
    heartbeat,
    shared_processing_context,
    ui_heartbeat,
)


def _point_layer(n: int = 3) -> QgsVectorLayer:
    layer = QgsVectorLayer("Point?crs=EPSG:25833", "pts", "memory")
    feats = []
    for i in range(n):
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(i * 10, 0)))
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    return layer


class TestSharedProcessingContext:
    """Scoping behaviour of shared_processing_context / current_processing_context."""

    @pytest.mark.unit
    def test_no_active_context_returns_none(self):
        """Outside a with-block there is no shared context (processing.run builds its own)."""
        assert current_processing_context() is None

    @pytest.mark.unit
    def test_inside_block_returns_same_context(self):
        with shared_processing_context() as ctx:
            assert isinstance(ctx, QgsProcessingContext)
            assert current_processing_context() is ctx
            assert current_processing_context() is ctx

    @pytest.mark.unit
    def test_context_is_reset_after_block(self):
        with shared_processing_context():
            pass
        assert current_processing_context() is None

    @pytest.mark.unit
    def test_context_is_reset_after_exception(self):
        with pytest.raises(RuntimeError):
            with shared_processing_context():
                raise RuntimeError("boom")
        assert current_processing_context() is None

    @pytest.mark.unit
    def test_each_block_gets_a_fresh_context(self):
        """One context per partition: consecutive blocks must not share a context."""
        with shared_processing_context() as first:
            pass
        with shared_processing_context() as second:
            pass
        assert first is not second

    @pytest.mark.unit
    def test_nested_block_restores_outer_context(self):
        with shared_processing_context() as outer:
            with shared_processing_context() as inner:
                assert current_processing_context() is inner
            assert current_processing_context() is outer

    @pytest.mark.unit
    def test_context_has_feedback_for_its_lifetime(self):
        """The context owns a feedback object, so processing.run never attaches a
        short-lived per-call feedback to it (dangling pointer)."""
        with shared_processing_context() as ctx:
            assert ctx.feedback() is not None


class TestSharedContextWithProcessing:
    """Real processing.run calls with the shared context."""

    @pytest.mark.integration
    def test_output_layers_are_handed_to_caller(self):
        """Result layers are transferred out of the context (no accumulation)."""
        with shared_processing_context() as ctx:
            for _ in range(5):
                result = processing.run("native:centroids", {
                    'INPUT': _point_layer(),
                    'ALL_PARTS': False,
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
                }, context=current_processing_context())['OUTPUT']
                assert isinstance(result, QgsVectorLayer)
                assert result.featureCount() == 3
            assert ctx.temporaryLayerStore().count() == 0

    @pytest.mark.integration
    def test_processing_run_does_not_create_contexts_inside_block(self):
        """With the shared context passed, createContext() is not called per run."""
        target = "processing.core.Processing.dataobjects.createContext"
        with shared_processing_context():
            with patch(target) as create_ctx:
                for _ in range(3):
                    processing.run("native:centroids", {
                        'INPUT': _point_layer(),
                        'ALL_PARTS': False,
                        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
                    }, context=current_processing_context())
        create_ctx.assert_not_called()


class TestUiHeartbeat:
    """ui_heartbeat(): keeps the QGIS UI responsive during long processing.

    The callback (in the plugin: processEvents + cancel check) is invoked from
    current_processing_context() — i.e. before every processing.run() — and
    from explicit heartbeat() calls in long Python loops, at most every
    *min_interval* seconds.
    """

    @pytest.mark.unit
    def test_no_callback_outside_block(self):
        calls = []
        heartbeat()
        current_processing_context()
        assert calls == []

    @pytest.mark.unit
    def test_current_processing_context_ticks_inside_block(self):
        calls = []
        with ui_heartbeat(lambda: calls.append(1), min_interval=0):
            current_processing_context()
            current_processing_context()
        assert len(calls) == 2

    @pytest.mark.unit
    def test_explicit_heartbeat_ticks_inside_block(self):
        calls = []
        with ui_heartbeat(lambda: calls.append(1), min_interval=0):
            heartbeat()
        assert calls == [1]

    @pytest.mark.unit
    def test_callback_is_throttled(self):
        """At most one callback per min_interval."""
        calls = []
        clock = iter([0.0, 0.05, 0.1, 0.25, 0.3, 0.6])
        with patch("ibtool.helpers.processing_context.time.monotonic",
                   side_effect=lambda: next(clock)):
            with ui_heartbeat(lambda: calls.append(1), min_interval=0.2):
                for _ in range(6):
                    heartbeat()
        # ticks at t=0.0 (first), 0.25, 0.6
        assert len(calls) == 3

    @pytest.mark.unit
    def test_exception_from_callback_propagates_and_block_resets(self):
        class Cancelled(BaseException):
            pass

        def cancel():
            raise Cancelled()

        with pytest.raises(Cancelled):
            with ui_heartbeat(cancel, min_interval=0):
                heartbeat()
        calls = []
        heartbeat()                      # no longer active
        assert calls == []

    @pytest.mark.unit
    def test_ticks_inside_shared_context_block(self):
        """Heartbeat and shared context are independent and can be combined."""
        calls = []
        with ui_heartbeat(lambda: calls.append(1), min_interval=0):
            with shared_processing_context() as ctx:
                assert current_processing_context() is ctx
        assert calls == [1]
