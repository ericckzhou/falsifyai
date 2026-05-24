"""End-to-end integration tests for ``falsifyai export`` (PR-32, Phase E).

Proves the run -> save -> export -> unzip -> round-trip chain. A real
``cmd_run`` invocation saved to a real SQLite store, exported as a
deterministic bundle, unzipped, and validated against the original.

Also covers SQLite payload mutation to confirm the integrity gate
actually inspects what the store returns.
"""

import argparse
import json
import sqlite3
import zipfile
from pathlib import Path

import falsifyai.cli.export as cli_export
import falsifyai.cli.run as cli_run
from falsifyai.replay.serialize import artifact_from_json
from falsifyai.replay.sqlite_store import SQLiteStore
from tests.fixtures.mock_adapter import MockAdapter

_SMOKE_SPEC = Path(__file__).resolve().parents[1] / "fixtures" / "specs" / "run_smoke.yaml"


def _run_args(spec_path: Path, store_path: str) -> argparse.Namespace:
    return argparse.Namespace(spec_path=str(spec_path), store_path=store_path)


def _export_args(
    session_id: str,
    bundle: str,
    store_path: str,
    *,
    allow_corrupted: bool = False,
    overwrite: bool = False,
    exported_at: str | None = "2026-05-24T12:00:00+00:00",
    spec_path: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        session_id=session_id,
        bundle=bundle,
        store_path=store_path,
        spec_path=spec_path,
        allow_corrupted=allow_corrupted,
        overwrite=overwrite,
        exported_at=exported_at,
    )


def _do_one_run(store_path: str, response: str = "Paris is the capital of France.") -> str:
    """Run cmd_run with a MockAdapter; return the new session id."""
    import falsifyai.cli.run as cli_run_mod

    adapter = MockAdapter(default_response=response)
    orig_build = cli_run_mod.build_adapter
    cli_run_mod.build_adapter = lambda model: adapter  # type: ignore[assignment]
    try:
        cli_run.cmd_run(_run_args(_SMOKE_SPEC, store_path))
    finally:
        cli_run_mod.build_adapter = orig_build  # type: ignore[assignment]

    with SQLiteStore(store_path) as store:
        latest = next(iter(store.query_sessions(limit=1)))
    return latest.session_id


def _read_manifest(bundle_path: Path) -> dict:
    with zipfile.ZipFile(bundle_path, "r") as zf:
        return json.loads(zf.read("manifest.json").decode("utf-8"))


def _read_artifact_json(bundle_path: Path) -> str:
    with zipfile.ZipFile(bundle_path, "r") as zf:
        return zf.read("artifact.json").decode("utf-8")


# ---------------------------------------------------------------------------
# E1a. Happy path: full pipeline returns exit 0; bundle is valid; round-trip OK
# ---------------------------------------------------------------------------


def test_export_clean_run_returns_exit_0_and_valid_bundle(tmp_path, capsys) -> None:
    db_path = str(tmp_path / "replays.db")
    session_id = _do_one_run(db_path)
    capsys.readouterr()  # drop cmd_run output

    bundle_path = tmp_path / "out.fai.zip"
    rc = cli_export.cmd_export(_export_args(session_id, str(bundle_path), db_path))
    captured = capsys.readouterr()

    assert rc == 0
    assert bundle_path.exists()
    assert zipfile.is_zipfile(bundle_path)
    assert "Bundle:" in captured.out
    assert "bundle_id:" in captured.out

    m = _read_manifest(bundle_path)
    assert m["session_id"] == session_id
    assert m["pre_export_integrity"]["status"] == "passed"
    assert m["exported_under_protest"] is False


def test_export_round_trips_artifact_through_serialize(tmp_path, capsys) -> None:
    """The artifact.json inside the bundle must deserialize back to a working ReplayArtifact."""
    db_path = str(tmp_path / "replays.db")
    session_id = _do_one_run(db_path)
    capsys.readouterr()

    bundle_path = tmp_path / "out.fai.zip"
    cli_export.cmd_export(_export_args(session_id, str(bundle_path), db_path))

    with SQLiteStore(db_path) as store:
        original = store.load_session(session_id)

    restored = artifact_from_json(_read_artifact_json(bundle_path))
    assert restored.session_id == original.session_id
    assert restored.materialized_hash == original.materialized_hash
    assert len(restored.case_results) == len(original.case_results)


