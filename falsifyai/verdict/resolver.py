"""Real verdict resolver: stratified bootstrap CI + oracle-arbitrated 9-verdict taxonomy.

Replaces the PR #8 placeholder that returned `STABLE` / `FRAGILE` / `INSUFFICIENT`
based on a "passes / total" fraction. This module produces verdicts with
defensible statistical backing -- bootstrap CI per perturbation family,
worst-case selection across families, lightweight ground-truth contradiction
check for CONSISTENTLY_WRONG, and per-case + suite-level falsifiability.

Verdict priority (worst/most-certain first), per ``resolve_case`` below and
plan.md section 13.1::

    INSUFFICIENT             -- no perturbed runs or no invariant results
    INVALID_EVAL             -- meta-oracle: the eval itself is broken (sole source)
    CONSISTENTLY_WRONG       -- consistent, confident, and contradicts ground truth
    -- instability band (worst-case stratum CI lower bound below the stable bar) --
    ADVERSARIALLY_VULNERABLE -- one family collapses while others hold (targeted)
    FRAGILE                  -- diffuse instability; even the CI ceiling is low
    AMBIGUOUS                -- ran but cannot discriminate (CI too wide)
    -- stable band (worst-case CI lower bound cleared the stable bar) --
    INFORMATION_NULL         -- structurally stable but semantically empty
    INFORMATION_PRESENT      -- stable AND grounding confirmed (gold standard)
    STABLE                   -- consistent under perturbation; no grounding claim

This module shipped (PR #11) with a 4-verdict chain
(``INSUFFICIENT -> CONSISTENTLY_WRONG -> FRAGILE -> STABLE``); the 0.6.x resolver
emits the full 9-class taxonomy above. The single-condition-per-branch discipline
is policed by ``tests/meta/test_resolver_branch_count.py``.

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
from falsifyai.oracles.information_null import InformationNullOracle
from falsifyai.oracles.meta import MetaOracle
from falsifyai.oracles.nli import NLIBackend
from falsifyai.replay.models import CaseResult, PerturbedRun, SessionVerdict
from falsifyai.spec.models import ExpectedSection
from falsifyai.verdict.models import Verdict
from falsifyai.verdict.stratify import (
    bootstrap_stability,
    failure_shape,
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
    fragile_threshold: float = 0.5,
    embedder: EmbeddingBackend | None = None,
    nli: NLIBackend | None = None,
) -> CaseResult:
    """Build the full case-level result, including stratified CI evidence.

    All keyword-only -- the signature is too wide for positional clarity.

    ``stable_threshold`` / ``fragile_threshold`` bound the confidence bands: a
    worst-case CI lower bound at/above ``stable_threshold`` is confidently stable;
    a CI *upper* bound below ``fragile_threshold`` is confidently broken; the band
    between them (a wide CI) is AMBIGUOUS -- the eval ran but cannot discriminate.

    ``embedder`` is optional and only used by the ConsistencyOracle's
    reference-agreement path. When None (the default), consistency falls back to
    the ground-truth string check, identical to the pre-oracle behavior.

    ``nli`` is optional and drives the PR-J semantic oracles (contradiction /
    hallucination / grounding). When None (the default), those oracles degrade to
    ``triggered=False`` and contribute nothing. The InformationNullOracle and the
    stratified failure-shape read need no backend, so INFORMATION_NULL and
    ADVERSARIALLY_VULNERABLE are reachable without opting into [nli].
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
    shape = failure_shape(per_family_triples)

    verdict = _decide_verdict(
        original_output=original_execution.output_text,
        perturbed_outputs=[r.execution.output_text for r in perturbed_runs],
        expected=expected,
        invariants=invariants,
        perturbed_runs=perturbed_runs,
        stability_ci_low=ci_low,
        stability_ci_high=ci_high,
        stable_threshold=stable_threshold,
        fragile_threshold=fragile_threshold,
        shape=shape,
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
    stability_ci_high: float,
    stable_threshold: float,
    fragile_threshold: float,
    shape: str,
    embedder: EmbeddingBackend | None = None,
    nli: NLIBackend | None = None,
) -> Verdict:
    """Apply the 8-verdict priority chain (plan.md §13.1), worst/most-certain first.

    INSUFFICIENT -> INVALID_EVAL -> CONSISTENTLY_WRONG -> [instability band:
    ADVERSARIALLY_VULNERABLE | FRAGILE | AMBIGUOUS] -> [stable band:
    INFORMATION_NULL | INFORMATION_PRESENT | STABLE].

    Discipline (``.claude/CLAUDE.md`` + ``tests/meta/test_resolver_branch_count``):
    every branch is a single condition over an *already-resolved* signal -- an
    oracle's pre-arbitrated contribution, or a stratified-stats field computed
    upstream (``shape``, the CI bounds). No detection logic lives here. The branch
    count grows from 5 to 9 because four genuine new verdict *classes* are wired in
    -- the one-time growth the meta-test sanctions -- not because an oracle leaked
    a branch. Each verdict class appears in exactly one ``return``.
    """
    if not perturbed_runs or not invariants:
        return Verdict.INSUFFICIENT

    oracle_context = OracleContext(
        original_output=original_output,
        perturbed_outputs=perturbed_outputs,
        expected=expected,
        embedder=embedder,
    )
    consistency = ConsistencyOracle().evaluate(oracle_context)

    # PR-J semantic oracles (NLI). Inert when ``nli`` is None. They are meta-oracle
    # peers, so their disagreement is what makes oracle-conflict detection live.
    semantic_peers = [
        ContradictionOracle(nli).evaluate(oracle_context),
        HallucinationOracle(nli).evaluate(oracle_context),
        GroundingOracle(nli).evaluate(oracle_context),
    ]
    # InformationNullOracle needs no backend. It is NOT a meta peer (a shape
    # detector, not a truth oracle -- it must not manufacture an oracle conflict).
    info_null = InformationNullOracle().evaluate(oracle_context)

    # Meta-oracle is the SOLE source of INVALID_EVAL. It sees the full invariant
    # matrix (baseline + every perturbed run) so it can tell a malformed invariant
    # (fails even the clean baseline) from a genuinely failing model. If the eval
    # itself is broken, no other verdict is trustworthy -> top priority.
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

    # Pre-arbitrated contributions, collapsed to a set the branches read by name.
    contributions = {
        v.verdict_contribution
        for v in (consistency, *semantic_peers, info_null)
        if v.triggered and v.verdict_contribution is not None
    }

    # CONSISTENTLY_WRONG: consistent, confident, and known-wrong. Highest-priority
    # substantive verdict -- more dangerous than any instability signal.
    if Verdict.CONSISTENTLY_WRONG in contributions:
        return Verdict.CONSISTENTLY_WRONG

    # Instability band: the worst-case family's CI lower bound failed the stable
    # bar. Three sub-cases by *shape* and *certainty*.
    if stability_ci_low < stable_threshold:
        # Targeted: one family collapses while others hold -> a known attack vector.
        if shape == "targeted":
            return Verdict.ADVERSARIALLY_VULNERABLE
        # Confidently broken: even the optimistic CI upper bound is below the
        # fragile bar -> diffuse, real fragility.
        if stability_ci_high < fragile_threshold:
            return Verdict.FRAGILE
        # Wide CI: low floor but high ceiling -- the eval ran but cannot
        # discriminate (typically small N). Honest "we don't know yet."
        return Verdict.AMBIGUOUS

    # Stable band: worst-case CI lower bound cleared the stable bar.
    # INFORMATION_NULL: stable in structure but empty of information (refusals).
    if Verdict.INFORMATION_NULL in contributions:
        return Verdict.INFORMATION_NULL
    # INFORMATION_PRESENT: stable AND grounding confirmed -- the gold standard.
    if Verdict.INFORMATION_PRESENT in contributions:
        return Verdict.INFORMATION_PRESENT

    return Verdict.STABLE


