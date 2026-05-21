"""Plain-text terminal output for ``falsifyai run``.

MVP scope: one row per case + a summary footer + the session id and store
path so the user can find their saved artifact. No colors, no boxes, no
JSON. Rich/colored output and ``--json`` land in Week 3 per
[plan.md section 22.1](../../plan.md).
"""

import sys
from typing import TextIO

from falsifyai.replay.models import ReplayArtifact
from falsifyai.verdict.models import Verdict

# Exit codes mapped to the MVP 5 verdicts per plan.md section 16.1.
#   STABLE              -> 0  SUCCESS
#   FRAGILE             -> 1  DEGRADED
#   CONSISTENTLY_WRONG  -> 2  FAILURE
#   INVALID_EVAL        -> 2  FAILURE
#   INSUFFICIENT        -> 4  INSUFFICIENT
# Code 3 (ERROR) is reserved for infrastructure failures raised by the CLI
# layer before a verdict exists; code 5 (REGRESSION) and 6 (LOW_FALSIFIABILITY)
# land with the Week 2 features.
_EXIT_CODES: dict[Verdict, int] = {
    Verdict.STABLE: 0,
    Verdict.FRAGILE: 1,
    Verdict.CONSISTENTLY_WRONG: 2,
    Verdict.INVALID_EVAL: 2,
    Verdict.INSUFFICIENT: 4,
}


def exit_code_for(verdict: Verdict) -> int:
    """CI exit code for a session-level verdict."""
    return _EXIT_CODES[verdict]


def render_session(
    artifact: ReplayArtifact,
    *,
    store_path: str,
    stream: TextIO | None = None,
) -> None:
    """Print one row per case, then a summary footer.

    Per-case row format:
        case: <id>  verdict: <V>  confidence: <p> (CI: <lo>-<hi>)  worst: <family>?

    The worst-case family is only shown for FRAGILE verdicts where one
    perturbation family drove the verdict.
    """
    out = stream if stream is not None else sys.stdout
    for case in artifact.case_results:
        line = (
            f"case: {case.case_id}  verdict: {case.verdict.value.upper()}  "
            f"confidence: {case.verdict_confidence:.2f} "
            f"(CI: {case.stability_ci_low:.2f}-{case.stability_ci_high:.2f})"
        )
        if case.verdict is Verdict.FRAGILE and case.worst_case_family:
            line += f"  worst: {case.worst_case_family}"
        out.write(line + "\n")
    out.write("=" * 65 + "\n")
    out.write(f"Session {artifact.session_id} -> {store_path}\n")
    sv = artifact.session_verdict
    out.write(
        f"{sv.case_count} case{'s' if sv.case_count != 1 else ''}, "
        f"verdict {sv.session_verdict.value.upper()}, "
        f"{sv.fragile_count} FRAGILE, "
        f"{sv.consistently_wrong_count} CONSISTENTLY_WRONG, "
        f"falsifiability {sv.falsifyai_falsifiability_score:.2f}\n"
    )
