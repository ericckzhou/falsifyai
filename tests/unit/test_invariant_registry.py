"""Tests for falsifyai.invariants.registry.build_invariant."""

import pytest

from falsifyai.invariants.contains import ContainsInvariant
from falsifyai.invariants.registry import build_invariant
from falsifyai.invariants.schema_match import SchemaMatchInvariant
from falsifyai.invariants.semantic import (
    SemanticEquivalenceInvariant,
    SentenceTransformerBackend,
)
from falsifyai.spec.models import (
    ContainsInvariantSpec,
    PluginInvariantSpec,
    SchemaMatchInvariantSpec,
    SemanticEquivalenceInvariantSpec,
)


def test_build_contains_invariant_propagates_config() -> None:
    spec = ContainsInvariantSpec(
        type="contains",
        values=["Paris", "France"],
        severity="critical",
        case_sensitive=True,
    )
    inv = build_invariant(spec)
    assert isinstance(inv, ContainsInvariant)
    assert inv.values == ["Paris", "France"]
    assert inv.case_sensitive is True
    assert inv.severity.value == "critical"


def test_build_semantic_equivalence_propagates_threshold() -> None:
    spec = SemanticEquivalenceInvariantSpec(
        type="semantic_equivalence", threshold=0.85, severity="high"
    )
    inv = build_invariant(spec)
    assert isinstance(inv, SemanticEquivalenceInvariant)
    assert inv.threshold == 0.85
    assert inv.severity.value == "high"
    # Default embedder is the lazy SentenceTransformerBackend.
    assert isinstance(inv.embedder, SentenceTransformerBackend)


def test_build_schema_match_propagates_schema() -> None:
    schema = {"type": "object", "required": ["capital"]}
    spec = SchemaMatchInvariantSpec(type="schema_match", schema=schema, severity="critical")
    inv = build_invariant(spec)
    assert isinstance(inv, SchemaMatchInvariant)
    assert inv.schema == schema
    assert inv.severity.value == "critical"


class _StubInvariant:
    def __init__(self, **params) -> None:
        self.params = params


def test_build_plugin_invariant_by_name(monkeypatch) -> None:
    """A plugin spec resolves a registered class via discovery and passes params."""
    monkeypatch.setattr(
        "falsifyai.invariants.registry.discover_invariants",
        lambda: {"stub": _StubInvariant},
    )
    inv = build_invariant(PluginInvariantSpec(type="plugin", name="stub", params={"x": 1}))
    assert isinstance(inv, _StubInvariant)
    assert inv.params == {"x": 1}


def test_build_plugin_invariant_unknown_name_raises() -> None:
    with pytest.raises(ValueError, match="No invariant plugin registered"):
        build_invariant(PluginInvariantSpec(type="plugin", name="does_not_exist"))


def test_build_unknown_spec_raises_value_error() -> None:
    class _Fake:
        pass

    with pytest.raises(ValueError, match="Unknown invariant spec"):
        build_invariant(_Fake())  # type: ignore[arg-type]


def test_round_trip_default_specs_produce_usable_runtimes() -> None:
    """End-to-end: spec models build runtimes; ContainsInvariant runs without a model load."""
    contains = build_invariant(ContainsInvariantSpec(type="contains", values=["Paris"]))
    # ContainsInvariant can run immediately -- no embedding model needed.
    result = contains.check("ignored", "The capital is Paris.", {})
    assert result.passed is True
