"""Stratified bootstrap stability per perturbation family.

The honest-confidence machinery that replaces the placeholder's
``passes / total`` fraction. Three layers:

- :func:`bootstrap_stability` -- given a list of pass/fail booleans,
  return ``(point_estimate, ci_low, ci_high)`` via percentile bootstrap.
- :func:`stratify_by_family` -- group per-run pass/fail booleans by
  ``lineage.perturbation_type``. A *run* passes iff every invariant on
  it passes; a single failing invariant counts the whole run as fail.
- :func:`worst_case_stratified` -- given per-family stability triples,
  return the family with the lowest CI lower bound. Per [plan.md
  section 12](../../plan.md): "worst-case stratified stability, not
  aggregate." Catches "model survives noise but breaks on paraphrase."

The bootstrap uses ``numpy.random.default_rng(seed)`` for reproducibility:
identical inputs + identical seed produce identical CIs.
"""

from collections import defaultdict
from typing import Final

import numpy as np

from falsifyai.replay.models import PerturbedRun

DEFAULT_BOOTSTRAP_SAMPLES: Final[int] = 1000
DEFAULT_CI_PERCENTILE: Final[float] = 0.95


def bootstrap_stability(
    passes: list[bool],
    *,
    seed: int,
    n_resamples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    ci: float = DEFAULT_CI_PERCENTILE,
) -> tuple[float, float, float]:
    """Percentile bootstrap CI for the pass rate of a list of trials.

    Returns ``(point_estimate, ci_low, ci_high)``. Empty input returns
    all zeros. Same ``seed`` + same input always returns the same CI.

    Note: when every trial agrees (all True or all False), every resample
    yields the same point estimate, so the CI collapses to that estimate.
    That is correct -- with no within-sample variance, the bootstrap has
    nothing to spread.
    """
    if not passes:
        return 0.0, 0.0, 0.0

    n = len(passes)
    point = sum(passes) / n
    arr = np.array(passes, dtype=np.float64)
    rng = np.random.default_rng(seed)

    # Resample indices with replacement; compute the mean per resample.
    indices = rng.integers(low=0, high=n, size=(n_resamples, n))
    resampled_means = arr[indices].mean(axis=1)

    alpha = (1.0 - ci) / 2.0
    lo = float(np.quantile(resampled_means, alpha))
    hi = float(np.quantile(resampled_means, 1.0 - alpha))
    return point, lo, hi


def stratify_by_family(perturbed_runs: list[PerturbedRun]) -> dict[str, list[bool]]:
    """Group per-run pass/fail booleans by perturbation family.

    A run *passes* iff every invariant_result on it passed. Returns a
    map ``{family_name: [bool, bool, ...]}`` ordered by encounter.
    """
    strata: dict[str, list[bool]] = defaultdict(list)
    for run in perturbed_runs:
        family = run.perturbed_input.lineage.perturbation_type
        run_passed = all(r.passed for r in run.invariant_results)
        strata[family].append(run_passed)
    return dict(strata)


# A family whose CI lower bound is below this is "broken"; at/above _HOLDING_CI
# it is "holding". The gap between the two bands is what separates a *targeted*
# attack (some families collapse while others hold) from *diffuse* fragility.
_BROKEN_CI: Final[float] = 0.5
_HOLDING_CI: Final[float] = 0.8


def failure_shape(per_family: dict[str, tuple[float, float, float]]) -> str:
    """Classify the *shape* of failure across perturbation families.

    Returns one of:

    - ``"targeted"`` -- at least one family is broken (CI low < 0.5) AND at least
      one other family is holding (CI low >= 0.8). A known attack vector: the
      model survives most perturbations but one family reliably breaks it. This
      is the ADVERSARIALLY_VULNERABLE signal.
    - ``"diffuse"`` -- one or more families are broken but none is clearly
      holding. Broad instability with no single dominating attack -> FRAGILE.
    - ``"none"`` -- no family is broken.

    Pure interpretation of evidence the resolver already computes (the per-family
    bootstrap triples); no new evidence generation. Requires >= 2 families to call
    a failure *targeted* -- a single broken family is ``"diffuse"`` (there is no
    other family for it to stand out against).
    """
    if not per_family:
        return "none"
    ci_lows = [lo for (_point, lo, _hi) in per_family.values()]
    broken = [lo for lo in ci_lows if lo < _BROKEN_CI]
    if not broken:
        return "none"
    if len(per_family) < 2:
        return "diffuse"
    holding = [lo for lo in ci_lows if lo >= _HOLDING_CI]
    return "targeted" if holding else "diffuse"


def worst_case_stratified(
    per_family: dict[str, tuple[float, float, float]],
) -> tuple[str | None, float, float, float]:
    """Pick the family with the lowest CI lower bound.

    Input maps each family name to its ``(point, ci_low, ci_high)``
    triple. Returns ``(family_name, point, ci_low, ci_high)`` for the
    worst-case family. Empty input returns ``(None, 0.0, 0.0, 0.0)``.
    """
    if not per_family:
        return None, 0.0, 0.0, 0.0
    worst_family = min(per_family.items(), key=lambda kv: kv[1][1])
    name, (point, lo, hi) = worst_family
    return name, point, lo, hi
