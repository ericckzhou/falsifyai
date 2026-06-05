"""Dogfood tests for the example specs under ``examples/``.

These tests are part of the default ``pytest`` run -- they're fast,
deterministic, and use MockAdapter. They serve a double role:

1. **Acceptance gate** — examples/stable.yaml must produce STABLE;
   examples/fragile.yaml must produce FRAGILE (per
   [plan.md section 22.1.1](../../plan.md)).
2. **Spec-language regression** — if the spec parser ever rejects a key
   the examples use, CI fails immediately. Examples ARE the canonical
   user-facing specs.

Pattern: load the YAML -> materialize -> harvest the realized perturbation
texts -> build a MockAdapter response_map keyed on those texts -> inject
via the ``build_adapter`` test seam -> run ``cmd_run`` -> assert exit code.

Semantic-equivalence invariants would normally pull in
``sentence-transformers`` on first ``.embed()``. We monkey-patch
``SentenceTransformerBackend.embed`` to a deterministic hash-based embedder
so CI never downloads a real model.
"""

import argparse
import hashlib
import re
from pathlib import Path

import numpy as np
import pytest

import falsifyai.cli.run as cli_run
import falsifyai.invariants.semantic as sem
from falsifyai.spec.loader import load_spec
from falsifyai.spec.materializer import materialize
from tests.fixtures.mock_adapter import MockAdapter

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _deterministic_embed(self, texts: list[str]) -> np.ndarray:  # noqa: ANN001
    """Hash-based replacement for SentenceTransformerBackend.embed.

    Identical input strings -> identical seed -> identical unit vector ->
    cosine similarity 1.0. That's what we want for stable cases where the
    mock returns the same output to baseline and perturbed prompts.
    """
    out = []
    for text in texts:
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big") % (2**32)
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(8)
        out.append(v / np.linalg.norm(v))
    return np.array(out, dtype=np.float64)


@pytest.fixture
def patch_embed_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace SentenceTransformerBackend.embed with a deterministic hash embedder."""
    monkeypatch.setattr(sem.SentenceTransformerBackend, "embed", _deterministic_embed)


def _build_response_map(spec, materialized, responses_by_case_id: dict[str, str]) -> dict[str, str]:
    """Per case, map both the baseline input and every perturbed input to one response."""
    out: dict[str, str] = {}
    for case_spec, mcase in zip(spec.cases, materialized.cases, strict=True):
        resp = responses_by_case_id[case_spec.id]
        out[mcase.original_input] = resp
        for pi in mcase.realized_perturbations:
            out[pi.text] = resp
    return out


def _args(spec_path: Path, store_path: str = ":memory:") -> argparse.Namespace:
    return argparse.Namespace(spec_path=str(spec_path), store_path=store_path)


# ---------------------------------------------------------------------------
# stable.yaml
# ---------------------------------------------------------------------------


def test_stable_yaml_is_a_valid_spec() -> None:
    """Cheap parse check; catches YAML typos before the heavier verdict test."""
    spec, spec_hash = load_spec(_EXAMPLES / "stable.yaml")
    assert spec.run.seed == 42
    assert {c.id for c in spec.cases} == {"capital_of_france", "define_photosynthesis"}
    assert len(spec_hash) == 64  # sha256


def test_stable_yaml_produces_stable_verdict(monkeypatch, patch_embed_backend) -> None:
    """Both cases pass under perturbation when the mock returns the same answer."""
    spec_path = _EXAMPLES / "stable.yaml"
    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)

    responses = {
        "capital_of_france": "Paris is the capital of France.",
        "define_photosynthesis": (
            "Photosynthesis is the process by which plants convert light into chemical energy."
        ),
    }
    adapter = MockAdapter(response_map=_build_response_map(spec, materialized, responses))
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    rc = cli_run.cmd_run(_args(spec_path))
    assert rc == 0  # STABLE -> SUCCESS


# ---------------------------------------------------------------------------
# fragile.yaml
# ---------------------------------------------------------------------------


def test_fragile_yaml_is_a_valid_spec() -> None:
    spec, _ = load_spec(_EXAMPLES / "fragile.yaml")
    assert spec.run.seed == 42
    assert [c.id for c in spec.cases] == ["capital_of_france_fragile"]
    # 5 typo samples requested.
    assert spec.cases[0].perturbations[0].count == 5


def test_fragile_yaml_produces_fragile_verdict(monkeypatch) -> None:
    """Baseline returns 'Paris'; every perturbed prompt returns 'I'm not sure.'"""
    spec_path = _EXAMPLES / "fragile.yaml"
    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)

    response_map: dict[str, str] = {}
    case = materialized.cases[0]
    response_map[case.original_input] = "Paris is the capital of France."
    for pi in case.realized_perturbations:
        response_map[pi.text] = "I'm not sure."
    adapter = MockAdapter(response_map=response_map)
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    rc = cli_run.cmd_run(_args(spec_path))
    assert rc == 1  # FRAGILE -> DEGRADED