def resolve_session(
    case_results: list[CaseResult],
    *,
    falsifiability_score: float,
) -> SessionVerdict:
    """Roll case-level verdicts up into a session-level verdict.

    Priority (worst-first): INVALID_EVAL -> CONSISTENTLY_WRONG ->
    ADVERSARIALLY_VULNERABLE -> FRAGILE -> AMBIGUOUS -> INFORMATION_NULL ->
    (all INSUFFICIENT) INSUFFICIENT -> (all INFORMATION_PRESENT)
    INFORMATION_PRESENT -> STABLE. The session takes its colour from its worst
    case: one broken case taints the run.

    Confidence is the mean of per-case confidences (0.0 on empty input).
    """
    fragile_count = sum(1 for c in case_results if c.verdict is Verdict.FRAGILE)
    consistently_wrong_count = sum(
        1 for c in case_results if c.verdict is Verdict.CONSISTENTLY_WRONG
    )
    invalid_eval_count = sum(1 for c in case_results if c.verdict is Verdict.INVALID_EVAL)
    case_count = len(case_results)

    def _any(verdict: Verdict) -> bool:
        return any(c.verdict is verdict for c in case_results)

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
        elif _any(Verdict.ADVERSARIALLY_VULNERABLE):
            verdict = Verdict.ADVERSARIALLY_VULNERABLE
        elif fragile_count > 0:
            verdict = Verdict.FRAGILE
        elif _any(Verdict.AMBIGUOUS):
            verdict = Verdict.AMBIGUOUS
        elif _any(Verdict.INFORMATION_NULL):
            verdict = Verdict.INFORMATION_NULL
        elif all(c.verdict is Verdict.INSUFFICIENT for c in case_results):
            verdict = Verdict.INSUFFICIENT
        elif all(c.verdict is Verdict.INFORMATION_PRESENT for c in case_results):
            verdict = Verdict.INFORMATION_PRESENT
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
