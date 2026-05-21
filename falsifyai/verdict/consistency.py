"""Lightweight CONSISTENTLY_WRONG detection.

Per [plan.md section 2.3](../../plan.md): a model that confidently and
consistently hallucinates the same wrong answer to every perturbation of a
question is the most dangerous production case. Without this verdict, that
behavior gets STABLE -- the worst false-positive in the framework.

The MVP check is pure string-match against the case's ground truth:

- ``expected.contains``: every output (original + perturbed) must contain
  ALL required values. If every output misses any required value, the
  model is consistently wrong about that fact.
- ``expected.not_contains``: every output must avoid ALL forbidden values.
  If every output contains a forbidden value, the model is consistently
  wrong about NOT saying it.

Case-insensitive matching matches the default behavior of
``ContainsInvariant`` (see PR #5).

Embedding-based contradiction (``expected.reference``) is deferred to the
full ``ConsistencyOracle`` in Phase 1. That path needs an embedding model
and an explicit contradiction notion; the lightweight check catches the
obvious case (model says "London" when ground truth says "Paris") without
either dependency.
"""

from falsifyai.spec.models import ExpectedSection


def is_consistently_wrong(
    original_output: str,
    perturbed_outputs: list[str],
    expected: ExpectedSection,
) -> bool:
    """Return True iff every output (original + perturbed) violates the ground truth.

    *Every* output must violate for the verdict to apply -- if even one
    output is correct, the model is at least sometimes right, which is
    FRAGILE, not consistently wrong.
    """
    all_outputs = [original_output, *perturbed_outputs]

    contains_violated = bool(expected.contains) and all(
        not _all_required_present(o, expected.contains) for o in all_outputs
    )
    not_contains_violated = bool(expected.not_contains) and all(
        _any_forbidden_present(o, expected.not_contains) for o in all_outputs
    )

    return contains_violated or not_contains_violated


def _all_required_present(output: str, required: list[str]) -> bool:
    """Case-insensitive check that every required string appears in output."""
    lowered = output.lower()
    return all(req.lower() in lowered for req in required)


def _any_forbidden_present(output: str, forbidden: list[str]) -> bool:
    """Case-insensitive check that any forbidden string appears in output."""
    lowered = output.lower()
    return any(forb.lower() in lowered for forb in forbidden)
