"""SchemaMatchInvariant -- strict structural assertion on JSON output.

For cases where the model is expected to emit structured output (JSON), this
invariant asserts that the perturbed output (a) contains a parseable JSON value
-- extracted from a surrounding markdown fence or sentence when present -- and
(b) conforms to a declared schema: required keys present, and declared property
types match. Extraction makes the *shape* check robust to how chat models wrap
JSON; it does not relax validation (a wrong type inside a fence still fails).

It deliberately implements a *small* subset of JSON Schema rather than pulling
in the ``jsonschema`` package. The supported keys are ``type``, ``required``,
and ``properties[*].type`` -- enough to assert the structural contracts the
MVP cares about (the README's ``structured_output`` case), no more. A failure
under this invariant means the model broke the *shape* of its answer, which is
a different and often more actionable signal than a wrong value.

Like ``ContainsInvariant``, this is a per-output assertion: it ignores
``original_output`` and judges the perturbed output on its own.
"""

import json
import re
from dataclasses import dataclass
from typing import ClassVar

from falsifyai.invariants.base import InvariantResult, Severity

# Models frequently wrap JSON in a markdown fence (```json ... ```) or a
# sentence. The first capture group is the fenced block's content.
_FENCE_RE = re.compile(r"```[A-Za-z0-9_-]*\s*\n(.*?)```", re.DOTALL)


def _extract_json(text: str) -> object:
    """Best-effort extraction of one JSON value from model output.

    Tries, in order: (1) the whole stripped string, (2) the first fenced code
    block's content, (3) the first balanced JSON value beginning at a ``{`` or
    ``[`` anywhere in the text (via ``raw_decode``, which ignores trailing
    prose). Raises ``ValueError`` if none parse -- the caller treats that as a
    parse failure, so output containing no JSON value (genuine prose) still
    fails the invariant. Extraction never relaxes downstream schema validation.
    """
    candidates = [text.strip()]
    fence = _FENCE_RE.search(text)
    if fence is not None:
        candidates.append(fence.group(1).strip())
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            pass
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char in "{[":
            try:
                obj, _end = decoder.raw_decode(text, index)
                return obj
            except (json.JSONDecodeError, ValueError):
                continue
    raise ValueError("no JSON value found in output")


# JSON Schema primitive type -> Python type(s). ``bool`` is handled specially
# because Python's ``bool`` is a subclass of ``int``.
_JSON_TYPES: dict[str, type | tuple[type, ...]] = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "null": type(None),
}


def _json_type_matches(value: object, json_type: str) -> bool:
    """Return True if ``value`` satisfies the JSON Schema primitive ``json_type``."""
    expected = _JSON_TYPES.get(json_type)
    if expected is None:
        # Unknown type keyword: don't assert on it (forward-compatible).
        return True
    if json_type == "boolean":
        return isinstance(value, bool)
    # ``True``/``False`` are ints in Python; exclude them from numeric types.
    if json_type in ("number", "integer") and isinstance(value, bool):
        return False
    return isinstance(value, expected)


@dataclass(frozen=True)
class SchemaMatchInvariant:
    """Assert that JSON output conforms to a declared structural schema.

    ``schema`` is a JSON-Schema-subset dict. Recognized keys:

    - ``type``: expected top-level type (default ``"object"``).
    - ``required``: list of keys that must be present (object schemas).
    - ``properties``: map of key -> ``{"type": <json-type>}``; present keys
      with a declared type are type-checked.

    ``passed`` is all-or-nothing (valid JSON, correct top-level type, no
    missing required keys, no type errors). ``score`` reports the fraction of
    required keys satisfied (present and correctly typed) for partial-credit
    reporting downstream.
    """

    schema: dict
    severity: Severity

    name: ClassVar[str] = "schema_match"

    def check(
        self,
        original_output: str,  # noqa: ARG002 -- per-output assertion; original ignored
        perturbed_output: str,
        context: dict[str, object],  # noqa: ARG002 -- forward-compat, currently unused
    ) -> InvariantResult:
        try:
            data = _extract_json(perturbed_output)
        except (json.JSONDecodeError, ValueError) as exc:
            return self._fail(
                score=0.0,
                details=f"output does not contain valid JSON: {exc}",
                evidence={"parse_error": str(exc)},
            )

        expected_type = self.schema.get("type", "object")
        if not _json_type_matches(data, expected_type):
            return self._fail(
                score=0.0,
                details=f"top-level type is {type(data).__name__}, expected {expected_type}",
                evidence={"type_mismatch": {"expected": expected_type}},
            )

        required: list[str] = list(self.schema.get("required", []))
        properties: dict = self.schema.get("properties", {})

        missing: list[str] = []
        type_errors: list[str] = []
        if isinstance(data, dict):
            missing = [key for key in required if key not in data]
            for key, prop in properties.items():
                declared = prop.get("type") if isinstance(prop, dict) else None
                if (
                    declared is not None
                    and key in data
                    and not _json_type_matches(data[key], declared)
                ):
                    type_errors.append(key)

        # A required key counts as satisfied only if present AND (no declared
        # type or its declared type matches).
        satisfied = sum(1 for key in required if key not in missing and key not in type_errors)
        score = satisfied / len(required) if required else (1.0 if not type_errors else 0.0)
        passed = not missing and not type_errors

        if passed:
            details = "output conforms to schema"
        else:
            parts = []
            if missing:
                parts.append(f"missing {len(missing)} required key(s)")
            if type_errors:
                parts.append(f"{len(type_errors)} type error(s)")
            details = "; ".join(parts)

        return InvariantResult(
            invariant_name=self.name,
            passed=passed,
            score=score,
            details=details,
            severity=self.severity,
            evidence={
                "missing": missing,
                "type_errors": type_errors,
                "required": required,
            },
        )

    def falsifiability_contribution(self) -> float:
        """min(1.0, len(required) * 0.2). More required fields = more restrictive.

        Per plan.md section 10.1. A schema with no required fields is barely
        restrictive (it only asserts "parses as JSON"); five or more required
        fields saturate the score.
        """
        required = self.schema.get("required", [])
        return min(1.0, len(required) * 0.2)

    def _fail(self, *, score: float, details: str, evidence: dict) -> InvariantResult:
        return InvariantResult(
            invariant_name=self.name,
            passed=False,
            score=score,
            details=details,
            severity=self.severity,
            evidence=evidence,
        )
