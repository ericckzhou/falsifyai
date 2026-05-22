"""Materialize a Spec into a fully-realized MaterializedSpec.

A materialized spec freezes the actual perturbed inputs that will be run, so
replay is sound even when perturbations are non-deterministic across library
versions or runs. See plan.md section 8 for design rationale.

Two hashes anchor identity:

- ``spec_hash``: sha256 of the YAML file bytes (computed by ``load_spec``).
  Anchors back to the user's source file.
- ``materialized_hash``: sha256 of a canonical JSON serialization of all
  realized perturbations + their lineage. Two materializations with the same
  hash are guaranteed to feed identical strings into the model.

Per-case seeds are derived from ``(session_seed, case_id)``, so reordering
cases in the YAML does NOT change individual case seeds — only the
``case_id`` matters. Per-perturbation seeds are derived from
``(case_seed, perturbation_index)`` within a case.
"""

import hashlib
import json
from dataclasses import dataclass
from importlib.metadata import version as _pkg_version
from typing import TYPE_CHECKING

from falsifyai.perturbation import PerturbedInput, build_perturbation
from falsifyai.spec.models import (
    CaseSpec,
    ExpectedSection,
    ModelConfig,
    RunConfig,
    Spec,
    VerdictConfig,
)

if TYPE_CHECKING:
    # Type-only imports. Paraphrase perturbations need a ModelAdapter and
    # EmbeddingBackend at materialization-time, but the materializer itself
    # only forwards them to build_perturbation — it doesn't import the
    # execution or invariants packages at runtime when not needed.
    from falsifyai.execution.adapter import ModelAdapter
    from falsifyai.invariants.base import EmbeddingBackend


@dataclass(frozen=True)
class MaterializedCase:
    """One case with all its perturbed inputs realized and frozen.

    ``case_seed`` is deterministically derived from ``(session_seed, case_id)``;
    every PerturbedInput in ``realized_perturbations`` carries a lineage that
    references this case's input via ``parent_input_hash``.
    """

    case_id: str
    case_seed: int
    original_input: str
    realized_perturbations: list[PerturbedInput]
    tags: list[str]
    expected: ExpectedSection
    verdict_config: VerdictConfig


@dataclass(frozen=True)
class MaterializedSpec:
    """A Spec with all perturbations realized + a hash identifying this materialization.

    Identity model:
    - ``spec_hash``: from the source YAML's bytes.
    - ``materialized_hash``: from the realized perturbation texts + lineage.

    The hash does NOT cover ``expected``, ``verdict_config``, or model/run
    settings — those affect downstream judging, not the materialized inputs.
    """

    spec_hash: str
    materialized_hash: str
    session_seed: int
    falsifyai_version: str
    model: ModelConfig
    run: RunConfig
    cases: list[MaterializedCase]


def materialize(
    spec: Spec,
    spec_hash: str,
    *,
    adapter: "ModelAdapter | None" = None,
    embedder: "EmbeddingBackend | None" = None,
) -> MaterializedSpec:
    """Realize all perturbations in ``spec`` and return a MaterializedSpec.

    Determinism: the same ``(spec, spec_hash)`` input produces an identical
    MaterializedSpec for pure perturbations (typo_noise, casing_variant).
    For perturbations that call external services (paraphrase), determinism
    relies on the realized output being persisted in
    ``MaterializedCase.realized_perturbations``; replay reads from there
    rather than regenerating.

    Args:
        spec: parsed spec.
        spec_hash: sha256 of the source YAML bytes.
        adapter: ModelAdapter for perturbations that need an LLM
            (paraphrase). Required when the spec contains a paraphrase
            perturbation; ignored otherwise.
        embedder: EmbeddingBackend for perturbations that need validity
            checks (paraphrase). If None and paraphrase is in the spec,
            ``SentenceTransformerBackend()`` is constructed (lazy-loaded).
    """
    session_seed = spec.run.seed
    cases = [
        _materialize_case(case, session_seed, adapter=adapter, embedder=embedder, primary_model=spec.model)
        for case in spec.cases
    ]
    return MaterializedSpec(
        spec_hash=spec_hash,
        materialized_hash=_compute_materialized_hash(cases),
        session_seed=session_seed,
        falsifyai_version=_pkg_version("falsifyai"),
        model=spec.model,
        run=spec.run,
        cases=cases,
    )


def _materialize_case(
    case: CaseSpec,
    session_seed: int,
    *,
    adapter: "ModelAdapter | None" = None,
    embedder: "EmbeddingBackend | None" = None,
    primary_model: "ModelConfig | None" = None,
) -> MaterializedCase:
    case_seed = _derive_case_seed(session_seed, case.id)
    realized: list[PerturbedInput] = []
    for index, perturbation_spec in enumerate(case.perturbations):
        perturbation = build_perturbation(
            perturbation_spec,
            primary_model=primary_model,
            adapter=adapter,
            embedder=embedder,
        )
        per_perturbation_seed = _derive_perturbation_seed(case_seed, index)
        realized.extend(perturbation.apply(case.input.text, seed=per_perturbation_seed))
    return MaterializedCase(
        case_id=case.id,
        case_seed=case_seed,
        original_input=case.input.text,
        realized_perturbations=realized,
        tags=list(case.tags),
        expected=case.expected,
        verdict_config=case.verdict_config,
    )


def _derive_case_seed(session_seed: int, case_id: str) -> int:
    """sha256(session_seed:case_id) -> 64-bit int. Stable across YAML reordering."""
    payload = f"{session_seed}:{case_id}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _derive_perturbation_seed(case_seed: int, index: int) -> int:
    """sha256(case_seed:index) -> 64-bit int. One seed per perturbation in a case."""
    payload = f"{case_seed}:{index}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _compute_materialized_hash(cases: list[MaterializedCase]) -> str:
    """sha256 over a canonical JSON serialization of all realized perturbations.

    Only the perturbation-realization data is hashed (texts + lineage +
    validity scores). ``expected``, ``verdict_config``, and ``metadata``
    are excluded — they affect downstream judging, not the materialized
    inputs themselves.
    """
    canonical: list[dict[str, object]] = []
    for case in cases:
        canonical.append(
            {
                "case_id": case.case_id,
                "case_seed": case.case_seed,
                "original_input": case.original_input,
                "perturbations": [
                    {
                        "text": p.text,
                        "validity_score": p.validity_score,
                        "lineage": {
                            "perturbation_type": p.lineage.perturbation_type,
                            "category": p.lineage.category.value,
                            "method": p.lineage.method,
                            "seed": p.lineage.seed,
                            "params": _jsonable(p.lineage.params),
                            "parent_input_hash": p.lineage.parent_input_hash,
                        },
                    }
                    for p in case.realized_perturbations
                ],
            }
        )
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _jsonable(params: dict[str, object]) -> dict[str, object]:
    """Coerce param values to JSON-safe types (handles ValidityResult etc.)."""
    out: dict[str, object] = {}
    for k, v in params.items():
        if isinstance(v, (str, int, float, bool, type(None))):
            out[k] = v
        else:
            out[k] = str(v)
    return out
