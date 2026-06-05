"""ContradictionOracle -- NLI contradiction, two ways.

Embedding cosine (the ConsistencyOracle's tool) can tell you outputs are *about*
the same thing; only NLI can tell you they *contradict*. This oracle reads two
distinct contradiction signals and pre-arbitrates each to its grid verdict:

1. **vs reference** (when ``expected.reference`` is present): the outputs
   contradict the ground truth -> CONSISTENTLY_WRONG. An entailment-grade
   complement to the ConsistencyOracle's embedding/string check.
2. **intra-set** (otherwise): the outputs contradict *each other* -> AMBIGUOUS.
   A set that disagrees with itself cannot support a confident verdict; this is
   the canonical disagreement the meta-oracle weighs against a peer that claims
   the set agrees (its CONSISTENTLY_WRONG vs this AMBIGUOUS is the textbook
   oracle conflict -> INVALID_EVAL).

The vs-reference path takes precedence: a set that contradicts known ground truth
is a stronger, more actionable claim than internal disagreement.

No backend -> ``triggered=False`` (inert without opt-in NLI).
"""

from typing import ClassVar

from falsifyai.oracles.base import OracleContext, OracleVerdict
from falsifyai.oracles.entailment_support import (
    majority_relation,
    pairwise_contradiction_fraction,
)
from falsifyai.oracles.nli import NLIBackend, NLILabel
from falsifyai.verdict.models import Verdict

# Fraction of outputs that must contradict the reference to fire the vs-ref path.
_REFERENCE_CONTRADICTION_SUPPORT = 0.5
# Fraction of output pairs that must mutually contradict to fire the intra-set path.
_INTRASET_CONTRADICTION_FRACTION = 0.5


class ContradictionOracle:
    """Argues CONSISTENTLY_WRONG (vs reference) or AMBIGUOUS (intra-set)."""

    name: ClassVar[str] = "contradiction"

    def __init__(self, nli: NLIBackend | None = None) -> None:
        self._nli = nli

    def evaluate(self, context: OracleContext) -> OracleVerdict:
        if self._nli is None:
            return OracleVerdict(
                oracle_name=self.name,
                triggered=False,
                verdict_contribution=None,
                confidence=0.0,
                reasoning="no NLI backend",
            )

        reference = context.expected.reference
        # --- vs-reference path (precedence) ---------------------------------
        if reference:
            label, support = majority_relation(self._nli, reference, context.all_outputs)
            if label is NLILabel.CONTRADICTION and support >= _REFERENCE_CONTRADICTION_SUPPORT:
                return OracleVerdict(
                    oracle_name=self.name,
                    triggered=True,
                    verdict_contribution=Verdict.CONSISTENTLY_WRONG,
                    confidence=support,
                    reasoning=(
                        f"{support:.0%} of outputs contradict the reference "
                        f"(>= {_REFERENCE_CONTRADICTION_SUPPORT:.0%})"
                    ),
                )

        # --- intra-set path --------------------------------------------------
        fraction = pairwise_contradiction_fraction(self._nli, context.all_outputs)
        if fraction >= _INTRASET_CONTRADICTION_FRACTION:
            return OracleVerdict(
                oracle_name=self.name,
                triggered=True,
                verdict_contribution=Verdict.AMBIGUOUS,
                confidence=fraction,
                reasoning=(
                    f"{fraction:.0%} of output pairs contradict each other "
                    f"(>= {_INTRASET_CONTRADICTION_FRACTION:.0%}); the set disagrees with itself"
                ),
            )

        return OracleVerdict(
            oracle_name=self.name,
            triggered=False,
            verdict_contribution=None,
            confidence=fraction,
            reasoning=(
                f"no dominant contradiction (intra-set contradiction fraction {fraction:.0%})"
            ),
        )
