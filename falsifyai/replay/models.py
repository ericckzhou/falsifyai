"""Persisted replay artifact shape.

A :class:`ReplayArtifact` is the immutable record of one ``falsify run``
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

from dataclasses import dataclass
from datetime import datetime

from falsifyai.execution.models import Execution
from falsifyai.invariants.base import InvariantResult
from falsifyai.perturbation.base import PerturbedInput
from falsifyai.spec.materializer import MaterializedSpec
from falsifyai.verdict.models import Verdict


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
    per realized perturbation, plus the case-level resolved verdict and its
    confidence.
    """

    case_id: str
    original_input: str
    original_execution: Execution
    perturbed: list[PerturbedRun]
    verdict: Verdict
    verdict_confidence: float


@dataclass(frozen=True)
class SessionVerdict:
    """Session-level roll-up of per-case verdicts.

    The MVP verdict resolver (separate PR) is the source of these counts.
    For PR #6 the writer (caller of ``ReplayStore.save_session``) supplies
    them directly.
    """

    session_verdict: Verdict
    confidence: float
    case_count: int
    fragile_count: int
    consistently_wrong_count: int


@dataclass(frozen=True)
class ReplayArtifact:
    """Self-contained snapshot of one ``falsify run`` invocation.

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
