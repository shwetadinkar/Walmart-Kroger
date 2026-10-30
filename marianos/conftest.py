"""Put the package root on sys.path.

Without this, pytest works only because it inserts the rootdir, and running a
test file directly fails with ModuleNotFoundError before a single test runs.
A reviewer invoking `python3 tests/test_x.py` by hand got zero tests and an
import error rather than a result.
"""
import sys
from pathlib import Path

root = str(Path(__file__).resolve().parent)
if root not in sys.path:
    sys.path.insert(0, root)
