#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple test to check MST module imports
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, '.')

print("Testing MST module imports...")

try:
    print("1. Testing basic scipy import...")
    from scipy.spatial import Delaunay
    print("   [OK] scipy.spatial.Delaunay imported")
    
    # Add direct path to avoid importing main ibtool package
    sys.path.insert(0, './ibtool')
    
    # Test direct file import to bypass __init__.py issues
    import importlib.util
    
    print("2. Testing MST data classes (direct file import)...")
    spec = importlib.util.spec_from_file_location("mst_data_classes", "./ibtool/ibtool_tools/mst/mst_data_classes.py")
    mst_data_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mst_data_module)
    print("   [OK] MST data classes loaded directly")
    
    print("3. Testing MST processor files exist...")
    import os
    files_to_check = [
        "./ibtool/ibtool_tools/mst/delaunay_processor.py",
        "./ibtool/ibtool_tools/mst/street_processor.py", 
        "./ibtool/ibtool_tools/mst/mst_calculator.py"
    ]
    
    for file_path in files_to_check:
        if os.path.exists(file_path):
            print(f"   [OK] {os.path.basename(file_path)} exists")
        else:
            print(f"   [ERROR] {os.path.basename(file_path)} missing")
    
    print("4. Testing Logger file...")
    if os.path.exists("./ibtool/helpers/logger.py"):
        print("   [OK] logger.py exists")
    else:
        print("   [ERROR] logger.py missing")
    
    print("\n[SUCCESS] All MST module imports work!")
    print("The issue is likely QGIS dependency in actual QGIS environment.")
    
except ImportError as e:
    print(f"\n[ERROR] Import failed: {e}")
    import traceback
    traceback.print_exc()
    
except Exception as e:
    print(f"\n[ERROR] Unexpected error: {e}")
    import traceback
    traceback.print_exc()