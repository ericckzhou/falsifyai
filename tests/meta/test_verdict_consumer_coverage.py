"""Structural guardrail: consumer-side verdict maps stay total over ``Verdict``.

Anti-entropy infrastructure, sibling to ``test_resolver_branch_count.py``. That
test guards verdict growth at the *producer* (the resolver's decision chain);
``test_verdict_models.py`` freezes the enum itself. This test guards the seam
those two leave open: the *consumer* classification tables that turn a verdict
into a CI signal. The enum can grow and the resolver can emit a new class while
a downstream map silently goes out of sync -- and the failure only surfaces in a
user's CI, not ours.

Two maps gate CI today:

  * ``render._EXIT_CODES`` -> ``exit_code_for`` indexes it directly
    (``_EXIT_CODES[verdict]``), so a verdict missing from the map is a
    ``KeyError`` *crash* the moment that verdict reaches the CLI. The contract is
    "one exit code your CI can gate on" (README); a crash is not an exit code.

  * ``diff._QUALITY_RANK`` -> ``_classify_transition`` reads it with ``.get()``,
    so a missing verdict does not crash -- it silently falls *off the ladder* and
    is reported as ``OTHER_CHANGE`` (informational), suppressing a regression
    signal. Two verdicts are deliberately off-ladder (``INVALID_EVAL``,
    ``INSUFFICIENT``); a *new* one landing there by omission is a bug.

When a verdict class is legitimately added, the fix is to wire it into both maps
(and, for the ladder, decide rank-vs-off-ladder on purpose) in the same commit
-- exactly what these assertions force.
"""

from falsifyai.cli import diff
from falsifyai.cli.render import _EXIT_CODES, exit_code_for
from falsifyai.verdict.models import Verdict

# The verdict-derived CI codes per plan.md section 16.1 (see render._EXIT_CODES):
#   0 SUCCESS · 1 DEGRADED · 2 FAILURE · 4 INSUFFICIENT.
# 3 (ERROR), 5 (REGRESSION), 6 (LOW_FALSIFIABILITY) are emitted by other surfaces,
# never by the verdict map, so a verdict must never map to one of them.
_ALLOWED_VERDICT_EXIT_CODES = frozenset({0, 1, 2, 4})

# Verdicts intentionally kept OFF diff's quality ladder (see diff._QUALITY_RANK
# docstring). A broken eval is not a point on the quality axis; "couldn't judge"
# is handled asymmetrically. Any *other* verdict missing from the ladder is an
# accidental omission, not a design choice -- this set pins the deliberate two.
_OFF_LADDER_VERDICTS = frozenset({Verdict.INVALID_EVAL, Verdict.INSUFFICIENT})


def test_exit_code_map_covers_every_verdict() -> None:
    """``_EXIT_CODES`` is total over ``Verdict`` -- no missing or stale keys."""
    assert set(_EXIT_CODES) == set(Verdict), (
        "render._EXIT_CODES is out of sync with the Verdict enum. Missing: "
        f"{sorted(v.name for v in set(Verdict) - set(_EXIT_CODES))}; "
        f"stale: {sorted(v.name for v in set(_EXIT_CODES) - set(Verdict))}. "
        "Every verdict needs a CI exit code; map the new class in the same commit."
    )


def test_exit_code_for_never_crashes_and_stays_in_band() -> None:
    """Every verdict resolves to a documented verdict-derived code (0/1/2/4)."""
    for verdict in Verdict:
        code = exit_code_for(verdict)  # would KeyError if the map were partial
        assert code in _ALLOWED_VERDICT_EXIT_CODES, (
            f"{verdict.name} maps to exit code {code}, which is not a "
            f"verdict-derived code {sorted(_ALLOWED_VERDICT_EXIT_CODES)}. "
            "Codes 3/5/6 belong to non-verdict surfaces (errors, diff)."
        )


def test_quality_rank_partitions_the_verdict_enum() -> None:
    """Every verdict is either ranked on diff's ladder or deliberately off it.

    Forces a conscious rank-vs-off-ladder decision when a verdict is added,
    instead of letting a new class silently default to ``OTHER_CHANGE`` and
    suppress a regression.
    """
    ranked = set(diff._QUALITY_RANK)
    off_ladder = set(Verdict) - ranked
    assert off_ladder == set(_OFF_LADDER_VERDICTS), (
        "diff._QUALITY_RANK no longer partitions the Verdict enum. Unranked: "
        f"{sorted(v.name for v in off_ladder)}; expected exactly "
        f"{sorted(v.name for v in _OFF_LADDER_VERDICTS)}. A new verdict must be "
        "ranked on the ladder OR added to the deliberate off-ladder set on purpose."
    )
