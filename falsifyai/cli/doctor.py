"""``falsifyai doctor`` -- read-only environment diagnostics.

Reports the runtime facts a user needs to explain a confusing install: the
Python and package versions, whether the core runtime dependencies import,
which optional extras (``[semantic]``, ``[nli]``) are available, and whether a
replay store can actually be written.

It *diagnoses only*. It never installs anything, writes config, or mutates user
data -- the store-writability probe lives in a tempfile and is deleted, and
availability is checked with ``importlib.util.find_spec`` so heavyweight modules
(torch) are never actually imported. Exit ``0`` when the environment is healthy;
exit ``3`` (ERROR -- infrastructure, per the CLI's exit-code scheme) when a
*required* check fails. A missing optional extra is informational, not a failure.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from falsifyai import __version__

# Exit 3 == ERROR (infrastructure failure) in the CLI's exit-code scheme
# (see falsifyai/cli/main.py). doctor is a diagnostic, not an eval, so it only
# ever returns 0 (healthy) or this.
_ERROR_EXIT = 3

# Per-check status. _INFO is a non-failing note (an absent optional extra);
# only _FAIL counts against the health verdict.
_OK = "ok"
_INFO = "info"
_FAIL = "fail"

_MARKERS = {_OK: "ok", _INFO: "--", _FAIL: "FAIL"}

# Core runtime deps: distribution name -> import name. These ship in
# [project.dependencies]; a missing one means a broken install, not a choice.
_CORE_DEPS = {"litellm": "litellm", "numpy": "numpy", "pydantic": "pydantic", "pyyaml": "yaml"}


@dataclass(frozen=True)
class Check:
    """One diagnostic line: a labeled fact plus a pass/info/fail status."""

    label: str
    detail: str
    status: str
    hint: str = ""


def _available(module: str) -> bool:
    """True if ``module`` is importable, without importing it.

    Uses ``find_spec`` so checking the ``[nli]`` extra never actually loads
    torch (slow) or triggers a model download.
    """
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        # A broken/partial install can raise rather than return None.
        return False


def _python_check() -> Check:
    ok = sys.version_info[:2] >= (3, 13)
    return Check(
        "python",
        platform.python_version(),
        _OK if ok else _FAIL,
        "" if ok else "falsifyai requires Python >= 3.13",
    )


def _core_deps_check() -> Check:
    missing = [dist for dist, mod in _CORE_DEPS.items() if not _available(mod)]
    if missing:
        return Check(
            "core deps",
            "missing: " + ", ".join(missing),
            _FAIL,
            "reinstall falsifyai (pip install --force-reinstall falsifyai)",
        )
    return Check("core deps", ", ".join(_CORE_DEPS), _OK)


def _extra_check(label: str, modules: list[str], extra: str) -> Check:
    if all(_available(m) for m in modules):
        return Check(label, " + ".join(modules), _OK)
    return Check(label, "not installed", _INFO, f'pip install "falsifyai[{extra}]"')


def _store_check(store_path: str) -> Check:
    """Prove a replay store can be written -- via a throwaway tempfile DB, never
    the user's real store -- and that the configured store dir is writable."""
    from falsifyai.replay.sqlite_store import SQLiteStore

    try:
        with tempfile.TemporaryDirectory(prefix="falsifyai-doctor-") as tmp:
            SQLiteStore(Path(tmp) / "probe.db").close()
    except Exception as exc:  # pragma: no cover - defensive; sqlite/fs failure
        return Check("store write", f"sqlite probe failed: {exc}", _FAIL)

    # Writability of the configured path: walk up to the nearest existing
    # ancestor so we test permissions without creating .falsifyai/ ourselves.
    ancestor = Path(store_path).parent
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    if not os.access(ancestor, os.W_OK):
        return Check(
            "store write",
            f"{store_path} (dir not writable)",
            _FAIL,
            f"check perms on {ancestor}",
        )
    return Check("store write", store_path, _OK)


def collect_checks(store_path: str) -> list[Check]:
    """Gather every diagnostic. Pure aside from the read-only probes above."""
    return [
        _python_check(),
        Check("falsifyai", __version__, _OK),
        _core_deps_check(),
        _extra_check("[semantic] extra", ["sentence_transformers"], "semantic"),
        _extra_check("[nli] extra", ["transformers", "torch"], "nli"),
        _store_check(store_path),
    ]


def render(checks: list[Check]) -> str:
    """One row per check: status marker, label, detail, optional hint."""
    width = max(len(c.label) for c in checks)
    lines = ["falsifyai doctor -- environment diagnostics", ""]
    for c in checks:
        row = f"  {_MARKERS[c.status]:<4}  {c.label.ljust(width)}  {c.detail}"
        if c.hint:
            row += f"  -> {c.hint}"
        lines.append(row)
    problems = sum(1 for c in checks if c.status == _FAIL)
    lines.append("")
    if problems:
        lines.append(f"unhealthy -- {len(checks)} checks, {problems} problem(s)")
    else:
        lines.append(f"healthy -- {len(checks)} checks, 0 problems")
    return "\n".join(lines)


def cmd_doctor(args: argparse.Namespace) -> int:
    checks = collect_checks(args.store_path)
    print(render(checks))
    return _ERROR_EXIT if any(c.status == _FAIL for c in checks) else 0
