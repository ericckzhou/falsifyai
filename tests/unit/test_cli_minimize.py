"""Tests for falsifyai.cli.minimize."""

from pathlib import Path

import pytest

from falsifyai.cli.errors import ConfigError, InfrastructureError
from falsifyai.cli.minimize import (
    _make_perturbation,
    _parse_levels,
    _select_case,
    search_minimal_falsifier,
)
from falsifyai.perturbation.typo_noise import TypoNoise
from falsifyai.perturbation.unicode_chars import UnicodePerturbation
from falsifyai.spec.loader import load_spec
from falsifyai.verdict.models import Verdict

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_search_stops_at_first_break_ascending() -> None:
    calls: list[float] = []

    def ev(strength: float) -> Verdict:
        calls.append(strength)
        return Verdict.STABLE if strength < 0.1 else Verdict.FRAGILE

    report = search_minimal_falsifier([0.2, 0.05, 0.1], ev, case_id="c", family="typo_noise")
    assert calls == [0.05, 0.1]  # sorted ascending, stopped at 0.1
    assert report.found is True
    assert report.minimal_strength == 0.1
    assert report.minimal_verdict is Verdict.FRAGILE
    assert len(report.levels) == 2


def test_search_robust_when_never_breaks() -> None:
    report = search_minimal_falsifier(
        [0.1, 0.2], lambda s: Verdict.STABLE, case_id="c", family="typo_noise"
    )
    assert report.found is False
    assert report.minimal_strength is None
    assert len(report.levels) == 2
    assert all(not level.broke for level in report.levels)


def test_consistently_wrong_also_counts_as_a_break() -> None:
    report = search_minimal_falsifier(
        [0.05], lambda s: Verdict.CONSISTENTLY_WRONG, case_id="c", family="typo_noise"
    )
    assert report.found is True
    assert report.minimal_verdict is Verdict.CONSISTENTLY_WRONG


def test_make_perturbation_typo() -> None:
    p = _make_perturbation("typo_noise", 0.3, 4)
    assert isinstance(p, TypoNoise)
    assert p.rate == 0.3
    assert p.count == 4


def test_make_perturbation_unicode() -> None:
    p = _make_perturbation("unicode", 0.3, 4)
    assert isinstance(p, UnicodePerturbation)
    assert p.rate == 0.3


def test_make_perturbation_unknown_raises() -> None:
    with pytest.raises(ConfigError, match="unsupported family"):
        _make_perturbation("paraphrase", 0.3, 4)


def test_parse_levels() -> None:
    assert _parse_levels("0.05, 0.1,0.2") == [0.05, 0.1, 0.2]


def test_parse_levels_invalid_raises() -> None:
    with pytest.raises(ConfigError, match="invalid --levels"):
        _parse_levels("0.1,abc")


def test_select_case_default_is_first() -> None:
    spec, _ = load_spec(_EXAMPLES / "fragile.yaml")
    assert _select_case(spec, None).id == "capital_of_france_fragile"


def test_select_case_unknown_raises() -> None:
    spec, _ = load_spec(_EXAMPLES / "fragile.yaml")
    with pytest.raises(InfrastructureError, match="not found"):
        _select_case(spec, "nope")
