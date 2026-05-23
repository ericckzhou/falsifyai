"""Tests for falsifyai.cli.history — temporal view of one case across sessions.

History reads preserved evidence; it never re-resolves or re-aggregates.
Decisions A1/B1/D1/E1/F1/G1 + X1/Y1/Z1 from
``dev_notes/plans/PR-24-falsifyai-history-cli.md``.

RED phase: these tests describe the public surface before it exists.
"""

import argparse
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from falsifyai.cli.errors import CLIError, InfrastructureError
from falsifyai.replay.in_memory_store import InMemoryStore
from falsifyai.verdict.models import Verdict
from tests.fixtures.build_artifact import make_artifact

# ---------------------------------------------------------------------------
# Test fixture helpers
# ---------------------------------------------------------------------------


def _args(
    case_id: str = "capital_of_france",
    *,
    limit: int = 20,
    store_path: str = ":memory:",
) -> argparse.Namespace:
    """Build an argparse.Namespace matching the history subcommand's flags."""
    return argparse.Namespace(
        case_id=case_id,
        limit=limit,
        store_path=store_path,
    )


def _patched_store(monkeypatch: pytest.MonkeyPatch, store: InMemoryStore) -> InMemoryStore:
    """Replace history._build_store so cmd_history sees the fixture-populated store."""
    from falsifyai.cli import history as history_module

    monkeypatch.setattr(history_module, "_build_store", lambda _path: store)
    return store


def _populate_three_sessions(store: InMemoryStore) -> list[str]:
    """Save three artifacts sharing case_id 'capital_of_france' with distinct timestamps + verdicts.

    Returns session_ids in oldest-to-newest order (caller can reverse for assertions).
    """
    base = datetime(2026, 5, 22, 12, 0, 0, tzinfo=UTC)
    sessions = [
        ("oldest-id", Verdict.STABLE, base),
        ("middle-id", Verdict.FRAGILE, base + timedelta(hours=1)),
        ("newest-id", Verdict.STABLE, base + timedelta(hours=2)),
    ]
    for sid, verdict, ts in sessions:
        store.save_session(make_artifact(session_id=sid, verdict=verdict, created_at=ts))
    return [sid for sid, _, _ in sessions]


# ---------------------------------------------------------------------------
# Header + footer
# ---------------------------------------------------------------------------


def test_history_renders_session_header(monkeypatch, capsys) -> None:
    """Output begins with a header naming the case_id and matching session count."""
    from falsifyai.cli import history as history_module

    store = InMemoryStore()
    store.save_session(make_artifact(session_id="only-id", verdict=Verdict.STABLE))
    _patched_store(monkeypatch, store)

    history_module.cmd_history(_args(case_id="capital_of_france"))
    out = capsys.readouterr().out
    assert "capital_of_france" in out
    # Header signals what we're inspecting
    assert "history" in out.lower() or "case" in out.lower()


def test_history_footer_shows_session_count(monkeypatch, capsys) -> None:
    """Footer summarizes how many sessions matched."""
    from falsifyai.cli import history as history_module

    store = InMemoryStore()
    _populate_three_sessions(store)
    _patched_store(monkeypatch, store)

    history_module.cmd_history(_args())
    out = capsys.readouterr().out
    # Footer mentions the count (3)
    assert "3" in out


# ---------------------------------------------------------------------------
# Row ordering (Y1: newest-first)
# ---------------------------------------------------------------------------


def test_history_default_newest_first(monkeypatch, capsys) -> None:
    """Multiple sessions render in newest-first order (decision Y1)."""
    from falsifyai.cli import history as history_module

    store = InMemoryStore()
    _populate_three_sessions(store)
    _patched_store(monkeypatch, store)

    history_module.cmd_history(_args())
    out = capsys.readouterr().out
    # newest-id appears before middle-id, which appears before oldest-id
    idx_newest = out.find("newest-id"[:8])
    idx_middle = out.find("middle-id"[:8])
    idx_oldest = out.find("oldest-id"[:8])
    assert -1 < idx_newest < idx_middle < idx_oldest


# ---------------------------------------------------------------------------
# Per-row contents (D1)
# ---------------------------------------------------------------------------


def test_history_row_columns_include_verdict_and_ci(monkeypatch, capsys) -> None:
    """Each row shows verdict and confidence/CI per decision D1."""
    from falsifyai.cli import history as history_module

    store = InMemoryStore()
    store.save_session(make_artifact(session_id="row-test-id", verdict=Verdict.FRAGILE))
    _patched_store(monkeypatch, store)

    history_module.cmd_history(_args())
    out = capsys.readouterr().out
    # Verdict label visible
    assert "FRAGILE" in out
    # Some CI representation appears (from the fixture: 0.88-0.96)
    assert "0.88" in out or "CI" in out


def test_history_fragile_row_shows_worst_family(monkeypatch, capsys) -> None:
    """A FRAGILE case's row includes the worst_case_family (e.g. typo_noise)."""
    from falsifyai.cli import history as history_module

    store = InMemoryStore()
    store.save_session(make_artifact(session_id="fragile-row-id", verdict=Verdict.FRAGILE))
    _patched_store(monkeypatch, store)

    history_module.cmd_history(_args())
    out = capsys.readouterr().out
    # The default fixture's worst_case_family is "typo_noise"
    assert "typo_noise" in out


# ---------------------------------------------------------------------------
# --limit (B1, F1)
# ---------------------------------------------------------------------------


