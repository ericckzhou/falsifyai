"""Map an InvariantSpec into a runtime Invariant instance.

Phase 0 uses a hardcoded ``isinstance`` dispatch. Phase 2 will replace this
with plugin discovery via ``importlib.metadata.entry_points`` under the
``falsifyai.invariants`` group (plan.md section 17).
"""

from falsifyai.invariants.base import Invariant, Severity
from falsifyai.invariants.contains import ContainsInvariant
from falsifyai.invariants.semantic import SemanticEquivalenceInvariant
from falsifyai.spec.models import (
    ContainsInvariantSpec,
    InvariantSpec,
    SemanticEquivalenceInvariantSpec,
)


def build_invariant(spec: InvariantSpec) -> Invariant:
    """Return a runtime Invariant for the given InvariantSpec.

    Raises:
        ValueError: if the spec type is not recognized.
    """
    if isinstance(spec, ContainsInvariantSpec):
        return ContainsInvariant(
            values=list(spec.values),
            severity=Severity(spec.severity),
            case_sensitive=spec.case_sensitive,
        )
    if isinstance(spec, SemanticEquivalenceInvariantSpec):
        return SemanticEquivalenceInvariant(
            threshold=spec.threshold,
            severity=Severity(spec.severity),
        )
    raise ValueError(f"Unknown invariant spec type: {type(spec).__name__}")