# ---------------------------------------------------------------------------
# consistently_wrong.yaml (PR #11)
# ---------------------------------------------------------------------------


def test_consistently_wrong_yaml_is_a_valid_spec() -> None:
    spec, _ = load_spec(_EXAMPLES / "consistently_wrong.yaml")
    assert spec.run.seed == 42
    assert [c.id for c in spec.cases] == ["capital_of_france_hallucinated"]
    assert spec.cases[0].expected.contains == ["Paris"]


def test_consistently_wrong_yaml_produces_consistently_wrong_verdict(monkeypatch) -> None:
    """Every output (baseline + perturbed) returns 'London' -- the wrong answer.

    Because expected.contains: ["Paris"] is violated on EVERY output, the
    resolver returns CONSISTENTLY_WRONG, not FRAGILE.
    """
    spec_path = _EXAMPLES / "consistently_wrong.yaml"
    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)

    responses = {
        "capital_of_france_hallucinated": "London is the capital of France.",
    }
    adapter = MockAdapter(response_map=_build_response_map(spec, materialized, responses))
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    rc = cli_run.cmd_run(_args(spec_path))
    assert rc == 2  # CONSISTENTLY_WRONG -> FAILURE


# ---------------------------------------------------------------------------
# model_migration.yaml (PR #14)
# ---------------------------------------------------------------------------


def test_model_migration_yaml_is_a_valid_spec() -> None:
    spec, _ = load_spec(_EXAMPLES / "model_migration.yaml")
    assert spec.run.seed == 42
    assert [c.id for c in spec.cases] == [
        "factual_recall",
        "structured_output",
        "extraction",
        "policy_summary",
    ]


def test_model_migration_yaml_diff_produces_regression(tmp_path, monkeypatch) -> None:
    """Run the spec twice with different MockAdapter responses; diff returns 5.

    Workflow demonstrated:
    1. "Model A" (good): all four cases pass their contains invariants -> STABLE.
    2. "Model B" (degraded): two cases (structured_output, extraction) lose
       required values -> CONSISTENTLY_WRONG; the other two stay STABLE.
    3. diff(A, B) detects 2 regressed cases (and 2 unchanged) -> exits 5.

    This is the multi-case behavioral-pattern story the README walkthrough
    teaches: a migration that breaks structured output and extraction but
    preserves factual recall and definitions.
    """
    import argparse

    import falsifyai.cli.diff as cli_diff_mod
    from falsifyai.replay.sqlite_store import SQLiteStore

    spec_path = _EXAMPLES / "model_migration.yaml"
    db_path = str(tmp_path / "replays.db")

    def _run_args(store_path: str):
        return argparse.Namespace(spec_path=str(spec_path), store_path=store_path)

    # Baseline run -- "good" model. All four contracts satisfied.
    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)
    good_responses = {
        "factual_recall": "Paris is the capital of France.",
        "structured_output": '{"capital": "Tokyo"}',
        "extraction": "alice@example.com, bob@example.com",
        "policy_summary": ("Refunds are available within 30 days for unused items with a receipt."),
    }
    good_adapter = MockAdapter(response_map=_build_response_map(spec, materialized, good_responses))
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: good_adapter)
    cli_run.cmd_run(_run_args(db_path))

    # Candidate run -- "degraded" model. Breaks structured_output (drops the
    # quoted "capital" key) and extraction (refuses to list emails); preserves
    # factual_recall and definition_consistency.
    bad_responses = {
        "factual_recall": "Paris is the capital of France.",  # unchanged -> STABLE
        "structured_output": "The capital is Tokyo.",  # missing '"capital"' -> CONSISTENTLY_WRONG
        "extraction": "I cannot list email addresses.",  # missing both emails -> CONSISTENTLY_WRONG
        # still mentions 30 days, unused, receipt -> STABLE (policy grounding preserved)
        "policy_summary": ("Refunds within 30 days, item must be unused, receipt required."),
    }
    bad_adapter = MockAdapter(response_map=_build_response_map(spec, materialized, bad_responses))
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: bad_adapter)
    cli_run.cmd_run(_run_args(db_path))

    # Retrieve both session ids (newest-first).
    with SQLiteStore(db_path) as store:
        sessions = list(store.query_sessions(limit=2))
    candidate_id, baseline_id = sessions[0].session_id, sessions[1].session_id

    rc = cli_diff_mod.cmd_diff(
        argparse.Namespace(
            baseline_session_id=baseline_id,
            candidate_session_id=candidate_id,
            store_path=db_path,
        )
    )
    assert rc == 5  # REGRESSION detected -> launch wedge acceptance gate item


