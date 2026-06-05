"""Real verdict resolver: stratified bootstrap CI + lightweight CONSISTENTLY_WRONG.

Replaces the PR #8 placeholder that returned `STABLE` / `FRAGILE` / `INSUFFICIENT`
based on a "passes / total" fraction. This module produces verdicts with
defensible statistical backing -- bootstrap CI per perturbation family,
worst-case selection across families, lightweight ground-truth contradiction
check for CONSISTENTLY_WRONG, and per-case + suite-level falsifiability.

Verdict priority (worst-first):

1. ``INSUFFICIENT`` -- no perturbed runs or no invariant results
2. ``CONSISTENTLY_WRONG`` -- every output (original + perturbed) violates the
   ground truth from ``expected.contains`` / ``expected.not_contains``
3. ``FRAGILE`` -- worst-case stratum CI lower bound below ``stable_threshold``
4. ``STABLE`` -- otherwise

The stratification keeps a single weak perturbation family from being drowned
by other families' data -- per [plan.md section 12](../../plan.md), "worst-case
stratified stability, not aggregate."

The bootstrap is seeded deterministically per case (``case_seed`` + a fixed
salt) so identical inputs always produce identical CIs.
"""

import hashlib

from falsifyai.invariants.base import EmbeddingBackend, Invariant
from falsifyai.oracles.base import OracleContext
from falsifyai.oracles.consistency import ConsistencyOracle
from falsifyai.replay.models import CaseResult, PerturbedRun, SessionVerdict
from falsifyai.spec.models import ExpectedSection
from falsifyai.verdict.models import Verdict
from falsifyai.verdict.stratify import (
    bootstrap_stability,
    stratify_by_family,
    worst_case_stratified,
)


def _bootstrap_seed_for_case(case_seed: int) -> int:
    """Derive a stable bootstrap seed from the case seed.

    Salting with ``"bootstrap"`` keeps this independent of any other RNG
    seeded from the same case_seed. The 32-bit truncation is required by
    numpy.random.default_rng on Windows.
    """
    payload = f"{case_seed}:bootstrap".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")


def resolve_case(
    *,
    case_id: str,
    original_input: str,
    original_execution,  # falsifyai.execution.models.Execution
    perturbed_runs: list[PerturbedRun],
    expected: ExpectedSection,
    invariants: list[Invariant],
    stable_threshold: float,
    case_seed: int,
    embedder: EmbeddingBackend | None = None,
) -> CaseResult:
    """Build the full case-level result, including stratified CI evidence.

    All keyword-only -- the signature is too wide for positional clarity.

    ``embedder`` is optional and only used by the ConsistencyOracle's
    reference-agreement path. When None (the default), consistency falls back to
    the ground-truth string check, identical to the pre-oracle behavior.
    """
    bootstrap_seed = _bootstrap_seed_for_case(case_seed)

    # Stratify perturbed runs into families and bootstrap each separately.
    strata = stratify_by_family(perturbed_runs)
    per_family_triples: dict[str, tuple[float, float, float]] = {}
    per_family_point: dict[str, float] = {}
    for family, passes in strata.items():
        triple = bootstrap_stability(passes, seed=bootstrap_seed)
        per_family_triples[family] = triple
        per_family_point[family] = triple[0]

    worst_family, stability, ci_low, ci_high = worst_case_stratified(per_family_triples)

    verdict = _decide_verdict(
        original_output=original_execution.output_text,
        perturbed_outputs=[r.execution.output_text for r in perturbed_runs],
        expected=expected,
        invariants=invariants,
        perturbed_runs=perturbed_runs,
        stability_ci_low=ci_low,
        stable_threshold=stable_threshold,
        embedder=embedder,
    )

    return CaseResult(
        case_id=case_id,
        original_input=original_input,
        original_execution=original_execution,
        perturbed=perturbed_runs,
        verdict=verdict,
        verdict_confidence=ci_low,  # semantic continuity with PR #8 era artifacts
        stability=stability,
        stability_ci_low=ci_low,
        stability_ci_high=ci_high,
        per_family_stability=per_family_point,
        worst_case_family=worst_family,
    )


def _decide_verdict(
    *,
    original_output: str,
    perturbed_outputs: list[str],
    expected: ExpectedSection,
    invariants: list[Invariant],
    perturbed_runs: list[PerturbedRun],
    stability_ci_low: float,
    stable_threshold: float,
    embedder: EmbeddingBackend | None = None,
) -> Verdict:
    """Apply the verdict priority chain.

    Order: INSUFFICIENT -> CONSISTENTLY_WRONG -> FRAGILE -> STABLE.
    """
    if not perturbed_runs or not invariants:
        return Verdict.INSUFFICIENT

    # CONSISTENTLY_WRONG must take priority over FRAGILE: the model could be
    # both unstable AND consistently wrong; the latter is the more dangerous
    # signal and the one the user needs to see. The ConsistencyOracle
    # pre-arbitrates into an OracleVerdict; the resolver consumes only its
    # ``triggered`` flag, so this stays one branch (see the branch-count
    # meta-test). Adding more oracles must not add branches here.
    consistency = ConsistencyOracle().evaluate(
        OracleContext(
            original_output=original_output,
            perturbed_outputs=perturbed_outputs,
            expected=expected,
            embedder=embedder,
        )
    )
    if consistency.triggered:
        return Verdict.CONSISTENTLY_WRONG

    if stability_ci_low < stable_threshold:
        return Verdict.FRAGILE

    return Verdict.STABLE


def resolve_session(
    case_results: list[CaseResult],
    *,
    falsifiability_score: float,
) -> SessionVerdict:
    """Roll case-level verdicts up into a session-level verdict.

    Priority (worst-first):
    1. Any CONSISTENTLY_WRONG -> CONSISTENTLY_WRONG
    2. Any FRAGILE -> FRAGILE
    3. All INSUFFICIENT -> INSUFFICIENT
    4. Otherwise -> STABLE

    Confidence is the mean of per-case confidences (0.0 on empty input).
    """
    fragile_count = sum(1 for c in case_results if c.verdict is Verdict.FRAGILE)
    consistently_wrong_count = sum(
        1 for c in case_results if c.verdict is Verdict.CONSISTENTLY_WRONG
    )
    case_count = len(case_results)

    if case_count == 0:
        verdict = Verdict.INSUFFICIENT
        confidence = 0.0
    else:
        if consistently_wrong_count > 0:
            verdict = Verdict.CONSISTENTLY_WRONG
        elif fragile_count > 0:
            verdict = Verdict.FRAGILE
        elif all(c.verdict is Verdict.INSUFFICIENT for c in case_results):
            verdict = Verdict.INSUFFICIENT
        else:
            verdict = Verdict.STABLE
        confidence = sum(c.verdict_confidence for c in case_results) / case_count

    return SessionVerdict(
        session_verdict=verdict,
        confidence=confidence,
        case_count=case_count,
        fragile_count=fragile_count,
        consistently_wrong_count=consistently_wrong_count,
        falsifyai_falsifiability_score=falsifiability_score,
    )
