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
from falsifyai.oracles.contradiction import ContradictionOracle
from falsifyai.oracles.grounding import GroundingOracle
from falsifyai.oracles.hallucination import HallucinationOracle
from falsifyai.oracles.meta import MetaOracle
from falsifyai.oracles.nli import NLIBackend
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
    nli: NLIBackend | None = None,
) -> CaseResult:
    """Build the full case-level result, including stratified CI evidence.

    All keyword-only -- the signature is too wide for positional clarity.

    ``embedder`` is optional and only used by the ConsistencyOracle's
    reference-agreement path. When None (the default), consistency falls back to
    the ground-truth string check, identical to the pre-oracle behavior.

    ``nli`` is optional and drives the PR-J semantic oracles (contradiction /
    hallucination / grounding). When None (the default), those oracles degrade to
    ``triggered=False`` and contribute nothing -- the resolver's emitted verdict
    is unchanged. Their contributions feed the meta-oracle's conflict detection
    and the replay artifact only when a backend is supplied.
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
        nli=nli,
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
    nli: NLIBackend | None = None,
) -> Verdict:
    """Apply the verdict priority chain.

    Order: INSUFFICIENT -> CONSISTENTLY_WRONG -> FRAGILE -> STABLE.

    PR-J note: the semantic oracles (contradiction / hallucination / grounding)
    are evaluated here and fed to the meta-oracle as peers, but no resolver
    branch consumes their contributions yet -- the emitted verdict set is
    unchanged (branch count stays 5). PR-K adds the branches that turn their
    evidence into INFORMATION_PRESENT / AMBIGUOUS / etc.
    """
    if not perturbed_runs or not invariants:
        return Verdict.INSUFFICIENT

    # Run primary oracles once, then consume their pre-arbitrated verdicts by
    # precedence. Each oracle collapses to one OracleVerdict, so adding an
    # oracle never adds a branch here (see the branch-count meta-test); only
    # adding a new verdict *class* does.
    oracle_context = OracleContext(
        original_output=original_output,
        perturbed_outputs=perturbed_outputs,
        expected=expected,
        embedder=embedder,
    )
    consistency = ConsistencyOracle().evaluate(oracle_context)

    # PR-J semantic oracles. Inert (triggered=False) when ``nli`` is None, which
    # is the default for ``falsifyai run`` -- so they change nothing in production
    # runs that have not opted into the [nli] extra. When a backend is supplied
    # they become live peers, which is what makes the meta-oracle's oracle-conflict
    # detection reachable (it needs >= 2 primary oracles disagreeing).
    semantic_peers = [
        ContradictionOracle(nli).evaluate(oracle_context),
        HallucinationOracle(nli).evaluate(oracle_context),
        GroundingOracle(nli).evaluate(oracle_context),
    ]

    # Meta-oracle is the SOLE source of INVALID_EVAL. It sees the full invariant
    # matrix (baseline + every perturbed run) so it can tell a malformed
    # invariant (fails even the clean baseline) from a genuinely failing model
    # (explained by a primary oracle, so degeneration is suppressed). If the
    # eval itself is broken, no other verdict is trustworthy -> top priority.
    baseline_results = [inv.check(original_output, original_output, {}) for inv in invariants]
    invariant_matrix = [baseline_results, *(run.invariant_results for run in perturbed_runs)]
    meta = MetaOracle().evaluate(
        OracleContext(
            original_output=original_output,
            perturbed_outputs=perturbed_outputs,
            expected=expected,
            embedder=embedder,
            invariant_results=invariant_matrix,
            peer_verdicts=[consistency, *semantic_peers],
        )
    )
    if meta.triggered:
        return Verdict.INVALID_EVAL

    # CONSISTENTLY_WRONG must take priority over FRAGILE: the model could be both
    # unstable AND consistently wrong; the latter is the more dangerous signal.
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
    invalid_eval_count = sum(1 for c in case_results if c.verdict is Verdict.INVALID_EVAL)
    case_count = len(case_results)

    if case_count == 0:
        verdict = Verdict.INSUFFICIENT
        confidence = 0.0
    else:
        # INVALID_EVAL dominates: if any case's evaluation is broken, the
        # session result cannot be trusted, regardless of other verdicts.
        if invalid_eval_count > 0:
            verdict = Verdict.INVALID_EVAL
        elif consistently_wrong_count > 0:
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
        invalid_eval_count=invalid_eval_count,
        falsifyai_falsifiability_score=falsifiability_score,
    )
