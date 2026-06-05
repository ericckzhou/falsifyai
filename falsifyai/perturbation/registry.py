"""Map a PerturbationSpec into a runtime Perturbation instance.

Dispatch is two-tier (decision 1A):

- **Built-ins** use typed, validated specs and hardcoded ``isinstance``
  dispatch. This keeps the discriminated-union validation that catches bad
  YAML loudly, and lets resource-needing perturbations (paraphrase) accept
  injected ``ModelAdapter`` / ``EmbeddingBackend`` keyword arguments.
- **Plugins** are discovered at runtime from the ``falsifyai.perturbations``
  entry-point group (:func:`discover_perturbations`) and referenced from YAML
  via the generic ``{type: plugin, name: ..., params: {...}}`` spec. Plugin
  classes must be constructible from ``params`` alone (pure/local).

The built-ins are themselves registered as entry points in ``pyproject.toml``,
so :func:`discover_perturbations` returns them too — the mechanism is dogfooded,
not bolted on for third parties only.
"""

from importlib.metadata import entry_points

from falsifyai.execution.adapter import ModelAdapter
from falsifyai.invariants.base import EmbeddingBackend
from falsifyai.oracles.nli import NLIBackend
from falsifyai.perturbation.base import Perturbation
from falsifyai.perturbation.casing_variant import CasingVariant
from falsifyai.perturbation.paraphrase import Paraphrase
from falsifyai.perturbation.typo_noise import TypoNoise
from falsifyai.perturbation.unicode_chars import UnicodePerturbation
from falsifyai.perturbation.validity import BidirectionalNLIValidator
from falsifyai.spec.models import (
    CasingVariantSpec,
    ModelConfig,
    ParaphrasePerturbationSpec,
    PerturbationSpec,
    PluginPerturbationSpec,
    TypoNoiseSpec,
    UnicodePerturbationSpec,
)

_ENTRY_POINT_GROUP = "falsifyai.perturbations"


def discover_perturbations() -> dict[str, type]:
    """Return ``{name: class}`` for every perturbation registered via entry points.

    Reads the ``falsifyai.perturbations`` group from installed package metadata.
    Built-ins are registered there too (see ``pyproject.toml``), so this is the
    single source of truth for "what perturbations exist", including plugins.
    """
    return {ep.name: ep.load() for ep in entry_points(group=_ENTRY_POINT_GROUP)}


def build_perturbation(
    spec: PerturbationSpec,
    *,
    primary_model: ModelConfig | None = None,
    adapter: ModelAdapter | None = None,
    embedder: EmbeddingBackend | None = None,
    nli_backend: NLIBackend | None = None,
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
        ValueError: if the spec type is not recognized, if a paraphrase
            spec is supplied without the resources it needs, or if a plugin
            spec names a perturbation that is not registered.
    """
    if isinstance(spec, TypoNoiseSpec):
        return TypoNoise(count=spec.count, rate=spec.rate)
    if isinstance(spec, CasingVariantSpec):
        return CasingVariant(variants=list(spec.variants))
    if isinstance(spec, UnicodePerturbationSpec):
        return UnicodePerturbation(
            methods=list(spec.methods),
            count=spec.count,
            rate=spec.rate,
        )
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
        # Optional NLI validity gate. When the run provisioned an NLI backend
        # (``--nli``), tighten paraphrase validity with bidirectional
        # entailment so omission-style invalid rewrites are rejected, not just
        # low-cosine ones (case study 06). No backend → cosine-only, unchanged.
        nli_validator = BidirectionalNLIValidator(nli_backend) if nli_backend is not None else None
        return Paraphrase(
            model_config=resolved_model,
            adapter=adapter,
            count=spec.count,
            similarity_threshold=spec.similarity_threshold,
            max_attempts=spec.max_attempts,
            embedder=embedder,
            nli_validator=nli_validator,
        )
    if isinstance(spec, PluginPerturbationSpec):
        registry = discover_perturbations()
        cls = registry.get(spec.name)
        if cls is None:
            raise ValueError(
                f"No perturbation plugin registered under name {spec.name!r}. "
                f"Available: {sorted(registry)}"
            )
        return cls(**spec.params)
    raise ValueError(f"Unknown perturbation spec type: {type(spec).__name__}")
