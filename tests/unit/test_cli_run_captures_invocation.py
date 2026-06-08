"""Unit tests for ``cmd_run``'s ``cli_invocation`` capture (PR-35, Phase C).

Exercises the ``cli_invocation`` capture helper and its field-attachment in
``cmd_run``.

Capture contract (per PR-35 plan §1):
- Capture at entry into ``cmd_run`` (single capture point)
- Normalize ``argv[0]`` to ``"falsifyai"`` regardless of entry path
- Preserve subsequent tokens verbatim from ``sys.argv``
- Stamp ``falsifyai_version`` from the runtime package metadata

Semantic boundary: this records *what command produced the artifact*, not
a determinism guarantee. The tests assert capture *behavior* — they do not
assert that re-running the captured argv produces identical outputs.
"""

import argparse
from pathlib import Path

import pytest

import falsifyai.cli.main as cli_main
import falsifyai.cli.run as cli_run
from falsifyai import __version__ as _runtime_version
from falsifyai.cli.run import _capture_cli_invocation
from falsifyai.replay.models import CliInvocation
from falsifyai.replay.sqlite_store import SQLiteStore
from tests.fixtures.mock_adapter import MockAdapter

_SMOKE_SPEC = Path(__file__).resolve().parents[1] / "fixtures" / "specs" / "run_smoke.yaml"


# ---------------------------------------------------------------------------
# _capture_cli_invocation helper — pure-function tests
# ---------------------------------------------------------------------------


def test_capture_returns_cli_invocation_instance() -> None:
    inv = _capture_cli_invocation(["falsifyai", "run", "spec.yaml"])
    assert isinstance(inv, CliInvocation)


def test_capture_canonicalizes_argv0_to_falsifyai() -> None:
    """argv[0] is normalized to 'falsifyai' regardless of entry path."""
    # Entry-point invocation: argv[0] is the absolute path to the launcher
    inv1 = _capture_cli_invocation(["/usr/local/bin/falsifyai", "run", "spec.yaml"])
    assert inv1.argv[0] == "falsifyai"

    # Windows entry-point
    inv2 = _capture_cli_invocation(
        [r"C:\Users\Eric\AppData\Local\Programs\Python\Scripts\falsifyai.exe", "run", "spec.yaml"]
    )
    assert inv2.argv[0] == "falsifyai"

    # python -m invocation: argv[0] is the __main__.py path
    inv3 = _capture_cli_invocation(["/path/to/falsifyai/cli/main.py", "run", "spec.yaml"])
    assert inv3.argv[0] == "falsifyai"


def test_capture_preserves_subsequent_tokens_verbatim() -> None:
    """Tokens after argv[0] are preserved as-passed."""
    raw = [
        "/usr/local/bin/falsifyai",
        "run",
        "specs/foo.yaml",
        "--store-path",
        ":memory:",
    ]
    inv = _capture_cli_invocation(raw)
    assert inv.argv == ("falsifyai", "run", "specs/foo.yaml", "--store-path", ":memory:")


def test_capture_stamps_runtime_falsifyai_version() -> None:
    inv = _capture_cli_invocation(["falsifyai", "run", "spec.yaml"])
    assert inv.falsifyai_version == _runtime_version


def test_capture_returns_tuple_not_list() -> None:
    """argv is a tuple per the CliInvocation dataclass contract."""
    inv = _capture_cli_invocation(["falsifyai", "run", "spec.yaml"])
    assert isinstance(inv.argv, tuple)


def test_capture_handles_empty_argv_defensively() -> None:
    """Edge case: if argv is empty (somehow), still produce a valid CliInvocation."""
    inv = _capture_cli_invocation([])
    assert inv.argv == ("falsifyai",)
    assert inv.falsifyai_version == _runtime_version


# ---------------------------------------------------------------------------
# End-to-end: cmd_run stamps invocation on the produced artifact
# ---------------------------------------------------------------------------


def _patch_adapter(monkeypatch, response: str = "Paris is the capital of France.") -> None:
    """Inject a MockAdapter so the smoke spec runs offline."""
    adapter = MockAdapter(default_response=response)
    monkeypatch.setattr(cli_run, "build_adapter", lambda _model: adapter)


