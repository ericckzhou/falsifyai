"""Falsifiability scoring.

Per [plan.md section 15](../../plan.md): every invariant exposes a
``falsifiability_contribution()`` in [0, 1]. A low score means the
invariant is permissive (e.g., ``contains: ["a"]`` matches almost anything).
A suite of low-falsifiability invariants will pass CI even on degraded
models -- that's the failure mode this score defends against.

Two layers:

- **case_falsifiability(invariants)** -- mean across the invariants
  configured for a single case.
- **suite_falsifiability(case_scores)** -- mean across cases in a session.

Aggregation is intentionally mean (not min or product). A single low-
contribution invariant on an otherwise-strict case shouldn't tank the
suite score; conversely, a single strict invariant doesn't redeem a
suite full of toothless ones.

The MVP uses LOW_FALSIFIABILITY_THRESHOLD = 0.5 for warn-only output.
Hard-fail with exit code 6 lands in a later PR after dogfooding.
"""

from typing import Final

from falsifyai.invariants.base import Invariant

LOW_FALSIFIABILITY_THRESHOLD: Final[float] = 0.5


def case_falsifiability(invariants: list[Invariant]) -> float:
    """Mean falsifiability contribution across a case's invariants.

    Returns 0.0 if the list is empty (no invariants -> no falsification
    pressure).
    """
    if not invariants:
        return 0.0
    return sum(inv.falsifiability_contribution() for inv in invariants) / len(invariants)


def suite_falsifiability(case_scores: list[float]) -> float:
    """Mean across per-case falsifiability scores.

    Returns 0.0 on empty input.
    """
    if not case_scores:
        return 0.0
    return sum(case_scores) / len(case_scores)
