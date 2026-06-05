"""Sanity test: package version matches the value installed by pip / uv.

Catches the easy mistake of bumping one but not the other when preparing
a release. The CHANGELOG entry, the git tag, and the PyPI upload all
read from the same source of truth -- if these two drift, every other
artifact is suspect.
"""

from importlib.metadata import version as _installed_version

import falsifyai


def test_dunder_version_is_0_6_0() -> None:
    assert falsifyai.__version__ == "0.6.0"


def test_dunder_version_matches_installed_metadata() -> None:
    assert falsifyai.__version__ == _installed_version("falsifyai")
