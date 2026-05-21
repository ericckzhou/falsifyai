"""Tests for falsifyai.spec.models — Pydantic v2 models for the YAML spec format."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from falsifyai.spec.models import (
    CaseSpec,
    CasingVariantSpec,
    ContainsInvariantSpec,
    SemanticEquivalenceInvariantSpec,
    Spec,
    TypoNoiseSpec,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "specs"


def _load_yaml(name: str) -> dict[str, Any]:
    return yaml.safe_load((FIXTURES / name).read_text())


# --- Happy path ------------------------------------------------------------


def test_minimal_spec_parses() -> None:
    spec = Spec.model_validate(_load_yaml("minimal.yaml"))
    assert spec.falsify.version == "1.0"
    assert spec.falsify.name == "minimal smoke test"
    assert spec.model.provider == "openai"
    assert spec.run.seed == 42
    assert len(spec.cases) == 1
    case = spec.cases[0]
    assert case.id == "hello"
    assert case.input.text == "Say hi."


def test_minimal_spec_applies_defaults() -> None:
    spec = Spec.model_validate(_load_yaml("minimal.yaml"))
    assert spec.model.temperature == 0.7
    assert spec.model.max_tokens == 512
    assert spec.model.seed is None
    assert spec.run.replications == 5
    assert spec.run.parallel == 1
    assert spec.run.timeout_seconds == 30
    assert spec.run.cache is True
    case = spec.cases[0]
    assert case.tags == []
    assert case.expected.contains == []
    assert case.expected.not_contains == []
    assert case.expected.reference is None
    assert case.verdict_config.stable_threshold == 0.95
    assert case.verdict_config.fragile_threshold == 0.5
    assert case.verdict_config.use_worst_case_stability is True


def test_full_spec_parses_all_fields() -> None:
    spec = Spec.model_validate(_load_yaml("full.yaml"))
    assert spec.run.replications == 3
    assert spec.run.seed == 12345
    case = spec.cases[0]
    assert case.tags == ["geography", "factual"]
    assert case.expected.contains == ["Paris"]
    assert case.expected.not_contains == ["Lyon", "Marseille"]
    assert case.expected.reference == "Paris is the capital of France."
    typo, casing = case.perturbations
    assert isinstance(typo, TypoNoiseSpec)
    assert typo.count == 5
    assert typo.rate == 0.05
    assert isinstance(casing, CasingVariantSpec)
    assert casing.variants == ["upper", "lower", "title"]
    contains_inv, sem_inv = case.invariants
    assert isinstance(contains_inv, ContainsInvariantSpec)
    assert contains_inv.values == ["Paris"]
    assert contains_inv.severity == "critical"
    assert isinstance(sem_inv, SemanticEquivalenceInvariantSpec)
    assert sem_inv.threshold == 0.85


# --- Discriminator routing -------------------------------------------------


def _case_with(perturbations: list, invariants: list) -> dict:
    return {
        "id": "x",
        "input": {"text": "hi"},
        "perturbations": perturbations,
        "invariants": invariants,
    }


def test_perturbation_discriminator_routes_typo_noise() -> None:
    case = CaseSpec.model_validate(
        _case_with([{"type": "typo_noise"}], [{"type": "contains", "values": ["hi"]}])
    )
    assert isinstance(case.perturbations[0], TypoNoiseSpec)


def test_perturbation_discriminator_routes_casing() -> None:
    case = CaseSpec.model_validate(
        _case_with([{"type": "casing"}], [{"type": "contains", "values": ["hi"]}])
    )
    assert isinstance(case.perturbations[0], CasingVariantSpec)


def test_invariant_discriminator_routes() -> None:
    case = CaseSpec.model_validate(
        _case_with(
            [{"type": "typo_noise"}],
            [
                {"type": "contains", "values": ["hi"]},
                {"type": "semantic_equivalence", "threshold": 0.8},
            ],
        )
    )
    assert isinstance(case.invariants[0], ContainsInvariantSpec)
    assert isinstance(case.invariants[1], SemanticEquivalenceInvariantSpec)


# --- Rejection cases (YAML fixtures) ---------------------------------------


def test_missing_cases_rejected() -> None:
    with pytest.raises(ValidationError):
        Spec.model_validate(_load_yaml("missing_cases.yaml"))


def test_unknown_top_level_field_rejected() -> None:
    with pytest.raises(ValidationError, match="bogus_top_level"):
        Spec.model_validate(_load_yaml("unknown_field.yaml"))


def test_unknown_perturbation_type_rejected() -> None:
    with pytest.raises(ValidationError):
        Spec.model_validate(_load_yaml("unknown_perturbation_type.yaml"))


def test_semantic_equivalence_requires_explicit_threshold() -> None:
    with pytest.raises(ValidationError, match="threshold"):
        Spec.model_validate(_load_yaml("missing_threshold.yaml"))


def test_run_block_requires_seed() -> None:
    with pytest.raises(ValidationError, match="seed"):
        Spec.model_validate(_load_yaml("missing_seed.yaml"))


# --- Field-level constraints -----------------------------------------------


def test_typo_noise_rate_must_be_in_unit_interval() -> None:
    with pytest.raises(ValidationError):
        TypoNoiseSpec.model_validate({"type": "typo_noise", "rate": 1.5})


def test_semantic_threshold_must_be_in_unit_interval() -> None:
    with pytest.raises(ValidationError):
        SemanticEquivalenceInvariantSpec.model_validate(
            {"type": "semantic_equivalence", "threshold": 1.5}
        )


def test_contains_invariant_requires_at_least_one_value() -> None:
    with pytest.raises(ValidationError):
        ContainsInvariantSpec.model_validate({"type": "contains", "values": []})


def test_case_requires_at_least_one_perturbation() -> None:
    with pytest.raises(ValidationError):
        CaseSpec.model_validate(_case_with([], [{"type": "contains", "values": ["hi"]}]))


def test_case_requires_at_least_one_invariant() -> None:
    with pytest.raises(ValidationError):
        CaseSpec.model_validate(_case_with([{"type": "typo_noise"}], []))


def test_casing_variant_rejects_unknown_variant() -> None:
    with pytest.raises(ValidationError):
        CasingVariantSpec.model_validate({"type": "casing", "variants": ["wonky"]})


def test_duplicate_case_ids_rejected() -> None:
    """Materializer derives seeds from case_id; duplicates would silently collide."""
    data = _load_yaml("minimal.yaml")
    # Duplicate the single case
    duplicate = dict(data["cases"][0])
    data["cases"] = [data["cases"][0], duplicate]
    with pytest.raises(ValidationError, match="Duplicate case ids"):
        Spec.model_validate(data)


def test_falsify_version_locked_to_1_0() -> None:
    data = _load_yaml("minimal.yaml")
    data["falsify"]["version"] = "2.0"
    with pytest.raises(ValidationError):
        Spec.model_validate(data)
