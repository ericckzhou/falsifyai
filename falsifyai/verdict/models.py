"""Verdict enum for the falsificationist evaluation taxonomy.

Phase 0 MVP ships the 5-verdict subset (per plan.md section 22.1). The full
8-verdict taxonomy (per plan.md section 2.2) lands in Phase 1 alongside the
full verdict resolver and meta-oracle.

Persistence note: string values are part of the public on-disk format for the
replay store (see falsifyai/replay/sqlite_store.py) and must not change once
the store is in use. Add new members; do not rename or repurpose existing
ones.
"""

from enum import Enum


class Verdict(Enum):
    """The Phase 0 MVP verdict set.

    - ``STABLE``: outputs are consistent under perturbation; no contradiction detected.
    - ``FRAGILE``: outputs vary materially under perturbation; reliability claim falsified.
    - ``CONSISTENTLY_WRONG``: outputs are consistent but contradict the provided
      ground truth; the most dangerous production case (a confidently
      hallucinating model that v1 frameworks would mark STABLE).
    - ``INSUFFICIENT``: not enough evidence to discriminate between states above
      (e.g., sample size too small). Replaces / precursor to the Phase 1
      ``AMBIGUOUS`` meta-verdict.
    - ``INVALID_EVAL``: the evaluation itself is broken (oracles disagree,
      invariants malformed, >50% perturbations invalid, etc.). Sole source is
      the meta-oracle.
    """

    STABLE = "stable"
    FRAGILE = "fragile"
    CONSISTENTLY_WRONG = "consistently_wrong"
    INSUFFICIENT = "insufficient"
    INVALID_EVAL = "invalid_eval"
