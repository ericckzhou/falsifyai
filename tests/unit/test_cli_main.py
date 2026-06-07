"""Tests for falsifyai.cli.main — argparse dispatch + top-level error handling."""

import pytest

import falsifyai.cli.main as cli_main
from falsifyai.cli.errors import SpecError


def test_help_exits_zero(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "falsifyai" in captured.out.lower()
    assert "run" in captured.out


def test_run_help_shows_spec_path_argument(capsys) -> None:
    with pytest.raises(SystemExit):
        cli_main.main(["run", "--help"])
    captured = capsys.readouterr()
    assert "spec_path" in captured.out
    assert "--store-path" in captured.out


def test_unknown_subcommand_exits_nonzero() -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["nope"])
    assert exc_info.value.code != 0


def test_empty_argv_prints_help_and_exits_zero(capsys) -> None:
    rc = cli_main.main([])
    assert rc == 0
    captured = capsys.readouterr()
    assert "falsifyai" in captured.out.lower()


def test_cli_error_is_caught_and_returns_exit_code(monkeypatch, capsys) -> None:
    """A CLIError raised by cmd_run is converted to its exit_code at the top level."""

    def _raise(args):  # noqa: ANN001
        raise SpecError("bad spec", exit_code=3)

    # main() imports the run module lazily inside its dispatch branch, so patch
    # the source attribute rather than a (no-longer-existing) main-level alias.
    monkeypatch.setattr("falsifyai.cli.run.cmd_run", _raise)
    rc = cli_main.main(["run", "missing.yaml"])
    assert rc == 3
    captured = capsys.readouterr()
    assert "bad spec" in captured.err
    assert "falsifyai" in captured.err.lower()


def test_run_missing_spec_path_argparse_errors() -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["run"])
    assert exc_info.value.code != 0