# ---------------------------------------------------------------------------
# falsifyai inspect <session_id> (PR #19)
# ---------------------------------------------------------------------------


def test_fragile_yaml_inspect_surfaces_worst_perturbation_evidence(
    tmp_path, monkeypatch, capsys
) -> None:
    """End-to-end: run fragile.yaml -> retrieve session -> inspect -> assert evidence.

    Verifies the dogfood flow:
    1. ``cmd_run`` against the fragile example produces a FRAGILE session.
    2. The stored artifact contains the per-case evidence trail.
    3. ``cmd_inspect <session_id>`` surfaces the worst-perturbation evidence
       (perturbed input + output excerpt + failing invariant) in its default
       output — the trust test from the PR-19 plan.

    The acceptance criterion: a reader looking at the inspect output should be
    able to reconstruct why the verdict was FRAGILE without consulting docs.
    """
    import argparse

    import falsifyai.cli.inspect as cli_inspect_mod
    from falsifyai.replay.sqlite_store import SQLiteStore

    spec_path = _EXAMPLES / "fragile.yaml"
    db_path = str(tmp_path / "replays.db")

    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)

    case = materialized.cases[0]
    response_map: dict[str, str] = {case.original_input: "Paris is the capital of France."}
    for pi in case.realized_perturbations:
        response_map[pi.text] = "I'm not sure."
    adapter = MockAdapter(response_map=response_map)
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    rc = cli_run.cmd_run(argparse.Namespace(spec_path=str(spec_path), store_path=db_path))
    assert rc == 1  # FRAGILE -> DEGRADED

    with SQLiteStore(db_path) as store:
        sessions = list(store.query_sessions(limit=1))
    session_id = sessions[0].session_id

    capsys.readouterr()  # discard run's output

    rc = cli_inspect_mod.cmd_inspect(
        argparse.Namespace(
            session_id=session_id,
            case=None,
            full=False,
            store_path=db_path,
        )
    )
    assert rc == 1  # FRAGILE -> DEGRADED (mirrors run)

    out = capsys.readouterr().out
    # Session header
    assert session_id in out
    assert "Inspecting session" in out
    # Per-case header with verdict + count
    assert "capital_of_france_fragile" in out
    assert "FRAGILE" in out
    assert "perturbations:" in out
    # Worst-perturbation evidence (the trust-test substance)
    assert "perturbed input:" in out
    assert "output excerpt:" in out
    assert "failing invariant:" in out
    # The mock response is the failing output
    assert "I'm not sure" in out


