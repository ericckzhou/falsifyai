"""Stale-doc tripwire: every CLI subcommand is referenced in the README.

The README is the public face of the CLI; its command reference is what a new
user reads to learn the surface. The failure mode this locks out is silent:
a new subcommand is wired into ``build_parser`` and ships, but the README is
never updated to mention it, so the documented surface drifts behind the real
one.

This is a **coarse** guard, deliberately. It asserts only that the literal
token ``falsifyai <command>`` appears somewhere in ``README.md`` for every
registered subcommand. It does not validate that the surrounding prose is
correct, complete, or current -- that is review's job. Catching the
"command exists but is undocumented" drift cheaply is the whole ambition.

The subcommand list is read from ``build_parser`` itself, not hardcoded, so
the guard tracks the real surface automatically as commands are added.

If this test fails, add the command to ``README.md`` -- do not weaken the
assertion.
"""

import argparse
from pathlib import Path

from falsifyai.cli.main import build_parser

_README = Path(__file__).resolve().parents[2] / "README.md"


def _subcommand_names() -> list[str]:
    parser = build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return sorted(action.choices)
    raise AssertionError(
        "build_parser() exposes no subparsers; the CLI dispatch shape changed. "
        "Update this guard to match how subcommands are now registered."
    )


def test_every_subcommand_is_referenced_in_readme() -> None:
    readme = _README.read_text(encoding="utf-8")
    commands = _subcommand_names()
    assert commands, "no subcommands discovered from build_parser()"

    missing = [c for c in commands if f"falsifyai {c}" not in readme]
    assert not missing, (
        f"README.md does not reference these CLI subcommands: {missing}. "
        f"A command is registered in build_parser() but the README command "
        f"reference never mentions ``falsifyai <command>`` for it. Document the "
        f"command before shipping."
    )
