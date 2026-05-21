"""Spec loading and validation for falsify YAML eval files.

The materializer (``falsifyai.spec.materializer``) is intentionally NOT
re-exported here -- it imports from ``falsifyai.perturbation`` which
creates a circular import. Use ``from falsifyai.spec.materializer import
materialize`` explicitly.
"""

from falsifyai.spec.errors import SpecLoadError, SpecParseError, SpecValidationError
from falsifyai.spec.loader import load_spec
from falsifyai.spec.models import Spec

__all__ = [
    "Spec",
    "SpecLoadError",
    "SpecParseError",
    "SpecValidationError",
    "load_spec",
]