def test_fragile_yaml_inspect_case_flag_shows_all_perturbations(
    tmp_path, monkeypatch, capsys
) -> None:
    """`falsifyai inspect <id> --case <case_id>` expands every perturbation."""
    import argparse

    import falsifyai.cli.inspect as cli_inspect_mod
    from falsifyai.replay.sqlite_store import SQLiteStore

    spec_path = _EXAMPLES / "fragile.yaml"
    db_path = str(tmp_path / "replays.db")

    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)

    case = materialized.cases[0]
    response_map: dict[str, str] = {case.original_input: "Paris is the capital of France."}
    for pi in case.realized_perturbations:
        response_map[pi.text] = "I'm not sure."
    adapter = MockAdapter(response_map=response_map)
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    cli_run.cmd_run(argparse.Namespace(spec_path=str(spec_path), store_path=db_path))

    with SQLiteStore(db_path) as store:
        sessions = list(store.query_sessions(limit=1))
    session_id = sessions[0].session_id

    capsys.readouterr()

    cli_inspect_mod.cmd_inspect(
        argparse.Namespace(
            session_id=session_id,
            case="capital_of_france_fragile",
            full=False,
            store_path=db_path,
        )
    )
    out = capsys.readouterr().out
    # Expanded view shows baseline + every perturbation, indexed
    assert "baseline input:" in out
    assert "baseline output:" in out
    # fragile.yaml has 5 typo samples, so [1] through [5] should appear
    assert "[1]" in out
    assert "[5]" in out
    # Every perturbation is from the typo_noise family
    assert out.count("typo_noise") >= 5


# ---------------------------------------------------------------------------
# paraphrase.yaml (PR #22)
# ---------------------------------------------------------------------------


def test_paraphrase_yaml_is_a_valid_spec() -> None:
    spec, _ = load_spec(_EXAMPLES / "paraphrase.yaml")
    assert spec.run.seed == 42
    assert [c.id for c in spec.cases] == ["capital_of_france_paraphrase"]
    assert spec.cases[0].perturbations[0].type == "paraphrase"
    assert spec.cases[0].perturbations[0].count == 3


def test_paraphrase_yaml_produces_stable_verdict(monkeypatch) -> None:
    """Run paraphrase.yaml end-to-end through MockAdapter.

    The adapter responds to BOTH paraphrase generation prompts (those
    containing "Rewritten:") and execution prompts (the paraphrased inputs).
    The embedding backend is monkey-patched to a constant-vector embedder so
    every paraphrase passes the validity gate.
    """
    spec_path = _EXAMPLES / "paraphrase.yaml"

    # Constant-vector embedder: all texts -> same unit vector -> cosine 1.0
    def _constant_embed(self, texts: list[str]) -> np.ndarray:  # noqa: ANN001
        return np.tile(np.array([1.0, 0.0, 0.0]), (len(texts), 1))

    monkeypatch.setattr(sem.SentenceTransformerBackend, "embed", _constant_embed)

    # MockAdapter with a callable default_response that distinguishes
    # paraphrase-generation prompts (contain "Rewritten:") from execution
    # prompts (everything else — the perturbed text itself).
    def _responder(prompt: str) -> str:
        if "Rewritten:" in prompt:
            # Paraphrase generation — return a semantically-equivalent rewrite.
            # The exact text doesn't matter; only that it differs from baseline
            # so the perturbation is meaningful.
            return "Which city serves as France's capital?"
        # Execution: the baseline or perturbed input arrives as the prompt.
        # Return the correct answer.
        return "Paris is the capital of France."

    # MockAdapter's response_map keys on exact prompts; we want callable
    # behavior so we use a callable default_response by sentinel.
    adapter = MockAdapter()
    adapter.response_map = {}
    original_execute = adapter.execute

    def stateful_execute(request):
        adapter.default_response = _responder(request.prompt)
        return original_execute(request)

    adapter.execute = stateful_execute  # type: ignore[method-assign]
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    rc = cli_run.cmd_run(_args(spec_path))
    assert rc == 0  # STABLE -> SUCCESS — "Paris" appears in every output


