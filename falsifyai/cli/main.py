"""``falsifyai`` CLI entry point.

Argparse-based dispatch. Ten subcommands: ``run`` (execute a spec),
``replay`` (re-render a stored session), ``inspect`` (per-case deep-dive
over preserved evidence), ``diff`` (compare two stored sessions and
exit 5 on regression), ``history`` (temporal view of one case across
saved sessions), ``timeline`` (longitudinal robustness trend for one
case; exit 5 on regression), ``matrix`` (cross-model reliability profiles
over N sessions), ``minimize`` (smallest perturbation that breaks a case),
``verify`` (replay-artifact integrity validation), and
``export`` (write a deterministic portable evidence bundle).

Exit codes (per [plan.md section 16.1](../../plan.md)):

- 0 SUCCESS — session verdict STABLE / INFORMATION_PRESENT
- 1 DEGRADED — session verdict FRAGILE / AMBIGUOUS / INFORMATION_NULL
- 2 FAILURE — session verdict CONSISTENTLY_WRONG / ADVERSARIALLY_VULNERABLE / INVALID_EVAL
- 3 ERROR — infrastructure failure (bad spec, missing credential, model call)
- 4 INSUFFICIENT — not enough evidence to discriminate

- 5 REGRESSION — ``diff`` found a verdict-class downgrade or (with ``--strict``) a confidence drop
- 6 LOW_FALSIFIABILITY — ``diff --strict``: candidate falsifiability below threshold
- 7 INTEGRITY_FAILURE — ``verify`` found at least one failed integrity check
"""

import argparse
import sys
from collections.abc import Sequence

