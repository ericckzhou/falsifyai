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

Exit 0 only if every step passes; any failure stops the run and exits non-zero.
"""

from __future__ import annotations

import glob
import shutil
import subprocess
import sys

# Keep in sync with .github/workflows/ci.yml (the Pytest + coverage gate step).
COVERAGE_FLOOR = 90


def _run(label: str, cmd: list[str]) -> bool:
    print(f"\n=== {label} ===\n  $ {' '.join(cmd)}", flush=True)
    ok = subprocess.run(cmd).returncode == 0
    print(f"  -> {'OK' if ok else 'FAIL'} ({label})", flush=True)
    return ok


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

    print("\nRelease gate PASSED -- all checks green.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
