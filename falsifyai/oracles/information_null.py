"""InformationNullOracle -- detects semantically empty outputs.

``INFORMATION_NULL`` (plan.md §2.2) is the cell of the grid where the model is
*stable* but says nothing: refusals, hedging, or empty/whitespace responses. The
outputs are structurally consistent (so naive stability marks them fine) yet
carry no information. This is distinct from CONSISTENTLY_WRONG, where the outputs
are coherent, confident, and *wrong* -- here they are coherent and *empty*.

Detection is deliberately conservative -- a lexicon of refusal/hedge markers plus
the truly-empty case. It does **not** use a generic short-length heuristic: a
valid terse answer ("Paris.") must never be flagged as null. Only outputs that
*refuse* or *hedge* (or are blank) count.

No backend needed; this is a content oracle, not an NLI one. It is kept out of
the meta-oracle's peer set (it is a shape detector, not a truth oracle, so it must
not manufacture an oracle conflict). The resolver consults its contribution only
in the stable region, after CONSISTENTLY_WRONG has been ruled out.
"""

from typing import ClassVar

from falsifyai.oracles.base import OracleContext, OracleVerdict
from falsifyai.verdict.models import Verdict

# Substrings (case-folded) that mark a response as a refusal or a non-answer hedge.
_NULL_MARKERS: tuple[str, ...] = (
    "i cannot",
    "i can't",
    "i can not",
    "i'm unable",
    "i am unable",
    "i'm not able",
    "i am not able",
    "unable to provide",
    "unable to help",
    "cannot help",
    "can't help",
    "as an ai",
    "i do not have",
    "i don't have",
    "i'm sorry, but",
    "i am sorry, but",
    "it depends",
    "i'm not sure",
    "i am not sure",
    "it's unclear",
    "it is unclear",
    "hard to say",
    "no comment",
)

# Fraction of outputs that must be empty-of-information for the set to count null.
_NULL_SUPPORT = 0.5


def _is_null(output: str) -> bool:
    stripped = output.strip()
    if not stripped:
        return True
    folded = stripped.casefold()
    return any(marker in folded for marker in _NULL_MARKERS)


class InformationNullOracle:
    """Argues INFORMATION_NULL when most outputs are refusals/hedges/empty."""

    name: ClassVar[str] = "information_null"

    def evaluate(self, context: OracleContext) -> OracleVerdict:
        outputs = context.all_outputs
        if not outputs:
            return OracleVerdict(
                oracle_name=self.name,
                triggered=False,
                verdict_contribution=None,
                confidence=0.0,
                reasoning="no outputs to evaluate",
            )
        null_count = sum(1 for o in outputs if _is_null(o))
        support = null_count / len(outputs)
        if support >= _NULL_SUPPORT:
            return OracleVerdict(
                oracle_name=self.name,
                triggered=True,
                verdict_contribution=Verdict.INFORMATION_NULL,
                confidence=support,
                reasoning=(
                    f"{support:.0%} of outputs are refusals/hedges/empty "
                    f"(>= {_NULL_SUPPORT:.0%}); structurally consistent but information-empty"
                ),
            )
        return OracleVerdict(
            oracle_name=self.name,
            triggered=False,
            verdict_contribution=None,
            confidence=support,
            reasoning=f"only {support:.0%} of outputs are information-empty",
        )
