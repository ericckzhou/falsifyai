"""Persisted replay artifact shape.

A :class:`ReplayArtifact` is the immutable record of one ``falsifyai run``
invocation. Everything needed to reconstruct what happened — the materialized
inputs, every execution, every invariant judgment, and the resolved verdict —
lives inside a single artifact so a saved session is **self-contained**:
loading from the store does not require the original YAML file to still exist
on disk.

Design notes:
- All dataclasses are frozen. Mutation post-construction is a bug.
- :class:`PerturbedRun` flattens what the plan originally sketched as a
  ``list[tuple[PerturbedInput, Execution, list[InvariantResult]]]``. The
  named-field form is friendlier to read and serialize than positional tuples.
- ``falsifyai_version`` is stored + exposed on every artifact but **not
  enforced** by the loader (we are pre-1.0; version semantics are not stable
  yet). Major-version refusal is a future PR.
"""

from dataclasses import dataclass, field
from datetime import datetime

from falsifyai.execution.models import Execution
from falsifyai.invariants.base import InvariantResult
from falsifyai.perturbation.base import PerturbedInput
from falsifyai.spec.materializer import MaterializedSpec
from falsifyai.verdict.models import Verdict


@dataclass(frozen=True)
class CliInvocation:
    """Descriptive provenance for the CLI command that produced this artifact (PR-35).

    Captured at entry into ``cmd_run``; never stamped by read-only consumer
    surfaces (``replay``, ``inspect``, ``history``, ``diff``, ``verify``,
    ``export``). Pre-PR-35 artifacts carry ``cli_invocation = None``.

    **Semantic boundary (load-bearing):** this records *what command produced
    the artifact*, NOT a guarantee that re-running the command will produce
    identical outputs. Files may move, models drift, providers change, hosted
    LLMs are not bit-stable across runs. Replay-determinism guarantees live in
    ``ReplayArtifact.materialized_hash`` (preserved perturbation evidence) and
    in the bundle's ``bundle_id`` (preserved manifest + file hashes).

    **Capture contract:**

    - ``argv`` — normalized invocation token list. Program name canonicalized
      to ``"falsifyai"`` regardless of entry path (entry point vs ``-m`` vs
      direct script). All subsequent tokens preserved verbatim from
      ``sys.argv``.
    - ``falsifyai_version`` — runtime package version at capture time.

    **Explicitly NOT captured** (each by deliberate restraint):

    - Environment variables (secret-leakage surface)
    - API keys (not in argv today; future auth-bearing flags MUST redact)
    - Current working directory (specs are referenced by path *in* argv)
    - Hostname / username / machine identifiers (operator identity belongs at
      the commit / export layer, not the artifact)
    - Shell history / pre-shell-expansion argv (unavailable by construction)
    - File contents (spec YAML lives in ``MaterializedSpec`` already)
    """

    argv: tuple[str, ...]
    falsifyai_version: str


@dataclass(frozen=True)
class PerturbedRun:
    """One perturbed input + its execution + the invariant judgments on its output."""

    perturbed_input: PerturbedInput
    execution: Execution
    invariant_results: list[InvariantResult]


@dataclass(frozen=True)
class CaseResult:
    """The full record for one case in a session.

    Pairs the original execution (baseline) with one :class:`PerturbedRun`
    per realized perturbation, plus the case-level resolved verdict and the
    statistical evidence behind it.

    The ``stability`` / ``stability_ci_low`` / ``stability_ci_high`` triple
    is the **worst-case stratified** estimate per [plan.md section 12](../../plan.md):
    each perturbation family is bootstrap-resampled separately, and we
    surface the family with the lowest CI lower bound. ``per_family_stability``
    preserves every family's point estimate so ``falsifyai diff`` can compare
    distributions, not just point estimates.

    For semantic continuity with PR #6/#8 era artifacts, ``verdict_confidence``
    is populated equal to ``stability_ci_low`` (the honest "how confident
    am I in this verdict?" number).
    """

    case_id: str
    original_input: str
    original_execution: Execution
    perturbed: list[PerturbedRun]
    verdict: Verdict
    verdict_confidence: float

    # PR #11+ fields. Defaults preserve forward-compat construction from
    # callers that haven't been updated yet (and backward-compat reads of
    # PR #6/#8 era artifacts that didn't carry them).
    stability: float = 0.0
    stability_ci_low: float = 0.0
    stability_ci_high: float = 0.0
    per_family_stability: dict[str, float] = field(default_factory=dict)
    worst_case_family: str | None = None


@dataclass(frozen=True)
class SessionVerdict:
    """Session-level roll-up of per-case verdicts.

    ``falsifyai_falsifiability_score`` is the mean per-case falsifiability
    contribution (see ``falsifyai.falsifiability.score``). Low scores mean
    the suite passes CI on weak assertions; the CLI warns when below
    ``LOW_FALSIFIABILITY_THRESHOLD`` (0.5).
    """

    session_verdict: Verdict
    confidence: float
    case_count: int
    fragile_count: int
    consistently_wrong_count: int

    # PR #11+ field. Default preserves backward-compat reads of older artifacts.
    falsifyai_falsifiability_score: float = 0.0


@dataclass(frozen=True)
class ReplayArtifact:
    """Self-contained snapshot of one ``falsifyai run`` invocation.

    Identity:
    - ``session_id``: uuid4 assigned at save time; unique per save.
    - ``spec_hash`` + ``materialized_hash``: anchor back to the source YAML
      and the realized perturbations respectively.
    - ``created_at``: UTC; naive datetimes are rejected by the serializer.
    """

    session_id: str
    created_at: datetime
    falsifyai_version: str
    spec_hash: str
    materialized_hash: str
    materialized: MaterializedSpec
    case_results: list[CaseResult]
    session_verdict: SessionVerdict

    # PR-35: descriptive provenance for the CLI command that produced this
    # artifact. Default None preserves backward compat with pre-PR-35
    # artifacts and with artifacts produced via read-only consumer commands
    # (which never stamp invocation by design). See ``CliInvocation`` above
    # for the full capture contract.
    cli_invocation: CliInvocation | None = None
