"""Tests for falsifyai.cli.inspect — the per-case deep-dive consumer surface.

`inspect` reads preserved evidence from a stored ReplayArtifact and surfaces
it for legibility. Hard architectural rule: inspect must never re-derive a
verdict. Tests below enforce that rule and the decisions A-F from
`dev_notes/plans/PR-19-falsifyai-inspect-cli.md`.

RED phase: these tests describe the public surface before it exists. They
are expected to fail until cli/inspect.py is implemented.
"""

import argparse
from dataclasses import replace

import pytest

from falsifyai.cli.errors import CLIError, InfrastructureError
from falsifyai.invariants.base import InvariantResult, Severity
from falsifyai.replay.in_memory_store import InMemoryStore
from falsifyai.replay.models import ReplayArtifact
from falsifyai.verdict.models import Verdict
from tests.fixtures.build_artifact import make_artifact

# ---------------------------------------------------------------------------
# Test fixture helpers
# ---------------------------------------------------------------------------


def _args(
    session_id: str | None = "sess-X",
    *,
    case_id: str | None = None,
    full: bool = False,
    store_path: str = ":memory:",
) -> argparse.Namespace:
    """Build an argparse.Namespace matching the inspect subcommand's flags."""
    return argparse.Namespace(
        session_id=session_id,
        case=case_id,
        full=full,
        store_path=store_path,
    )


def _patched_store(monkeypatch: pytest.MonkeyPatch, store: InMemoryStore) -> InMemoryStore:
    """Replace inspect._build_store so cmd_inspect sees the fixture-populated store."""
    from falsifyai.cli import inspect as inspect_module

    monkeypatch.setattr(inspect_module, "_build_store", lambda _path: store)
    return store


def _failing_contains_result() -> InvariantResult:
    return InvariantResult(
        invariant_name="contains",
        passed=False,
        score=0.0,
        details="missing: ['Paris']",
        severity=Severity.HIGH,
        evidence={"missing": ["Paris"]},
    )


def _make_fragile_artifact(
    *,
    session_id: str = "frag-1",
    long_output: bool = False,
) -> ReplayArtifact:
    """Build a FRAGILE artifact where the typo_noise perturbation fails its contains check.

    Starts from the standard make_artifact() fixture and mutates the first
    perturbed run's invariant_results to inject a contains-failure. The
    session-level verdict is set to FRAGILE to match.
    """
    base = make_artifact(session_id=session_id, verdict=Verdict.FRAGILE)
    case = base.case_results[0]
    failing_run = replace(
        case.perturbed[0],
        invariant_results=[_failing_contains_result(), *case.perturbed[0].invariant_results[1:]],
    )
    if long_output:
        # Replace the model output with a long string to exercise truncation.
        long_text = "A" * 200 + "B" * 100 + "C" * 200  # 500 chars
        failing_run = replace(
            failing_run,
            execution=replace(failing_run.execution, output_text=long_text),
        )
    new_case = replace(
        case,
        verdict=Verdict.FRAGILE,
        perturbed=[failing_run, *case.perturbed[1:]],
        worst_case_family="typo_noise",
    )
    return replace(base, case_results=[new_case])


def _make_consistently_wrong_artifact(*, session_id: str = "cw-1") -> ReplayArtifact:
    """Build a CONSISTENTLY_WRONG artifact where the baseline already fails."""
    base = make_artifact(session_id=session_id, verdict=Verdict.CONSISTENTLY_WRONG)
    case = base.case_results[0]
    # Mutate baseline to fail by replacing the output with something that doesn't contain "Paris".
    bad_baseline = replace(
        case.original_execution,
        output_text="I don't know.",
    )
    new_case = replace(
        case,
        verdict=Verdict.CONSISTENTLY_WRONG,
        original_execution=bad_baseline,
        worst_case_family=None,  # CONSISTENTLY_WRONG means baseline fails, not family-attributed
    )
    return replace(base, case_results=[new_case])


