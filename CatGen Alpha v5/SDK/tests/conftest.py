"""pytest conftest.py — auto-runs before every test in SDK/tests/.

Sets up sys.path so that:
  - 'core', 'game', 'ui'  resolve to Main/
  - 'network'             resolves to SDK/network/
No test file needs to do its own sys.path setup.
"""
import os
import sys

_TESTS = os.path.dirname(os.path.abspath(__file__))  # SDK/tests/
_SDK   = os.path.dirname(_TESTS)                      # SDK/
_ROOT  = os.path.dirname(_SDK)                        # project root
_MAIN  = os.path.join(_ROOT, "Main")

for _p in (_MAIN, _SDK):
    if _p not in sys.path:
        sys.path.insert(0, _p)