def test_paraphrase_yaml_lineage_carries_paraphrase_metadata(monkeypatch) -> None:
    """After materialize+execute, the realized perturbations carry the
    paraphrase-specific lineage fields documented in PR-22."""
    spec_path = _EXAMPLES / "paraphrase.yaml"

    def _constant_embed(self, texts: list[str]) -> np.ndarray:  # noqa: ANN001
        return np.tile(np.array([1.0, 0.0, 0.0]), (len(texts), 1))

    monkeypatch.setattr(sem.SentenceTransformerBackend, "embed", _constant_embed)

    adapter = MockAdapter()
    adapter.response_map = {}
    original_execute = adapter.execute

    def stateful_execute(request):
        if "Rewritten:" in request.prompt:
            adapter.default_response = "Which city is the capital of France?"
        else:
            adapter.default_response = "Paris is France's capital."
        return original_execute(request)

    adapter.execute = stateful_execute  # type: ignore[method-assign]

    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash, adapter=adapter)

    case = materialized.cases[0]
    assert len(case.realized_perturbations) == 3
    for pi in case.realized_perturbations:
        params = pi.lineage.params
        assert pi.lineage.perturbation_type == "paraphrase"
        assert params["requested_count"] == 3
        assert "attempts_used" in params
        assert "validity_score" in params


# ---------------------------------------------------------------------------
# unicode_regression.yaml (PR-A) — closes the CS-01 loop
# ---------------------------------------------------------------------------


def test_unicode_regression_yaml_is_a_valid_spec() -> None:
    spec, _ = load_spec(_EXAMPLES / "unicode_regression.yaml")
    assert spec.run.seed == 42
    assert [c.id for c in spec.cases] == ["capital_of_france_unicode"]
    pert = spec.cases[0].perturbations[0]
    assert pert.type == "unicode"
    assert pert.methods == ["invisible_space", "zero_width", "homoglyph"]
    assert pert.count == 3


def test_unicode_regression_yaml_produces_fragile_verdict(monkeypatch) -> None:
    """Baseline returns 'Paris'; every invisible-char perturbation returns the
    wrong answer -> FRAGILE. This is the generation-side complement to CS-01:
    FalsifyAI now *generates* the byte-different input that breaks the model."""
    spec_path = _EXAMPLES / "unicode_regression.yaml"
    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)

    case = materialized.cases[0]
    # Sanity: the realized perturbations are byte-different from the original
    # (they carry invisible/confusable characters) yet share its meaning.
    assert any(pi.text != case.original_input for pi in case.realized_perturbations)

    response_map: dict[str, str] = {case.original_input: "Paris is the capital of France."}
    for pi in case.realized_perturbations:
        response_map[pi.text] = "I'm not sure."
    adapter = MockAdapter(response_map=response_map)
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    rc = cli_run.cmd_run(_args(spec_path))
    assert rc == 1  # FRAGILE -> DEGRADED


# ---------------------------------------------------------------------------
# schema_match.yaml (PR-B) — structural JSON assertion
# ---------------------------------------------------------------------------


def test_schema_match_yaml_is_a_valid_spec() -> None:
    spec, _ = load_spec(_EXAMPLES / "schema_match.yaml")
    assert spec.run.seed == 42
    assert [c.id for c in spec.cases] == ["capital_json_schema"]
    inv = spec.cases[0].invariants[0]
    assert inv.type == "schema_match"
    assert inv.json_schema["required"] == ["capital"]


def test_schema_match_yaml_produces_fragile_verdict(monkeypatch) -> None:
    """Baseline returns valid JSON; every perturbation degrades to prose, which
    fails the schema -> FRAGILE. This is the structured-output assertion the
    `contains` invariant could only approximate."""
    spec_path = _EXAMPLES / "schema_match.yaml"
    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)

    case = materialized.cases[0]
    response_map: dict[str, str] = {case.original_input: '{"capital": "Tokyo"}'}
    for pi in case.realized_perturbations:
        response_map[pi.text] = "The capital is Tokyo."  # prose -> not valid JSON
    adapter = MockAdapter(response_map=response_map)
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    rc = cli_run.cmd_run(_args(spec_path))
    assert rc == 1  # FRAGILE -> DEGRADED


def test_schema_match_yaml_stable_when_structure_preserved(monkeypatch) -> None:
    """When every output is valid JSON conforming to the schema -> STABLE."""
    spec_path = _EXAMPLES / "schema_match.yaml"
    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)

    responses = {"capital_json_schema": '{"capital": "Tokyo"}'}
    adapter = MockAdapter(response_map=_build_response_map(spec, materialized, responses))
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    rc = cli_run.cmd_run(_args(spec_path))
    assert rc == 0  # STABLE -> SUCCESS


