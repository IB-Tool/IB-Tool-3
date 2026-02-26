#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test runner for MST functionality tests

Provides a convenient way to run all MST-related tests.
"""

import sys
import os
import pytest
from pathlib import Path


def run_mst_tests():
    """Run all MST-related tests."""
    
    # Get the test directory
    test_dir = Path(__file__).parent
    
    # Define MST test files
    mst_test_files = [
        'test_create_mst.py',
        'test_mst_components.py', 
        'test_mst_modules.py',
        'test_mst_performance_edge_cases.py'
    ]
    
    # Check which test files exist
    existing_files = []
    for test_file in mst_test_files:
        test_path = test_dir / test_file
        if test_path.exists():
            existing_files.append(str(test_path))
        else:
            print(f"Warning: Test file not found: {test_file}")
    
    if not existing_files:
        print("Error: No MST test files found!")
        return 1
        
    print(f"Running MST tests from {len(existing_files)} files...")
    
    # Configure pytest arguments
    pytest_args = [
        '-v',                    # Verbose output
        '--tb=short',           # Short traceback format
        '--strict-markers',     # Strict marker handling
        '-x',                   # Stop on first failure (optional)
        '--color=yes'           # Colored output
    ]
    
    # Add test files
    pytest_args.extend(existing_files)
    
    # Run tests
    exit_code = pytest.main(pytest_args)
    
    return exit_code


def run_specific_test_category(category):
    """Run specific category of MST tests."""
    
    test_dir = Path(__file__).parent
    
    category_files = {
        'integration': ['test_create_mst.py'],
        'unit': ['test_mst_components.py'],
        'modules': ['test_mst_modules.py'],
        'performance': ['test_mst_performance_edge_cases.py']
    }
    
    if category not in category_files:
        print(f"Error: Unknown test category '{category}'")
        print(f"Available categories: {', '.join(category_files.keys())}")
        return 1
        
    test_files = category_files[category]
    existing_files = []
    
    for test_file in test_files:
        test_path = test_dir / test_file
        if test_path.exists():
            existing_files.append(str(test_path))
            
    if not existing_files:
        print(f"Error: No test files found for category '{category}'")
        return 1
        
    print(f"Running {category} tests...")
    
    pytest_args = [
        '-v',
        '--tb=short',
        '--color=yes'
    ]
    pytest_args.extend(existing_files)
    
    exit_code = pytest.main(pytest_args)
    return exit_code


def run_tests_with_coverage():
    """Run MST tests with coverage reporting."""
    
    test_dir = Path(__file__).parent
    
    # MST test files
    mst_test_files = [
        'test_create_mst.py',
        'test_mst_components.py',
        'test_mst_modules.py', 
        'test_mst_performance_edge_cases.py'
    ]
    
    existing_files = [
        str(test_dir / f) for f in mst_test_files 
        if (test_dir / f).exists()
    ]
    
    if not existing_files:
        print("Error: No MST test files found!")
        return 1
        
    print("Running MST tests with coverage...")
    
    # Coverage configuration
    pytest_args = [
        '--cov=ibtool.ibtool_tools.CreateMST',
        '--cov=ibtool.ibtool_tools.mst',
        '--cov-report=html:htmlcov_mst',
        '--cov-report=term-missing',
        '--cov-fail-under=70',  # Require at least 70% coverage
        '-v',
        '--tb=short'
    ]
    pytest_args.extend(existing_files)
    
    exit_code = pytest.main(pytest_args)
    
    if exit_code == 0:
        print("\nCoverage report generated in htmlcov_mst/")
        
    return exit_code


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Run MST tests')
    parser.add_argument(
        'category', 
        nargs='?', 
        choices=['all', 'integration', 'unit', 'modules', 'performance'],
        default='all',
        help='Test category to run (default: all)'
    )
    parser.add_argument(
        '--coverage',
        action='store_true',
        help='Run tests with coverage reporting'
    )
    
    args = parser.parse_args()
    
    if args.coverage:
        exit_code = run_tests_with_coverage()
    elif args.category == 'all':
        exit_code = run_mst_tests()
    else:
        exit_code = run_specific_test_category(args.category)
        
    sys.exit(exit_code)