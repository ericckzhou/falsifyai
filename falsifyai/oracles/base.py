"""Oracle Protocol + shared currency types (``OracleVerdict``, ``OracleContext``).

Oracles are the *semantic-judgment* layer — the part of evidence interpretation
that goes beyond per-output invariant checks to reason about a whole execution
set (do the outputs agree? do they contradict ground truth? is the evaluation
itself broken?). This is the layer that separates FalsifyAI from frameworks that
only report per-output pass/fail.

Two design rules make oracles safe to add without inflating the resolver
(see ``.claude/CLAUDE.md`` and ``tests/meta/test_resolver_branch_count.py``):

1. **Oracles pre-arbitrate.** Every oracle collapses its judgment into a single
   :class:`OracleVerdict`. The resolver consumes resolved contributions, never
   raw oracle heuristics — so adding an oracle is a change to the *consumer
   surface*, not to the verdict priority chain.
2. **Uniform in, uniform out.** Every oracle reads from one :class:`OracleContext`
   and returns one :class:`OracleVerdict`. Different oracles read different
   fields of the context; the shape stays stable as the layer grows.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from falsifyai.verdict.models import Verdict

if TYPE_CHECKING:
    from falsifyai.invariants.base import EmbeddingBackend, InvariantResult
    from falsifyai.spec.models import ExpectedSection


@dataclass(frozen=True)
class OracleVerdict:
    """One oracle's pre-arbitrated judgment over an execution set.

    ``verdict_contribution`` is the verdict this oracle argues for when
    ``triggered`` is True, and ``None`` when the oracle did not fire. The
    resolver (or the meta-oracle) arbitrates among contributions by precedence;
    an oracle never decides the final verdict alone.
    """

    oracle_name: str
    triggered: bool
    verdict_contribution: Verdict | None
    confidence: float
    reasoning: str


@dataclass(frozen=True)
class OracleContext:
    """The evidence bag every oracle reads from.

    Fields are optional so the context can be built from whatever evidence is
    available at the call site. PR-C oracles read the output/expected/embedder
    fields; later oracles (meta-oracle) read ``invariant_results`` and
    ``peer_verdicts``. Adding a field here is how the layer grows — never by
    widening an oracle's own ``evaluate`` signature.
    """

    original_output: str
    perturbed_outputs: list[str]
    expected: "ExpectedSection"
    embedder: "EmbeddingBackend | None" = None
    invariant_results: list[list["InvariantResult"]] = field(default_factory=list)
    peer_verdicts: list[OracleVerdict] = field(default_factory=list)
    # Retrieved/grounding context for RAG-style cases. The GroundingOracle checks
    # output entailment against this; when absent it falls back to
    # ``expected.reference`` (MVP: reference doubles as the grounding source).
    context_text: str | None = None

    @property
    def all_outputs(self) -> list[str]:
        """Original output followed by every perturbed output."""
        return [self.original_output, *self.perturbed_outputs]


@runtime_checkable
class Oracle(Protocol):
    """Runtime interface for a semantic-judgment oracle."""

    name: str

    def evaluate(self, context: OracleContext) -> OracleVerdict:
        """Judge the execution set in ``context`` and return one verdict."""
        ...
