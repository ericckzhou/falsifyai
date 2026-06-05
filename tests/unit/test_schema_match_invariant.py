"""Tests for falsifyai.invariants.schema_match.SchemaMatchInvariant."""

import pytest

from falsifyai.invariants.base import Severity
from falsifyai.invariants.schema_match import SchemaMatchInvariant

_CAPITAL_SCHEMA = {
    "type": "object",
    "required": ["capital"],
    "properties": {"capital": {"type": "string"}},
}


def _check(inv: SchemaMatchInvariant, perturbed: str, *, original: str = "<ignored>"):
    return inv.check(original_output=original, perturbed_output=perturbed, context={})


def test_valid_json_matching_schema_passes() -> None:
    inv = SchemaMatchInvariant(schema=_CAPITAL_SCHEMA, severity=Severity.HIGH)
    result = _check(inv, '{"capital": "Tokyo"}')
    assert result.passed is True
    assert result.score == 1.0


def test_non_json_output_fails() -> None:
    inv = SchemaMatchInvariant(schema=_CAPITAL_SCHEMA, severity=Severity.HIGH)
    result = _check(inv, "The capital is Tokyo.")
    assert result.passed is False
    assert result.score == 0.0
    assert "parse_error" in result.evidence


def test_missing_required_key_fails() -> None:
    inv = SchemaMatchInvariant(schema=_CAPITAL_SCHEMA, severity=Severity.HIGH)
    result = _check(inv, '{"country": "Japan"}')
    assert result.passed is False
    assert result.score == 0.0
    assert "capital" in result.evidence["missing"]  # type: ignore[operator]


def test_wrong_property_type_fails() -> None:
    inv = SchemaMatchInvariant(schema=_CAPITAL_SCHEMA, severity=Severity.HIGH)
    result = _check(inv, '{"capital": 42}')  # number, expected string
    assert result.passed is False
    assert "capital" in result.evidence["type_errors"]  # type: ignore[operator]


def test_partial_required_yields_fractional_score() -> None:
    schema = {"type": "object", "required": ["a", "b", "c"]}
    inv = SchemaMatchInvariant(schema=schema, severity=Severity.HIGH)
    result = _check(inv, '{"a": 1, "b": 2}')  # 2 of 3 required present
    assert result.passed is False
    assert result.score == pytest.approx(2 / 3)


def test_top_level_type_mismatch_fails() -> None:
    schema = {"type": "object", "required": []}
    inv = SchemaMatchInvariant(schema=schema, severity=Severity.HIGH)
    result = _check(inv, "[1, 2, 3]")  # array, expected object
    assert result.passed is False
    assert result.score == 0.0
    assert "type_mismatch" in result.evidence


def test_array_top_level_type() -> None:
    schema = {"type": "array"}
    inv = SchemaMatchInvariant(schema=schema, severity=Severity.HIGH)
    assert _check(inv, "[1, 2, 3]").passed is True
    assert _check(inv, '{"a": 1}').passed is False


def test_boolean_is_not_an_integer() -> None:
    """Python's bool is an int subclass; the validator must not conflate them."""
    schema = {"type": "object", "properties": {"flag": {"type": "integer"}}, "required": ["flag"]}
    inv = SchemaMatchInvariant(schema=schema, severity=Severity.HIGH)
    assert _check(inv, '{"flag": true}').passed is False  # bool, not integer
    assert _check(inv, '{"flag": 1}').passed is True


def test_integer_satisfies_number() -> None:
    schema = {"type": "object", "properties": {"n": {"type": "number"}}, "required": ["n"]}
    inv = SchemaMatchInvariant(schema=schema, severity=Severity.HIGH)
    assert _check(inv, '{"n": 3}').passed is True
    assert _check(inv, '{"n": 3.5}').passed is True


def test_empty_schema_accepts_any_json_object() -> None:
    inv = SchemaMatchInvariant(schema={}, severity=Severity.HIGH)
    assert _check(inv, '{"anything": "goes"}').passed is True


