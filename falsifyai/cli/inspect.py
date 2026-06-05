"""``falsifyai inspect <session_id>`` -- per-case deep-dive over preserved evidence.

Loads a stored ``ReplayArtifact`` and surfaces the per-case evidence trail that
``run`` and ``replay`` deliberately compress: every perturbed input, every
model output, every invariant judgment. The artifact is the durable record;
this command makes it legible.

Invariants (load-bearing — see PR-19 plan and ``docs/EVIDENCE.md`` for context):

- **Read-only.** Verdicts shown are the verdicts assigned at run time. The
  resolver is never invoked here. The architectural test
  ``test_inspect_does_not_import_resolver`` enforces this rule by import-graph
  introspection. Do not add a resolver import.
- **No synthesis.** If a field is absent from the preserved artifact (e.g. an
  empty ``invariant_results`` list on a perturbation), inspect surfaces the
  gap explicitly. It does not substitute a default or silently omit. See
  PR-19 plan §12.3.
- **Compressed by default, expanded on demand.** STABLE cases show verdict +
  perturbation count only. FRAGILE / CONSISTENTLY_WRONG cases also show the
  worst-perturbation evidence. ``--case <id>`` expands to every perturbation
  for one case. ``--full`` disables output truncation. See plan §11 decisions
  B (verbosity) and C (truncation).
- **Band-aware metric label.** The per-case ``verdict_confidence`` is surfaced
  via ``render._metric_label`` — the same band-aware naming ``run`` / ``replay``
  use. Stable-band verdicts read it as ``confidence``; instability-band verdicts
  (ADVERSARIALLY_VULNERABLE / FRAGILE / AMBIGUOUS) read it as ``stability floor``
  so a near-zero CI floor does not masquerade as low confidence. See
  docs/case-studies/05-confidence-floor-inversion.md.
- **Exit codes mirror ``replay`` / ``run``.** STABLE->0, FRAGILE->1,
  CONSISTENTLY_WRONG->2. Code 3 (ERROR) for infrastructure failures (missing
  session, unknown case_id).
"""

import argparse
import contextlib
import sys
from typing import TextIO

from falsifyai.cli import render
from falsifyai.cli.errors import InfrastructureError
from falsifyai.replay.models import CaseResult, PerturbedRun, ReplayArtifact
from falsifyai.replay.protocol import SessionNotFoundError
from falsifyai.replay.registry import build_store
from falsifyai.verdict.models import Verdict

# Output truncation thresholds (plan §11 decision C1).
_TRUNCATE_THRESHOLD = 400
_HEAD_CHARS = 200
_TAIL_CHARS = 100


def _truncate_output(text: str, *, full: bool) -> str:
    """Truncate long outputs to head + tail with an explicit marker.

    Default keeps the first 200 chars and last 100 chars of any output
    exceeding 400 chars. ``--full`` disables the truncation. The omission
    marker tells the reader exactly how to see the full text.
    """
    if full or len(text) <= _TRUNCATE_THRESHOLD:
        return text
    head = text[:_HEAD_CHARS]
    tail = text[-_TAIL_CHARS:]
    omitted = len(text) - _HEAD_CHARS - _TAIL_CHARS
    return f"{head}...[{omitted} chars omitted; rerun with --full]...{tail}"


def _select_worst_perturbation(case: CaseResult) -> PerturbedRun | None:
    """Pick the worst perturbation for default rendering of a FRAGILE case.

    Returns ``None`` when no perturbation-level evidence should be surfaced:
    - STABLE cases (no worst family attributed)
    - CONSISTENTLY_WRONG cases (the failure is in the baseline, not a
      perturbation; the caller renders baseline evidence instead)

    Otherwise, finds the first perturbation in ``case.worst_case_family``
    that has at least one failing invariant_result. Falls back to the first
    family member if all somehow pass (defensive — shouldn't happen for
    FRAGILE in a well-formed artifact).
    """
    if case.verdict is not Verdict.FRAGILE:
        return None
    if case.worst_case_family is None:
        return None
    family = case.worst_case_family
    candidates = [
        pr for pr in case.perturbed if pr.perturbed_input.lineage.perturbation_type == family
    ]
    if not candidates:
        return None
    for pr in candidates:
        if any(not r.passed for r in pr.invariant_results):
            return pr
    return candidates[0]


