"""End-to-end: `minimize` finds the smallest noise level that breaks a case."""

import argparse
from pathlib import Path

import falsifyai.cli.minimize as cli_minimize
from falsifyai.spec.loader import load_spec
from tests.fixtures.mock_adapter import MockAdapter

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _args(spec_path: Path, **kw) -> argparse.Namespace:
    base = dict(
        spec_path=str(spec_path),
        case=None,
        family="typo_noise",
        levels="0.05,0.1,0.2",
        samples=3,
    )
    base.update(kw)
    return argparse.Namespace(**base)


def test_minimize_reports_minimal_falsifier(monkeypatch, capsys) -> None:
    """Baseline answers correctly; every perturbed prompt drifts -> breaks at the
    lowest tested level."""
    spec_path = _EXAMPLES / "fragile.yaml"
    spec, _ = load_spec(spec_path)
    case_input = spec.cases[0].input.text

    adapter = MockAdapter(response_map={case_input: "Paris is the capital of France."})
    adapter.default_response = "I am not sure."  # any perturbed (typo'd) prompt drifts
    monkeypatch.setattr(cli_minimize, "build_adapter", lambda model: adapter)

    rc = cli_minimize.cmd_minimize(_args(spec_path))
    assert rc == 0

    out = capsys.readouterr().out
    assert "minimal falsifier" in out
    assert "0.05" in out  # broke at the lowest level
    assert "FRAGILE" in out


def test_minimize_reports_robust_when_model_holds(monkeypatch, capsys) -> None:
    """Model answers correctly at every level -> no falsifier found."""
    spec_path = _EXAMPLES / "fragile.yaml"
    adapter = MockAdapter()
    adapter.default_response = "Paris is the capital of France."  # always correct
    monkeypatch.setattr(cli_minimize, "build_adapter", lambda model: adapter)

    rc = cli_minimize.cmd_minimize(_args(spec_path))
    assert rc == 0

    out = capsys.readouterr().out
    assert "no falsifier found" in out
