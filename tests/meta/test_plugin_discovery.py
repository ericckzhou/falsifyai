"""Meta tests: the entry-point plugin system discovers built-ins and third parties.

These prove the OSS-adoption lever works: someone can add a perturbation or
invariant by registering an entry point, without forking FalsifyAI. The
built-ins are dogfooded through the same mechanism.
"""

from falsifyai.invariants.contains import ContainsInvariant
from falsifyai.invariants.registry import discover_invariants
from falsifyai.invariants.schema_match import SchemaMatchInvariant
from falsifyai.invariants.semantic import SemanticEquivalenceInvariant
from falsifyai.perturbation import registry as pert_registry
from falsifyai.perturbation.casing_variant import CasingVariant
from falsifyai.perturbation.registry import discover_perturbations
from falsifyai.perturbation.typo_noise import TypoNoise
from falsifyai.perturbation.unicode_chars import UnicodePerturbation


def test_builtin_perturbations_are_discoverable() -> None:
    found = discover_perturbations()
    assert found.get("typo_noise") is TypoNoise
    assert found.get("casing") is CasingVariant
    assert found.get("unicode") is UnicodePerturbation


def test_builtin_invariants_are_discoverable() -> None:
    found = discover_invariants()
    assert found.get("contains") is ContainsInvariant
    assert found.get("semantic_equivalence") is SemanticEquivalenceInvariant
    assert found.get("schema_match") is SchemaMatchInvariant


class _FakeEntryPoint:
    def __init__(self, name: str, cls: type) -> None:
        self.name = name
        self._cls = cls

    def load(self) -> type:
        return self._cls


class _ThirdPartyPerturbation:
    """Stands in for a plugin shipped by another package."""


def test_third_party_plugin_is_discovered(monkeypatch) -> None:
    """A perturbation registered by an external package is found via entry points.

    Patching ``entry_points`` simulates the external package being installed,
    without actually installing one in CI.
    """

    def _fake_entry_points(*, group: str):
        assert group == "falsifyai.perturbations"
        return [_FakeEntryPoint("custom_legal_paraphrase", _ThirdPartyPerturbation)]

    monkeypatch.setattr(pert_registry, "entry_points", _fake_entry_points)
    found = pert_registry.discover_perturbations()
    assert found == {"custom_legal_paraphrase": _ThirdPartyPerturbation}
