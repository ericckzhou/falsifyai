"""MetaOracle -- the sole source of INVALID_EVAL.

INVALID_EVAL answers a question no other verdict can: *is the evaluation itself
trustworthy?* A framework that silently reports STABLE/FRAGILE on a broken eval
is worse than useless — it launders a measurement error into a confident claim.
The meta-oracle makes INVALID_EVAL rigorous rather than ad-hoc (plan.md §11.2).

PR-D implements 2 of the 4 detection classes (per plan.md §22.2):

1. **ORACLE CONFLICT** — two primary oracles argue for *different* verdicts,
   both at high confidence. If they can't both be right, the evaluation can't be
   trusted. (Reachable once a second primary oracle exists; until then there is
   only one peer, so it never fires — but the logic is live and tested.)
2. **INVARIANT DEGENERATION** — an invariant fails on >95% of outputs
   *including the unperturbed baseline*. A correct invariant should pass on a
   good baseline answer; one that rejects nearly everything (including the
   clean output) is malformed (too strict, wrong type, impossible schema).

The "including baseline" detail is load-bearing: it is what distinguishes a
*malformed invariant* from a *genuinely failing model*. The latter is explained
by a primary oracle (ConsistencyOracle → CONSISTENTLY_WRONG), so degeneration is
suppressed whenever any peer oracle has already triggered.

Deferred to later milestones: PERTURBATION DEGENERATION (>50% perturbations fail
validity) and CALIBRATION FAILURE (needs ground-truth fixtures) — plan.md §11.2.
"""

from typing import ClassVar

from falsifyai.oracles.base import OracleContext, OracleVerdict
from falsifyai.verdict.models import Verdict

# An invariant failing at or above this fraction (baseline included) is degenerate.
_DEGENERATION_THRESHOLD = 0.95
# Two oracles disagreeing, both at or above this confidence, is a conflict.
_HIGH_CONFIDENCE = 0.8


class MetaOracle:
    """Detects evaluation-validity failures and emits INVALID_EVAL."""

    name: ClassVar[str] = "meta"

    def evaluate(self, context: OracleContext) -> OracleVerdict:
        conflict = _detect_oracle_conflict(context.peer_verdicts)
        if conflict is not None:
            return OracleVerdict(
                oracle_name=self.name,
                triggered=True,
                verdict_contribution=Verdict.INVALID_EVAL,
                confidence=conflict[0],
                reasoning=conflict[1],
            )

        # Degeneration is only meaningful when no primary oracle has already
        # explained the failures (a consistently-wrong model is not a broken eval).
        if not any(v.triggered for v in context.peer_verdicts):
            degenerate = _detect_invariant_degeneration(context.invariant_results)
            if degenerate is not None:
                inv_name, fail_rate = degenerate
                return OracleVerdict(
                    oracle_name=self.name,
                    triggered=True,
                    verdict_contribution=Verdict.INVALID_EVAL,
                    confidence=fail_rate,
                    reasoning=(
                        f"invariant '{inv_name}' fails on {fail_rate:.0%} of outputs "
                        f"including the baseline (> {_DEGENERATION_THRESHOLD:.0%}); "
                        f"the invariant is malformed, not the model"
                    ),
                )

        return OracleVerdict(
            oracle_name=self.name,
            triggered=False,
            verdict_contribution=None,
            confidence=0.0,
            reasoning="no evaluation-validity failure detected",
        )


def _detect_oracle_conflict(verdicts: list[OracleVerdict]) -> tuple[float, str] | None:
    """Return (confidence, reasoning) if two high-confidence oracles disagree."""
    high_conf = [
        v
        for v in verdicts
        if v.triggered and v.verdict_contribution is not None and v.confidence >= _HIGH_CONFIDENCE
    ]
    for i in range(len(high_conf)):
        for j in range(i + 1, len(high_conf)):
            a, b = high_conf[i], high_conf[j]
            if a.verdict_contribution is not b.verdict_contribution:
                confidence = min(a.confidence, b.confidence)
                reasoning = (
                    f"oracle conflict: '{a.oracle_name}' argues "
                    f"{a.verdict_contribution.value} ({a.confidence:.2f}) but "
                    f"'{b.oracle_name}' argues {b.verdict_contribution.value} "
                    f"({b.confidence:.2f}); cannot both be true"
                )
                return confidence, reasoning
    return None


def _detect_invariant_degeneration(
    invariant_results: list[list],
) -> tuple[str, float] | None:
    """Return (invariant_name, fail_rate) for the worst degenerate invariant, else None.

    ``invariant_results`` is a matrix: one row per output (baseline first, then
    each perturbed run), each row a list of ``InvariantResult`` aligned by
    invariant index. An invariant whose fail rate across all rows exceeds the
    threshold is malformed.
    """
    rows = [row for row in invariant_results if row]
    if not rows:
        return None
    n_invariants = len(rows[0])
    n_outputs = len(rows)
    worst: tuple[str, float] | None = None
    for j in range(n_invariants):
        column = [row[j] for row in rows if j < len(row)]
        if len(column) != n_outputs:
            continue  # ragged matrix; skip rather than guess
        fails = sum(1 for r in column if not r.passed)
        fail_rate = fails / n_outputs
        if fail_rate > _DEGENERATION_THRESHOLD and (worst is None or fail_rate > worst[1]):
            worst = (column[0].invariant_name, fail_rate)
    return worst
