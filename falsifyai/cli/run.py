"""``falsifyai run`` — orchestration that wires every Phase 0 layer together.

Pipeline:

    load_spec -> materialize -> for each case: execute baseline +
    each perturbation -> judge with invariants -> resolve case verdict
    -> resolve session verdict -> persist via ReplayStore -> render

The function-level seam ``build_adapter`` exists so integration tests can
inject ``MockAdapter`` without monkey-patching imports inside the package
(decision L1 in the PR #8 plan).
"""

import argparse
import uuid
from datetime import UTC, datetime
from importlib.metadata import version as _pkg_version

from falsifyai.cli import render
from falsifyai.cli.errors import ConfigError, InfrastructureError, SpecError
from falsifyai.execution.adapter import ModelAdapter
from falsifyai.execution.cache import InMemoryCache
from falsifyai.execution.engine import ExecutionEngine
from falsifyai.execution.errors import ExecutionError
from falsifyai.execution.litellm_adapter import LiteLLMAdapter
from falsifyai.execution.models import ModelRequest
from falsifyai.invariants.registry import build_invariant
from falsifyai.replay.in_memory_store import InMemoryStore
from falsifyai.replay.models import CaseResult, PerturbedRun, ReplayArtifact
from falsifyai.replay.protocol import ReplayStore
from falsifyai.replay.sqlite_store import SQLiteStore
from falsifyai.spec.errors import SpecLoadError
from falsifyai.spec.loader import load_spec
from falsifyai.spec.materializer import MaterializedSpec, materialize
from falsifyai.spec.models import ModelConfig, RunConfig, Spec
from falsifyai.verdict.resolver import resolve_case, resolve_session


def build_adapter(model: ModelConfig) -> ModelAdapter:
    """Construct the ModelAdapter for a spec. Test seam: monkey-patch this.

    The default returns a ``LiteLLMAdapter``. Tests replace this function with
    one that returns a ``MockAdapter`` so the full chain can run offline.
    """
    try:
        return LiteLLMAdapter()
    except Exception as exc:  # pragma: no cover - construction is trivial
        raise ConfigError(f"failed to construct LiteLLMAdapter: {exc}") from exc


def _build_store(store_path: str) -> ReplayStore:
    """Pick an impl based on the path. ``:memory:`` -> InMemoryStore."""
    if store_path == ":memory:":
        return InMemoryStore()
    return SQLiteStore(store_path)


def _build_request(model: ModelConfig, run: RunConfig, prompt: str) -> ModelRequest:
    return ModelRequest(
        provider=model.provider,
        model=model.model,
        prompt=prompt,
        temperature=model.temperature,
        max_tokens=model.max_tokens,
        seed=model.seed,
        timeout_seconds=run.timeout_seconds,
    )


def _run_case(
    spec: Spec,
    materialized_case_index: int,
    materialized: MaterializedSpec,
    engine: ExecutionEngine,
) -> CaseResult:
    case_spec = spec.cases[materialized_case_index]
    mcase = materialized.cases[materialized_case_index]

    invariants = [build_invariant(inv_spec) for inv_spec in case_spec.invariants]

    try:
        original_exec = engine.execute(_build_request(spec.model, spec.run, mcase.original_input))
    except ExecutionError as exc:
        raise InfrastructureError(
            f"original execution failed for case '{case_spec.id}': {exc}"
        ) from exc

    perturbed_runs: list[PerturbedRun] = []
    for perturbed_input in mcase.realized_perturbations:
        try:
            perturbed_exec = engine.execute(
                _build_request(spec.model, spec.run, perturbed_input.text)
            )
        except ExecutionError as exc:
            raise InfrastructureError(
                f"perturbed execution failed for case '{case_spec.id}': {exc}"
            ) from exc

        invariant_results = [
            inv.check(
                original_output=original_exec.output_text,
                perturbed_output=perturbed_exec.output_text,
                context={},
            )
            for inv in invariants
        ]
        perturbed_runs.append(
            PerturbedRun(
                perturbed_input=perturbed_input,
                execution=perturbed_exec,
                invariant_results=invariant_results,
            )
        )

    verdict, confidence = resolve_case(perturbed_runs)
    return CaseResult(
        case_id=case_spec.id,
        original_input=mcase.original_input,
        original_execution=original_exec,
        perturbed=perturbed_runs,
        verdict=verdict,
        verdict_confidence=confidence,
    )


def cmd_run(args: argparse.Namespace) -> int:
    """Entry point for the ``run`` subcommand. Returns an exit code."""
    try:
        spec, spec_hash = load_spec(args.spec_path)
    except SpecLoadError as exc:
        raise SpecError(f"failed to load spec: {exc}") from exc

    materialized = materialize(spec, spec_hash)

    adapter = build_adapter(spec.model)
    cache = InMemoryCache() if spec.run.cache else None
    engine = ExecutionEngine(adapter=adapter, cache=cache)

    case_results = [
        _run_case(spec, i, materialized, engine) for i in range(len(materialized.cases))
    ]
    session_verdict = resolve_session(case_results)

    artifact = ReplayArtifact(
        session_id=uuid.uuid4().hex,
        created_at=datetime.now(UTC),
        falsifyai_version=_pkg_version("falsifyai"),
        spec_hash=spec_hash,
        materialized_hash=materialized.materialized_hash,
        materialized=materialized,
        case_results=case_results,
        session_verdict=session_verdict,
    )

    store = _build_store(args.store_path)
    try:
        store.save_session(artifact)
        render.render_session(artifact, store_path=args.store_path)
    finally:
        # InMemoryStore has no close(); SQLiteStore does.
        close = getattr(store, "close", None)
        if callable(close):
            close()

    return render.exit_code_for(session_verdict.session_verdict)
