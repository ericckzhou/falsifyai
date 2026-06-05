"""HallucinationOracle -- detects outputs that CONTRADICT the reference.

Hallucination is the strong-negative end of the grounding axis. The outputs
hold one of three NLI relations to ``expected.reference``:

- **ENTAILMENT** -- outputs are grounded; :class:`GroundingOracle` argues
  INFORMATION_PRESENT.
- **CONTRADICTION** -- outputs assert the opposite of the reference; this oracle
  argues CONSISTENTLY_WRONG (the confident, repeatable falsehood of the §2.1
  grid).
- **NEUTRAL** -- entailment could not be established either way. This is
  *grounding unconfirmed*, NOT wrongness: a correct answer that merely rephrases
  the reference is routinely labeled NEUTRAL by a sentence-pair NLI head. So
  NEUTRAL is an **abstention** -- the oracle does not fire, and the statistical
  verdict (e.g. STABLE) stands.

Folding NEUTRAL into "unsupported" was a 0.6.0 false positive: it reported
correct, stable, paraphrased outputs as CONSISTENTLY_WRONG at full confidence
(see ``docs/case-studies/probe-03/RESULTS.md``, case
``cancellation_deadline_inversion``). Reserving the verdict for genuine
CONTRADICTION fixes that.

This overlaps :class:`ContradictionOracle`'s vs-reference path by design
(defense in depth; agreement strengthens the meta-oracle's confidence). A future
refactor may merge them; they are kept separate for now.

No backend or no reference -> ``triggered=False`` (inert without opt-in NLI).
"""

from typing import ClassVar

from falsifyai.oracles.base import OracleContext, OracleVerdict
from falsifyai.oracles.entailment_support import majority_relation
from falsifyai.oracles.nli import NLIBackend, NLILabel
from falsifyai.verdict.models import Verdict

# Fraction of outputs that must contradict the reference for the set to count
# as hallucinating.
_CONTRADICTION_SUPPORT = 0.5


class HallucinationOracle:
    """Argues CONSISTENTLY_WRONG when outputs contradict the reference."""

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
        contradicts = label is NLILabel.CONTRADICTION and support >= _CONTRADICTION_SUPPORT
        if contradicts:
            return OracleVerdict(
                oracle_name=self.name,
                triggered=True,
                verdict_contribution=Verdict.CONSISTENTLY_WRONG,
                confidence=support,
                reasoning=(
                    f"{support:.0%} of outputs contradict the reference "
                    f"(majority relation {label.value}); claims are unsupported"
                ),
            )
        # ENTAILMENT (grounded, GroundingOracle's job) or NEUTRAL (grounding
        # unconfirmed) -> abstain. NEUTRAL is NOT wrongness; firing here was the
        # 0.6.0 false positive.
        unconfirmed = label is NLILabel.NEUTRAL
        return OracleVerdict(
            oracle_name=self.name,
            triggered=False,
            verdict_contribution=None,
            confidence=support,
            reasoning=(
                f"no contradiction: majority relation to reference is "
                f"{label.value} (support {support:.0%}); "
                f"{'grounding unconfirmed' if unconfirmed else 'grounded'}, abstaining"
            ),
        )
