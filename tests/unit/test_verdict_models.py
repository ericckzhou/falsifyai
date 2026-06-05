"""Tests for falsifyai.verdict.models.Verdict (full 8-verdict taxonomy).

The 0.6.0 milestone adds the four remaining classes (INFORMATION_PRESENT,
ADVERSARIALLY_VULNERABLE, INFORMATION_NULL, AMBIGUOUS) to the 0.5.0 set, giving
the full §2.2 taxonomy plus INSUFFICIENT (the structural-gap class) and
INVALID_EVAL (the meta-verdict).

String values are part of the public replay-store on-disk format and must never
change once written -- this test pins them so a rename or value change is caught.
"""

from falsifyai.verdict.models import Verdict

# Frozen: value strings persisted in replay artifacts. Add members, never rename.
_FROZEN_VALUES = {
    "INFORMATION_PRESENT": "information_present",
    "STABLE": "stable",
    "CONSISTENTLY_WRONG": "consistently_wrong",
    "ADVERSARIALLY_VULNERABLE": "adversarially_vulnerable",
    "FRAGILE": "fragile",
    "INFORMATION_NULL": "information_null",
    "AMBIGUOUS": "ambiguous",
    "INSUFFICIENT": "insufficient",
    "INVALID_EVAL": "invalid_eval",
}


def test_all_members_present_and_frozen() -> None:
    """The full taxonomy: 8 verdicts (§2.2) + INSUFFICIENT, with frozen values."""
    assert {v.name: v.value for v in Verdict} == _FROZEN_VALUES


def test_string_values_match_plan() -> None:
    """String values must be stable for persistence; lower_snake_case per existing pattern."""
    assert Verdict.STABLE.value == "stable"
    assert Verdict.FRAGILE.value == "fragile"
    assert Verdict.CONSISTENTLY_WRONG.value == "consistently_wrong"
    assert Verdict.INSUFFICIENT.value == "insufficient"
    assert Verdict.INVALID_EVAL.value == "invalid_eval"
    assert Verdict.INFORMATION_PRESENT.value == "information_present"
    assert Verdict.ADVERSARIALLY_VULNERABLE.value == "adversarially_vulnerable"
    assert Verdict.INFORMATION_NULL.value == "information_null"
    assert Verdict.AMBIGUOUS.value == "ambiguous"


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
