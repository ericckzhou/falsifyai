"""End-to-end: a case that degrades across runs exits 5 from `timeline`."""

import argparse
from pathlib import Path

import falsifyai.cli.run as cli_run
import falsifyai.cli.timeline as cli_timeline
from falsifyai.spec.loader import load_spec
from falsifyai.spec.materializer import materialize
from tests.fixtures.mock_adapter import MockAdapter

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _run(spec_path: Path, db_path: str, response: str, monkeypatch) -> None:
    spec, spec_hash = load_spec(spec_path)
    materialized = materialize(spec, spec_hash)
    case = materialized.cases[0]
    response_map = {case.original_input: "Paris is the capital of France."}
    for pi in case.realized_perturbations:
        response_map[pi.text] = response
    adapter = MockAdapter(response_map=response_map)
    monkeypatch.setattr(cli_run, "build_adapter", lambda model: adapter)
    cli_run.cmd_run(argparse.Namespace(spec_path=str(spec_path), store_path=db_path))


def test_timeline_detects_regression_and_exits_5(tmp_path, monkeypatch, capsys) -> None:
    spec_path = _EXAMPLES / "fragile.yaml"
    db_path = str(tmp_path / "replays.db")

    # Run 1: perturbations also answer correctly -> STABLE.
    _run(spec_path, db_path, "Paris is the capital of France.", monkeypatch)
    # Run 2: perturbations drift -> FRAGILE (a regression vs run 1).
    _run(spec_path, db_path, "I am not sure.", monkeypatch)

    capsys.readouterr()
    rc = cli_timeline.cmd_timeline(
        argparse.Namespace(case_id="capital_of_france_fragile", limit=20, store_path=db_path)
    )
    assert rc == 5  # REGRESSION detected over the case's history

    out = capsys.readouterr().out
    assert "REGRESSION" in out
    assert "trend" in out
    assert "1 regression" in out
