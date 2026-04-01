# -*- coding: utf-8 -*-
"""
Configuration Manager

Manages plugin configuration from CONFIG.ini file and provides default settings.
"""

import os
import configparser
from typing import Dict, Any
from dataclasses import dataclass, field
from .logger import Logger
from .qgis_defaults import DEFAULT_CRS_EPSG


@dataclass
class InputDataConfig:  # pylint: disable=too-many-instance-attributes
    """Configuration for input data paths and their last-known file checksums."""
    building_footprints_path: str = ""
    road_network_path: str = ""
    partitions_path: str = ""
    aux_layer_path: str = ""
    filter_file_path: str = ""
    # MD5 checksums computed at the time of the last successful path check.
    building_footprints_checksum: str = ""
    road_network_checksum: str = ""
    partitions_checksum: str = ""
    aux_layer_checksum: str = ""
    filter_file_checksum: str = ""


@dataclass
class ValidationCacheConfig:
    """Cached result of the last successful full validation run.

    Errors and warnings are stored as JSON-encoded lists so they survive a
    plugin restart and allow skipping re-validation when checksums match.
    """
    errors: str = "[]"    # JSON list[str]
    warnings: str = "[]"  # JSON list[str]
    context_signature: str = ""  # JSON object with validation-relevant UI state


@dataclass
class ProcessingConfig:  # pylint: disable=too-many-instance-attributes
    """Configuration for processing parameters."""
    # MST parameters
    road_length_threshold: float = 50.0
    coordinate_tolerance: float = 0.0001
    buffer_distance: float = 5.0

    # Footprint density parameters
    grid_size: float = 100.0
    min_building_count: int = 5
    density_threshold: float = 0.3

    # Clustering parameters
    min_cluster_size: int = 3
    max_distance: float = 200.0

    # Partition processing
    part_start: int = 1
    part_end: int = -1  # -1 means process all
    part_list: str = ""  # Comma-separated list of partition IDs

    # General processing
    crs_epsg: int = DEFAULT_CRS_EPSG  # Default EPSG code
    output_format: str = "gpkg"  # Persisted in config; runtime output is GeoPackage

    # Settlement analysis parameters (UI fields)
    min_overlap_blocks: float = 0.0
    global_footprint_density: float = 0.0
    min_area: float = 0.0
    min_patch_size: float = 0.0
    max_hole_size: float = 0.0
    max_gap_size: float = 0.0

    # Debug / run control
    debug_mode: bool = False
    delete_part_log: bool = True


@dataclass
class OutputConfig:
    """Configuration for output settings."""
    workspace_directory: str = ""
    output_directory: str = ""  # Historical key name: stores the full OutputPath file path
    output_prefix: str = "ibtool_result"
    auto_save: bool = True
    add_to_map: bool = True
    overwrite_existing: bool = False


@dataclass
class UIConfig:
    """Configuration for UI behavior."""
    auto_load_last_used: bool = True
    show_progress_details: bool = True
    log_level: str = "INFO"  # CRITICAL, WARNING, INFO, SUCCESS
    log_directory: str = ""
    remember_window_size: bool = True


@dataclass
class PluginConfig:
    """Complete plugin configuration."""
    input_data: InputDataConfig
    processing: ProcessingConfig
    output: OutputConfig
    ui: UIConfig  # pylint: disable=invalid-name
    validation_cache: ValidationCacheConfig = field(default_factory=ValidationCacheConfig)


