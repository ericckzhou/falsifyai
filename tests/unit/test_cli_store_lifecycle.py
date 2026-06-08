"""Centralized guardrail: every read-only CLI consumer closes its ReplayStore.

Each consumer command builds a store via ``build_store`` and owns its lifecycle:
the store must be closed in a ``finally`` block whether the command returns
normally or a post-construction store read raises. ``SQLiteStore`` holds a file
handle; leaking it across a long-lived process — or, on Windows, blocking a
later unlink of the database file — is the failure this locks out.

This is a single parametrized harness rather than a close assertion duplicated
across eight command test files. ``run`` is intentionally absent: it is a
*producer* that orchestrates generation -> interpretation -> preservation, not a
read-only consumer, and its store lifecycle is asserted in its own test file
where the execution stack is already mocked. ``minimize`` is also absent for a
different reason -- it never opens a ``ReplayStore`` at all (it runs an
in-memory search and persists nothing), so there is no store lifecycle to pin.
Folding either in here would blur the producer/consumer boundary the harness
exists to protect.

Two situations matter, for every consumer:

* **normal return** — the ``try`` block completes (any exit code); ``finally``
  must close. This harness asserts the close, not the exit code — exit semantics
  are each command's own tests' job.
* **read failure** — a store read raises after construction; ``finally`` must
  still close, and the exception must propagate.

The store stand-in only ever returns/raises; it never reaches a real database,
so the harness stays decoupled from store backends and from each command's
rendering details.
"""

import argparse
from collections.abc import Iterator

import pytest

import falsifyai.cli.diff as cli_diff
import falsifyai.cli.export as cli_export
import falsifyai.cli.history as cli_history
import falsifyai.cli.inspect as cli_inspect
import falsifyai.cli.matrix as cli_matrix
import falsifyai.cli.replay as cli_replay
import falsifyai.cli.timeline as cli_timeline
import falsifyai.cli.verify as cli_verify
from falsifyai.cli.errors import InfrastructureError
from falsifyai.replay.models import ReplayArtifact
from falsifyai.replay.protocol import SessionNotFoundError
from tests.fixtures.build_artifact import make_artifact

_SESSION_ID = "11111111-1111-1111-1111-111111111111"

# Exceptions a consumer may raise once a post-construction read fails: most wrap
# the miss into InfrastructureError; the query-based commands (history, timeline)
# let SessionNotFoundError propagate. Either way the store must already be closed.
_READ_FAILURE_EXC = (InfrastructureError, SessionNotFoundError)


class _TrackingStore:
    """ReplayStore stand-in that records ``close()`` and can fail reads on demand.

    ``raise_on_read=True`` makes both read methods raise ``SessionNotFoundError``
    *after* construction, simulating a store that built fine but whose read
    fails. ``artifacts`` stays directly readable so a test can derive ids / case
    ids for argument construction without tripping the forced failure.
    """

    def __init__(self, artifacts: list[ReplayArtifact], *, raise_on_read: bool = False) -> None:
        self.artifacts = list(artifacts)
        self._by_id = {a.session_id: a for a in artifacts}
        self.raise_on_read = raise_on_read
        self.closed = False

    def load_session(self, session_id: str) -> ReplayArtifact:
        if self.raise_on_read or session_id not in self._by_id:
            raise SessionNotFoundError(session_id)
        return self._by_id[session_id]

    def query_sessions(self, **_kwargs) -> Iterator[ReplayArtifact]:
        if self.raise_on_read:
            raise SessionNotFoundError("forced read failure")
        yield from sorted(self.artifacts, key=lambda a: a.created_at, reverse=True)

    def close(self) -> None:
        self.closed = True


# ---------------------------------------------------------------------------
# Per-command argument builders. Each takes the served artifact (for ids /
# case ids) and a tmp_path (only export needs a real output path), and returns
# a Namespace shaped like the command's argparse output.
# ---------------------------------------------------------------------------


