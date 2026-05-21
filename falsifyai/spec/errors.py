"""Exception types raised by the spec loader."""

from pathlib import Path

from pydantic import ValidationError


class SpecLoadError(Exception):
    """Base exception for any failure to load a falsify spec from disk."""


class SpecParseError(SpecLoadError):
    """Raised when the YAML file cannot be parsed (syntax error, encoding, etc.)."""

    def __init__(self, path: Path, original: Exception) -> None:
        super().__init__(f"Failed to parse YAML at {path}: {original}")
        self.path = path
        self.original = original


class SpecValidationError(SpecLoadError):
    """Raised when the parsed YAML does not satisfy the falsify schema."""

    def __init__(self, path: Path, validation_error: ValidationError) -> None:
        super().__init__(f"Spec at {path} failed validation:\n{validation_error}")
        self.path = path
        self.validation_error = validation_error
