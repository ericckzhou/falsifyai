"""Shared NLI-aggregation helpers for the semantic oracles (PR-J).

The Contradiction / Hallucination / Grounding oracles all reduce many per-output
NLI judgments into one signal. Two reductions cover all three:

- :func:`majority_relation` -- "how does this *set* of outputs relate to one
  premise (the reference/context)?" Used by Hallucination (entailment) and
  Grounding (entailment) and the vs-reference path of Contradiction.
- :func:`pairwise_contradiction_fraction` -- "do the outputs contradict *each
  other*?" Used by the intra-set path of Contradiction (the AMBIGUOUS signal).

Confidence is reported as the fraction of items carrying the decisive label, a
clean ``[0, 1]`` number the meta-oracle's high-confidence conflict gate consumes
directly.
"""

from collections import Counter

from falsifyai.oracles.nli import NLIBackend, NLILabel


def majority_relation(
    nli: NLIBackend, premise: str, hypotheses: list[str]
) -> tuple[NLILabel, float]:
    """Classify each hypothesis against ``premise``; return (majority label, support).

    ``support`` is the fraction of hypotheses assigned the majority label -- a
    confidence in how uniformly the set relates to the premise. Empty input
    returns ``(NEUTRAL, 0.0)`` (nothing to judge).
    """
    if not hypotheses:
        return NLILabel.NEUTRAL, 0.0
    labels = [nli.classify(premise, h).label for h in hypotheses]
    counts = Counter(labels)
    label, count = counts.most_common(1)[0]
    return label, count / len(hypotheses)


def pairwise_contradiction_fraction(nli: NLIBackend, texts: list[str]) -> float:
    """Fraction of distinct output pairs that contradict each other.

    NLI is directional, so a pair contradicts if *either* direction is labeled
    ``CONTRADICTION``. Fewer than two texts -> 0.0 (a set cannot disagree with
    itself).
    """
    n = len(texts)
    if n < 2:
        return 0.0
    contradictory = 0
    total = 0
    for i in range(n):
        for j in range(i + 1, n):
            total += 1
            forward = nli.classify(texts[i], texts[j]).label
            backward = nli.classify(texts[j], texts[i]).label
            if NLILabel.CONTRADICTION in (forward, backward):
                contradictory += 1
    return contradictory / total
