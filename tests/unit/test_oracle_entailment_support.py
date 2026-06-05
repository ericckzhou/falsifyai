"""Tests for the shared NLI-aggregation helpers (PR-J)."""

from falsifyai.oracles.entailment_support import (
    majority_relation,
    pairwise_contradiction_fraction,
)
from falsifyai.oracles.nli import MockNLIBackend, NLILabel


class TestMajorityRelation:
    def test_empty_hypotheses_is_neutral_zero(self) -> None:
        label, support = majority_relation(MockNLIBackend(), "premise", [])
        assert label is NLILabel.NEUTRAL
        assert support == 0.0

    def test_all_same_label_full_support(self) -> None:
        nli = MockNLIBackend(default_label=NLILabel.ENTAILMENT)
        label, support = majority_relation(nli, "p", ["a", "b", "c"])
        assert label is NLILabel.ENTAILMENT
        assert support == 1.0

    def test_majority_wins_with_partial_support(self) -> None:
        nli = MockNLIBackend(
            rules={
                ("p", "a"): NLILabel.CONTRADICTION,
                ("p", "b"): NLILabel.CONTRADICTION,
                ("p", "c"): NLILabel.ENTAILMENT,
            }
        )
        label, support = majority_relation(nli, "p", ["a", "b", "c"])
        assert label is NLILabel.CONTRADICTION
        assert support == 2 / 3


class TestPairwiseContradictionFraction:
    def test_fewer_than_two_is_zero(self) -> None:
        assert pairwise_contradiction_fraction(MockNLIBackend(), ["only"]) == 0.0

    def test_all_pairs_contradict(self) -> None:
        nli = MockNLIBackend(default_label=NLILabel.CONTRADICTION)
        assert pairwise_contradiction_fraction(nli, ["a", "b", "c"]) == 1.0

    def test_no_pairs_contradict(self) -> None:
        nli = MockNLIBackend(default_label=NLILabel.NEUTRAL)
        assert pairwise_contradiction_fraction(nli, ["a", "b", "c"]) == 0.0

    def test_contradiction_in_either_direction_counts(self) -> None:
        # forward (a,b) entails, backward (b,a) contradicts -> the pair counts.
        nli = MockNLIBackend(
            rules={("a", "b"): NLILabel.ENTAILMENT, ("b", "a"): NLILabel.CONTRADICTION}
        )
        assert pairwise_contradiction_fraction(nli, ["a", "b"]) == 1.0