from falsifyai.cli import diff as diff_cmd
from falsifyai.cli import export as export_cmd
from falsifyai.cli import history as history_cmd
from falsifyai.cli import inspect as inspect_cmd
from falsifyai.cli import matrix as matrix_cmd
from falsifyai.cli import minimize as minimize_cmd
from falsifyai.cli import replay as replay_cmd
from falsifyai.cli import run as run_cmd
from falsifyai.cli import timeline as timeline_cmd
from falsifyai.cli import verify as verify_cmd
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

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Per-case deep-dive over a stored session's preserved evidence.",
    )
    inspect_parser.add_argument(
        "session_id",
        nargs="?",
        default=None,
        help="Session id to inspect.",
    )
    inspect_parser.add_argument(
        "--case",
        default=None,
        help="Drill into one case_id, expanding every perturbation. "
        "Default behavior shows worst-perturbation evidence per case.",
    )
    inspect_parser.add_argument(
        "--full",
        action="store_true",
        help="Disable output truncation. Default truncates long model outputs "
        "to head-200 + tail-100 chars.",
    )
    inspect_parser.add_argument(
        "--store-path",
        default=".falsifyai/replays.db",
        help="ReplayStore path. Default: .falsifyai/replays.db",
    )

    diff_parser = subparsers.add_parser(
        "diff",
        help="Compare two stored sessions case-by-case. Exit 5 if any case regressed.",
    )
    diff_parser.add_argument("baseline_session_id", help="Baseline session id.")
    diff_parser.add_argument("candidate_session_id", help="Candidate session id.")
    diff_parser.add_argument(
        "--store-path",
        default=".falsifyai/replays.db",
        help="ReplayStore path (both artifacts assumed in same store). "
        "Default: .falsifyai/replays.db",
    )
    diff_parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Stricter exit criteria: exit 5 on same-verdict confidence drop >= 0.10; "
        "exit 6 (LOW_FALSIFIABILITY) when candidate falsifiability < 0.50.",
    )
    diff_parser.add_argument(
        "--show-timeline",
        dest="show_timeline",
        action="store_true",
        default=False,
        help="Show every case with a per-row direction marker and confidence delta. "
        "Display-only; does not affect the exit code.",
    )

    history_parser = subparsers.add_parser(
        "history",
        help="Show how one case has behaved across saved sessions (newest-first).",
    )
    history_parser.add_argument(
        "case_id",
        help="The case_id to trace across sessions in the store.",
    )
    history_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max sessions to show. Default 20; use 0 for unlimited.",
    )
    history_parser.add_argument(
        "--store-path",
        default=".falsifyai/replays.db",
        help="ReplayStore path. Default: .falsifyai/replays.db",
    )

    timeline_parser = subparsers.add_parser(
        "timeline",
        help="Longitudinal robustness trend for one case; exit 5 if it regressed.",
    )
    timeline_parser.add_argument(
        "case_id",
        help="The case_id to trace chronologically across sessions.",
    )
    timeline_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max sessions to include. Default 20; use 0 for unlimited.",
    )
    timeline_parser.add_argument(
        "--store-path",
        default=".falsifyai/replays.db",
        help="ReplayStore path. Default: .falsifyai/replays.db",
    )

    matrix_parser = subparsers.add_parser(
        "matrix",
        help="Cross-model reliability profiles: N sessions x perturbation families.",
    )
    matrix_parser.add_argument(
        "session_ids",
        nargs="+",
        help="Two or more session ids to profile side by side.",
    )
    matrix_parser.add_argument(
        "--store-path",
        default=".falsifyai/replays.db",
        help="ReplayStore path. Default: .falsifyai/replays.db",
    )

    minimize_parser = subparsers.add_parser(
        "minimize",
        help="Find the smallest perturbation strength that breaks a case (minimal falsifier).",
    )
    minimize_parser.add_argument("spec_path", help="Path to the YAML spec file.")
    minimize_parser.add_argument(
        "--case",
        default=None,
        help="Case id to minimize. Defaults to the first case in the spec.",
    )
    minimize_parser.add_argument(
        "--family",
        default="typo_noise",
        choices=["typo_noise", "unicode"],
        help="Perturbation family to escalate. Default: typo_noise.",
    )
    minimize_parser.add_argument(
        "--levels",
        default=None,
        help="Comma-separated ascending strengths to try. Default: 0.02,0.05,0.1,0.2,0.4,0.8.",
    )
    minimize_parser.add_argument(
        "--samples",
        type=int,
        default=5,
        help="Perturbation samples per strength level. Default: 5.",
    )

    export_parser = subparsers.add_parser(
        "export",
        help=(
            "Export a stored ReplayArtifact as a deterministic portable "
            "evidence bundle (.fai.zip recommended)."
        ),
    )
    export_parser.add_argument("session_id", help="Session id to export.")
    export_parser.add_argument(
        "--bundle",
        required=True,
        help="Output bundle path. Convention: .fai.zip (any extension accepted).",
    )
    export_parser.add_argument(
        "--spec-path",
        default=None,
        dest="spec_path",
        help=(
            "Optional path to the source spec YAML; included byte-identically "
            "in the bundle when supplied."
        ),
    )
    export_parser.add_argument(
        "--allow-corrupted",
        action="store_true",
        default=False,
        dest="allow_corrupted",
        help=(
            "Write the bundle even when integrity checks fail. Sets "
            "exported_under_protest=true in the manifest; result is NOT "
            "WORM-suitable."
        ),
    )
    export_parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Replace an existing output file. Refuse by default.",
    )
    export_parser.add_argument(
        "--exported-at",
        default=None,
        dest="exported_at",
        help=(
            "ISO 8601 timestamp (UTC, tz-aware) for reproducibility pinning. "
            "Defaults to current UTC time."
        ),
    )
    export_parser.add_argument(
        "--store-path",
        default=".falsifyai/replays.db",
        help="ReplayStore path. Default: .falsifyai/replays.db",
    )

    verify_parser = subparsers.add_parser(
        "verify",
        help="Validate a stored ReplayArtifact's integrity. Exit 7 on any failed check.",
    )
    verify_parser.add_argument(
        "session_id",
        nargs="?",
        default=None,
        help="Session id to verify. Omit if using --all.",
    )
    verify_parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Verify every session in the store. Aggregate exit 7 if any failed.",
    )
    verify_parser.add_argument(
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
        if args.command == "inspect":
            return inspect_cmd.cmd_inspect(args)
        if args.command == "diff":
            return diff_cmd.cmd_diff(args)
        if args.command == "history":
            return history_cmd.cmd_history(args)
        if args.command == "timeline":
            return timeline_cmd.cmd_timeline(args)
        if args.command == "matrix":
            return matrix_cmd.cmd_matrix(args)
        if args.command == "minimize":
            return minimize_cmd.cmd_minimize(args)
        if args.command == "verify":
            return verify_cmd.cmd_verify(args)
        if args.command == "export":
            return export_cmd.cmd_export(args)
    except CLIError as exc:
        print(f"falsifyai: error: {exc}", file=sys.stderr)
        return exc.exit_code

    # Unknown subcommand (argparse would normally have caught this).
    parser.error(f"unknown command: {args.command}")
    return 2  # pragma: no cover - parser.error raises SystemExit


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