def _render_invariant_result(result, *, label_prefix: str = "invariant") -> str:
    """One-line invariant judgment summary. Uses ASCII-only punctuation so the
    output is identical across terminal encodings (no cp1252 surprises)."""
    status = "PASS" if result.passed else "FAIL"
    return f"    {label_prefix}: {result.invariant_name} {status} -- {result.details}"


def _render_perturbed_evidence(
    pr: PerturbedRun,
    *,
    full: bool,
    failed_invariant_label: str,
) -> list[str]:
    """Render one perturbed run's input + output + invariant judgments.

    Returns a list of indented lines. Used by both default (worst-perturbation
    only) and ``--case`` (every perturbation) paths. The output preserves the
    no-synthesis rule: if ``invariant_results`` is empty, the gap is named.
    """
    lines: list[str] = []
    lines.append(f"  perturbed input:  {pr.perturbed_input.text}")
    lines.append(f"  output excerpt:   {_truncate_output(pr.execution.output_text, full=full)}")
    if not pr.invariant_results:
        # §12.3 no-synthesis: name the gap, don't fabricate a judgment.
        lines.append("    <no invariant results preserved for this perturbation>")
        return lines
    # Surface the failing invariant first, then any others for context.
    failing = [r for r in pr.invariant_results if not r.passed]
    passing = [r for r in pr.invariant_results if r.passed]
    for r in failing:
        lines.append(_render_invariant_result(r, label_prefix=failed_invariant_label))
    for r in passing:
        lines.append(_render_invariant_result(r, label_prefix="invariant"))
    return lines


def _render_case_default(case: CaseResult, *, full: bool, stream: TextIO) -> None:
    """Default per-case render: verdict + perturbation count + worst-perturbation evidence."""
    is_legacy = render._is_legacy_case(case)
    perturbation_count = len(case.perturbed)
    if is_legacy:
        header = (
            f"case: {case.case_id}  verdict: {case.verdict.value.upper()}  "
            f"{render._metric_label(case)}  (legacy)  "
            f"perturbations: {perturbation_count}"
        )
    else:
        header = (
            f"case: {case.case_id}  verdict: {case.verdict.value.upper()}  "
            f"{render._metric_label(case)} "
            f"(CI: {case.stability_ci_low:.2f}-{case.stability_ci_high:.2f})  "
            f"perturbations: {perturbation_count}"
        )
        if case.verdict is Verdict.FRAGILE and case.worst_case_family:
            header += f"  worst: {case.worst_case_family}"
    stream.write(header + "\n")

    # STABLE cases stop at the header (plan §11 decision B refined).
    if case.verdict is Verdict.STABLE:
        return

    # CONSISTENTLY_WRONG: render the baseline output + its failing original-judgment
    # context, since the failure is in the baseline itself. The original execution
    # is what the reader needs to inspect.
    if case.verdict is Verdict.CONSISTENTLY_WRONG:
        baseline_text = _truncate_output(case.original_execution.output_text, full=full)
        stream.write(f"  baseline input:   {case.original_input}\n")
        stream.write(f"  baseline output:  {baseline_text}\n")
        stream.write(
            "    (CONSISTENTLY_WRONG: baseline already violates the contract; "
            "perturbations did not change that)\n"
        )
        return

    # FRAGILE: render worst-perturbation evidence
    worst = _select_worst_perturbation(case)
    if worst is None:
        stream.write("    <no worst perturbation identifiable in preserved evidence>\n")
        return
    for line in _render_perturbed_evidence(
        worst, full=full, failed_invariant_label="failing invariant"
    ):
        stream.write(line + "\n")