# ---------------------------------------------------------------------------
# invalid_eval.yaml (PR-D) — meta-oracle / INVALID_EVAL
# ---------------------------------------------------------------------------


def test_invalid_eval_yaml_is_a_valid_spec() -> None:
    spec, _ = load_spec(_EXAMPLES / "invalid_eval.yaml")
    assert spec.run.seed == 42
    assert [c.id for c in spec.cases] == ["arithmetic_malformed_invariant"]
    assert spec.cases[0].invariants[0].values == ["ELEPHANT"]


def test_invalid_eval_yaml_produces_invalid_eval_verdict(monkeypatch) -> None:
    """The contains invariant fails on the baseline AND every perturbation, with
    no ground truth to explain it -> the meta-oracle flags INVALID_EVAL (exit 2)."""
    spec_path = _EXAMPLES / "invalid_eval.yaml"
    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)

    # Model answers correctly ("4") everywhere; the invariant is the broken part.
    responses = {"arithmetic_malformed_invariant": "The answer is 4."}
    adapter = MockAdapter(response_map=_build_response_map(spec, materialized, responses))
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    rc = cli_run.cmd_run(_args(spec_path))
    assert rc == 2  # INVALID_EVAL -> exit 2


# ---------------------------------------------------------------------------
# falsifyai history <case_id> (PR #24)
# ---------------------------------------------------------------------------


def test_history_against_repeated_runs(tmp_path, monkeypatch, capsys) -> None:
    """End-to-end: run stable.yaml twice, then `history <case_id>` shows both
    sessions in newest-first order.

    Verifies the dogfood flow:
    1. Two ``cmd_run`` invocations against the same spec produce two
       distinct sessions sharing the same case_id.
    2. ``cmd_history <case_id>`` against the SQLite store surfaces both
       sessions, newest-first (decision Y1).
    3. Exit code 0 on render success regardless of verdict mix (E1).
    """
    import argparse

    import falsifyai.cli.history as cli_history_mod
    from falsifyai.replay.sqlite_store import SQLiteStore

    spec_path = _EXAMPLES / "stable.yaml"
    db_path = str(tmp_path / "replays.db")

    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)

    responses = {
        "capital_of_france": "Paris is the capital of France.",
        "define_photosynthesis": (
            "Photosynthesis is the process by which plants convert light into chemical energy."
        ),
    }
    adapter = MockAdapter(response_map=_build_response_map(spec, materialized, responses))
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    # Run twice — two distinct sessions, same case_ids
    monkeypatch.setattr(sem.SentenceTransformerBackend, "embed", _deterministic_embed)
    cli_run.cmd_run(_args(spec_path, store_path=db_path))
    cli_run.cmd_run(_args(spec_path, store_path=db_path))

    with SQLiteStore(db_path) as store:
        sessions = list(store.query_sessions(limit=5))
    assert len(sessions) == 2  # two saved runs against the same spec
    newer_id, older_id = sessions[0].session_id, sessions[1].session_id

    capsys.readouterr()  # discard run output

    rc = cli_history_mod.cmd_history(
        argparse.Namespace(
            case_id="capital_of_france",
            limit=20,
            store_path=db_path,
        )
    )
    assert rc == 0  # E1: render-success exit code

    out = capsys.readouterr().out
    # Both session prefixes appear
    assert newer_id[:8] in out
    assert older_id[:8] in out
    # Newest-first ordering: the newer session_id appears before the older
    assert out.find(newer_id[:8]) < out.find(older_id[:8])
    # Verdict (STABLE) and case_id present
    assert "STABLE" in out
    assert "capital_of_france" in out
    # Footer shows the count
    assert "2 sessions matched" in out


def test_history_unknown_case_raises_infrastructure_error(tmp_path, monkeypatch) -> None:
    """A case_id that matches zero sessions raises InfrastructureError → exit 3."""
    import argparse

    import falsifyai.cli.history as cli_history_mod
    from falsifyai.cli.errors import InfrastructureError

    spec_path = _EXAMPLES / "stable.yaml"
    db_path = str(tmp_path / "replays.db")

    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)
    responses = {
        "capital_of_france": "Paris.",
        "define_photosynthesis": "Plants convert light.",
    }
    adapter = MockAdapter(response_map=_build_response_map(spec, materialized, responses))
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)
    monkeypatch.setattr(sem.SentenceTransformerBackend, "embed", _deterministic_embed)
    cli_run.cmd_run(_args(spec_path, store_path=db_path))

    with pytest.raises(InfrastructureError):
        cli_history_mod.cmd_history(
            argparse.Namespace(
                case_id="does_not_exist",
                limit=20,
                store_path=db_path,
            )
        )


