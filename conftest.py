"""
Root conftest.py — its mere presence makes pytest add this directory to
sys.path, so `from termio import ...` resolves the same way whether tests
are run from the repo root or from inside tests/.
"""
