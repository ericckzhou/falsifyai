"""Stale-config tripwire: the release gate's coverage floor matches CI's.

``scripts/release_gate.py`` runs ``pytest --cov-fail-under=COVERAGE_FLOOR`` and
``.github/workflows/ci.yml`` runs ``pytest ... --cov-fail-under=N``. These are
two independently hardcoded copies of the same number, kept in step today only
by a hand-maintained "keep in sync" comment in the CI workflow. That is exactly
the kind of duplicated constant that drifts silently: bump one, forget the
other, and the release tooling no longer enforces what CI enforces (or vice
versa).

This guard makes the drift fail loudly. It parses both numbers and asserts
equality -- nothing more. It does not opine on what the floor *should* be; it
only refuses to let the two copies disagree.

If this test fails, reconcile ``COVERAGE_FLOOR`` in scripts/release_gate.py with
``--cov-fail-under`` in .github/workflows/ci.yml so they are equal again.
"""

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_RELEASE_GATE = _ROOT / "scripts" / "release_gate.py"
_CI_WORKFLOW = _ROOT / ".github" / "workflows" / "ci.yml"


def _release_gate_floor() -> int:
    text = _RELEASE_GATE.read_text(encoding="utf-8")
    match = re.search(r"^COVERAGE_FLOOR\s*=\s*(\d+)", text, re.MULTILINE)
    assert match, (
        "could not find a top-level ``COVERAGE_FLOOR = <int>`` in "
        "scripts/release_gate.py; the release-gate coverage constant moved or "
        "was renamed. Update this guard to read it from its new home."
    )
    return int(match.group(1))


def _ci_floor() -> int:
    text = _CI_WORKFLOW.read_text(encoding="utf-8")
    matches = re.findall(r"--cov-fail-under=(\d+)", text)
    assert matches, (
        "could not find ``--cov-fail-under=<int>`` in .github/workflows/ci.yml; "
        "the CI coverage gate moved or was renamed. Update this guard to read it "
        "from its new home."
    )
    distinct = set(matches)
    assert len(distinct) == 1, (
        f".github/workflows/ci.yml uses multiple --cov-fail-under values "
        f"{sorted(distinct)}; the CI coverage floor is no longer a single number, "
        f"so 'matches release gate' is ambiguous. Reconcile CI first."
    )
    return int(matches[0])


def test_release_gate_coverage_floor_matches_ci() -> None:
    gate = _release_gate_floor()
    ci = _ci_floor()
    assert gate == ci, (
        f"coverage floor drift: scripts/release_gate.py COVERAGE_FLOOR={gate} but "
        f".github/workflows/ci.yml --cov-fail-under={ci}. Release tooling and CI "
        f"must enforce the same coverage floor. Reconcile the two constants."
    )
