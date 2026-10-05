"""
Test package for AI Resume Checker.

Run all tests with::

    python -m unittest discover -s tests -v

or simply::

    python tests/run_tests.py
"""

import os
import sys

# Make sure the project root is importable when tests run from anywhere.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)