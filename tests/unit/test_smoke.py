"""Smoke tests — verify the package imports cleanly and basic identity holds.

The current version is asserted in tests/unit/test_version.py; this file
just ensures the package imports without raising and that `__version__`
exists as a string.
"""

import falsifyai


def test_package_imports_and_has_version() -> None:
    assert isinstance(falsifyai.__version__, str)
    assert falsifyai.__version__
