"""Unit tests for ``falsifyai doctor`` (read-only environment diagnostics).

The dev environment has every core dep and both extras installed (dev deps pull
sentence-transformers -> torch + transformers), so the happy path is real.
Failure and optional-absent paths are driven by monkeypatching the module's
``_available`` probe and ``os.access`` -- no uninstalling, no real breakage.
"""

import argparse

import falsifyai.cli.doctor as doctor
from falsifyai.cli.doctor import Check, cmd_doctor, collect_checks, render


def _args(store_path: str) -> argparse.Namespace:
    return argparse.Namespace(store_path=store_path)


def _patch_absent(monkeypatch, absent: set[str]) -> None:
    """Make ``_available`` report the named modules as not importable."""
    monkeypatch.setattr(doctor, "_available", lambda module: module not in absent)


class TestHealthyPath:
    def test_cmd_doctor_returns_0_in_dev_env(self, tmp_path, capsys) -> None:
        rc = cmd_doctor(_args(str(tmp_path / "replays.db")))
        out = capsys.readouterr().out
        assert rc == 0
        assert "healthy" in out
        assert "0 problems" in out

    def test_output_reports_core_facts(self, tmp_path, capsys) -> None:
        cmd_doctor(_args(str(tmp_path / "replays.db")))
        out = capsys.readouterr().out
        assert "python" in out
        assert "falsifyai" in out
        assert "store write" in out

    def test_via_main_cli_dispatch(self, tmp_path) -> None:
        import falsifyai.cli.main as cli_main

        rc = cli_main.main(["doctor", "--store-path", str(tmp_path / "replays.db")])
        assert rc == 0


class TestRequiredFailures:
    def test_missing_core_dep_is_unhealthy_exit_3(self, tmp_path, capsys, monkeypatch) -> None:
        _patch_absent(monkeypatch, {"numpy"})
        rc = cmd_doctor(_args(str(tmp_path / "replays.db")))
        out = capsys.readouterr().out
        assert rc == 3
        assert "unhealthy" in out
        assert "missing: numpy" in out

    def test_unwritable_store_dir_is_unhealthy(self, tmp_path, capsys, monkeypatch) -> None:
        # The tempfile SQLite probe still succeeds (real write); only the
        # configured-path writability check trips.
        monkeypatch.setattr(doctor.os, "access", lambda _path, _mode: False)
        rc = cmd_doctor(_args(str(tmp_path / "replays.db")))
        out = capsys.readouterr().out
        assert rc == 3
        assert "not writable" in out


class TestOptionalExtras:
    def test_absent_extra_is_informational_not_a_failure(
        self, tmp_path, capsys, monkeypatch
    ) -> None:
        _patch_absent(monkeypatch, {"transformers", "torch"})
        rc = cmd_doctor(_args(str(tmp_path / "replays.db")))
        out = capsys.readouterr().out
        assert rc == 0  # missing optional extra does not fail the environment
        assert 'pip install "falsifyai[nli]"' in out
        assert "not installed" in out


class TestRender:
    def test_render_flags_problems(self) -> None:
        checks = [Check("x", "detail", "fail", hint="do something")]
        text = render(checks)
        assert "unhealthy" in text
        assert "FAIL" in text
        assert "-> do something" in text

    def test_collect_checks_rows(self, tmp_path) -> None:
        checks = collect_checks(str(tmp_path / "replays.db"))
        labels = [c.label for c in checks]
        assert labels == [
            "python",
            "falsifyai",
            "core deps",
            "[semantic] extra",
            "[nli] extra",
            "store backend",
            "store write",
        ]


class TestStoreBackend:
    def test_default_path_reports_sqlite_backend(self, tmp_path, capsys) -> None:
        rc = cmd_doctor(_args(str(tmp_path / "replays.db")))
        out = capsys.readouterr().out
        assert rc == 0
        assert "store backend" in out
        assert "sqlite" in out

    def test_unknown_scheme_is_unhealthy_exit_3(self, capsys) -> None:
        # No store plugin handles 'postgres' in this install, so backend
        # resolution fails in diagnostics instead of crashing at run time.
        rc = cmd_doctor(_args("postgres://host/db"))
        out = capsys.readouterr().out
        assert rc == 3
        assert "no backend registered" in out

    def test_memory_scheme_is_ephemeral_ok(self, capsys) -> None:
        rc = cmd_doctor(_args(":memory:"))
        out = capsys.readouterr().out
        assert rc == 0
        assert "ephemeral" in out

    def test_registered_plugin_scheme_is_not_probed(self, capsys, monkeypatch) -> None:
        # Simulate an installed plugin store without shipping one: the scheme is
        # registered, but doctor must not construct it (possible side effects).
        monkeypatch.setattr(
            "falsifyai.replay.registry.discover_stores",
            lambda: {"sqlite": object(), "memory": object(), "postgres": object()},
        )
        rc = cmd_doctor(_args("postgres://host/db"))
        out = capsys.readouterr().out
        assert rc == 0
        assert "plugin store; not probed" in out
