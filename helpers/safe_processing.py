# -*- coding: utf-8 -*-
"""Safe wrapper for QGIS processing.run with geometry repair and debug support."""
from qgis.core import QgsProcessing
from qgis import processing

from .logger import Logger
from .debug_utils import save_debug_layer


def safe_processing_run(algorithm_name, parameters, fix_geometries=True,
                        debug_mode=False, workspace_path=None, tool_name=""):
    """Safe wrapper for processing.run with automatic geometry repair on failure.

    On a geometry-related exception the function attempts to repair all input
    layers via ``native:fixgeometries`` and retries the algorithm. If the retry
    also fails, ``INVALID_FEATURE_HANDLING=1`` is added as a last resort to
    skip invalid features. Non-geometry exceptions are re-raised immediately.

    When ``debug_mode`` is active, every failing input layer is saved as a
    numbered error file (``_err`` suffix) for post-mortem analysis.

    Args:
        algorithm_name: Name of the QGIS processing algorithm to run.
        parameters: Parameter dictionary for the algorithm.
        fix_geometries: If True, attempts to repair invalid geometries and
            retries the algorithm before raising an error.
        debug_mode: If True, saves failing input layers as debug files.
        workspace_path: Base path for debug output files.
        tool_name: Tool name used as the debug sub-folder prefix.
            Pass explicitly when debug_mode=True; e.g. ``"GapClose"``.

    Returns:
        Result dictionary returned by processing.run.

    Raises:
        Exception: Re-raises the original exception if the error is not
            geometry-related or if all repair attempts fail.
    """
    try:
        return processing.run(algorithm_name, parameters)
    except Exception as e:
        error_msg = str(e).lower()
        geometry_error_hints = [
            'ungültige geometrie', 'invalid geometry',
            'objekt nicht schreiben', 'could not write',
            'self-intersection', 'self intersection',
        ]
        is_geometry_error = any(hint in error_msg for hint in geometry_error_hints)

        # Save failing input layers as debug files for post-mortem analysis
        if debug_mode and workspace_path:
            for key, value in parameters.items():
                if key in ['INPUT', 'OVERLAY', 'INTERSECT'] and hasattr(value, 'isValid'):
                    step = f"{algorithm_name.replace(':', '_')}_{key}"
                    save_debug_layer(value, tool_name, step, workspace_path, is_error=True)

        if fix_geometries and is_geometry_error:
            Logger.log(
                f"Geometry error in {algorithm_name}, attempting repair: {e}",
                level="WARNING"
            )
            # Attempt to repair all input layers before retrying
            repaired_params = parameters.copy()
            for key, value in parameters.items():
                if key in ['INPUT', 'OVERLAY', 'INTERSECT'] and hasattr(value, 'isValid'):
                    try:
                        repaired_layer = processing.run("native:fixgeometries", {
                            'INPUT': value,
                            'METHOD': 1,
                            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                        })['OUTPUT']
                        repaired_params[key] = repaired_layer
                    except Exception:
                        pass  # Keep original layer if repair fails

            # Retry with repaired geometries
            try:
                return processing.run(algorithm_name, repaired_params)
            except Exception as e2:
                Logger.log(
                    f"Retry after repair failed for {algorithm_name}: {e2}",
                    level="WARNING"
                )
                # Last resort: set INVALID_FEATURE_HANDLING=1 to skip invalid features
                if 'INVALID_FEATURE_HANDLING' not in repaired_params:
                    repaired_params['INVALID_FEATURE_HANDLING'] = 1
                return processing.run(algorithm_name, repaired_params)
        else:
            Logger.log(str(e), level="CRITICAL")
            raise e
