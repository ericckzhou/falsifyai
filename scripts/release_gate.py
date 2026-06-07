#!/usr/bin/env python3
"""Single release gate: run every pre-tag check in one command.

Mirrors the manual pre-release checklist in ``docs/RELEASE.md`` so the steps are
*executed*, not remembered. Cross-platform — invoke with::

    uv run python scripts/release_gate.py

Steps, fail-fast in order:

1. ``ruff check .``
2. ``ruff format --check .``
3. ``pytest`` with coverage, gated at ``--cov-fail-under`` (matches CI)
4. build sdist + wheel (``uv build``)
5. ``twine check`` on the built distributions
6. wheel-install smoke: install the freshly built wheel into a clean, isolated
   venv and exercise ``falsifyai --help`` + a version import (mirrors the
   pre-upload smoke in ``.github/workflows/publish.yml``)

Exit 0 only if every step passes; any failure stops the run and exits non-zero.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile

# Keep in sync with .github/workflows/ci.yml (the Pytest + coverage gate step).
COVERAGE_FLOOR = 90


def _run(label: str, cmd: list[str]) -> bool:
    print(f"\n=== {label} ===\n  $ {' '.join(cmd)}", flush=True)
    ok = subprocess.run(cmd).returncode == 0
    print(f"  -> {'OK' if ok else 'FAIL'} ({label})", flush=True)
    return ok


def _wheel_smoke() -> bool:
    """Install the freshly built wheel into a clean, isolated venv (NOT the
    project ``.venv``, which carries an editable install + dev deps) and exercise
    the real console entry point + import.

    Catches packaging breakage that source-tree ``pytest`` structurally cannot:
    missing package data, a broken ``[project.scripts]`` entry, or an import that
    only works from the repo root. Mirrors the pre-upload smoke in
    ``.github/workflows/publish.yml`` -- but cross-platform: the workflow runs on
    Linux (``bin/``), this also runs on a maintainer's Windows box (``Scripts/``,
    ``.exe``).
    """
    print("\n=== wheel-install smoke ===", flush=True)
    wheels = sorted(glob.glob("dist/*.whl"))
    if not wheels:
        print("  -> FAIL: no wheel in dist/ to smoke-test", file=sys.stderr)
        return False
    wheel = wheels[-1]
    venv_dir = tempfile.mkdtemp(prefix="falsifyai-wheel-smoke-")
    bindir = "Scripts" if os.name == "nt" else "bin"
    exe = ".exe" if os.name == "nt" else ""
    py = os.path.join(venv_dir, bindir, f"python{exe}")
    cli = os.path.join(venv_dir, bindir, f"falsifyai{exe}")
    try:
        steps: list[list[str]] = [
            ["uv", "venv", venv_dir],
            ["uv", "pip", "install", "--python", py, wheel],
            [cli, "--help"],
            [py, "-c", "import falsifyai; print('import OK:', falsifyai.__version__)"],
        ]
        for cmd in steps:
            print(f"  $ {' '.join(cmd)}", flush=True)
            if subprocess.run(cmd).returncode != 0:
                print("  -> FAIL (wheel-install smoke)", file=sys.stderr)
                return False
        print("  -> OK (wheel-install smoke)", flush=True)
        return True
    finally:
        shutil.rmtree(venv_dir, ignore_errors=True)


def main() -> int:
    if shutil.which("uv") is None:
        print("error: `uv` not found on PATH; install uv first.", file=sys.stderr)
        return 127

    # Clean dist/ so `twine check` only inspects artifacts from this run.
    shutil.rmtree("dist", ignore_errors=True)

    checks: list[tuple[str, list[str]]] = [
        ("ruff check", ["uv", "run", "ruff", "check", "."]),
        ("ruff format --check", ["uv", "run", "ruff", "format", "--check", "."]),
        (
            "pytest + coverage",
            [
                "uv",
                "run",
                "pytest",
                "--cov=falsifyai",
                "--cov-report=term-missing",
                f"--cov-fail-under={COVERAGE_FLOOR}",
            ],
        ),
        ("build sdist + wheel", ["uv", "build"]),
    ]
    for label, cmd in checks:
        if not _run(label, cmd):
            print(f"\nRelease gate FAILED at: {label}", file=sys.stderr)
            return 1

    # twine check needs the built artifacts; glob in Python so no shell is involved.
    dists = sorted(glob.glob("dist/*"))
    if not dists:
        print("error: no distributions in dist/ after build", file=sys.stderr)
        return 1
    if not _run("twine check", ["uv", "run", "--with", "twine", "twine", "check", *dists]):
        print("\nRelease gate FAILED at: twine check", file=sys.stderr)
        return 1

    if not _wheel_smoke():
        print("\nRelease gate FAILED at: wheel-install smoke", file=sys.stderr)
        return 1

    print("\nRelease gate PASSED -- all checks green.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
