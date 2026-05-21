"""Load a falsify spec from a YAML file with content-hash for replay determinism."""

import hashlib
from pathlib import Path

import yaml
from pydantic import ValidationError

from falsifyai.spec.errors import SpecParseError, SpecValidationError
from falsifyai.spec.models import Spec


def load_spec(path: Path | str) -> tuple[Spec, str]:
    """Load and validate a falsify spec YAML file.

    Returns:
        Tuple of (Spec, spec_hash) where spec_hash is the sha256 hex digest
        of the file's raw bytes. The hash anchors replay to specific spec
        content; see plan.md section 8.

    Raises:
        FileNotFoundError: If path does not exist.
        SpecParseError:    If the file is not valid YAML.
        SpecValidationError: If parsed YAML does not satisfy the schema.
    """
    p = Path(path)
    raw_bytes = p.read_bytes()
    spec_hash = hashlib.sha256(raw_bytes).hexdigest()

    try:
        data = yaml.safe_load(raw_bytes)
    except yaml.YAMLError as exc:
        raise SpecParseError(p, exc) from exc

    try:
        spec = Spec.model_validate(data)
    except ValidationError as exc:
        raise SpecValidationError(p, exc) from exc

    return spec, spec_hash