# ---------------------------------------------------------------------------
# adversarially_vulnerable.yaml (PR-K)
# ---------------------------------------------------------------------------


def test_adversarially_vulnerable_yaml_is_a_valid_spec() -> None:
    spec, _ = load_spec(_EXAMPLES / "adversarially_vulnerable.yaml")
    assert spec.run.seed == 42
    assert [c.id for c in spec.cases] == ["capital_of_france_casing_attack"]


def test_adversarially_vulnerable_yaml_produces_adversarially_vulnerable(
    monkeypatch, capsys
) -> None:
    """typo_noise outputs are correct; casing outputs are wrong -> targeted attack."""
    spec_path = _EXAMPLES / "adversarially_vulnerable.yaml"
    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)

    case = materialized.cases[0]
    response_map: dict[str, str] = {case.original_input: "Paris is the capital of France."}
    for pi in case.realized_perturbations:
        if pi.lineage.perturbation_type == "typo_noise":
            response_map[pi.text] = "Paris is the capital of France."  # family holds
        else:  # casing
            response_map[pi.text] = "London is the capital."  # family collapses
    adapter = MockAdapter(response_map=response_map)
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    rc = cli_run.cmd_run(_args(spec_path))
    assert rc == 2  # ADVERSARIALLY_VULNERABLE -> FAILURE

    # Gate-6 dogfood (case study 05): instability-band verdicts surface the
    # stability *floor*, not "confidence". The rendered metric is verdict_confidence
    # = ci_low, near 0 exactly when most broken -- the "confidence" label inverted
    # its meaning here, so the per-case row must read "stability floor:" instead.
    out = capsys.readouterr().out
    assert "ADVERSARIALLY_VULNERABLE" in out
    assert "stability floor:" in out
    assert "confidence:" not in out


def test_adversarially_vulnerable_inspect_shows_stability_floor(
    monkeypatch, capsys, tmp_path
) -> None:
    """End-to-end dogfood for the band-aware label on the *inspect* surface
    (case study 05 follow-up). ``inspect`` renders the per-case metric with its
    own code path, so the band-aware label is proved here through the real
    run -> save -> inspect pipeline: a genuine near-zero CI floor on a true
    ADVERSARIALLY_VULNERABLE verdict must read ``stability floor:``, never
    ``confidence:``."""
    import falsifyai.cli.inspect as cli_inspect

    spec_path = _EXAMPLES / "adversarially_vulnerable.yaml"
    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)

    case = materialized.cases[0]
    response_map: dict[str, str] = {case.original_input: "Paris is the capital of France."}
    for pi in case.realized_perturbations:
        if pi.lineage.perturbation_type == "typo_noise":
            response_map[pi.text] = "Paris is the capital of France."  # family holds
        else:  # casing
            response_map[pi.text] = "London is the capital."  # family collapses
    adapter = MockAdapter(response_map=response_map)
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    db = tmp_path / "replays.db"
    rc = cli_run.cmd_run(_args(spec_path, store_path=str(db)))
    assert rc == 2  # ADVERSARIALLY_VULNERABLE -> FAILURE
    run_out = capsys.readouterr().out
    m = re.search(r"Session (\S+) ->", run_out)
    assert m, run_out
    session_id = m.group(1)

    inspect_args = argparse.Namespace(
        session_id=session_id, case=None, full=False, store_path=str(db)
    )
    ic = cli_inspect.cmd_inspect(inspect_args)
    assert ic == 2  # inspect mirrors the session-verdict exit code
    out = capsys.readouterr().out
    assert "ADVERSARIALLY_VULNERABLE" in out
    assert "stability floor:" in out
    assert "confidence:" not in out


# ---------------------------------------------------------------------------
# information_null.yaml (PR-K)
# ---------------------------------------------------------------------------


