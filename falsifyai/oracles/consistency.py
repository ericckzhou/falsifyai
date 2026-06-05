"""ConsistencyOracle -- detects CONSISTENTLY_WRONG over an execution set.

The most dangerous production failure (plan.md §2.3): a model that confidently
and *consistently* gives the same wrong answer under every perturbation. Naive
stability scoring marks this STABLE (low variance!) — the worst false positive
in the framework.

This oracle promotes the lightweight string-match check
(``verdict/consistency.py::is_consistently_wrong``) into the Oracle layer and
adds an optional embedding signal:

- **Ground-truth path** (no embedder needed): every output violates explicit
  ground truth (``expected.contains`` missing everywhere, or
  ``expected.not_contains`` present everywhere). This preserves the exact
  pre-oracle behavior, so wiring the oracle into the resolver changes nothing
  when no embedder is supplied.
- **Reference-agreement path** (needs an embedder + ``expected.reference``):
  the outputs agree strongly with *each other* (low variance) yet are
  dissimilar to the reference. High agreement on a non-reference answer is the
  embedding signature of confident, consistent wrongness.

Heavyweight NLI contradiction is deferred to Phase 1 per plan.md §22.1; the
embedding agreement signal is the MVP stand-in.
"""

from typing import ClassVar

import numpy as np

from falsifyai.oracles.base import OracleContext, OracleVerdict
from falsifyai.verdict.consistency import is_consistently_wrong
from falsifyai.verdict.models import Verdict

# Outputs this similar to each other count as "agreeing" (low variance).
_AGREEMENT_THRESHOLD = 0.9
# Outputs this *dissimilar* to the reference count as contradicting it.
_REFERENCE_CONTRADICTION_THRESHOLD = 0.5


def _mean_pairwise_cosine(vectors: np.ndarray) -> float:
    """Mean cosine similarity over all distinct pairs of row vectors.

    Returns 1.0 for a single vector (trivially self-consistent). Zero-norm
    vectors are treated as contributing 0 similarity.
    """
    n = vectors.shape[0]
    if n < 2:
        return 1.0
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    unit = vectors / norms
    gram = unit @ unit.T
    # Average the strict upper triangle (each distinct pair once).
    iu = np.triu_indices(n, k=1)
    return float(np.mean(gram[iu]))


def _mean_cosine_to_reference(vectors: np.ndarray, reference: np.ndarray) -> float:
    ref_norm = float(np.linalg.norm(reference))
    if ref_norm == 0.0:
        return 0.0
    ref_unit = reference / ref_norm
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    unit = vectors / norms
    return float(np.mean(unit @ ref_unit))


class ConsistencyOracle:
    """Returns a CONSISTENTLY_WRONG contribution when outputs are uniformly wrong."""

    name: ClassVar[str] = "consistency"

    def evaluate(self, context: OracleContext) -> OracleVerdict:
        expected = context.expected

        # --- Ground-truth path (always available) ---------------------------
        if is_consistently_wrong(context.original_output, context.perturbed_outputs, expected):
            return OracleVerdict(
                oracle_name=self.name,
                triggered=True,
                verdict_contribution=Verdict.CONSISTENTLY_WRONG,
                confidence=1.0,
                reasoning=(
                    "every output violates explicit ground truth "
                    "(expected.contains / expected.not_contains)"
                ),
            )

        # --- Reference-agreement path (needs embedder + reference) ----------
        reference = expected.reference
        if context.embedder is not None and reference:
            outputs = context.all_outputs
            embeddings = context.embedder.embed(outputs)
            reference_emb = context.embedder.embed([reference])[0]

            agreement = _mean_pairwise_cosine(np.asarray(embeddings))
            reference_similarity = _mean_cosine_to_reference(
                np.asarray(embeddings), np.asarray(reference_emb)
            )
            if (
                agreement >= _AGREEMENT_THRESHOLD
                and reference_similarity < _REFERENCE_CONTRADICTION_THRESHOLD
            ):
                return OracleVerdict(
                    oracle_name=self.name,
                    triggered=True,
                    verdict_contribution=Verdict.CONSISTENTLY_WRONG,
                    confidence=agreement,
                    reasoning=(
                        f"outputs agree (mean pairwise cosine {agreement:.3f} >= "
                        f"{_AGREEMENT_THRESHOLD}) but contradict the reference "
                        f"(mean cosine {reference_similarity:.3f} < "
                        f"{_REFERENCE_CONTRADICTION_THRESHOLD})"
                    ),
                )
            return OracleVerdict(
                oracle_name=self.name,
                triggered=False,
                verdict_contribution=None,
                confidence=agreement,
                reasoning=(
                    f"no consistent contradiction: agreement {agreement:.3f}, "
                    f"reference similarity {reference_similarity:.3f}"
                ),
            )

        return OracleVerdict(
            oracle_name=self.name,
            triggered=False,
            verdict_contribution=None,
            confidence=0.0,
            reasoning="no ground-truth violation; no embedder/reference for agreement check",
        )
