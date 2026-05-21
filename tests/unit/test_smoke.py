"""Smoke tests — verify the package imports cleanly and basic identity holds."""

import falsifyai


def test_package_imports() -> None:
    assert falsifyai.__version__ == "0.0.0"
