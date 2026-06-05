"""``falsifyai minimize <spec> [--case <id>]`` — smallest perturbation that breaks a case.

On-thesis with the project's evidence-density principle: the single *smallest*
perturbation that flips a case out of STABLE is the maximally informative piece
of evidence about its fragility. Instead of reporting "fails under 5% noise and
10% and 20%...", minimize reports the threshold — the minimal falsifier.

It sweeps a perturbation family's strength from low to high, re-running the case
(execute -> judge -> resolve) at each level, and stops at the first strength that
produces a non-STABLE verdict. Ascending order + early stop means the reported
strength is genuinely minimal among the tested levels, and the search costs no
more model calls than it must.

Unlike ``matrix`` / ``timeline`` (read-only consumers of stored artifacts),
``minimize`` is an *orchestrator*: it generates, executes, and resolves, exactly
like ``run``. It therefore legitimately imports the resolver.
"""

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field

from falsifyai.cli.errors import ConfigError, InfrastructureError, SpecError
from falsifyai.cli.run import _build_request, build_adapter
from falsifyai.execution.cache import InMemoryCache
from falsifyai.execution.engine import ExecutionEngine
from falsifyai.execution.errors import ExecutionError
from falsifyai.invariants.registry import build_invariant
from falsifyai.perturbation.typo_noise import TypoNoise
from falsifyai.perturbation.unicode_chars import UnicodePerturbation
from falsifyai.replay.models import PerturbedRun
from falsifyai.spec.errors import SpecLoadError
from falsifyai.spec.loader import load_spec
from falsifyai.spec.models import CaseSpec, Spec
from falsifyai.verdict.models import Verdict
from falsifyai.verdict.resolver import resolve_case

_DEFAULT_LEVELS = [0.02, 0.05, 0.1, 0.2, 0.4, 0.8]
_SUPPORTED_FAMILIES = ("typo_noise", "unicode")


@dataclass(frozen=True)
class FalsifierLevel:
    strength: float
    verdict: Verdict
    broke: bool


@dataclass(frozen=True)
class MinimizeReport:
    case_id: str
    family: str
    levels: list[FalsifierLevel] = field(default_factory=list)
    minimal_strength: float | None = None
    minimal_verdict: Verdict | None = None

    @property
    def found(self) -> bool:
        return self.minimal_strength is not None


def search_minimal_falsifier(
    strengths: list[float],
    evaluate_at: Callable[[float], Verdict],
    *,
    case_id: str,
    family: str,
) -> MinimizeReport:
    """Sweep strengths ascending; stop at the first that yields a non-STABLE verdict.

    Pure orchestration over ``evaluate_at`` so the search is testable without a
    model: ``evaluate_at(strength)`` returns the resolved verdict at that level.
    """
    levels: list[FalsifierLevel] = []
    for strength in sorted(strengths):
        verdict = evaluate_at(strength)
        broke = verdict is not Verdict.STABLE
        levels.append(FalsifierLevel(strength=strength, verdict=verdict, broke=broke))
        if broke:
            return MinimizeReport(
                case_id=case_id,
                family=family,
                levels=levels,
                minimal_strength=strength,
                minimal_verdict=verdict,
            )
    return MinimizeReport(case_id=case_id, family=family, levels=levels)


def _make_perturbation(family: str, strength: float, samples: int):
    if family == "typo_noise":
        return TypoNoise(count=samples, rate=strength)
    if family == "unicode":
        return UnicodePerturbation(
            methods=["invisible_space", "zero_width", "homoglyph"],
            count=samples,
            rate=strength,
        )
    raise ConfigError(
        f"unsupported family {family!r} for minimize; choose one of {list(_SUPPORTED_FAMILIES)}"
    )


def _select_case(spec: Spec, case_id: str | None) -> CaseSpec:
    if case_id is None:
        return spec.cases[0]
    for case in spec.cases:
        if case.id == case_id:
            return case
    raise InfrastructureError(f"case {case_id!r} not found in spec")


def _render(report: MinimizeReport) -> None:
    print(f"falsifyai minimize | case: {report.case_id} | family: {report.family}")
    print("=" * 60)
    for level in report.levels:
        marker = "  <-- minimal falsifier" if level.broke else ""
        print(f"  strength {level.strength:<6} ->  {level.verdict.value.upper()}{marker}")
    print("=" * 60)
    if report.found:
        print(
            f"minimal falsifier: {report.family} strength={report.minimal_strength} "
            f"-> {report.minimal_verdict.value.upper()}"
        )
    else:
        widest = max((level.strength for level in report.levels), default=0.0)
        print(f"no falsifier found across tested levels (robust up to strength={widest})")


def cmd_minimize(args: argparse.Namespace) -> int:
    """Entry point for the ``minimize`` subcommand. Returns an exit code.

    Exit: 0 on a completed search (informational — finding a falsifier is the
    expected outcome, not an error); 3 on infrastructure/spec failure.
    """
    if args.family not in _SUPPORTED_FAMILIES:
        raise ConfigError(
            f"unsupported family {args.family!r}; choose one of {list(_SUPPORTED_FAMILIES)}"
        )
    levels = _parse_levels(args.levels) if args.levels else list(_DEFAULT_LEVELS)

    try:
        spec, _ = load_spec(args.spec_path)
    except SpecLoadError as exc:
        raise SpecError(f"failed to load spec: {exc}") from exc

    case_spec = _select_case(spec, args.case)
    invariants = [build_invariant(inv_spec) for inv_spec in case_spec.invariants]

    adapter = build_adapter(spec.model)
    engine = ExecutionEngine(adapter=adapter, cache=InMemoryCache())

    try:
        original_exec = engine.execute(_build_request(spec.model, spec.run, case_spec.input.text))
    except ExecutionError as exc:
        raise InfrastructureError(
            f"baseline execution failed for case '{case_spec.id}': {exc}"
        ) from exc

    def _evaluate_at(strength: float) -> Verdict:
        perturbation = _make_perturbation(args.family, strength, args.samples)
        perturbed_inputs = perturbation.apply(case_spec.input.text, seed=spec.run.seed)
        perturbed_runs: list[PerturbedRun] = []
        for pi in perturbed_inputs:
            try:
                exec_result = engine.execute(_build_request(spec.model, spec.run, pi.text))
            except ExecutionError as exc:
                raise InfrastructureError(
                    f"perturbed execution failed for case '{case_spec.id}': {exc}"
                ) from exc
            inv_results = [
                inv.check(original_exec.output_text, exec_result.output_text, {})
                for inv in invariants
            ]
            perturbed_runs.append(
                PerturbedRun(
                    perturbed_input=pi, execution=exec_result, invariant_results=inv_results
                )
            )
        case_result = resolve_case(
            case_id=case_spec.id,
            original_input=case_spec.input.text,
            original_execution=original_exec,
            perturbed_runs=perturbed_runs,
            expected=case_spec.expected,
            invariants=invariants,
            stable_threshold=case_spec.verdict_config.stable_threshold,
            case_seed=spec.run.seed,
        )
        return case_result.verdict

    report = search_minimal_falsifier(
        levels, _evaluate_at, case_id=case_spec.id, family=args.family
    )
    _render(report)
    return 0


def _parse_levels(raw: str) -> list[float]:
    try:
        return [float(x) for x in raw.split(",") if x.strip()]
    except ValueError as exc:
        raise ConfigError(f"invalid --levels {raw!r}; expected comma-separated floats") from exc


__all__ = ["cmd_minimize", "search_minimal_falsifier", "MinimizeReport", "FalsifierLevel"]