def _diff_args(a: ReplayArtifact, tmp_path) -> argparse.Namespace:
    return argparse.Namespace(
        store_path=":memory:",
        baseline_session_id=a.session_id,
        candidate_session_id=a.session_id,
        strict=False,
        show_timeline=False,
    )


def _export_args(a: ReplayArtifact, tmp_path) -> argparse.Namespace:
    return argparse.Namespace(
        session_id=a.session_id,
        bundle=str(tmp_path / "bundle.fai.zip"),
        spec_path=None,
        allow_corrupted=False,
        overwrite=False,
        exported_at=None,
        store_path=":memory:",
    )


def _history_args(a: ReplayArtifact, tmp_path) -> argparse.Namespace:
    return argparse.Namespace(case_id=a.case_results[0].case_id, limit=0, store_path=":memory:")


def _inspect_args(a: ReplayArtifact, tmp_path) -> argparse.Namespace:
    return argparse.Namespace(session_id=a.session_id, store_path=":memory:", case=None, full=False)


def _matrix_args(a: ReplayArtifact, tmp_path) -> argparse.Namespace:
    return argparse.Namespace(session_ids=[a.session_id], store_path=":memory:")


def _replay_args(a: ReplayArtifact, tmp_path) -> argparse.Namespace:
    return argparse.Namespace(store_path=":memory:", session_id=a.session_id, latest=False)


def _timeline_args(a: ReplayArtifact, tmp_path) -> argparse.Namespace:
    return argparse.Namespace(case_id=a.case_results[0].case_id, limit=0, store_path=":memory:")


def _verify_args(a: ReplayArtifact, tmp_path) -> argparse.Namespace:
    return argparse.Namespace(session_id=a.session_id, all=False, store_path=":memory:")


# (id, cli_module, cmd_callable, build_args). The module is needed to patch its
# ``build_store`` binding; consumers import it by name into their own namespace.
_CONSUMERS = [
    ("diff", cli_diff, cli_diff.cmd_diff, _diff_args),
    ("export", cli_export, cli_export.cmd_export, _export_args),
    ("history", cli_history, cli_history.cmd_history, _history_args),
    ("inspect", cli_inspect, cli_inspect.cmd_inspect, _inspect_args),
    ("matrix", cli_matrix, cli_matrix.cmd_matrix, _matrix_args),
    ("replay", cli_replay, cli_replay.cmd_replay, _replay_args),
    ("timeline", cli_timeline, cli_timeline.cmd_timeline, _timeline_args),
    ("verify", cli_verify, cli_verify.cmd_verify, _verify_args),
]

_PARAMS = [(module, cmd, build_args) for _id, module, cmd, build_args in _CONSUMERS]
_IDS = [entry[0] for entry in _CONSUMERS]


@pytest.mark.parametrize("module, cmd, build_args", _PARAMS, ids=_IDS)
def test_consumer_closes_store_on_completion(
    module, cmd, build_args, monkeypatch, tmp_path, capsys
):
    """A normal return runs the ``finally`` close. Exit code is irrelevant here."""
    artifact = make_artifact(session_id=_SESSION_ID)
    store = _TrackingStore([artifact])
    monkeypatch.setattr(module, "build_store", lambda _p: store)

    cmd(build_args(artifact, tmp_path))

    assert store.closed is True


@pytest.mark.parametrize("module, cmd, build_args", _PARAMS, ids=_IDS)
def test_consumer_closes_store_on_read_failure(
    module, cmd, build_args, monkeypatch, tmp_path, capsys
):
    """A post-construction read failure still runs the ``finally`` close."""
    artifact = make_artifact(session_id=_SESSION_ID)
    store = _TrackingStore([artifact], raise_on_read=True)
    monkeypatch.setattr(module, "build_store", lambda _p: store)

    with pytest.raises(_READ_FAILURE_EXC):
        cmd(build_args(artifact, tmp_path))

    assert store.closed is True
