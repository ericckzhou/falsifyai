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
import sys
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
from falsifyai.falsifiability.score import (
    LOW_FALSIFIABILITY_THRESHOLD,
    case_falsifiability,
    suite_falsifiability,
)
from falsifyai.invariants.base import Invariant
from falsifyai.invariants.registry import build_invariant
from falsifyai.replay.in_memory_store import InMemoryStore
from falsifyai.replay.models import CaseResult, CliInvocation, PerturbedRun, ReplayArtifact
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


def _capture_cli_invocation(argv: list[str] | tuple[str, ...]) -> CliInvocation:
    """Capture the CLI invocation that produced this run (PR-35).

    Normalizes ``argv[0]`` to ``"falsifyai"`` regardless of entry path
    (entry-point launcher, ``python -m falsifyai.cli.main``, direct script
    invocation) so the captured argv is portable and replay-stable across
    install methods. All subsequent tokens preserved verbatim from
    ``sys.argv``.

    **Semantic boundary:** this records *what command produced the artifact*,
    NOT a guarantee that re-running it will produce identical outputs. See
    :class:`falsifyai.replay.models.CliInvocation` for the full capture
    contract and exclusion list.

    **Future risk:** if FalsifyAI ever adds an auth-bearing CLI flag (e.g.,
    ``--anthropic-api-key``), this helper MUST be updated to redact that
    flag's value (replacing with a ``[REDACTED]`` sentinel) at the same time
    as the flag lands. Today no such flag exists; argv carries only spec
    paths and store paths.
    """
    tokens = tuple(argv)
    if not tokens:
        return CliInvocation(argv=("falsifyai",), falsifyai_version=_pkg_version("falsifyai"))
    return CliInvocation(
        argv=("falsifyai",) + tokens[1:],
        falsifyai_version=_pkg_version("falsifyai"),
    )


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
) -> tuple[CaseResult, list[Invariant]]:
    """Run a single case end-to-end. Returns the CaseResult and the list of
    runtime Invariant instances built from the case spec (the caller needs them
    for falsifiability scoring).
    """
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

    case_result = resolve_case(
        case_id=case_spec.id,
        original_input=mcase.original_input,
        original_execution=original_exec,
        perturbed_runs=perturbed_runs,
        expected=case_spec.expected,
        invariants=invariants,
        stable_threshold=case_spec.verdict_config.stable_threshold,
        fragile_threshold=case_spec.verdict_config.fragile_threshold,
        case_seed=mcase.case_seed,
    )
    return case_result, invariants


def cmd_run(args: argparse.Namespace) -> int:
    """Entry point for the ``run`` subcommand. Returns an exit code."""
    # PR-35: capture invocation FIRST, before anything else can mutate sys.argv.
    # Single capture point — read-only consumer commands never call this.
    cli_invocation = _capture_cli_invocation(sys.argv)

    try:
        spec, spec_hash = load_spec(args.spec_path)
    except SpecLoadError as exc:
        raise SpecError(f"failed to load spec: {exc}") from exc

    # Build the adapter BEFORE materialization. Most perturbations are pure
    # functions of (input, seed) and don't need it, but paraphrase calls the
    # LLM at materialization-time to produce its rewrites. The same adapter
    # is then reused by the execution engine below.
    adapter = build_adapter(spec.model)

    materialized = materialize(spec, spec_hash, adapter=adapter)

    cache = InMemoryCache() if spec.run.cache else None
    engine = ExecutionEngine(adapter=adapter, cache=cache)

    case_results: list[CaseResult] = []
    case_falsifiability_scores: list[float] = []
    for i in range(len(materialized.cases)):
        case_result, invariants = _run_case(spec, i, materialized, engine)
        case_results.append(case_result)
        case_falsifiability_scores.append(case_falsifiability(invariants))

    falsifiability_score = suite_falsifiability(case_falsifiability_scores)
    session_verdict = resolve_session(case_results, falsifiability_score=falsifiability_score)

    if falsifiability_score < LOW_FALSIFIABILITY_THRESHOLD:
        print(
            f"falsifyai: warning: low suite falsifiability "
            f"({falsifiability_score:.2f} < {LOW_FALSIFIABILITY_THRESHOLD}); "
            f"invariants may be too permissive to catch real failures.",
            file=sys.stderr,
        )

    artifact = ReplayArtifact(
        session_id=uuid.uuid4().hex,
        created_at=datetime.now(UTC),
        falsifyai_version=_pkg_version("falsifyai"),
        spec_hash=spec_hash,
        materialized_hash=materialized.materialized_hash,
        materialized=materialized,
        case_results=case_results,
        session_verdict=session_verdict,
        cli_invocation=cli_invocation,
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
