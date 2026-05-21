"""Snapshot tests for the CLI render output *shape*.

These tests catch render-format drift -- if anyone changes the per-case
row layout, the summary footer, or the diff transition row, these tests
fail loudly. They do NOT validate exact numeric values: floats, session
IDs, timestamps, and other variable bits are normalized to placeholder
tokens before comparison.

Why this matters: the README walkthrough shows example output. If
render.py drifts and the README still claims the old format, users
notice. These tests pair with the README so anyone changing the format
is reminded to update the docs too.

Update path: if you change `render_session` or `render_diff` deliberately,
re-run this file, copy the failing output into the EXPECTED_* constants
below, and verify the README still matches the new shape.
"""

import io
import re

from falsifyai.cli.diff import (
    CaseTransition,
    DiffReport,
    TransitionKind,
)
from falsifyai.cli.render import render_diff, render_session
from falsifyai.verdict.models import Verdict
from tests.fixtures.build_artifact import make_artifact

_NORMALIZERS = [
    # ISO-8601 timestamp (with timezone)
    (re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)"), "<TS>"),
    # UUID-style or hyphenated id (any hex+dash pattern of >=8 chars)
    (re.compile(r"\b[0-9a-fA-F]{8,}(?:-[0-9a-fA-F]+){1,4}\b"), "<ID>"),
    # Floats with 2 decimal places (the render format)
    (re.compile(r"\b\d+\.\d{2}\b"), "<NUM>"),
]


def _normalize(text: str) -> str:
    for pattern, replacement in _NORMALIZERS:
        text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# Expected schemas
# ---------------------------------------------------------------------------

EXPECTED_RUN_SCHEMA = """\
case: capital_of_france  verdict: STABLE  confidence: <NUM> (CI: <NUM>-<NUM>)
=================================================================
Session <ID> -> <STORE>
1 case, verdict STABLE, 0 FRAGILE, 0 CONSISTENTLY_WRONG, falsifiability <NUM>
"""

EXPECTED_REPLAY_SCHEMA = """\
Loaded session <ID> · created_at <TS> from <STORE>
case: capital_of_france  verdict: STABLE  confidence: <NUM> (CI: <NUM>-<NUM>)
=================================================================
Session <ID> -> <STORE>
1 case, verdict STABLE, 0 FRAGILE, 0 CONSISTENTLY_WRONG, falsifiability <NUM>
"""

EXPECTED_DIFF_REGRESSION_SCHEMA = """\
Diff: baseline <ID> -> candidate <ID>
Store: <STORE>
=================================================================
case: capital_of_france  baseline: STABLE (<NUM>)  candidate: FRAGILE (<NUM>)  REGRESSED
=================================================================
1 regressed, 0 improved, 0 unchanged, 0 other, 0 added, 0 removed
"""


# ---------------------------------------------------------------------------
# render_session
# ---------------------------------------------------------------------------


def test_run_path_render_matches_schema() -> None:
    """`falsifyai run` (loaded_from=None) renders in this exact shape."""
    artifact = make_artifact(verdict=Verdict.STABLE)
    buf = io.StringIO()
    render_session(artifact, store_path="<STORE>", stream=buf)
    normalized = _normalize(buf.getvalue())
    assert normalized == EXPECTED_RUN_SCHEMA, (
        f"render_session run-path schema drifted.\n"
        f"Got:\n{normalized!r}\nExpected:\n{EXPECTED_RUN_SCHEMA!r}"
    )


def test_replay_path_render_matches_schema() -> None:
    """`falsifyai replay` (loaded_from set) adds the header line."""
    from datetime import UTC, datetime

    artifact = make_artifact(verdict=Verdict.STABLE)
    buf = io.StringIO()
    render_session(
        artifact,
        store_path="<STORE>",
        stream=buf,
        loaded_from=datetime(2026, 5, 21, 12, 0, 0, tzinfo=UTC),
    )
    normalized = _normalize(buf.getvalue())
    assert normalized == EXPECTED_REPLAY_SCHEMA, (
        f"render_session replay-path schema drifted.\n"
        f"Got:\n{normalized!r}\nExpected:\n{EXPECTED_REPLAY_SCHEMA!r}"
    )


# ---------------------------------------------------------------------------
# render_diff
# ---------------------------------------------------------------------------


def test_diff_render_matches_schema_on_regression() -> None:
    report = DiffReport(
        baseline_session_id="11111111-1111-1111-1111-111111111111",
        candidate_session_id="22222222-2222-2222-2222-222222222222",
        materialized_hash_mismatch=False,
        transitions=[
            CaseTransition(
                case_id="capital_of_france",
                baseline_verdict=Verdict.STABLE,
                candidate_verdict=Verdict.FRAGILE,
                baseline_stability_ci_low=0.92,
                candidate_stability_ci_low=0.45,
                transition_kind=TransitionKind.REGRESSED,
            )
        ],
        regressed_count=1,
        improved_count=0,
        unchanged_count=0,
        other_change_count=0,
        added_count=0,
        removed_count=0,
    )
    buf = io.StringIO()
    render_diff(report, store_path="<STORE>", stream=buf)
    normalized = _normalize(buf.getvalue())
    assert normalized == EXPECTED_DIFF_REGRESSION_SCHEMA, (
        f"render_diff regression-path schema drifted.\n"
        f"Got:\n{normalized!r}\nExpected:\n{EXPECTED_DIFF_REGRESSION_SCHEMA!r}"
    )


# ---------------------------------------------------------------------------
# Sanity: the normalizer itself is reasonable
# ---------------------------------------------------------------------------


def test_normalize_replaces_uuids_and_floats_and_timestamps() -> None:
    sample = (
        "case: c  verdict: STABLE  confidence: 0.95 (CI: 0.92-0.98) "
        "Session 7c4f1234-5678-9abc-def0-1111aabbccdd at 2026-05-21T12:00:00+00:00"
    )
    out = _normalize(sample)
    assert "0.95" not in out
    assert "0.92" not in out
    assert "7c4f" not in out
    assert "2026-05-21" not in out
    assert out.count("<NUM>") == 3
    assert "<ID>" in out
    assert "<TS>" in out
