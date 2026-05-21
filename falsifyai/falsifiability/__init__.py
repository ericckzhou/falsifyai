"""Falsifiability scoring — defends against passing CI with toothless assertions."""

from falsifyai.falsifiability.score import (
    LOW_FALSIFIABILITY_THRESHOLD,
    case_falsifiability,
    suite_falsifiability,
)

__all__ = ["LOW_FALSIFIABILITY_THRESHOLD", "case_falsifiability", "suite_falsifiability"]
