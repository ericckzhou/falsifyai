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
    assert [c.id for c in spec.cases] == ["capital_factual", "definition_consistency"]


def test_model_migration_yaml_diff_produces_regression(tmp_path, monkeypatch) -> None:
    """Run the spec twice with different MockAdapter responses; diff returns 5.

    Workflow demonstrated:
    1. "Model A" (good): answers contain "Paris" and "plants" -> both STABLE.
    2. "Model B" (degraded): answers miss both ground-truth keywords ->
       CONSISTENTLY_WRONG on both cases.
    3. diff(A, B) detects the regression and exits 5.
    """
    import argparse

    import falsifyai.cli.diff as cli_diff_mod
    from falsifyai.replay.sqlite_store import SQLiteStore

    spec_path = _EXAMPLES / "model_migration.yaml"
    db_path = str(tmp_path / "replays.db")

    def _run_args(store_path: str):
        return argparse.Namespace(spec_path=str(spec_path), store_path=store_path)

    # Baseline run -- "good" model.
    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)
    good_responses = {
        "capital_factual": "Paris is the capital of France.",
        "definition_consistency": "Photosynthesis is the process by which plants make energy.",
    }
    good_adapter = MockAdapter(response_map=_build_response_map(spec, materialized, good_responses))
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: good_adapter)
    cli_run.cmd_run(_run_args(db_path))

    # Candidate run -- "degraded" model that misses ground-truth keywords.
    bad_responses = {
        "capital_factual": "I'm not sure what the capital is.",
        "definition_consistency": "It's a biological process I can't fully define.",
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
