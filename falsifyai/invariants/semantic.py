"""SemanticEquivalenceInvariant + SentenceTransformerBackend (lazy load).

Compares the original and perturbed outputs by embedding both and checking
that their cosine similarity meets a user-configured threshold. Catches
paraphrases that simple string matching misses ("Paris is the capital" vs
"The capital is Paris").

The default ``SentenceTransformerBackend`` loads ``all-MiniLM-L6-v2``
lazily on first ``.embed()`` call -- construction is cheap so tests can
instantiate without triggering a model download.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

import numpy as np

from falsifyai.invariants.base import EmbeddingBackend, InvariantResult, Severity

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class SentenceTransformerBackend:
    """Embeds via ``sentence-transformers`` (default model ``all-MiniLM-L6-v2``).

    Lazy: the underlying ``SentenceTransformer`` is constructed on the first
    ``embed()`` call so importing this module (and constructing instances)
    is cheap. Tests that use ``MockEmbedder`` never trigger a model load.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model: SentenceTransformer | None = None

    def embed(self, texts: list[str]) -> np.ndarray:
        if self._model is None:
            # Imported lazily so unit tests that only use MockEmbedder never
            # pay the ~few-second sentence_transformers import cost. The
            # package is an optional install (`pip install "falsifyai[semantic]"`)
            # because it pulls PyTorch; raise a friendly error if the user
            # reached this path without it.
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise ImportError(
                    "The `semantic_equivalence` invariant requires "
                    "sentence-transformers. Install it with: "
                    'pip install "falsifyai[semantic]"'
                ) from exc

            self._model = SentenceTransformer(self.model_name)
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return np.asarray(embeddings, dtype=np.float64)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


@dataclass(frozen=True)
class SemanticEquivalenceInvariant:
    """Cosine-similarity check between original and perturbed outputs.

    Passes iff ``cosine_similarity(embed(original), embed(perturbed)) >= threshold``.
    The ``context`` parameter on ``check`` is accepted but unused; kept for
    forward-compat with Phase 1 oracles.
    """

    threshold: float
    severity: Severity
    embedder: EmbeddingBackend = field(default_factory=SentenceTransformerBackend)

    name: ClassVar[str] = "semantic_equivalence"

    def check(
        self,
        original_output: str,
        perturbed_output: str,
        context: dict[str, object],  # noqa: ARG002 -- forward-compat, currently unused
    ) -> InvariantResult:
        embeddings = self.embedder.embed([original_output, perturbed_output])
        similarity = _cosine_similarity(embeddings[0], embeddings[1])
        passed = similarity >= self.threshold
        return InvariantResult(
            invariant_name=self.name,
            passed=passed,
            score=similarity,
            details=(
                f"cosine_similarity={similarity:.4f} "
                f"{'>=' if passed else '<'} threshold={self.threshold}"
            ),
            severity=self.severity,
            evidence={
                "similarity": similarity,
                "threshold": self.threshold,
            },
        )

    def falsifiability_contribution(self) -> float:
        """max(0.0, (threshold - 0.5) * 2). Higher threshold = more restrictive.

        Per plan.md section 10.1. A threshold of 0.5 or below is treated as
        non-restrictive (score 0); 1.0 is maximally restrictive (score 1.0).
        """
        return max(0.0, (self.threshold - 0.5) * 2)
