"""End-to-end: run a spec across two sessions, then `matrix` profiles them."""

import argparse
from pathlib import Path

import falsifyai.cli.matrix as cli_matrix
import falsifyai.cli.run as cli_run
from falsifyai.replay.sqlite_store import SQLiteStore
from falsifyai.spec.loader import load_spec
from falsifyai.spec.materializer import materialize
from tests.fixtures.mock_adapter import MockAdapter

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _run(spec_path: Path, db_path: str, response: str, monkeypatch) -> None:
    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)
    case = materialized.cases[0]
    response_map = {case.original_input: response}
    for pi in case.realized_perturbations:
        response_map[pi.text] = response
    adapter = MockAdapter(response_map=response_map)
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)
    cli_run.cmd_run(argparse.Namespace(spec_path=str(spec_path), store_path=db_path))


def test_matrix_profiles_two_sessions(tmp_path, monkeypatch, capsys) -> None:
    spec_path = _EXAMPLES / "fragile.yaml"
    db_path = str(tmp_path / "replays.db")

    # Session 1: model stays correct -> high typo_noise stability.
    _run(spec_path, db_path, "Paris is the capital of France.", monkeypatch)
    # Session 2: model drifts -> low typo_noise stability.
    _run(spec_path, db_path, "I am not sure.", monkeypatch)

    with SQLiteStore(db_path) as store:
        sessions = list(store.query_sessions(limit=2))
    ids = [s.session_id for s in sessions]
    assert len(ids) == 2

    capsys.readouterr()  # discard run output
    rc = cli_matrix.cmd_matrix(argparse.Namespace(session_ids=ids, store_path=db_path))
    assert rc == 0

    out = capsys.readouterr().out
    assert "typo_noise" in out  # the perturbation family row
    assert "M1" in out and "M2" in out  # two model columns
    assert "legend:" in out
