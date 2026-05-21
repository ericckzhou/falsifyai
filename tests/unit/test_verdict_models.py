"""Tests for falsifyai.verdict.models.Verdict (MVP 5-verdict subset).

Per plan.md section 22.1, the Phase 0 MVP ships 5 verdicts:
STABLE, FRAGILE, CONSISTENTLY_WRONG, INSUFFICIENT, INVALID_EVAL.

The full 8-verdict taxonomy (per plan.md section 2.2) lands in Phase 1.
"""

from falsifyai.verdict.models import Verdict


def test_enum_has_exactly_five_mvp_values() -> None:
    """Per plan.md section 22.1: MVP set is exactly these 5, no more, no less."""
    assert {v.name for v in Verdict} == {
        "STABLE",
        "FRAGILE",
        "CONSISTENTLY_WRONG",
        "INSUFFICIENT",
        "INVALID_EVAL",
    }


def test_string_values_match_plan() -> None:
    """String values must be stable for persistence; lower_snake_case per existing pattern."""
    assert Verdict.STABLE.value == "stable"
    assert Verdict.FRAGILE.value == "fragile"
    assert Verdict.CONSISTENTLY_WRONG.value == "consistently_wrong"
    assert Verdict.INSUFFICIENT.value == "insufficient"
    assert Verdict.INVALID_EVAL.value == "invalid_eval"


def test_members_compare_and_hash_correctly() -> None:
    """Enum members are singletons and hashable for use as dict keys / set members."""
    # Identity / equality
    assert Verdict.STABLE is Verdict.STABLE
    assert Verdict.STABLE == Verdict.STABLE
    assert Verdict.STABLE != Verdict.FRAGILE

    # Reconstruction by value (used by deserializer)
    assert Verdict("stable") is Verdict.STABLE
    assert Verdict("consistently_wrong") is Verdict.CONSISTENTLY_WRONG

    # Hashable / usable as dict key
    counts: dict[Verdict, int] = {Verdict.STABLE: 1, Verdict.FRAGILE: 2}
    counts[Verdict.STABLE] += 1
    assert counts[Verdict.STABLE] == 2
    assert counts[Verdict.FRAGILE] == 2
