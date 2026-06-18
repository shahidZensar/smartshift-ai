import os
import sys

# Make the `app` package importable when pytest is run from anywhere.
# (tests/ lives next to app/ under temp/.)
TEMP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TEMP_DIR not in sys.path:
    sys.path.insert(0, TEMP_DIR)