def test_original_output_is_ignored() -> None:
    inv = SchemaMatchInvariant(schema=_CAPITAL_SCHEMA, severity=Severity.HIGH)
    a = _check(inv, '{"capital": "Tokyo"}', original="completely different")
    b = _check(inv, '{"capital": "Tokyo"}', original='{"capital": "Paris"}')
    assert a.passed is True and b.passed is True


def test_protocol_attributes_and_result_metadata() -> None:
    inv = SchemaMatchInvariant(schema=_CAPITAL_SCHEMA, severity=Severity.CRITICAL)
    assert inv.name == "schema_match"
    assert inv.severity is Severity.CRITICAL
    result = _check(inv, '{"capital": "Tokyo"}')
    assert result.invariant_name == "schema_match"
    assert result.severity is Severity.CRITICAL


def test_falsifiability_contribution_scales_with_required_count() -> None:
    """Per plan section 10.1: min(1.0, len(required) * 0.2)."""
    none = SchemaMatchInvariant(schema={"type": "object"}, severity=Severity.HIGH)
    two = SchemaMatchInvariant(
        schema={"type": "object", "required": ["a", "b"]}, severity=Severity.HIGH
    )
    many = SchemaMatchInvariant(
        schema={"type": "object", "required": ["a", "b", "c", "d", "e", "f"]},
        severity=Severity.HIGH,
    )
    assert none.falsifiability_contribution() == 0.0
    assert two.falsifiability_contribution() == pytest.approx(0.4)
    assert many.falsifiability_contribution() == 1.0


# --- JSON extraction from wrapped output (case study 03, Finding 3b) ---------
# Models commonly wrap correct JSON in a markdown fence or a sentence. The
# invariant extracts the JSON before validating; genuine prose with no JSON
# value still fails (the "broke the shape" contract is preserved).


def test_json_in_json_fenced_block_passes() -> None:
    inv = SchemaMatchInvariant(schema=_CAPITAL_SCHEMA, severity=Severity.HIGH)
    result = _check(inv, '```json\n{"capital": "Tokyo"}\n```')
    assert result.passed is True
    assert result.score == 1.0


def test_json_in_bare_fenced_block_passes() -> None:
    inv = SchemaMatchInvariant(schema=_CAPITAL_SCHEMA, severity=Severity.HIGH)
    result = _check(inv, '```\n{"capital": "Tokyo"}\n```')
    assert result.passed is True


def test_json_object_embedded_in_prose_passes() -> None:
    inv = SchemaMatchInvariant(schema=_CAPITAL_SCHEMA, severity=Severity.HIGH)
    result = _check(
        inv,
        'Sure! Here is the result: {"capital": "Tokyo"}. Let me know if you need more.',
    )
    assert result.passed is True


def test_json_array_embedded_in_prose_passes() -> None:
    inv = SchemaMatchInvariant(schema={"type": "array"}, severity=Severity.HIGH)
    assert _check(inv, "The list is [1, 2, 3] as requested.").passed is True


def test_prose_without_any_json_still_fails() -> None:
    inv = SchemaMatchInvariant(schema=_CAPITAL_SCHEMA, severity=Severity.HIGH)
    result = _check(inv, "The capital is Tokyo.")
    assert result.passed is False
    assert result.score == 0.0
    assert "parse_error" in result.evidence


def test_fenced_block_with_invalid_json_fails() -> None:
    inv = SchemaMatchInvariant(schema=_CAPITAL_SCHEMA, severity=Severity.HIGH)
    result = _check(inv, "```json\n{capital: Tokyo}\n```")  # unquoted -> not JSON
    assert result.passed is False
    assert "parse_error" in result.evidence


def test_extracted_json_is_still_schema_validated() -> None:
    """Extraction does not relax validation: wrong type inside a fence still fails."""
    inv = SchemaMatchInvariant(schema=_CAPITAL_SCHEMA, severity=Severity.HIGH)
    result = _check(inv, '```json\n{"capital": 42}\n```')  # number, expected string
    assert result.passed is False
    assert "capital" in result.evidence["type_errors"]  # type: ignore[operator]
