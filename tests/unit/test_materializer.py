"""Tests for falsifyai.spec.materializer."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from falsifyai.perturbation import hash_input
from falsifyai.spec import load_spec
from falsifyai.spec.materializer import (
    MaterializedCase,
    MaterializedSpec,
    materialize,
)
from falsifyai.spec.models import (
    CaseSpec,
    FalsifyMeta,
    ModelConfig,
    RunConfig,
    Spec,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "specs"


def _make_spec(
    *,
    session_seed: int = 42,
    cases_data: list[dict] | None = None,
) -> Spec:
    """Build a Spec programmatically for tests that need controlled input."""
    if cases_data is None:
        cases_data = [
            {
                "id": "case_a",
                "input": {"text": "What is the capital of France?"},
                "perturbations": [{"type": "typo_noise", "count": 3, "rate": 0.1}],
                "invariants": [{"type": "contains", "values": ["Paris"]}],
            }
        ]
    return Spec(
        falsify=FalsifyMeta(version="1.0", name="programmatic test"),
        model=ModelConfig(provider="openai", model="gpt-4o-mini"),
        run=RunConfig(seed=session_seed),
        cases=[CaseSpec.model_validate(c) for c in cases_data],
    )


# --- Structure -------------------------------------------------------------


def test_materialize_returns_materialized_spec() -> None:
    spec = _make_spec()
    result = materialize(spec, spec_hash="abc")
    assert isinstance(result, MaterializedSpec)
    assert len(result.cases) == 1
    assert isinstance(result.cases[0], MaterializedCase)


def test_realized_perturbations_count_matches_spec() -> None:
    """typo_noise count=5 + casing variants=[upper,lower,title] -> 5+3 = 8."""
    spec = _make_spec(
        cases_data=[
            {
                "id": "x",
                "input": {"text": "Hello, world."},
                "perturbations": [
                    {"type": "typo_noise", "count": 5, "rate": 0.1},
                    {"type": "casing", "variants": ["upper", "lower", "title"]},
                ],
                "invariants": [{"type": "contains", "values": ["x"]}],
            }
        ]
    )
    result = materialize(spec, spec_hash="abc")
    assert len(result.cases[0].realized_perturbations) == 8


def test_original_input_carried() -> None:
    spec = _make_spec()
    result = materialize(spec, spec_hash="abc")
    assert result.cases[0].original_input == "What is the capital of France?"


def test_lineage_parent_input_hash_matches() -> None:
    spec = _make_spec()
    result = materialize(spec, spec_hash="abc")
    expected_hash = hash_input(spec.cases[0].input.text)
    for p in result.cases[0].realized_perturbations:
        assert p.lineage.parent_input_hash == expected_hash


def test_expected_and_verdict_config_carried() -> None:
    spec = _make_spec(
        cases_data=[
            {
                "id": "x",
                "input": {"text": "Hello"},
                "expected": {"contains": ["Hi"], "reference": "Hello there"},
                "perturbations": [{"type": "typo_noise"}],
                "invariants": [{"type": "contains", "values": ["x"]}],
                "verdict_config": {"stable_threshold": 0.99},
            }
        ]
    )
    result = materialize(spec, spec_hash="abc")
    case = result.cases[0]
    assert case.expected.contains == ["Hi"]
    assert case.expected.reference == "Hello there"
    assert case.verdict_config.stable_threshold == 0.99


def test_session_seed_and_model_and_run_carried() -> None:
    spec = _make_spec(session_seed=99)
    result = materialize(spec, spec_hash="abc")
    assert result.session_seed == 99
    assert result.run.seed == 99
    assert result.model.provider == "openai"


def test_falsifyai_version_populated() -> None:
    spec = _make_spec()
    result = materialize(spec, spec_hash="abc")
    assert isinstance(result.falsifyai_version, str)
    assert len(result.falsifyai_version) > 0


# --- Determinism + hashing -------------------------------------------------


def test_materialize_is_deterministic() -> None:
    spec = _make_spec()
    a = materialize(spec, spec_hash="abc")
    b = materialize(spec, spec_hash="abc")
    assert a.materialized_hash == b.materialized_hash
    assert [p.text for p in a.cases[0].realized_perturbations] == [
        p.text for p in b.cases[0].realized_perturbations
    ]


def test_materialized_hash_is_hex_sha256() -> None:
    spec = _make_spec()
    result = materialize(spec, spec_hash="abc")
    assert len(result.materialized_hash) == 64
    int(result.materialized_hash, 16)  # raises if not hex


def test_changing_session_seed_changes_perturbation_outputs() -> None:
    """Different session_seed -> different perturbations -> different hash."""
    spec_a = _make_spec(session_seed=1)
    spec_b = _make_spec(session_seed=2)
    a = materialize(spec_a, spec_hash="abc")
    b = materialize(spec_b, spec_hash="abc")
    assert a.materialized_hash != b.materialized_hash


def test_changing_case_id_changes_case_seed() -> None:
    """Per-case seed is derived from (session_seed, case_id)."""
    spec_a = _make_spec(
        cases_data=[
            {
                "id": "alpha",
                "input": {"text": "Hello"},
                "perturbations": [{"type": "typo_noise", "count": 3, "rate": 0.1}],
                "invariants": [{"type": "contains", "values": ["x"]}],
            }
        ]
    )
    spec_b = _make_spec(
        cases_data=[
            {
                "id": "beta",
                "input": {"text": "Hello"},
                "perturbations": [{"type": "typo_noise", "count": 3, "rate": 0.1}],
                "invariants": [{"type": "contains", "values": ["x"]}],
            }
        ]
    )
    a = materialize(spec_a, spec_hash="abc")
    b = materialize(spec_b, spec_hash="abc")
    assert a.cases[0].case_seed != b.cases[0].case_seed


def test_case_reordering_preserves_individual_case_seeds() -> None:
    """id-based seed derivation is robust to case reordering in YAML."""
    case_a = {
        "id": "alpha",
        "input": {"text": "A"},
        "perturbations": [{"type": "typo_noise", "count": 1, "rate": 0.1}],
        "invariants": [{"type": "contains", "values": ["x"]}],
    }
    case_b = {
        "id": "beta",
        "input": {"text": "B"},
        "perturbations": [{"type": "typo_noise", "count": 1, "rate": 0.1}],
        "invariants": [{"type": "contains", "values": ["x"]}],
    }
    ordered = materialize(_make_spec(cases_data=[case_a, case_b]), spec_hash="abc")
    reversed_ = materialize(_make_spec(cases_data=[case_b, case_a]), spec_hash="abc")
    # Same case_id -> same case_seed regardless of position
    alpha_seed_a = next(c.case_seed for c in ordered.cases if c.case_id == "alpha")
    alpha_seed_b = next(c.case_seed for c in reversed_.cases if c.case_id == "alpha")
    assert alpha_seed_a == alpha_seed_b


def test_materialized_hash_differs_across_specs() -> None:
    """Sanity: materialized_hash isn't always the same."""
    spec_a = _make_spec(
        cases_data=[
            {
                "id": "x",
                "input": {"text": "Hello, world."},
                "perturbations": [{"type": "typo_noise", "count": 3, "rate": 0.1}],
                "invariants": [{"type": "contains", "values": ["x"]}],
            }
        ]
    )
    spec_b = _make_spec(
        cases_data=[
            {
                "id": "x",
                "input": {"text": "Goodbye, moon."},
                "perturbations": [{"type": "typo_noise", "count": 3, "rate": 0.1}],
                "invariants": [{"type": "contains", "values": ["x"]}],
            }
        ]
    )
    a = materialize(spec_a, spec_hash="abc")
    b = materialize(spec_b, spec_hash="abc")
    assert a.materialized_hash != b.materialized_hash


# --- Frozen guarantees ------------------------------------------------------


def test_materialized_spec_is_frozen() -> None:
    spec = _make_spec()
    result = materialize(spec, spec_hash="abc")
    with pytest.raises(FrozenInstanceError):
        result.session_seed = 999  # type: ignore[misc]


def test_materialized_case_is_frozen() -> None:
    spec = _make_spec()
    result = materialize(spec, spec_hash="abc")
    with pytest.raises(FrozenInstanceError):
        result.cases[0].case_id = "mutated"  # type: ignore[misc]


# --- End-to-end with real YAML fixture --------------------------------------


def test_end_to_end_with_full_yaml() -> None:
    spec, spec_hash = load_spec(FIXTURES / "full.yaml")
    result = materialize(spec, spec_hash=spec_hash)
    assert result.spec_hash == spec_hash
    assert len(result.cases) == 1
    case = result.cases[0]
    # full.yaml has typo_noise (count=5) + casing (3 variants) = 8 perturbations
    assert len(case.realized_perturbations) == 8
    assert case.case_id == "capital_france"
