"""Tests for falsifyai.perturbation.base -- dataclasses, enum, hash helper."""

from dataclasses import FrozenInstanceError

import pytest

from falsifyai.perturbation.base import (
    PerturbationCategory,
    PerturbationLineage,
    PerturbedInput,
    ValidityResult,
    hash_input,
)


def _lineage() -> PerturbationLineage:
    return PerturbationLineage(
        perturbation_type="x",
        category=PerturbationCategory.LEXICAL,
        method="m",
        seed=1,
        params={"sample_index": 0},
        parent_input_hash="abc",
    )


def test_perturbation_category_has_five_members() -> None:
    assert {c.value for c in PerturbationCategory} == {
        "lexical",
        "syntactic",
        "semantic",
        "contextual",
        "adversarial",
    }


def test_perturbation_lineage_is_frozen() -> None:
    lineage = _lineage()
    with pytest.raises(FrozenInstanceError):
        lineage.seed = 99  # type: ignore[misc]


def test_perturbed_input_is_frozen() -> None:
    pi = PerturbedInput(text="t", lineage=_lineage(), validity_score=1.0)
    with pytest.raises(FrozenInstanceError):
        pi.text = "mutated"  # type: ignore[misc]


def test_validity_result_is_frozen() -> None:
    vr = ValidityResult(is_valid=True, validity_score=1.0, reason="r", method="m")
    with pytest.raises(FrozenInstanceError):
        vr.is_valid = False  # type: ignore[misc]


def test_perturbed_input_default_metadata_is_empty() -> None:
    pi = PerturbedInput(text="t", lineage=_lineage(), validity_score=1.0)
    assert pi.metadata == {}


def test_hash_input_is_deterministic() -> None:
    assert hash_input("hello") == hash_input("hello")


def test_hash_input_differs_for_different_text() -> None:
    assert hash_input("hello") != hash_input("world")


def test_hash_input_is_hex_sha256() -> None:
    h = hash_input("anything")
    assert len(h) == 64
    int(h, 16)
