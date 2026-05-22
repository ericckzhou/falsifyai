"""Paraphrase perturbation — LLM-driven semantic-preserving rewrites.

Phase B of the validation campaign. Tests *semantic* robustness, orthogonal
to the character-level pressure axes the existing ``typo_noise`` and
``casing_variant`` families exercise.

Architectural notes:

- **LLM-backed.** Each paraphrase = one ``ModelAdapter.execute()`` call. The
  adapter is injected at construction; the same MockAdapter test seam used
  elsewhere in the repo works here.

- **Validity-gated.** Every generated paraphrase is checked against the
  original via embedding cosine similarity (default 0.85 threshold,
  configurable per spec). Failed paraphrases are dropped and the
  perturbation retries up to ``max_attempts`` times per requested sample.

- **Result count may be less than `count`.** If all attempts for a sample
  fail validity, that slot is dropped. Returning fewer than ``count`` is a
  legitimate honest signal — the spec asked for N, the framework produced
  M valid ones, the materializer can surface the gap.

- **Determinism via materialization persistence.** This perturbation is
  *not* a pure function of (input, seed) — the LLM is variable. Determinism
  is provided by materializing once and storing the realized paraphrases in
  ``MaterializedCase.realized_perturbations``. Replay reads from there;
  never regenerates.

- **Replay-stable lineage.** Each accepted PerturbedInput's lineage carries
  ``sample_index``, ``attempts_used``, ``requested_count``,
  ``similarity_threshold``, and the ``model`` name. A reader can
  reconstruct how the paraphrase was produced and how many tries it took.
"""

from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np

from falsifyai.execution.adapter import ModelAdapter
from falsifyai.execution.models import ModelRequest
from falsifyai.invariants.base import EmbeddingBackend
from falsifyai.invariants.semantic import SentenceTransformerBackend
from falsifyai.perturbation.base import (
    PerturbationCategory,
    PerturbationLineage,
    PerturbedInput,
    ValidityResult,
    hash_input,
)
from falsifyai.spec.models import ModelConfig

# Prompt template. Variation hints (sample_index + attempt) make each call
# cache-distinct so different paraphrases come back per sample.
_PARAPHRASE_PROMPT = (
    "Rewrite the following text in a different way while preserving the "
    "exact meaning. Output ONLY the rewritten text, with no preamble, "
    "explanation, or quotation marks.\n\n"
    "Variation: sample={sample_index} attempt={attempt}\n"
    "Original: {input}\n\n"
    "Rewritten:"
)

# OpenAI / Groq / most LLM provider APIs constrain the `seed` parameter to
# int32 range. The materializer's `_derive_perturbation_seed` produces 64-bit
# values via sha256, which overflow. We modulo the per-call seed below to
# fit. Two-step is fine — paraphrase determinism doesn't depend on the API
# honoring the seed; the variation hint inside the prompt already makes each
# call cache-distinct (and the materialized output is what guarantees
# replay-stability).
_MAX_API_SEED = 2**31 - 1


@dataclass(frozen=True)
class Paraphrase:
    """LLM-driven semantic-preserving rewrites with validity gating."""

    model_config: ModelConfig
    adapter: ModelAdapter
    count: int = 3
    similarity_threshold: float = 0.85
    max_attempts: int = 3
    embedder: EmbeddingBackend = field(default_factory=SentenceTransformerBackend)
    timeout_seconds: int = 30

    name: ClassVar[str] = "paraphrase"
    category: ClassVar[PerturbationCategory] = PerturbationCategory.SEMANTIC
    is_deterministic: ClassVar[bool] = False
    is_local: ClassVar[bool] = False

    def apply(self, input_text: str, seed: int) -> list[PerturbedInput]:
        """Generate `count` paraphrases, retrying on validity failure.

        Returns up to ``count`` valid PerturbedInputs. May return fewer if
        ``max_attempts`` is exhausted on one or more samples.
        """
        parent_hash = hash_input(input_text)
        results: list[PerturbedInput] = []
        for sample_index in range(self.count):
            for attempt in range(self.max_attempts):
                request = self._build_request(input_text, seed, sample_index, attempt)
                execution = self.adapter.execute(request)
                paraphrase_text = execution.output_text.strip()
                validity = self.validate(input_text, paraphrase_text)
                if validity.is_valid:
                    lineage = PerturbationLineage(
                        perturbation_type=self.name,
                        category=self.category,
                        method="llm_rewrite",
                        seed=seed,
                        params={
                            "sample_index": sample_index,
                            "attempts_used": attempt + 1,
                            "requested_count": self.count,
                            "similarity_threshold": self.similarity_threshold,
                            "model": self.model_config.model,
                            "validity_score": validity.validity_score,
                        },
                        parent_input_hash=parent_hash,
                    )
                    results.append(
                        PerturbedInput(
                            text=paraphrase_text,
                            lineage=lineage,
                            validity_score=validity.validity_score,
                            metadata={"validity": validity},
                        )
                    )
                    break
            # If we exhausted max_attempts without a valid paraphrase, drop
            # this sample slot. The materializer will surface the gap as
            # `requested vs valid` count when rendering.
        return results

    def validate(self, original: str, perturbed: str) -> ValidityResult:
        """Cosine similarity of embeddings vs threshold."""
        embeddings = self.embedder.embed([original, perturbed])
        similarity = _cosine_similarity(embeddings[0], embeddings[1])
        is_valid = similarity >= self.similarity_threshold
        return ValidityResult(
            is_valid=is_valid,
            validity_score=similarity,
            reason=(
                f"cosine_similarity={similarity:.4f} "
                f"{'>=' if is_valid else '<'} threshold={self.similarity_threshold}"
            ),
            method="embedding_cosine",
        )

    def _build_request(
        self,
        input_text: str,
        seed: int,
        sample_index: int,
        attempt: int,
    ) -> ModelRequest:
        prompt = _PARAPHRASE_PROMPT.format(
            sample_index=sample_index,
            attempt=attempt,
            input=input_text,
        )
        # Per-call seed varies so adapters that honor `seed` see distinct
        # calls. Modulo by _MAX_API_SEED so the value fits int32 (Groq /
        # OpenAI API requirement). Deterministic mapping is preserved
        # (same input -> same output).
        per_call_seed = (seed + sample_index * self.max_attempts + attempt) % _MAX_API_SEED
        return ModelRequest(
            provider=self.model_config.provider,
            model=self.model_config.model,
            prompt=prompt,
            temperature=self.model_config.temperature,
            max_tokens=self.model_config.max_tokens,
            seed=per_call_seed,
            timeout_seconds=self.timeout_seconds,
        )


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