def test_information_null_yaml_is_a_valid_spec() -> None:
    spec, _ = load_spec(_EXAMPLES / "information_null.yaml")
    assert [c.id for c in spec.cases] == ["refused_question"]


def test_information_null_yaml_produces_information_null(monkeypatch, patch_embed_backend) -> None:
    """Every output is the same refusal: stable structure, empty information."""
    spec_path = _EXAMPLES / "information_null.yaml"
    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)

    refusal = "I cannot answer that question."
    adapter = MockAdapter(
        response_map=_build_response_map(spec, materialized, {"refused_question": refusal})
    )
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    rc = cli_run.cmd_run(_args(spec_path))
    assert rc == 1  # INFORMATION_NULL -> DEGRADED


# ---------------------------------------------------------------------------
# ambiguous.yaml (PR-K)
# ---------------------------------------------------------------------------


def test_ambiguous_yaml_is_a_valid_spec() -> None:
    spec, _ = load_spec(_EXAMPLES / "ambiguous.yaml")
    assert [c.id for c in spec.cases] == ["capital_of_france_underpowered"]
    assert spec.cases[0].perturbations[0].count == 2  # deliberately underpowered


def test_ambiguous_yaml_produces_ambiguous(monkeypatch) -> None:
    """Two samples, one right one wrong -> wide CI -> AMBIGUOUS (can't discriminate)."""
    spec_path = _EXAMPLES / "ambiguous.yaml"
    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)

    case = materialized.cases[0]
    response_map: dict[str, str] = {case.original_input: "Paris is the capital of France."}
    for idx, pi in enumerate(case.realized_perturbations):
        response_map[pi.text] = (
            "Paris is the capital of France." if idx % 2 == 0 else "London is the capital."
        )
    adapter = MockAdapter(response_map=response_map)
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    rc = cli_run.cmd_run(_args(spec_path))
    assert rc == 1  # AMBIGUOUS -> DEGRADED


# ---------------------------------------------------------------------------
# information_present.yaml (PR-L: --nli wiring)
# ---------------------------------------------------------------------------


def test_information_present_yaml_is_a_valid_spec() -> None:
    spec, _ = load_spec(_EXAMPLES / "information_present.yaml")
    assert [c.id for c in spec.cases] == ["capital_of_france_grounded"]
    assert spec.cases[0].expected.reference == "The capital of France is Paris."


def test_information_present_yaml_produces_information_present(monkeypatch) -> None:
    """Stable AND grounded (NLI entailment vs reference) -> INFORMATION_PRESENT.

    Injects a deterministic MockNLIBackend through the build_nli_backend seam so
    CI never downloads the real model; the --nli flag path is exercised end-to-end.
    """
    from falsifyai.oracles.nli import MockNLIBackend, NLILabel

    spec_path = _EXAMPLES / "information_present.yaml"
    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)

    answer = "Paris is the capital of France."
    adapter = MockAdapter(
        response_map=_build_response_map(spec, materialized, {"capital_of_france_grounded": answer})
    )
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)
    # Seam: every output entails the reference -> grounded.
    grounded_nli = MockNLIBackend(default_label=NLILabel.ENTAILMENT)
    monkeypatch.setattr(cli_run, "build_nli_backend", lambda enabled: grounded_nli)

    args = argparse.Namespace(spec_path=str(spec_path), store_path=":memory:", nli=True)
    rc = cli_run.cmd_run(args)
    assert rc == 0  # INFORMATION_PRESENT -> SUCCESS


def test_information_present_yaml_without_nli_is_stable(monkeypatch) -> None:
    """Same spec, no --nli: grounding isn't computed -> plain STABLE (still exit 0)."""
    spec_path = _EXAMPLES / "information_present.yaml"
    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)

    answer = "Paris is the capital of France."
    adapter = MockAdapter(
        response_map=_build_response_map(spec, materialized, {"capital_of_france_grounded": answer})
    )
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)

    args = argparse.Namespace(spec_path=str(spec_path), store_path=":memory:", nli=False)
    rc = cli_run.cmd_run(args)
    assert rc == 0  # STABLE -> SUCCESS (no NLI backend -> grounding inert)