# ---------------------------------------------------------------------------
# E1b. Mutation detected: SQLite payload edit → exit 7, no bundle
# ---------------------------------------------------------------------------


def test_export_refuses_corrupted_artifact_from_real_sqlite_store(tmp_path, capsys) -> None:
    db_path = str(tmp_path / "replays.db")
    session_id = _do_one_run(db_path)
    capsys.readouterr()

    # Mutate the stored JSON to corrupt the materialized_hash.
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT payload_json FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        payload = json.loads(row[0])
        payload["materialized_hash"] = "0" * 64
        conn.execute(
            "UPDATE sessions SET payload_json = ? WHERE session_id = ?",
            (json.dumps(payload), session_id),
        )
        conn.commit()

    bundle_path = tmp_path / "out.fai.zip"
    rc = cli_export.cmd_export(_export_args(session_id, str(bundle_path), db_path))
    captured = capsys.readouterr()

    assert rc == 7
    assert not bundle_path.exists()
    assert "refusing to export" in captured.out
    assert "materialized_hash" in captured.out


# ---------------------------------------------------------------------------
# E1c. Mutation + --allow-corrupted → bundle written with predicate set
# ---------------------------------------------------------------------------


def test_export_allow_corrupted_writes_bundle_with_protest_flag(tmp_path, capsys) -> None:
    db_path = str(tmp_path / "replays.db")
    session_id = _do_one_run(db_path)
    capsys.readouterr()

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT payload_json FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        payload = json.loads(row[0])
        payload["materialized_hash"] = "0" * 64
        conn.execute(
            "UPDATE sessions SET payload_json = ? WHERE session_id = ?",
            (json.dumps(payload), session_id),
        )
        conn.commit()

    bundle_path = tmp_path / "out.fai.zip"
    rc = cli_export.cmd_export(
        _export_args(session_id, str(bundle_path), db_path, allow_corrupted=True)
    )
    captured = capsys.readouterr()

    assert rc == 0
    assert bundle_path.exists()
    m = _read_manifest(bundle_path)
    assert m["exported_under_protest"] is True
    assert m["pre_export_integrity"]["status"] == "failed"
    assert "materialized_hash" in m["pre_export_integrity"]["failed_checks"]
    # stderr warning emitted
    assert "WARNING" in captured.err or "NOT WORM-suitable" in captured.err


# ---------------------------------------------------------------------------
# E1d. Determinism: two exports of same artifact + same exported_at → byte-identical
# ---------------------------------------------------------------------------


def test_export_two_consecutive_exports_byte_identical(tmp_path, capsys) -> None:
    db_path = str(tmp_path / "replays.db")
    session_id = _do_one_run(db_path)
    capsys.readouterr()

    b1 = tmp_path / "b1.fai.zip"
    b2 = tmp_path / "b2.fai.zip"
    cli_export.cmd_export(_export_args(session_id, str(b1), db_path))
    cli_export.cmd_export(_export_args(session_id, str(b2), db_path))

    assert b1.read_bytes() == b2.read_bytes()


# ---------------------------------------------------------------------------
# E1e. CLI dispatch: end-to-end through cli/main.py argparse
# ---------------------------------------------------------------------------


def test_export_via_main_cli_returns_exit_0(tmp_path, capsys) -> None:
    import falsifyai.cli.main as cli_main

    db_path = str(tmp_path / "replays.db")
    session_id = _do_one_run(db_path)
    capsys.readouterr()

    bundle_path = tmp_path / "out.fai.zip"
    rc = cli_main.main(
        [
            "export",
            session_id,
            "--bundle",
            str(bundle_path),
            "--store-path",
            db_path,
            "--exported-at",
            "2026-05-24T12:00:00+00:00",
        ]
    )
    assert rc == 0
    assert bundle_path.exists()
