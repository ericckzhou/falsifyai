"""ContainsInvariant -- per-output substring assertion."""

from dataclasses import dataclass
from typing import ClassVar

from falsifyai.invariants.base import InvariantResult, Severity


@dataclass(frozen=True)
class ContainsInvariant:
    """Checks that the perturbed output contains every required substring.

    All-or-nothing for the ``passed`` flag; ``score`` reports the fraction
    of required values that were present, which downstream layers can use
    for partial-credit reporting.

    Ignores ``original_output`` -- this is a per-output assertion (the
    model's answer should contain certain text regardless of how the input
    was perturbed).
    """

    values: list[str]
    severity: Severity
    case_sensitive: bool = False

    name: ClassVar[str] = "contains"

    def check(
        self,
        original_output: str,  # noqa: ARG002 -- ignored per docstring
        perturbed_output: str,
        context: dict[str, object],  # noqa: ARG002 -- forward-compat, currently unused
    ) -> InvariantResult:
        haystack = perturbed_output if self.case_sensitive else perturbed_output.lower()
        missing: list[str] = []
        for value in self.values:
            needle = value if self.case_sensitive else value.lower()
            if needle not in haystack:
                missing.append(value)
        present_count = len(self.values) - len(missing)
        score = present_count / len(self.values)
        passed = len(missing) == 0
        details = (
            "all required values present"
            if passed
            else f"missing {len(missing)} of {len(self.values)} required values"
        )
        return InvariantResult(
            invariant_name=self.name,
            passed=passed,
            score=score,
            details=details,
            severity=self.severity,
            evidence={"missing": missing, "values_required": list(self.values)},
        )

    def falsifiability_contribution(self) -> float:
        """min(1.0, total_chars_required / 50). Longer required substrings = more restrictive.

        Per plan.md section 10.1. The 50-char denominator is heuristic: a
        single short value like "yes" contributes very little (3/50 = 0.06),
        while several long values quickly saturate the score.
        """
        total = sum(len(v) for v in self.values)
        return min(1.0, total / 50)
