"""Bidirectional-NLI perturbation validity — the gate plan.md §9.3 specified.

The default validity check for paraphrase perturbations is cosine similarity of
embeddings (see :mod:`falsifyai.perturbation.paraphrase`). Cosine is *symmetric*
and *topical*: a paraphrase that **omits** the original's load-bearing content
but keeps its vocabulary still embeds close to the original and passes the gate.

Case study 06 documents exactly this failure. An ``llm_rewrite`` paraphrase
stripped an access-policy body ("Only administrators may delete records…") and
embedded a fabricated answer; it stayed topically near-identical, slipped the
0.85 cosine gate, drove the model to refuse ("I don't see the access policy"),
and the refusal scored as ``CONSISTENTLY_WRONG`` — a manufactured false positive
in the *evidence-generation* layer.

Bidirectional NLI catches it. A valid intent-preserving rewrite must **entail
the original and be entailed by it**. Omission breaks ``perturbed ⊨ original``:
the perturbed text no longer supports the original's dropped clauses, so the
reverse direction falls out of ENTAILMENT and the paraphrase is rejected.

The NLI backend here is the *same* one ``--nli`` provisions for the semantic
oracles (:mod:`falsifyai.oracles.nli`). Routing it into the generation-layer
validity gate is resource sharing, not logic sharing — the validity *logic*
lives here, in the perturbation package, and never reaches into the resolver.
"""

from dataclasses import dataclass

from falsifyai.oracles.nli import NLIBackend, NLILabel
from falsifyai.perturbation.base import ValidityResult


@dataclass(frozen=True)
class BidirectionalNLIValidator:
    """Valid iff ``original ⊨ perturbed`` **and** ``perturbed ⊨ original``.

    ``entailment_threshold`` is the minimum entailment score required in each
    direction (matches plan.md §9.3's 0.7 default). The validity score is the
    *weaker* of the two directions — a paraphrase is only as valid as its
    weakest entailment — so an omission (strong forward, weak reverse) scores
    low and is rejected.
    """

    nli: NLIBackend
    entailment_threshold: float = 0.7

    method: str = "nli_bidirectional"

    def validate(self, original: str, perturbed: str) -> ValidityResult:
        forward = self.nli.classify(original, perturbed)  # original ⊨ perturbed?
        reverse = self.nli.classify(perturbed, original)  # perturbed ⊨ original?

        fwd_score = forward.scores.get(NLILabel.ENTAILMENT, 0.0)
        rev_score = reverse.scores.get(NLILabel.ENTAILMENT, 0.0)
        fwd_ok = forward.label is NLILabel.ENTAILMENT and fwd_score >= self.entailment_threshold
        rev_ok = reverse.label is NLILabel.ENTAILMENT and rev_score >= self.entailment_threshold

        is_valid = fwd_ok and rev_ok
        return ValidityResult(
            is_valid=is_valid,
            validity_score=min(fwd_score, rev_score),
            reason=(
                f"forward={forward.label.value}/{fwd_score:.2f}, "
                f"reverse={reverse.label.value}/{rev_score:.2f} "
                f"(entailment_threshold={self.entailment_threshold})"
            ),
            method=self.method,
        )
