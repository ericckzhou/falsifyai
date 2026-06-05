"""HallucinationOracle -- detects outputs unsupported by the reference.

Hallucination is the negative half of the grounding axis: when the outputs are
*not* entailed by ``expected.reference`` (the NLI relation is NEUTRAL or
CONTRADICTION rather than ENTAILMENT), the model is asserting claims the
reference does not support. Read against the §2.1 grid, ungrounded outputs that
are also mutually consistent are the CONSISTENTLY_WRONG cell -- the confident,
repeatable falsehood. So this oracle pre-arbitrates to CONSISTENTLY_WRONG, the
most dangerous reading of "ungrounded."

It is an *independent* signal from :class:`ContradictionOracle`'s vs-reference
path: hallucination fires on entailment-*failure* (the broad NEUTRAL∪CONTRADICTION
set), contradiction fires on explicit CONTRADICTION. They can agree (defense in
depth) or disagree (feeding the meta-oracle's conflict detection). MVP overlap on
the grounding axis is intentional; splitting reference-grounding from
retrieved-context grounding is a Phase 1 refinement.

No backend or no reference -> ``triggered=False`` (inert without opt-in NLI).
"""

from typing import ClassVar

from falsifyai.oracles.base import OracleContext, OracleVerdict
from falsifyai.oracles.entailment_support import majority_relation
from falsifyai.oracles.nli import NLIBackend, NLILabel
from falsifyai.verdict.models import Verdict

# Fraction of outputs that must be unsupported for the set to count as hallucinating.
_UNSUPPORTED_SUPPORT = 0.5


class HallucinationOracle:
    """Argues CONSISTENTLY_WRONG when outputs are unsupported by the reference."""

    name: ClassVar[str] = "hallucination"

    def __init__(self, nli: NLIBackend | None = None) -> None:
        self._nli = nli

    def evaluate(self, context: OracleContext) -> OracleVerdict:
        reference = context.expected.reference
        if self._nli is None or not reference:
            return OracleVerdict(
                oracle_name=self.name,
                triggered=False,
                verdict_contribution=None,
                confidence=0.0,
                reasoning="no NLI backend or no reference to check support against",
            )

        label, support = majority_relation(self._nli, reference, context.all_outputs)
        unsupported = label is not NLILabel.ENTAILMENT and support >= _UNSUPPORTED_SUPPORT
        if unsupported:
            return OracleVerdict(
                oracle_name=self.name,
                triggered=True,
                verdict_contribution=Verdict.CONSISTENTLY_WRONG,
                confidence=support,
                reasoning=(
                    f"{support:.0%} of outputs are not entailed by the reference "
                    f"(majority relation {label.value}); claims are unsupported"
                ),
            )
        return OracleVerdict(
            oracle_name=self.name,
            triggered=False,
            verdict_contribution=None,
            confidence=support,
            reasoning=(
                f"outputs are supported: majority relation to reference is "
                f"{label.value} (support {support:.0%})"
            ),
        )
