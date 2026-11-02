# -*- coding: utf-8 -*-
"""The partition pipeline (steps 1–10 for one partition) without any UI.

Single implementation used by the sequential path (``IBTool``) and by the
worker processes (``ibtool/partition_worker.py``), so both compute exactly the
same. Progress is reported via callbacks instead of dialog updates.

Copyright: (C) 2026 by Oliver Harig
License: GNU General Public License v2 or later
"""
import os
from typing import Callable, Optional

from qgis import processing
from qgis.core import QgsProcessing

from .geometry_utils import select_and_save_by_location
from .logger import Logger as logger
from .processing_context import current_processing_context
from ..ibtool_tools.AddSingleBuilding import add_single_bdg
from ..ibtool_tools.Blocker import blocker
from ..ibtool_tools.CreateMST import calculate_mst
from ..ibtool_tools.EdgeCatch import edge_catch
from ..ibtool_tools.ErodeEmptyAreas import erode_empty_areas
from ..ibtool_tools.FootprintDensity import calc_footprint_density, identify_dense_blocks
from ..ibtool_tools.GapClose import gap_close
from ..ibtool_tools.ImportFilter import input_hu_filter
from ..ibtool_tools.MST_Clustering import mst_clustering
from ..ibtool_tools.PatchRemove import patch_remove

PHASES = {2: "Calculate Blocks", 3: "Apply Filter", 4: "Calculate MST", 5: "Clustering",
          6: "Erode Empty Areas", 7: "Close Gaps", 8: "Remove Patches"}
"""Phases reported during a partition (English; the UI translates them)."""

PHASE_PERCENT = {2: 10, 3: 20, 4: 35, 5: 50, 6: 70, 7: 80, 8: 90}
"""Progress within a partition at the start of each phase (percent)."""


def _report(progress: Optional[Callable[[int, str], None]], phase: int) -> None:
    """Call the progress callback (if any) for *phase*."""
    if progress:
        progress(phase, PHASES[phase])