def test_cmd_run_via_main_captures_invocation(monkeypatch, tmp_path, capsys) -> None:
    """End-to-end through cli_main.main(): captured argv matches the canonical form."""
    _patch_adapter(monkeypatch)
    db_path = str(tmp_path / "replays.db")

    # main() reads sys.argv when argv=None; pass argv explicitly to control capture.
    # The capture helper reads sys.argv at cmd_run entry, so we must set sys.argv too.
    raw_argv = ["/usr/local/bin/falsifyai", "run", str(_SMOKE_SPEC), "--store-path", db_path]
    monkeypatch.setattr("sys.argv", raw_argv)
    rc = cli_main.main(raw_argv[1:])  # main(argv) strips program name; we feed [run, ...]
    capsys.readouterr()
    assert rc == 0

    with SQLiteStore(db_path) as store:
        sessions = list(store.query_sessions(limit=1))
        artifact = store.load_session(sessions[0].session_id)

    assert artifact.cli_invocation is not None
    assert artifact.cli_invocation.argv == (
        "falsifyai",
        "run",
        str(_SMOKE_SPEC),
        "--store-path",
        db_path,
    )
    assert artifact.cli_invocation.falsifyai_version == _runtime_version


def test_cmd_run_direct_call_captures_current_sys_argv(monkeypatch, tmp_path, capsys) -> None:
    """If cmd_run is called directly (bypassing main()), capture reflects sys.argv at entry."""
    _patch_adapter(monkeypatch)
    db_path = str(tmp_path / "replays.db")

    # Build args manually (no argparse round-trip)
    args = argparse.Namespace(spec_path=str(_SMOKE_SPEC), store_path=db_path)

    # Document the contract: direct callers get whatever sys.argv is.
    raw_argv = ["falsifyai", "run", "synthetic-direct-call"]
    monkeypatch.setattr("sys.argv", raw_argv)
    rc = cli_run.cmd_run(args)
    capsys.readouterr()
    assert rc == 0

    with SQLiteStore(db_path) as store:
        sessions = list(store.query_sessions(limit=1))
        artifact = store.load_session(sessions[0].session_id)

    assert artifact.cli_invocation is not None
    # Direct-call captures the synthetic sys.argv (documents the contract honestly)
    assert artifact.cli_invocation.argv == ("falsifyai", "run", "synthetic-direct-call")


def test_cmd_run_falsifyai_version_field_matches_runtime(monkeypatch, tmp_path, capsys) -> None:
    """The captured falsifyai_version matches the runtime package version."""
    _patch_adapter(monkeypatch)
    db_path = str(tmp_path / "replays.db")
    monkeypatch.setattr("sys.argv", ["falsifyai", "run", str(_SMOKE_SPEC), "--store-path", db_path])
    rc = cli_main.main(["run", str(_SMOKE_SPEC), "--store-path", db_path])
    capsys.readouterr()
    assert rc == 0

    with SQLiteStore(db_path) as store:
        artifact = next(iter(store.query_sessions(limit=1)))

    assert artifact.cli_invocation is not None
    # Both fields should match — the artifact's own version field comes from
    # importlib.metadata, and the capture's version field also comes from it.
    assert artifact.cli_invocation.falsifyai_version == artifact.falsifyai_version


# ---------------------------------------------------------------------------
# Negative: read-only commands do NOT capture invocation (PR-35 plan §1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module_path",
    [
        "falsifyai.cli.replay",
        "falsifyai.cli.diff",
        "falsifyai.cli.verify",
        "falsifyai.cli.export",
        "falsifyai.cli.inspect",
        "falsifyai.cli.history",
    ],
)
def test_read_only_commands_do_not_import_capture_helper(module_path: str) -> None:
    """Read-only consumer commands never stamp invocation (preservation discipline).

    Enforced structurally: no read-only CLI module imports
    ``_capture_cli_invocation`` from ``cli.run``. The helper is private to
    ``cli.run`` and stays private. If a future preservation-side command needs
    invocation-aware behavior, it should *read* the stored field on a loaded
    artifact, never *stamp* a new one.
    """
    import importlib

    mod = importlib.import_module(module_path)
    # Walk module attributes; the capture helper must not be referenced.
    for name in dir(mod):
        obj = getattr(mod, name, None)
        # Skip non-callable / non-module attributes
        if not callable(obj) and not hasattr(obj, "__module__"):
            continue
        # The helper itself, if accidentally re-exported, would show up here.
        assert name != "_capture_cli_invocation", (
            f"{module_path} must not import _capture_cli_invocation "
            "(read-only consumer commands never stamp invocation)"
        )