def test_history_limit_truncates_output(monkeypatch, capsys) -> None:
    """`--limit 2` against 3 sessions shows 2 rows + footer indicates truncation."""
    from falsifyai.cli import history as history_module

    store = InMemoryStore()
    _populate_three_sessions(store)
    _patched_store(monkeypatch, store)

    history_module.cmd_history(_args(limit=2))
    out = capsys.readouterr().out
    # Only the two newest are present (oldest is dropped)
    assert "newest-id"[:8] in out
    assert "middle-id"[:8] in out
    assert "oldest-id"[:8] not in out


def test_history_limit_zero_means_unlimited(monkeypatch, capsys) -> None:
    """`--limit 0` shows all matching sessions (F1)."""
    from falsifyai.cli import history as history_module

    store = InMemoryStore()
    _populate_three_sessions(store)
    _patched_store(monkeypatch, store)

    history_module.cmd_history(_args(limit=0))
    out = capsys.readouterr().out
    # All three rows present
    assert "newest-id"[:8] in out
    assert "middle-id"[:8] in out
    assert "oldest-id"[:8] in out


# ---------------------------------------------------------------------------
# Legacy artifact handling (D1 reuse of `_is_legacy_case`)
# ---------------------------------------------------------------------------


def test_history_legacy_artifact_shows_legacy_tag(monkeypatch, capsys) -> None:
    """Pre-PR-11 artifacts render `(legacy)` instead of misleading 0.00-0.00 CI."""
    from falsifyai.cli import history as history_module

    # Build a legacy artifact: case has verdict_confidence > 0 but zero CI fields
    base = make_artifact(session_id="legacy-row-id", verdict=Verdict.STABLE)
    case = base.case_results[0]
    legacy_case = replace(
        case,
        stability=0.0,
        stability_ci_low=0.0,
        stability_ci_high=0.0,
        per_family_stability={},
        worst_case_family=None,
    )
    legacy = replace(base, case_results=[legacy_case])
    store = InMemoryStore()
    store.save_session(legacy)
    _patched_store(monkeypatch, store)

    history_module.cmd_history(_args())
    out = capsys.readouterr().out
    assert "(legacy)" in out
    assert "0.00-0.00" not in out


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------


def test_history_unknown_case_id_raises(monkeypatch) -> None:
    """A case_id matching zero sessions raises InfrastructureError → exit 3."""
    from falsifyai.cli import history as history_module

    store = InMemoryStore()
    store.save_session(make_artifact(session_id="some-id"))
    _patched_store(monkeypatch, store)

    with pytest.raises((InfrastructureError, CLIError)):
        history_module.cmd_history(_args(case_id="nonexistent_case"))


# ---------------------------------------------------------------------------
# Architectural assertion (§12.2)
# ---------------------------------------------------------------------------


def test_history_does_not_import_resolver() -> None:
    """history.py must not transitively import the resolver module.

    Same architectural rule as inspect (PR-19): consumer surfaces over
    preserved evidence never re-resolve. The verdict shown is the one
    stored at run time; re-resolving would violate EVIDENCE.md §5.1.
    """
    import sys

    for mod_name in list(sys.modules):
        if mod_name.startswith("falsifyai.cli.history"):
            del sys.modules[mod_name]
        if mod_name == "falsifyai.verdict.resolver":
            del sys.modules[mod_name]

    import falsifyai.cli.history  # noqa: F401

    assert "falsifyai.verdict.resolver" not in sys.modules, (
        "falsifyai.cli.history must not import falsifyai.verdict.resolver "
        "(re-resolving violates the preservation guarantee). Read case.verdict "
        "from the loaded artifact instead."
    )


# ---------------------------------------------------------------------------
# Exit code (E1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "verdict",
    [Verdict.STABLE, Verdict.FRAGILE, Verdict.CONSISTENTLY_WRONG],
)
def test_history_exit_code_zero_on_render_success(monkeypatch, verdict) -> None:
    """Successful render returns exit 0 regardless of verdict mix (E1)."""
    from falsifyai.cli import history as history_module

    store = InMemoryStore()
    store.save_session(make_artifact(session_id="exit-test-id", verdict=verdict))
    _patched_store(monkeypatch, store)

    rc = history_module.cmd_history(_args())
    assert rc == 0


# ---------------------------------------------------------------------------
# G1: duplicate case_id within one artifact
# ---------------------------------------------------------------------------


def test_history_duplicate_case_id_in_artifact_renders_malformed_row(monkeypatch, capsys) -> None:
    """Decision G1: a session whose artifact contains the same case_id twice is
    treated as malformed evidence. Render a `<malformed: N matches>` row
    naming the issue, continue with other sessions, exit 3.

    This is the no-synthesis discipline applied to corrupt preserved evidence:
    don't silently pick one, don't hide the gap — name it.
    """
    from falsifyai.cli import history as history_module

    # Build a malformed artifact: two CaseResults sharing one case_id
    base = make_artifact(session_id="malformed-id", verdict=Verdict.STABLE)
    duplicate_case = base.case_results[0]  # same case_id "capital_of_france"
    malformed = replace(base, case_results=[duplicate_case, duplicate_case])

    # Also a normal session so we can verify rendering continues
    normal_ts = datetime(2026, 5, 22, 10, 0, 0, tzinfo=UTC)
    normal = make_artifact(session_id="normal-id", verdict=Verdict.STABLE, created_at=normal_ts)

    store = InMemoryStore()
    store.save_session(normal)
    store.save_session(malformed)  # newer, will appear first
    _patched_store(monkeypatch, store)

    rc = history_module.cmd_history(_args())
    out = capsys.readouterr().out
    # Malformed row is explicit
    assert "malformed" in out.lower()
    assert "malformed-id"[:8] in out
    # Normal session still renders
    assert "normal-id"[:8] in out
    # Exit code signals the anomaly to scripts (G1: exit 3)
    assert rc == 3
