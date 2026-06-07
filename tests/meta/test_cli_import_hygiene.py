"""Structural guardrail: read-only CLI commands stay off the model stack.

A diagnostic or artifact-reading command (``doctor``, ``verify``, ``replay``,
``inspect``, ``diff``, ``history``, ``timeline``, ``matrix``, ``export``) reads
preserved evidence; it never calls a model. Loading the model-execution stack
(``litellm`` / the execution adapter) for one of these is dead weight, and
``litellm`` emits import-time warnings — exactly the noise that prompted this
guard. Only ``run`` and ``minimize`` legitimately execute a model.

The dispatcher (``falsifyai/cli/main.py``) enforces this by importing each
command module lazily inside its dispatch branch. This test locks that in: it
imports each read-only command module — *plus the dispatcher itself* — in a
fresh interpreter and asserts the forbidden modules never landed in
``sys.modules``. Importing ``falsifyai.cli.main`` is the key case: if a command
import leaks back to module top level, importing the dispatcher pulls litellm
and this test fails.

A subprocess per module is mandatory: ``sys.modules`` is process-global, so once
any in-process test imports ``run``, litellm is resident and an in-process check
would be meaningless.
"""

import subprocess
import sys

import pytest

# Read-only / consumer commands plus the dispatcher. ``run`` and ``minimize`` are
# intentionally absent — they execute the model and legitimately import litellm.
READ_ONLY_MODULES = [
    "falsifyai.cli.main",
    "falsifyai.cli.replay",
    "falsifyai.cli.inspect",
    "falsifyai.cli.diff",
    "falsifyai.cli.history",
    "falsifyai.cli.timeline",
    "falsifyai.cli.matrix",
    "falsifyai.cli.verify",
    "falsifyai.cli.export",
    "falsifyai.cli.doctor",
]

FORBIDDEN = ("litellm", "falsifyai.execution.litellm_adapter")

# Imported in a clean interpreter; prints leaked module names and exits non-zero.
_PROBE = (
    "import importlib, sys\n"
    "importlib.import_module(sys.argv[1])\n"
    "forbidden = ('litellm', 'falsifyai.execution.litellm_adapter')\n"
    "leaked = [m for m in forbidden if m in sys.modules]\n"
    "if leaked:\n"
    "    sys.stderr.write(', '.join(leaked))\n"
    "    sys.exit(1)\n"
)


@pytest.mark.parametrize("module", READ_ONLY_MODULES)
def test_read_only_command_does_not_import_model_stack(module: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE, module],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"{module} transitively imported the model stack ({proc.stderr.strip()}). "
        f"Read-only commands must not import {FORBIDDEN}. If this is "
        f"falsifyai.cli.main, a command import probably leaked back to module top "
        f"level instead of staying in its lazy dispatch branch."
    )
