"""``falsifyai`` CLI entry point.

Argparse-based dispatch. Two subcommands so far: ``run`` (execute a spec)
and ``replay`` (re-render a stored session). Week 2 adds ``diff``.

Exit codes (per [plan.md section 16.1](../../plan.md)):

- 0 SUCCESS — session verdict STABLE
- 1 DEGRADED — session verdict FRAGILE
- 2 FAILURE — session verdict CONSISTENTLY_WRONG / INVALID_EVAL
- 3 ERROR — infrastructure failure (bad spec, missing credential, model call)
- 4 INSUFFICIENT — not enough evidence to discriminate

Codes 5 (REGRESSION) and 6 (LOW_FALSIFIABILITY) ship with Week 2 features.
"""

import argparse
import sys
from collections.abc import Sequence

from falsifyai.cli import replay as replay_cmd
from falsifyai.cli import run as run_cmd
from falsifyai.cli.errors import CLIError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="falsifyai",
        description="Falsification-first reliability testing for AI systems.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    run_parser = subparsers.add_parser("run", help="Run a falsification eval against a spec.")
    run_parser.add_argument("spec_path", help="Path to the YAML spec file.")
    run_parser.add_argument(
        "--store-path",
        default=".falsifyai/replays.db",
        help="ReplayStore path. Use ':memory:' for an ephemeral run. "
        "Default: .falsifyai/replays.db",
    )

    replay_parser = subparsers.add_parser(
        "replay", help="Load and re-render a previously stored session."
    )
    replay_parser.add_argument(
        "session_id",
        nargs="?",
        default=None,
        help="Session id to load. Omit if using --latest.",
    )
    replay_parser.add_argument(
        "--latest",
        action="store_true",
        help="Load the most recent session in the store. Mutually exclusive with session_id.",
    )
    replay_parser.add_argument(
        "--store-path",
        default=".falsifyai/replays.db",
        help="ReplayStore path. Default: .falsifyai/replays.db",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    try:
        if args.command == "run":
            return run_cmd.cmd_run(args)
        if args.command == "replay":
            return replay_cmd.cmd_replay(args)
    except CLIError as exc:
        print(f"falsifyai: error: {exc}", file=sys.stderr)
        return exc.exit_code

    # Unknown subcommand (argparse would normally have caught this).
    parser.error(f"unknown command: {args.command}")
    return 2  # pragma: no cover - parser.error raises SystemExit


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
