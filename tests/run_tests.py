#!/usr/bin/env python3
"""
Convenience test runner.

    python tests/run_tests.py            # run everything
    python tests/run_tests.py -v         # verbose
    python tests/run_tests.py test_scoring.py

Equivalent to ``python -m unittest discover -s tests -p "test_*.py"``.
"""

import os
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, TESTS_DIR)


def main() -> int:
    verbosity = 2 if "-v" in sys.argv or "--verbose" in sys.argv else 1

    loader = unittest.TestLoader()
    pattern = "test_*.py"
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            pattern = arg if arg.endswith(".py") else f"test_{arg}.py"

    suite = loader.discover(start_dir=TESTS_DIR, pattern=pattern)
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    print("\n" + "=" * 62)
    if result.wasSuccessful():
        print(f"  ALL TESTS PASSED - {result.testsRun} test(s) ran successfully.")
    else:
        print(f"  FAILED - {len(result.failures)} failure(s), "
              f"{len(result.errors)} error(s) out of {result.testsRun} test(s).")
    print("=" * 62)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())