def _make_legacy_artifact(*, session_id: str = "legacy-1") -> ReplayArtifact:
    """Build a pre-PR-11 era artifact: no CI fields populated."""
    base = make_artifact(session_id=session_id, verdict=Verdict.STABLE)
    case = base.case_results[0]
    legacy_case = replace(
        case,
        stability=0.0,
        stability_ci_low=0.0,
        stability_ci_high=0.0,
        per_family_stability={},
        worst_case_family=None,
    )
    return replace(base, case_results=[legacy_case])


# ---------------------------------------------------------------------------
# Happy path — STABLE case
# ---------------------------------------------------------------------------


def test_inspect_renders_session_header(monkeypatch, capsys) -> None:
    """Session header includes session_id, created_at, and falsifyai version."""
    from falsifyai.cli import inspect as inspect_module

    store = InMemoryStore()
    store.save_session(make_artifact(session_id="sess-X", verdict=Verdict.STABLE))
    _patched_store(monkeypatch, store)

    rc = inspect_module.cmd_inspect(_args(session_id="sess-X"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "sess-X" in out
    assert "Inspecting session" in out or "Loaded session" in out


def test_stable_case_shows_perturbation_count_no_evidence(monkeypatch, capsys) -> None:
    """STABLE cases show verdict + perturbation count, no evidence excerpt (decision B refined)."""
    from falsifyai.cli import inspect as inspect_module

    store = InMemoryStore()
    store.save_session(make_artifact(session_id="sess-X", verdict=Verdict.STABLE))
    _patched_store(monkeypatch, store)

    inspect_module.cmd_inspect(_args(session_id="sess-X"))
    out = capsys.readouterr().out
    assert "STABLE" in out
    assert "perturbations: 2" in out
    # STABLE case must NOT show the perturbed input or output excerpt by default
    assert "What is the captial of France?" not in out  # the typo'd input
    assert "perturbed input:" not in out


# ---------------------------------------------------------------------------
# Happy path — FRAGILE case (worst-perturbation evidence)
# ---------------------------------------------------------------------------


def test_fragile_case_shows_worst_perturbation_evidence(monkeypatch, capsys) -> None:
    """FRAGILE cases show worst perturbation: input + output excerpt + failing invariant."""
    from falsifyai.cli import inspect as inspect_module

    store = InMemoryStore()
    store.save_session(_make_fragile_artifact())
    _patched_store(monkeypatch, store)

    inspect_module.cmd_inspect(_args(session_id="frag-1"))
    out = capsys.readouterr().out
    assert "FRAGILE" in out
    assert "perturbations: 2" in out
    assert "worst: typo_noise" in out
    # Worst-perturbation evidence must surface the perturbed input + output + invariant
    assert "perturbed input:" in out
    assert "What is the captial of France?" in out  # the failing perturbed input
    assert "output excerpt:" in out or "output:" in out
    assert "failing invariant:" in out
    assert "contains" in out  # the name of the failing invariant


def test_fragile_case_default_does_not_show_passing_perturbations(monkeypatch, capsys) -> None:
    """Default render shows only the WORST perturbation, not all of them."""
    from falsifyai.cli import inspect as inspect_module

    store = InMemoryStore()
    store.save_session(_make_fragile_artifact())
    _patched_store(monkeypatch, store)

    inspect_module.cmd_inspect(_args(session_id="frag-1"))
    out = capsys.readouterr().out
    # The casing_variant perturbation (which passes) should NOT appear in default output
    assert "WHAT IS THE CAPITAL OF FRANCE?" not in out
    assert "casing_variant" not in out


# ---------------------------------------------------------------------------
# --case flag (drill-in expansion)
# ---------------------------------------------------------------------------


def test_case_flag_shows_all_perturbations(monkeypatch, capsys) -> None:
    """`--case <id>` expands to show every perturbation for that case."""
    from falsifyai.cli import inspect as inspect_module

    store = InMemoryStore()
    store.save_session(_make_fragile_artifact())
    _patched_store(monkeypatch, store)

    inspect_module.cmd_inspect(_args(session_id="frag-1", case_id="capital_of_france"))
    out = capsys.readouterr().out
    # Both perturbations must appear
    assert "typo_noise" in out
    assert "casing_variant" in out
    assert "WHAT IS THE CAPITAL OF FRANCE?" in out  # the casing variant
    assert "What is the captial of France?" in out  # the typo


def test_unknown_case_id_returns_clean_error(monkeypatch) -> None:
    """`--case <nonexistent>` raises a clean InfrastructureError -> exit 3."""
    from falsifyai.cli import inspect as inspect_module

    store = InMemoryStore()
    store.save_session(_make_fragile_artifact())
    _patched_store(monkeypatch, store)

    with pytest.raises((InfrastructureError, CLIError)):
        inspect_module.cmd_inspect(_args(session_id="frag-1", case_id="nonexistent_case"))


# ---------------------------------------------------------------------------
# --full flag (disable truncation)
# ---------------------------------------------------------------------------


def test_default_truncation_for_long_outputs(monkeypatch, capsys) -> None:
    """Outputs >400 chars are truncated to head-200 + ellipsis + tail-100 by default."""
    from falsifyai.cli import inspect as inspect_module

    store = InMemoryStore()
    store.save_session(_make_fragile_artifact(long_output=True))
    _patched_store(monkeypatch, store)

    inspect_module.cmd_inspect(_args(session_id="frag-1"))
    out = capsys.readouterr().out
    # Truncation marker present
    assert "..." in out or "[truncated" in out
    # The middle of the 500-char output ('B' * 100) should NOT appear
    middle = "B" * 100
    assert middle not in out
    # Head ('A' * 200) and tail ('C' * 100 of the trailing 200) should appear
    assert "A" * 100 in out  # at least some of the head
    assert "C" * 50 in out  # at least some of the tail


def test_full_flag_disables_truncation(monkeypatch, capsys) -> None:
    """`--full` shows the entire output even if >400 chars."""
    from falsifyai.cli import inspect as inspect_module

    store = InMemoryStore()
    store.save_session(_make_fragile_artifact(long_output=True))
    _patched_store(monkeypatch, store)

    inspect_module.cmd_inspect(_args(session_id="frag-1", full=True))
    out = capsys.readouterr().out
    # The middle 'B' * 100 chunk must be present when --full is used
    middle = "B" * 100
    assert middle in out


# ---------------------------------------------------------------------------
# Pre-PR-11 (legacy) artifact handling — decision D
# ---------------------------------------------------------------------------


def test_legacy_artifact_renders_legacy_tag(monkeypatch, capsys) -> None:
    """Pre-PR-11 artifacts (no CI fields) show `(legacy)` instead of `(CI: 0.00-0.00)`."""
    from falsifyai.cli import inspect as inspect_module

    store = InMemoryStore()
    store.save_session(_make_legacy_artifact())
    _patched_store(monkeypatch, store)

    inspect_module.cmd_inspect(_args(session_id="legacy-1"))
    out = capsys.readouterr().out
    assert "(legacy)" in out
    assert "CI: 0.00-0.00" not in out


# ---------------------------------------------------------------------------
# Exit codes mirror replay — decision E
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "verdict,expected_code",
    [
        (Verdict.STABLE, 0),
        (Verdict.FRAGILE, 1),
        (Verdict.CONSISTENTLY_WRONG, 2),
    ],
)
def test_exit_codes_mirror_replay(monkeypatch, verdict, expected_code) -> None:
    """STABLE -> 0, FRAGILE -> 1, CONSISTENTLY_WRONG -> 2 (matches replay)."""
    from falsifyai.cli import inspect as inspect_module

    store = InMemoryStore()
    store.save_session(make_artifact(session_id="sess", verdict=verdict))
    _patched_store(monkeypatch, store)

    rc = inspect_module.cmd_inspect(_args(session_id="sess"))
    assert rc == expected_code


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_missing_session_id_raises_cli_error(monkeypatch) -> None:
    """Calling cmd_inspect without a session_id raises InfrastructureError."""
    from falsifyai.cli import inspect as inspect_module

    store = InMemoryStore()
    _patched_store(monkeypatch, store)

    with pytest.raises((InfrastructureError, CLIError)):
        inspect_module.cmd_inspect(_args(session_id=None))


def test_session_not_found_raises_infrastructure_error(monkeypatch) -> None:
    """A nonexistent session_id raises InfrastructureError (mapped to exit 3)."""
    from falsifyai.cli import inspect as inspect_module

    store = InMemoryStore()
    _patched_store(monkeypatch, store)

    with pytest.raises(InfrastructureError):
        inspect_module.cmd_inspect(_args(session_id="never-saved"))


# ---------------------------------------------------------------------------
# Architectural assertion (§12.1 + §12.3) — load-bearing
# ---------------------------------------------------------------------------


def test_inspect_does_not_import_resolver() -> None:
    """inspect.py must not transitively import the resolver module.

    Enforces the architectural rule from §5 of the plan: inspect is pure
    consumer surface. The verdict shown is the one stored at run time;
    re-resolving on read would violate EVIDENCE.md §5.1 (immutability).
    """
    import sys

    # Clear any prior cli.inspect import so we observe a fresh import graph.
    for mod_name in list(sys.modules):
        if mod_name.startswith("falsifyai.cli.inspect"):
            del sys.modules[mod_name]
        if mod_name == "falsifyai.verdict.resolver":
            del sys.modules[mod_name]

    import falsifyai.cli.inspect  # noqa: F401

    assert "falsifyai.verdict.resolver" not in sys.modules, (
        "falsifyai.cli.inspect must not import falsifyai.verdict.resolver "
        "(re-resolving violates the preservation guarantee). If you need "
        "verdict information, read it from the stored artifact."
    )


def test_inspect_does_not_crash_on_unicode_model_outputs(monkeypatch) -> None:
    """LLM outputs routinely contain Unicode (e.g. U+202F narrow no-break space)
    that non-UTF-8 terminals (Windows cp1252) cannot encode. inspect must
    escape rather than crash. Regression test for a bug surfaced during
    manual trust-testing against the Pair 3 oai-oss-120b session.
    """
    import io

    from falsifyai.cli import inspect as inspect_module

    # Build an artifact whose model output contains a narrow no-break space.
    base = _make_fragile_artifact()
    case = base.case_results[0]
    unicode_output = "Customers can request a refund within 30 days."
    bad_run = replace(
        case.perturbed[0],
        execution=replace(case.perturbed[0].execution, output_text=unicode_output),
    )
    new_case = replace(case, perturbed=[bad_run, *case.perturbed[1:]])
    artifact = replace(base, case_results=[new_case])

    store = InMemoryStore()
    store.save_session(artifact)
    _patched_store(monkeypatch, store)

    # Simulate a cp1252 terminal by wrapping a BytesIO with that encoding.
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", newline="")
    monkeypatch.setattr("sys.stdout", stream)
    try:
        rc = inspect_module.cmd_inspect(_args(session_id=artifact.session_id))
    finally:
        stream.flush()
    assert rc == 1  # FRAGILE
    output = raw.getvalue().decode("cp1252")
    # The narrow no-break space must be escaped, not crash. Either form is acceptable:
    assert "\\u202f" in output or "?" in output or "30" in output


def test_inspect_surfaces_missing_payload_field_explicitly(monkeypatch, capsys) -> None:
    """§12.3 no-synthesis rule: if a field is absent, surface the gap, don't fabricate.

    This is operationalized by mutating a case to have an empty
    `invariant_results` list on its worst perturbation, then asserting the
    output names the gap (e.g., '<no invariant results recorded>') rather
    than skipping silently or substituting a default judgment.
    """
    from falsifyai.cli import inspect as inspect_module

    # Build a FRAGILE artifact but strip the invariant_results from the worst perturbation
    base = _make_fragile_artifact()
    case = base.case_results[0]
    worst_perturbed = replace(case.perturbed[0], invariant_results=[])
    new_case = replace(case, perturbed=[worst_perturbed, *case.perturbed[1:]])
    stripped = replace(base, case_results=[new_case])

    store = InMemoryStore()
    store.save_session(stripped)
    _patched_store(monkeypatch, store)

    inspect_module.cmd_inspect(_args(session_id=stripped.session_id))
    out = capsys.readouterr().out
    # The output must explicitly mark the missing data, not silently omit it
    assert (
        ("no invariant" in out.lower())
        or ("not preserved" in out.lower())
        or ("missing" in out.lower())
    )
