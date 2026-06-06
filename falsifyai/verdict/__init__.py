"""Verdict types — the falsificationist evaluation taxonomy.

Ships the full verdict taxonomy (9 enum members); the 0.1.0 MVP shipped a
5-verdict subset. ``falsifyai.verdict.models`` is the authoritative source.
"""

from falsifyai.verdict.models import Verdict

__all__ = ["Verdict"]
