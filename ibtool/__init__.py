# -*- coding: utf-8 -*-
"""
IBTool Package - Main package initialization

This package contains the core functionality of the IBTool QGIS Plugin
for settlement delineation based on building footprints.
"""

# Re-export main plugin class for backwards compatibility
from .ibtool import IBTool

__all__ = ['IBTool']
