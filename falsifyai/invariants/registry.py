"""Map an InvariantSpec into a runtime Invariant instance.

Dispatch is two-tier (decision 1A), mirroring the perturbation registry:

- **Built-ins** use typed, validated specs and ``isinstance`` dispatch.
- **Plugins** are discovered at runtime from the ``falsifyai.invariants``
  entry-point group (:func:`discover_invariants`) and referenced from YAML via
  the generic ``{type: plugin, name: ..., params: {...}}`` spec.

Built-ins are registered as entry points in ``pyproject.toml`` so the mechanism
is dogfooded.
"""

from importlib.metadata import entry_points

from falsifyai.invariants.base import Invariant, Severity
from falsifyai.invariants.contains import ContainsInvariant
from falsifyai.invariants.schema_match import SchemaMatchInvariant
from falsifyai.invariants.semantic import SemanticEquivalenceInvariant
from falsifyai.spec.models import (
    ContainsInvariantSpec,
    InvariantSpec,
    PluginInvariantSpec,
    SchemaMatchInvariantSpec,
    SemanticEquivalenceInvariantSpec,
)

_ENTRY_POINT_GROUP = "falsifyai.invariants"


def discover_invariants() -> dict[str, type]:
    """Return ``{name: class}`` for every invariant registered via entry points."""
    return {ep.name: ep.load() for ep in entry_points(group=_ENTRY_POINT_GROUP)}


def build_invariant(spec: InvariantSpec) -> Invariant:
    """Return a runtime Invariant for the given InvariantSpec.

    Raises:
        ValueError: if the spec type is not recognized, or if a plugin spec
            names an invariant that is not registered.
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
    if isinstance(spec, SchemaMatchInvariantSpec):
        return SchemaMatchInvariant(
            schema=spec.json_schema,
            severity=Severity(spec.severity),
        )
    if isinstance(spec, PluginInvariantSpec):
        registry = discover_invariants()
        cls = registry.get(spec.name)
        if cls is None:
            raise ValueError(
                f"No invariant plugin registered under name {spec.name!r}. "
                f"Available: {sorted(registry)}"
            )
        return cls(**spec.params)
    raise ValueError(f"Unknown invariant spec type: {type(spec).__name__}")
