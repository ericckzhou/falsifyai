"""GroundingOracle -- positive confirmation that outputs are grounded.

The gold-standard verdict ``INFORMATION_PRESENT`` (plan.md §2.2) requires more
than stability: the outputs must be *grounded* -- entailed by the supplied
context (RAG) or, in the MVP, by ``expected.reference``. This oracle supplies
that positive signal via NLI entailment.

It is the affirmative half of the grounding axis; :class:`HallucinationOracle`
is the negative half. By construction they will not both trigger on the same
set: a set that is majority-ENTAILMENT is grounded, and anything else is not.

No backend or no grounding source -> the oracle degrades to ``triggered=False``,
so wiring it into the resolver changes nothing in runs that do not opt into NLI.
"""

from typing import ClassVar

from falsifyai.oracles.base import OracleContext, OracleVerdict
from falsifyai.oracles.entailment_support import majority_relation
from falsifyai.oracles.nli import NLIBackend, NLILabel
from falsifyai.verdict.models import Verdict

# Fraction of outputs that must be entailed for the set to count as grounded.
_GROUNDED_SUPPORT = 0.5


class GroundingOracle:
    """Argues INFORMATION_PRESENT when outputs are entailed by the grounding source."""

    name: ClassVar[str] = "grounding"

    def __init__(self, nli: NLIBackend | None = None) -> None:
        self._nli = nli

    def evaluate(self, context: OracleContext) -> OracleVerdict:
        source = context.context_text or context.expected.reference
        if self._nli is None or not source:
            return OracleVerdict(
                oracle_name=self.name,
                triggered=False,
                verdict_contribution=None,
                confidence=0.0,
                reasoning="no NLI backend or no grounding source (context/reference)",
            )

        label, support = majority_relation(self._nli, source, context.all_outputs)
        grounded = label is NLILabel.ENTAILMENT and support >= _GROUNDED_SUPPORT
        if grounded:
            return OracleVerdict(
                oracle_name=self.name,
                triggered=True,
                verdict_contribution=Verdict.INFORMATION_PRESENT,
                confidence=support,
                reasoning=(
                    f"{support:.0%} of outputs are entailed by the grounding source "
                    f"(>= {_GROUNDED_SUPPORT:.0%}); outputs are grounded"
                ),
            )
        return OracleVerdict(
            oracle_name=self.name,
            triggered=False,
            verdict_contribution=None,
            confidence=support,
            reasoning=(
                f"outputs not grounded: majority relation to source is "
                f"{label.value} (support {support:.0%})"
            ),
        )
