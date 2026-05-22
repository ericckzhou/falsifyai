"""Map a PerturbationSpec into a runtime Perturbation instance.

Phase 0 uses hardcoded ``isinstance`` dispatch. Phase 2 will replace this
with plugin discovery via ``importlib.metadata.entry_points`` under the
``falsifyai.perturbations`` group (plan.md section 17).

PR #22 (paraphrase) introduces the first perturbation that needs runtime
resources — a ``ModelAdapter`` (for the LLM call) and an
``EmbeddingBackend`` (for the validity gate). These are passed as keyword
arguments; pure perturbations (typo_noise, casing_variant) ignore them.
The materializer at run time decides whether it needs to construct
these resources based on whether any perturbation in the spec is a
paraphrase.
"""

from falsifyai.execution.adapter import ModelAdapter
from falsifyai.invariants.base import EmbeddingBackend
from falsifyai.perturbation.base import Perturbation
from falsifyai.perturbation.casing_variant import CasingVariant
from falsifyai.perturbation.paraphrase import Paraphrase
from falsifyai.perturbation.typo_noise import TypoNoise
from falsifyai.spec.models import (
    CasingVariantSpec,
    ModelConfig,
    ParaphrasePerturbationSpec,
    PerturbationSpec,
    TypoNoiseSpec,
)


def build_perturbation(
    spec: PerturbationSpec,
    *,
    primary_model: ModelConfig | None = None,
    adapter: ModelAdapter | None = None,
    embedder: EmbeddingBackend | None = None,
) -> Perturbation:
    """Return a runtime ``Perturbation`` for the given ``PerturbationSpec``.

    Keyword args are only used by perturbations that need external
    resources (currently only ``paraphrase``). Pure perturbations ignore
    them entirely.

    Args:
        spec: the perturbation config from the parsed spec.
        primary_model: the spec's top-level ``model`` config. Used as the
            paraphrase model when the paraphrase spec doesn't override it.
        adapter: a ``ModelAdapter`` for paraphrase generation. Required if
            ``spec`` is a ``ParaphrasePerturbationSpec``.
        embedder: an ``EmbeddingBackend`` for paraphrase validity. If
            None and ``spec`` is paraphrase, defaults to
            ``SentenceTransformerBackend()`` (lazy-loaded on first use).

    Raises:
        ValueError: if the spec type is not recognized, or if a paraphrase
            spec is supplied without the resources it needs.
    """
    if isinstance(spec, TypoNoiseSpec):
        return TypoNoise(count=spec.count, rate=spec.rate)
    if isinstance(spec, CasingVariantSpec):
        return CasingVariant(variants=list(spec.variants))
    if isinstance(spec, ParaphrasePerturbationSpec):
        # Resolve which model to use: spec override beats primary.
        resolved_model = spec.model or primary_model
        if resolved_model is None:
            raise ValueError(
                "paraphrase perturbation requires a model: set either "
                "`paraphrase.model` on the spec or supply `primary_model` "
                "from spec.model"
            )
        if adapter is None:
            raise ValueError(
                "paraphrase perturbation requires a ModelAdapter; the materializer must supply one"
            )
        # Embedder: default to SentenceTransformerBackend (lazy) if absent.
        # Match the SemanticEquivalenceInvariant convention.
        if embedder is None:
            from falsifyai.invariants.semantic import SentenceTransformerBackend

            embedder = SentenceTransformerBackend()
        return Paraphrase(
            model_config=resolved_model,
            adapter=adapter,
            count=spec.count,
            similarity_threshold=spec.similarity_threshold,
            max_attempts=spec.max_attempts,
            embedder=embedder,
        )
    raise ValueError(f"Unknown perturbation spec type: {type(spec).__name__}")
