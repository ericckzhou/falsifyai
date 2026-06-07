"""Stale-doc tripwire for the evidence-protocol contract document.

``docs/EVIDENCE.md`` is the artifact contract: it specifies what the replay
artifact *is*, what its verdicts mean as claims, and what consumers may do with
it. Stale claims there are higher-risk than stale claims anywhere else in the
repo, because the document is the thing external readers trust.

This is a **coarse** freshness guard, not a prose validator. It enforces two
cheap, high-signal invariants and nothing semantic:

1. Every ``Verdict`` enum member is named at least once in the document. This
   catches the failure mode where a new verdict class is wired into the
   taxonomy but the contract doc is never updated to mention it. It does *not*
   catch a verdict named in one section but stale in another (e.g. an outdated
   per-section list while §7 stays complete) -- a document-wide substring scan
   cannot see intra-document inconsistency. That class of drift is caught by
   review, not here.
2. The document names the read-only preservation consumers at least once, so
   the producer/consumer boundary the artifact depends on stays documented as
   the command surface grows.

If this test fails, update ``docs/EVIDENCE.md`` -- do not weaken the assertion.
"""

from pathlib import Path

from falsifyai.verdict.models import Verdict

_EVIDENCE_DOC = Path(__file__).resolve().parents[2] / "docs" / "EVIDENCE.md"

# Read-only consumers of a preserved artifact. The protocol guarantee is that
# these re-present preserved evidence and never re-derive the claim; the doc
# must keep describing that surface as it grows.
_READONLY_CONSUMERS = (
    "replay",
    "inspect",
    "diff",
    "history",
    "timeline",
    "matrix",
    "verify",
    "export",
)


def _doc_text() -> str:
    assert _EVIDENCE_DOC.exists(), f"evidence contract doc missing: {_EVIDENCE_DOC}"
    return _EVIDENCE_DOC.read_text(encoding="utf-8")


def test_every_verdict_appears_in_evidence_doc() -> None:
    text = _doc_text()
    missing = [v.name for v in Verdict if v.name not in text]
    assert not missing, (
        f"docs/EVIDENCE.md does not mention these Verdict members: {missing}. "
        f"A new verdict class was wired into the taxonomy but the artifact "
        f"contract doc was not updated. Add the verdict (at minimum to the §7 "
        f"claim table) before shipping."
    )


def test_evidence_doc_names_readonly_consumers() -> None:
    text = _doc_text()
    missing = [c for c in _READONLY_CONSUMERS if c not in text]
    assert not missing, (
        f"docs/EVIDENCE.md no longer names these read-only consumers: {missing}. "
        f"The producer/consumer boundary is load-bearing protocol semantics; "
        f"keep the consumer surface documented."
    )