class ConfigManager:
    """Manages plugin configuration loading and saving."""

    CONFIG_FILENAME = "CONFIG.ini"

    def __init__(self, plugin_root_dir: str):
        """
        Initialize configuration manager.

        Args:
            plugin_root_dir: Root directory of the plugin
        """
        self.plugin_root_dir = plugin_root_dir
        self.config_file_path = os.path.join(plugin_root_dir, self.CONFIG_FILENAME)
        self.config = self._create_default_config()
        self._load_config_if_exists()

    def _create_default_config(self) -> PluginConfig:
        """Create default configuration."""
        # Set default paths relative to plugin directory
        default_log_dir = os.path.join(self.plugin_root_dir, "logs")
        default_workspace = os.path.join(os.path.expanduser("~"), "ibtool_workspace")

        return PluginConfig(
            input_data=InputDataConfig(),
            processing=ProcessingConfig(),
            output=OutputConfig(
                workspace_directory=default_workspace
            ),
            ui=UIConfig(
                log_directory=default_log_dir
            ),
            validation_cache=ValidationCacheConfig(),
        )

    def _load_config_if_exists(self) -> None:
        """Load configuration from CONFIG.ini if it exists."""
        if os.path.exists(self.config_file_path):
            try:
                self.load_config()
            except (configparser.Error, OSError, ValueError) as exc:
                Logger.log(f"Could not load CONFIG.ini: {exc}", level="WARNING")
                Logger.log("Using default configuration instead.", level="WARNING")

    def load_config(self) -> None:  # pylint: disable=too-many-statements
        """Load configuration from CONFIG.ini file."""
        if not os.path.exists(self.config_file_path):
            raise FileNotFoundError(f"Config file not found: {self.config_file_path}")

        config_parser = configparser.ConfigParser()
        config_parser.read(self.config_file_path, encoding='utf-8')

        # Load input data configuration
        if config_parser.has_section('INPUT_DATA'):
            section = config_parser['INPUT_DATA']
            self.config.input_data.building_footprints_path = section.get('building_footprints_path', '')
            self.config.input_data.road_network_path = section.get('road_network_path', '')
            self.config.input_data.partitions_path = section.get('partitions_path', '')
            self.config.input_data.aux_layer_path = section.get('aux_layer_path', '')
            self.config.input_data.filter_file_path = section.get('filter_file_path', '')
            self.config.input_data.building_footprints_checksum = section.get('building_footprints_checksum', '')
            self.config.input_data.road_network_checksum = section.get('road_network_checksum', '')
            self.config.input_data.partitions_checksum = section.get('partitions_checksum', '')
            self.config.input_data.aux_layer_checksum = section.get('aux_layer_checksum', '')
            self.config.input_data.filter_file_checksum = section.get('filter_file_checksum', '')

        # Load validation cache
        if config_parser.has_section('VALIDATION_CACHE'):
            section = config_parser['VALIDATION_CACHE']
            self.config.validation_cache.errors = section.get('errors', '[]')
            self.config.validation_cache.warnings = section.get('warnings', '[]')
            self.config.validation_cache.context_signature = section.get(
                'context_signature', ''
            )

        # Load processing configuration
        if config_parser.has_section('PROCESSING'):
            section = config_parser['PROCESSING']
            self.config.processing.road_length_threshold = section.getfloat('road_length_threshold', 50.0)
            self.config.processing.coordinate_tolerance = section.getfloat('coordinate_tolerance', 0.0001)
            self.config.processing.buffer_distance = section.getfloat('buffer_distance', 5.0)
            self.config.processing.grid_size = section.getfloat('grid_size', 100.0)
            self.config.processing.min_building_count = section.getint('min_building_count', 5)
            self.config.processing.density_threshold = section.getfloat('density_threshold', 0.3)
            self.config.processing.min_cluster_size = section.getint('min_cluster_size', 3)
            self.config.processing.max_distance = section.getfloat('max_distance', 200.0)
            self.config.processing.crs_epsg = section.getint('crs_epsg', DEFAULT_CRS_EPSG)
            self.config.processing.output_format = section.get('output_format', 'gpkg')
            self.config.processing.part_start = section.getint('part_start', 1)
            self.config.processing.part_end = section.getint('part_end', -1)
            self.config.processing.part_list = section.get('part_list', '')
            self.config.processing.min_overlap_blocks = section.getfloat('min_overlap_blocks', 0.0)
            self.config.processing.global_footprint_density = section.getfloat('global_footprint_density', 0.0)
            self.config.processing.min_area = section.getfloat('min_area', 0.0)
            self.config.processing.min_patch_size = section.getfloat('min_patch_size', 0.0)
            self.config.processing.max_hole_size = section.getfloat('max_hole_size', 0.0)
            self.config.processing.max_gap_size = section.getfloat('max_gap_size', 0.0)
            self.config.processing.debug_mode = section.getboolean('debug_mode', False)
            self.config.processing.delete_part_log = section.getboolean('delete_part_log', True)

        # Load output configuration
        if config_parser.has_section('OUTPUT'):
            section = config_parser['OUTPUT']
            self.config.output.workspace_directory = section.get('workspace_directory', '')
            self.config.output.output_directory = section.get('output_directory', '')
            self.config.output.output_prefix = section.get('output_prefix', 'ibtool_result')
            self.config.output.auto_save = section.getboolean('auto_save', True)
            self.config.output.add_to_map = section.getboolean('add_to_map', True)
            self.config.output.overwrite_existing = section.getboolean('overwrite_existing', False)

        # Load UI configuration
        if config_parser.has_section('UI'):
            section = config_parser['UI']
            self.config.ui.auto_load_last_used = section.getboolean('auto_load_last_used', True)
            self.config.ui.show_progress_details = section.getboolean('show_progress_details', True)
            self.config.ui.log_level = section.get('log_level', 'INFO')
            self.config.ui.log_directory = section.get('log_directory', '')
            self.config.ui.remember_window_size = section.getboolean('remember_window_size', True)

    def save_config(self) -> None:
        """Save current configuration to CONFIG.ini file."""
        config_parser = configparser.ConfigParser()

        # Add input data section
        config_parser['INPUT_DATA'] = {
            'building_footprints_path': self.config.input_data.building_footprints_path,
            'road_network_path': self.config.input_data.road_network_path,
            'partitions_path': self.config.input_data.partitions_path,
            'aux_layer_path': self.config.input_data.aux_layer_path,
            'filter_file_path': self.config.input_data.filter_file_path,
            'building_footprints_checksum': self.config.input_data.building_footprints_checksum,
            'road_network_checksum': self.config.input_data.road_network_checksum,
            'partitions_checksum': self.config.input_data.partitions_checksum,
            'aux_layer_checksum': self.config.input_data.aux_layer_checksum,
            'filter_file_checksum': self.config.input_data.filter_file_checksum,
        }

        # Add processing section
        config_parser['PROCESSING'] = {
            'road_length_threshold': str(self.config.processing.road_length_threshold),
            'coordinate_tolerance': str(self.config.processing.coordinate_tolerance),
            'buffer_distance': str(self.config.processing.buffer_distance),
            'grid_size': str(self.config.processing.grid_size),
            'min_building_count': str(self.config.processing.min_building_count),
            'density_threshold': str(self.config.processing.density_threshold),
            'min_cluster_size': str(self.config.processing.min_cluster_size),
            'max_distance': str(self.config.processing.max_distance),
            'crs_epsg': str(self.config.processing.crs_epsg),
            'output_format': self.config.processing.output_format,
            'part_start': str(self.config.processing.part_start),
            'part_end': str(self.config.processing.part_end),
            'part_list': self.config.processing.part_list,
            'min_overlap_blocks': str(self.config.processing.min_overlap_blocks),
            'global_footprint_density': str(self.config.processing.global_footprint_density),
            'min_area': str(self.config.processing.min_area),
            'min_patch_size': str(self.config.processing.min_patch_size),
            'max_hole_size': str(self.config.processing.max_hole_size),
            'max_gap_size': str(self.config.processing.max_gap_size),
            'debug_mode': str(self.config.processing.debug_mode),
            'delete_part_log': str(self.config.processing.delete_part_log),
        }

        # Add output section
        config_parser['OUTPUT'] = {
            'workspace_directory': self.config.output.workspace_directory,
            'output_directory': self.config.output.output_directory,
            'output_prefix': self.config.output.output_prefix,
            'auto_save': str(self.config.output.auto_save),
            'add_to_map': str(self.config.output.add_to_map),
            'overwrite_existing': str(self.config.output.overwrite_existing)
        }

        # Add UI section
        config_parser['UI'] = {
            'auto_load_last_used': str(self.config.ui.auto_load_last_used),
            'show_progress_details': str(self.config.ui.show_progress_details),
            'log_level': self.config.ui.log_level,
            'log_directory': self.config.ui.log_directory,
            'remember_window_size': str(self.config.ui.remember_window_size)
        }

        # Add validation cache section
        config_parser['VALIDATION_CACHE'] = {
            'errors': self.config.validation_cache.errors,
            'warnings': self.config.validation_cache.warnings,
            'context_signature': self.config.validation_cache.context_signature,
        }

        # Write to file
        with open(self.config_file_path, 'w', encoding='utf-8') as config_file:
            config_parser.write(config_file)

    def create_example_config(self) -> None:
        """Create an example CONFIG.ini file with comments."""
        example_content = """# IBTool Configuration File
# This file allows you to pre-configure input paths and processing parameters
# Remove the # at the beginning of lines to activate settings

[INPUT_DATA]
# Paths to input data files (use forward slashes or double backslashes)
# building_footprints_path = C:/data/buildings.shp
# road_network_path = C:/data/streets.shp
# partitions_path = C:/data/partitions.shp
# aux_layer_path = C:/data/auxiliary.shp
# filter_file_path = C:/data/filter.txt

[PROCESSING]
# Processing parameters
road_length_threshold = 50.0
coordinate_tolerance = 0.0001
buffer_distance = 5.0
grid_size = 100.0
min_building_count = 5
density_threshold = 0.3
min_cluster_size = 3
max_distance = 200.0
crs_epsg = 25832
output_format = gpkg

[OUTPUT]
# Output settings
# workspace_directory = C:/Users/{username}/ibtool_workspace
output_prefix = ibtool_result
auto_save = True
add_to_map = True
overwrite_existing = False

[UI]
# User interface settings
auto_load_last_used = True
show_progress_details = True
log_level = INFO
# log_directory =
remember_window_size = True
"""

        with open(self.config_file_path, 'w', encoding='utf-8') as config_file:
            config_file.write(example_content)

    def get_config(self) -> PluginConfig:
        """Get current configuration."""
        return self.config

    def update_config(self, **kwargs) -> None:
        """Update configuration with new values."""
        for section_name, section_data in kwargs.items():
            if hasattr(self.config, section_name):
                section = getattr(self.config, section_name)
                for key, value in section_data.items():
                    if hasattr(section, key):
                        setattr(section, key, value)

    def validate_paths(self) -> Dict[str, bool]:
        """
        Validate that configured paths exist.

        Returns:
            Dictionary with path validity status
        """
        paths_status = {}

        # Check input data paths
        input_paths = {
            'building_footprints': self.config.input_data.building_footprints_path,
            'road_network': self.config.input_data.road_network_path,
            'partitions': self.config.input_data.partitions_path,
            'aux_layer': self.config.input_data.aux_layer_path,
            'filter_file': self.config.input_data.filter_file_path
        }

        for name, path in input_paths.items():
            if path:  # Only check non-empty paths
                paths_status[name] = os.path.exists(path)
            else:
                paths_status[name] = None  # Path not configured

        # Check output directories
        if self.config.output.workspace_directory:
            paths_status['workspace_directory'] = os.path.exists(self.config.output.workspace_directory)
        else:
            paths_status['workspace_directory'] = None

        if self.config.output.output_directory:
            paths_status['output_directory'] = os.path.exists(self.config.output.output_directory)
        else:
            paths_status['output_directory'] = None

        if self.config.ui.log_directory:
            paths_status['log_directory'] = os.path.exists(self.config.ui.log_directory)
        else:
            paths_status['log_directory'] = None

        return paths_status

    def get_missing_paths(self) -> list:
        """Get list of configured but missing paths."""
        paths_status = self.validate_paths()
        return [name for name, exists in paths_status.items() if exists is False]

    def config_exists(self) -> bool:
        """Check if CONFIG.ini exists."""
        return os.path.exists(self.config_file_path)

    def apply_to_ui_elements(self, ui_elements: Dict[str, Any]) -> None:
        """
        Apply configuration to UI elements.

        Args:
            ui_elements: Dictionary mapping config keys to UI elements
        """
        # Apply input data paths
        input_mapping = {
            'building_footprints_path': 'HuPath',
            'road_network_path': 'RnPath',
            'partitions_path': 'PartPath',
            'aux_layer_path': 'AuxPath',
            'filter_file_path': 'FilterPath'
        }

        for config_key, ui_key in input_mapping.items():
            if ui_key in ui_elements:
                path = getattr(self.config.input_data, config_key)
                if path and hasattr(ui_elements[ui_key], 'setText'):
                    ui_elements[ui_key].setText(path)

        # Apply workspace directory
        if 'WorkspacePath' in ui_elements and self.config.output.workspace_directory:
            if hasattr(ui_elements['WorkspacePath'], 'setText'):
                ui_elements['WorkspacePath'].setText(self.config.output.workspace_directory)

        # Apply output directory (overrides workspace if set)
        if 'OutputPath' in ui_elements and self.config.output.output_directory:
            if hasattr(ui_elements['OutputPath'], 'setText'):
                ui_elements['OutputPath'].setText(self.config.output.output_directory)

        # Apply log directory
        if 'LogDirPath' in ui_elements and self.config.ui.log_directory:
            if hasattr(ui_elements['LogDirPath'], 'setText'):
                ui_elements['LogDirPath'].setText(self.config.ui.log_directory)

    def get_effective_output_directory(self) -> str:
        """Get the effective output directory (output_directory if set, otherwise workspace_directory)."""
        return self.config.output.output_directory or self.config.output.workspace_directory

    def get_effective_log_directory(self) -> str:
        """Get the effective log directory (ui.log_directory if set, otherwise default logs directory)."""
        if self.config.ui.log_directory:
            return self.config.ui.log_directory
        return os.path.join(self.plugin_root_dir, "logs")

    def get_processing_parameters(self) -> Dict[str, Any]:
        """Get processing parameters as dictionary for algorithms."""
        return {
            'road_length_threshold': self.config.processing.road_length_threshold,
            'coordinate_tolerance': self.config.processing.coordinate_tolerance,
            'buffer_distance': self.config.processing.buffer_distance,
            'grid_size': self.config.processing.grid_size,
            'min_building_count': self.config.processing.min_building_count,
            'density_threshold': self.config.processing.density_threshold,
            'min_cluster_size': self.config.processing.min_cluster_size,
            'max_distance': self.config.processing.max_distance,
            'part_start': self.config.processing.part_start,
            'part_end': self.config.processing.part_end,
            'part_list': self.config.processing.part_list,
            'crs_epsg': self.config.processing.crs_epsg,
            'output_format': self.config.processing.output_format,
            'min_overlap_blocks': self.config.processing.min_overlap_blocks,
            'global_footprint_density': self.config.processing.global_footprint_density,
            'min_area': self.config.processing.min_area,
            'min_patch_size': self.config.processing.min_patch_size,
            'max_hole_size': self.config.processing.max_hole_size,
            'max_gap_size': self.config.processing.max_gap_size,
        }
