import os
import sys

# Make the odds package (a directory of modules) importable as a flat layout.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "odds"))