def run_partition(  # pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
        part_name, layers, spatial_reference, workspace_path, debug_mode,
        global_footprint_density, params,
        progress: Optional[Callable[[int, str], None]] = None,
        on_selected: Optional[Callable[[int], None]] = None):
    """Run the delineation pipeline for one partition (see docs/how-it-works.md).

    Args:
        part_name: Partition identifier string (matches ``NAME`` field).
        layers: Dict with keys ``layer_part``, ``layer_hu``, ``layer_rn``,
            and ``aux_layers_line``.
        spatial_reference: QgsCoordinateReferenceSystem for all outputs.
        workspace_path: Workspace directory path (trailing slash).
        debug_mode: Whether to save intermediate debug layers.
        global_footprint_density: Pre-computed global density threshold.
        params: Numeric parameter dict from ``IBTool._parse_numeric_params()``,
            extended with ``input_filter`` (path string).
        progress: Optional ``callback(phase, phase_name)`` at the start of
            phases 2–8.
        on_selected: Optional ``callback(building_count)`` right after the
            building selection.

    Returns:
        Tuple ``(result_layer, building_count)``; *result_layer* is ``None``
        if the partition is skipped.
    """
    if debug_mode and workspace_path:
        part_workspace = os.path.join(workspace_path, "debug", f"PART_{part_name}")
    else:
        part_workspace = workspace_path

    sel_part_layer = processing.run(
        "native:extractbyexpression", {
            'INPUT': layers['layer_part'],
            'EXPRESSION': f"\"NAME\" = '{part_name}'",
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }, context=current_processing_context())['OUTPUT']

    hu_layer = select_and_save_by_location(layers['layer_hu'], sel_part_layer)
    anz_hu = hu_layer.featureCount()
    if on_selected:
        on_selected(anz_hu)

    if anz_hu < 10:
        logger.log(
            "Warning: No or less than 10 buildings selected in partition", 'WARNING')
        return None, anz_hu

    sel_strassen_layer = select_and_save_by_location(layers['layer_rn'], sel_part_layer)
    anz_strassen = sel_strassen_layer.featureCount()

    if anz_strassen < 5:
        logger.log(
            f"Warning: No or less than 5 roads selected in partition {part_name}",
            'WARNING')

    aux_lines_sel = select_and_save_by_location(layers['aux_layers_line'], sel_part_layer)

    logger.log(f"SelHU Count = {anz_hu}", 'SUCCESS')
    logger.log(f"SelStrassen Count = {anz_strassen}", 'SUCCESS')

    min_overlap_mst = calc_footprint_density(
        hu_layer, sel_strassen_layer, 100,
        global_footprint_density, 'local', params['min_bdg_count'],
        debug_mode=debug_mode, workspace_path=part_workspace)
    logger.log(f"Local building coverage = {min_overlap_mst}", 'SUCCESS')

    sel_hu_layer = processing.run("native:splitwithlines",
                                  {'INPUT': hu_layer,
                                   'LINES': sel_strassen_layer,
                                   'OUTPUT': 'memory:'
                                   }, context=current_processing_context())['OUTPUT']

    _report(progress, 2)
    blocks = blocker(aux_lines_sel, sel_hu_layer, sel_part_layer,
                     debug_mode=debug_mode, workspace_path=part_workspace)

    _report(progress, 3)
    hu_filter = input_hu_filter(
        sel_hu_layer, params['input_filter'], params['min_area'], 50, 200,
        debug_mode=debug_mode, workspace_path=part_workspace)
    blocks_dense = identify_dense_blocks(
        hu_filter, blocks, params['min_overlap_blocks'],
        debug_mode=debug_mode, workspace_path=part_workspace)
    hu_filter_sel = select_and_save_by_location(hu_filter, blocks_dense, [2], 0)

    _report(progress, 4)
    mst_layer = calculate_mst(hu_filter_sel, sel_strassen_layer, spatial_reference,
                              debug_mode=debug_mode, workspace_path=part_workspace)

    if mst_layer is None:
        logger.log(
            f"MST calculation failed for partition {part_name}, skipping", 'WARNING')
        return None, anz_hu

    _report(progress, 5)
    hu_cluster_output = mst_clustering(
        hu_filter_sel, mst_layer, spatial_reference,
        min_overlap_mst, debug_mode=debug_mode, workspace_path=part_workspace)

    add_sing_bdg = add_single_bdg(
        hu_filter_sel, hu_cluster_output, spatial_reference,
        part_workspace, debug_mode=debug_mode)

    rect_merged = processing.run("qgis:mergevectorlayers", {
        'LAYERS': [add_sing_bdg, hu_cluster_output],
        'CRS': spatial_reference,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, context=current_processing_context())['OUTPUT']

    snapped_rect = edge_catch(
        rect_merged, hu_filter_sel, sel_strassen_layer, blocks,
        spatial_reference, part_workspace, debug_mode=debug_mode)

    blocks_merge = processing.run("qgis:mergevectorlayers", {
        'LAYERS': [snapped_rect, blocks_dense],
        'CRS': spatial_reference,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, context=current_processing_context())['OUTPUT']

    _report(progress, 6)
    eroded = erode_empty_areas(
        blocks_merge, sel_hu_layer,
        workspace_path=part_workspace,
        debug_mode=debug_mode,
    )

    _report(progress, 7)
    gaps_closed = gap_close(
        eroded, blocks, params['max_hole_size'], params['max_gap_size'],
        spatial_reference, gap_dist=30,
        debug_mode=debug_mode, workspace_path=part_workspace)

    _report(progress, 8)
    patch_removed = patch_remove(
        gaps_closed, sel_hu_layer, spatial_reference, part_workspace,
        min_patch_size=params['min_patch_size'],
        min_bdg_count=params['min_bdg_count'],
        footprint_area_sum=6000,
        footprint_density_threshold=18,
        debug_mode=debug_mode)

    return patch_removed, anz_hu
