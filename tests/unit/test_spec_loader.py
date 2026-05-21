"""Tests for falsifyai.spec.loader — YAML file loading with content-hash."""

from pathlib import Path

import pytest

from falsifyai.spec import Spec, SpecParseError, SpecValidationError, load_spec

FIXTURES = Path(__file__).parent.parent / "fixtures" / "specs"


def test_load_spec_returns_spec_and_hex_hash() -> None:
    spec, spec_hash = load_spec(FIXTURES / "minimal.yaml")
    assert isinstance(spec, Spec)
    assert isinstance(spec_hash, str)
    assert len(spec_hash) == 64  # sha256 hex digest
    int(spec_hash, 16)  # raises ValueError if not hex


def test_spec_hash_is_deterministic_across_paths(tmp_path: Path) -> None:
    src = FIXTURES / "minimal.yaml"
    copy = tmp_path / "elsewhere.yaml"
    copy.write_bytes(src.read_bytes())
    _, hash_a = load_spec(src)
    _, hash_b = load_spec(copy)
    assert hash_a == hash_b


def test_spec_hash_changes_when_content_changes(tmp_path: Path) -> None:
    src = FIXTURES / "minimal.yaml"
    modified = tmp_path / "modified.yaml"
    modified.write_bytes(src.read_bytes() + b"\n# trailing comment\n")
    _, hash_a = load_spec(src)
    _, hash_b = load_spec(modified)
    assert hash_a != hash_b


def test_load_spec_accepts_string_path() -> None:
    spec, _ = load_spec(str(FIXTURES / "minimal.yaml"))
    assert spec.falsify.name == "minimal smoke test"


def test_load_spec_missing_file_raises_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_spec(FIXTURES / "does_not_exist.yaml")


def test_load_spec_malformed_yaml_raises_parse_error() -> None:
    with pytest.raises(SpecParseError) as exc_info:
        load_spec(FIXTURES / "malformed.yaml")
    assert "malformed.yaml" in str(exc_info.value)


def test_load_spec_invalid_schema_raises_validation_error() -> None:
    with pytest.raises(SpecValidationError) as exc_info:
        load_spec(FIXTURES / "missing_seed.yaml")
    message = str(exc_info.value)
    assert "missing_seed.yaml" in message
    assert "seed" in message
