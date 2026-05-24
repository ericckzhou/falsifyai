"""Integrity checks for stored ReplayArtifacts (PR-31).

Pure read-only checks: given a loaded ``ReplayArtifact``, report whether the
artifact is internally consistent and whether its load-bearing identity hash
(``materialized_hash``) round-trips. No re-resolution, no IO, no network.

The CLI surface is ``falsifyai verify <session_id>`` in :mod:`falsifyai.cli.verify`.
"""

from falsifyai.integrity.checks import (
    CheckResult,
    CheckStatus,
    IntegrityReport,
    run_integrity_checks,
)

__all__ = [
    "CheckResult",
    "CheckStatus",
    "IntegrityReport",
    "run_integrity_checks",
]
