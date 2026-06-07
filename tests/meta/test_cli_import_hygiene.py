"""Structural guardrail: read-only CLI commands stay off the model stack and the
verdict resolver.

A diagnostic or artifact-reading command (``doctor``, ``verify``, ``replay``,
``inspect``, ``diff``, ``history``, ``timeline``, ``matrix``, ``export``) reads
preserved evidence. It must not load either of:

* **the model-execution stack** (``litellm`` / the execution adapter). Loading it
  for a read-only command is dead weight, and ``litellm`` emits import-time
  warnings — exactly the noise that first prompted this guard.
* **the verdict resolver** (``falsifyai.verdict.resolver``). The verdict is
  assigned once, at ``run`` time, and preserved in the artifact; a consumer reads
  ``case.verdict`` from what was stored and *never re-resolves* (ARCHITECTURE.md:
  "Replay does NOT re-invoke the resolver"). Re-importing the resolver in a
  consumer is the first step toward silently re-deriving a claim the artifact
  already preserves. Consumers may import the ``Verdict`` *enum*
  (``falsifyai.verdict.models``) to read and compare stored verdicts — only the
  resolver *module* is forbidden.

Only ``run`` and ``minimize`` legitimately execute a model and resolve verdicts;
both are intentionally absent from the list below.

This centralizes a guarantee that previously lived as per-command assertions
scattered across the command test files using two weaker techniques (in-process
``sys.modules`` deletion, and AST direct-import scans that miss transitive
imports). The dispatcher (``falsifyai/cli/main.py``) enforces the
no-model-stack half by importing each command module lazily inside its dispatch
branch; importing ``falsifyai.cli.main`` is the key case — if a command import
leaks back to module top level, importing the dispatcher pulls the forbidden
module and this test fails.

A subprocess per module is mandatory: ``sys.modules`` is process-global, so once
any in-process test imports ``run``, both litellm and the resolver are resident
and an in-process check would be meaningless.
"""

import subprocess
import sys

import pytest

# Read-only / consumer commands plus the dispatcher. ``run`` and ``minimize`` are
# intentionally absent — they execute the model and resolve verdicts, so they
# legitimately import both the model stack and the resolver.
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

# The model-execution stack and the verdict resolver: a read-only consumer must
# import neither. The enum module (``falsifyai.verdict.models``) is deliberately
# NOT here — consumers read stored verdicts from it.
FORBIDDEN = (
    "litellm",
    "falsifyai.execution.litellm_adapter",
    "falsifyai.verdict.resolver",
)

# Imported in a clean interpreter; prints leaked module names and exits non-zero.
_PROBE = (
    "import importlib, sys\n"
    "importlib.import_module(sys.argv[1])\n"
    "forbidden = (\n"
    "    'litellm',\n"
    "    'falsifyai.execution.litellm_adapter',\n"
    "    'falsifyai.verdict.resolver',\n"
    ")\n"
    "leaked = [m for m in forbidden if m in sys.modules]\n"
    "if leaked:\n"
    "    sys.stderr.write(', '.join(leaked))\n"
    "    sys.exit(1)\n"
)


@pytest.mark.parametrize("module", READ_ONLY_MODULES)
def test_read_only_command_does_not_import_model_stack_or_resolver(module: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE, module],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"{module} transitively imported a forbidden module ({proc.stderr.strip()}). "
        f"Read-only commands must import none of {FORBIDDEN}: the model stack is dead "
        f"weight, and the resolver must not be re-entered (consumers read the stored "
        f"verdict, they never re-resolve). If this is falsifyai.cli.main, a command "
        f"import probably leaked back to module top level instead of staying in its "
        f"lazy dispatch branch."
    )
