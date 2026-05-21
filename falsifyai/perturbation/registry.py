"""Map a PerturbationSpec into a runtime Perturbation instance.

Phase 0 uses a hardcoded ``isinstance`` dispatch. Phase 2 will replace this
with plugin discovery via ``importlib.metadata.entry_points`` under the
``falsifyai.perturbations`` group (plan.md section 17).
"""

from falsifyai.perturbation.base import Perturbation
from falsifyai.perturbation.casing_variant import CasingVariant
from falsifyai.perturbation.typo_noise import TypoNoise
from falsifyai.spec.models import (
    CasingVariantSpec,
    PerturbationSpec,
    TypoNoiseSpec,
)


def build_perturbation(spec: PerturbationSpec) -> Perturbation:
    """Return a runtime ``Perturbation`` for the given ``PerturbationSpec``.

    Raises:
        ValueError: if the spec type is not recognized.
    """
    if isinstance(spec, TypoNoiseSpec):
        return TypoNoise(count=spec.count, rate=spec.rate)
    if isinstance(spec, CasingVariantSpec):
        return CasingVariant(variants=list(spec.variants))
    raise ValueError(f"Unknown perturbation spec type: {type(spec).__name__}")