def _render_case_expanded(case: CaseResult, *, full: bool, stream: TextIO) -> None:
    """Expanded per-case render (--case <id>): every perturbation, baseline included."""
    is_legacy = render._is_legacy_case(case)
    perturbation_count = len(case.perturbed)
    if is_legacy:
        header = (
            f"case: {case.case_id}  verdict: {case.verdict.value.upper()}  "
            f"{render._metric_label(case)}  (legacy)  "
            f"perturbations: {perturbation_count}"
        )
    else:
        header = (
            f"case: {case.case_id}  verdict: {case.verdict.value.upper()}  "
            f"{render._metric_label(case)} "
            f"(CI: {case.stability_ci_low:.2f}-{case.stability_ci_high:.2f})  "
            f"perturbations: {perturbation_count}"
        )
        if case.verdict is Verdict.FRAGILE and case.worst_case_family:
            header += f"  worst: {case.worst_case_family}"
    stream.write(header + "\n")

    # Baseline (original) — always shown in expanded mode
    stream.write(f"  baseline input:   {case.original_input}\n")
    stream.write(
        f"  baseline output:  {_truncate_output(case.original_execution.output_text, full=full)}\n"
    )

    # Each perturbation, indexed
    for idx, pr in enumerate(case.perturbed, start=1):
        family = pr.perturbed_input.lineage.perturbation_type
        method = pr.perturbed_input.lineage.method
        stream.write(f"  [{idx}] {family} ({method}):\n")
        for line in _render_perturbed_evidence(
            pr,
            full=full,
            failed_invariant_label="invariant",
        ):
            # Indent one more level under [N]
            stream.write("  " + line + "\n")


def _render_session(
    artifact: ReplayArtifact,
    *,
    store_path: str,
    case_id: str | None,
    full: bool,
    stream: TextIO,
) -> None:
    """Top-level inspect render: header + per-case content.

    Reconfigures stdout's error handler to ``backslashreplace`` so non-UTF-8
    terminals (e.g., Windows cp1252) escape unprintable characters in model
    outputs rather than crashing. Model-emitted Unicode like narrow no-break
    spaces (``\\u202f``) frequently appears in LLM completions and would
    otherwise raise ``UnicodeEncodeError`` mid-render.
    """
    # Test streams (capsys) or wrapped streams may not support reconfigure;
    # fall back to default behavior in those cases.
    with contextlib.suppress(AttributeError, ValueError):
        stream.reconfigure(errors="backslashreplace")  # type: ignore[union-attr]

    stream.write(
        f"Inspecting session {artifact.session_id} | "
        f"created_at {artifact.created_at.isoformat()} | "
        f"falsifyai {artifact.falsifyai_version} | "
        f"store {store_path}\n"
    )
    stream.write("=" * 65 + "\n")

    if case_id is not None:
        target = next((c for c in artifact.case_results if c.case_id == case_id), None)
        if target is None:
            available = ", ".join(c.case_id for c in artifact.case_results) or "<none>"
            raise InfrastructureError(f"unknown case_id: {case_id!r} (available: {available})")
        _render_case_expanded(target, full=full, stream=stream)
    else:
        for case in artifact.case_results:
            _render_case_default(case, full=full, stream=stream)

    stream.write("=" * 65 + "\n")
    sv = artifact.session_verdict
    stream.write(
        f"{sv.case_count} case{'s' if sv.case_count != 1 else ''}, "
        f"verdict {sv.session_verdict.value.upper()}, "
        f"{sv.fragile_count} FRAGILE, "
        f"{sv.consistently_wrong_count} CONSISTENTLY_WRONG, "
        f"falsifiability {sv.falsifyai_falsifiability_score:.2f}\n"
    )


def cmd_inspect(args: argparse.Namespace) -> int:
    """Entry point for the ``inspect`` subcommand. Returns an exit code."""
    if args.session_id is None:
        raise InfrastructureError("session_id is required")

    store = build_store(args.store_path)
    try:
        try:
            artifact = store.load_session(args.session_id)
        except SessionNotFoundError as exc:
            raise InfrastructureError(f"session not found: {args.session_id}") from exc
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()

    _render_session(
        artifact,
        store_path=args.store_path,
        case_id=args.case,
        full=args.full,
        stream=sys.stdout,
    )

    return render.exit_code_for(artifact.session_verdict.session_verdict)


__all__ = ["cmd_inspect"]
