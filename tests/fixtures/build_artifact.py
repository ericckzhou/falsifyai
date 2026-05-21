"""Builder helpers for realistic ReplayArtifact fixtures.

Used by test_replay_serialize.py and test_replay_store_contract.py to avoid
duplicating ~80 LOC of construction boilerplate across tests.

Construction is pure data — no MockAdapter or MockEmbedder is invoked here.
The artifact shape is what matters; the *contents* are realistic enough to
exercise serialization / persistence without coupling tests to runtime
behavior of any specific perturbation or invariant implementation.
"""

from datetime import UTC, datetime

from falsifyai.execution.models import Execution, ModelRequest
from falsifyai.invariants.base import InvariantResult, Severity
from falsifyai.perturbation.base import (
    PerturbationCategory,
    PerturbationLineage,
    PerturbedInput,
    hash_input,
)
from falsifyai.replay.models import (
    CaseResult,
    PerturbedRun,
    ReplayArtifact,
    SessionVerdict,
)
from falsifyai.spec.materializer import MaterializedCase, MaterializedSpec
from falsifyai.spec.models import (
    ExpectedSection,
    ModelConfig,
    RunConfig,
    VerdictConfig,
)
from falsifyai.verdict.models import Verdict

_ORIGINAL_INPUT = "What is the capital of France?"
_OUTPUT_TEXT = "Paris is the capital of France."


def _request(prompt: str) -> ModelRequest:
    return ModelRequest(
        provider="mock",
        model="mock-model",
        prompt=prompt,
        temperature=0.0,
        max_tokens=128,
        seed=42,
        timeout_seconds=30,
    )


def _execution(prompt: str, output: str = _OUTPUT_TEXT, cached: bool = False) -> Execution:
    return Execution(
        request=_request(prompt),
        output_text=output,
        latency_ms=12.3,
        prompt_tokens=8,
        completion_tokens=7,
        cached=cached,
        seed_provided=True,
    )


def _typo_perturbation(text: str, sample_index: int, seed: int) -> PerturbedInput:
    return PerturbedInput(
        text=text,
        lineage=PerturbationLineage(
            perturbation_type="typo_noise",
            category=PerturbationCategory.LEXICAL,
            method="substitute",
            seed=seed,
            params={"sample_index": sample_index, "intensity": 0.1},
            parent_input_hash=hash_input(_ORIGINAL_INPUT),
        ),
        validity_score=0.95,
    )


def _casing_perturbation(text: str, variant: str, seed: int) -> PerturbedInput:
    return PerturbedInput(
        text=text,
        lineage=PerturbationLineage(
            perturbation_type="casing_variant",
            category=PerturbationCategory.LEXICAL,
            method=variant,
            seed=seed,
            params={"sample_index": 0, "variant": variant},
            parent_input_hash=hash_input(_ORIGINAL_INPUT),
        ),
        validity_score=1.0,
    )


def _contains_result(passed: bool = True) -> InvariantResult:
    return InvariantResult(
        invariant_name="contains",
        passed=passed,
        score=1.0 if passed else 0.0,
        details="all values present" if passed else "missing: ['Paris']",
        severity=Severity.HIGH,
        evidence={"missing": [] if passed else ["Paris"]},
    )


def _semantic_result(similarity: float) -> InvariantResult:
    return InvariantResult(
        invariant_name="semantic_equivalence",
        passed=similarity >= 0.85,
        score=similarity,
        details=f"cosine={similarity:.3f} vs threshold=0.85",
        severity=Severity.HIGH,
        evidence={"similarity": similarity, "threshold": 0.85},
    )


def _materialized_case(perturbations: list[PerturbedInput]) -> MaterializedCase:
    return MaterializedCase(
        case_id="capital_of_france",
        case_seed=1234567890,
        original_input=_ORIGINAL_INPUT,
        realized_perturbations=perturbations,
        tags=["geography", "factual"],
        expected=ExpectedSection(contains=["Paris"]),
        verdict_config=VerdictConfig(),
    )


def _materialized_spec(case: MaterializedCase) -> MaterializedSpec:
    return MaterializedSpec(
        spec_hash="a" * 64,
        materialized_hash="b" * 64,
        session_seed=42,
        falsifyai_version="0.0.1",
        model=ModelConfig(provider="mock", model="mock-model"),
        run=RunConfig(seed=42),
        cases=[case],
    )


def make_artifact(
    *,
    session_id: str = "11111111-1111-1111-1111-111111111111",
    verdict: Verdict = Verdict.STABLE,
    created_at: datetime | None = None,
) -> ReplayArtifact:
    """Build a realistic ReplayArtifact for tests.

    One case with two perturbations: one ``typo_noise`` sample and one
    ``casing_variant`` (upper). Each perturbation is judged by both invariants
    (``contains`` + ``semantic_equivalence``). The original baseline execution
    is also present.
    """
    typo = _typo_perturbation("What is the captial of France?", sample_index=0, seed=11)
    casing = _casing_perturbation("WHAT IS THE CAPITAL OF FRANCE?", variant="upper", seed=22)
    perturbations = [typo, casing]

    perturbed_runs = [
        PerturbedRun(
            perturbed_input=typo,
            execution=_execution(prompt=typo.text, output=_OUTPUT_TEXT),
            invariant_results=[_contains_result(passed=True), _semantic_result(0.97)],
        ),
        PerturbedRun(
            perturbed_input=casing,
            execution=_execution(prompt=casing.text, output=_OUTPUT_TEXT, cached=True),
            invariant_results=[_contains_result(passed=True), _semantic_result(0.99)],
        ),
    ]

    case_result = CaseResult(
        case_id="capital_of_france",
        original_input=_ORIGINAL_INPUT,
        original_execution=_execution(prompt=_ORIGINAL_INPUT),
        perturbed=perturbed_runs,
        verdict=verdict,
        verdict_confidence=0.92,
        # PR #11 fields: realistic-but-fixed values for fixture stability.
        stability=0.92,
        stability_ci_low=0.88,
        stability_ci_high=0.96,
        per_family_stability={"typo_noise": 0.85, "casing_variant": 1.0},
        worst_case_family="typo_noise",
    )

    materialized = _materialized_spec(_materialized_case(perturbations))

    return ReplayArtifact(
        session_id=session_id,
        created_at=created_at or datetime(2026, 5, 21, 14, 30, 0, tzinfo=UTC),
        falsifyai_version="0.0.1",
        spec_hash=materialized.spec_hash,
        materialized_hash=materialized.materialized_hash,
        materialized=materialized,
        case_results=[case_result],
        session_verdict=SessionVerdict(
            session_verdict=verdict,
            confidence=0.92,
            case_count=1,
            fragile_count=1 if verdict is Verdict.FRAGILE else 0,
            consistently_wrong_count=1 if verdict is Verdict.CONSISTENTLY_WRONG else 0,
            falsifyai_falsifiability_score=0.65,
        ),
    )
