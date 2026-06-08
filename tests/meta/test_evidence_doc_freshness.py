"""Stale-doc tripwire for the evidence-protocol contract document.

``docs/EVIDENCE.md`` is the artifact contract: it specifies what the replay
artifact *is*, what its verdicts mean as claims, and what consumers may do with
it. Stale claims there are higher-risk than stale claims anywhere else in the
repo, because the document is the thing external readers trust.

This is a **coarse** freshness guard, not a prose validator. It enforces three
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
3. Every leaf consumer box in the §3 lifecycle diagram names a real CLI
   command. This catches the specific drift where the diagram keeps a node for
   an operation that was never (or no longer) a command -- e.g. a stale
   ``archive`` box surviving long after the consumer surface settled on
   ``replay`` / ``inspect`` / ``diff``. The prose word "archive" is allowed to
   appear elsewhere (retention discussion); only diagram *boxes* are checked.

If this test fails, update ``docs/EVIDENCE.md`` -- do not weaken the assertion.
"""

import re
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


# Every CLI command FalsifyAI ships. A leaf box in the lifecycle diagram must
# name one of these; "archive" (a past stale node) is intentionally absent.
_ALL_COMMANDS = frozenset(
    {
        "run",
        "replay",
        "inspect",
        "diff",
        "history",
        "timeline",
        "matrix",
        "minimize",
        "export",
        "verify",
        "doctor",
    }
)

# A box-drawing cell holding a single lowercase token: ``│ replay │``. The
# inner whitespace is horizontal-only (``[^\S\n]`` not ``\s``) so a token never
# pairs an opening ``│`` on one line with a closing ``│`` on the next -- that
# cross-line greediness would otherwise capture a trailing label like the
# ``│   evidence`` annotation beside the artifact box. Matched non-overlapping
# so a one-line ``│ replay │  │ inspect │  │ diff │`` row yields all three.
# Multi-word boxes ("the durable record") never match: ``[a-z_]+`` stops at the
# first space and the following ``│`` is not adjacent.
_DIAGRAM_BOX = re.compile(r"│[^\S\n]*([a-z_]+)[^\S\n]*│")


def _doc_text() -> str:
    assert _EVIDENCE_DOC.exists(), f"evidence contract doc missing: {_EVIDENCE_DOC}"
    return _EVIDENCE_DOC.read_text(encoding="utf-8")


def _lifecycle_diagram() -> str:
    """The fenced ASCII block in §3 -- the one containing the artifact node."""
    blocks = _doc_text().split("```")
    # Fenced content sits at odd indices once split on the fence marker.
    for block in blocks[1::2]:
        if "REPLAY ARTIFACT" in block:
            return block
    raise AssertionError(
        "lifecycle diagram not found in docs/EVIDENCE.md: no fenced block names "
        "'REPLAY ARTIFACT'. The §3 diagram is the artifact contract's visual "
        "anchor -- if it was removed or renamed, update this guard deliberately."
    )


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


def test_lifecycle_diagram_leaf_consumers_are_real_commands() -> None:
    # Leaf consumer boxes fan out *below* the artifact node; restrict the scan
    # to that region so upstream pipeline boxes ("spec", etc.) are not checked.
    _, _, leaf_region = _lifecycle_diagram().partition("REPLAY ARTIFACT")
    boxes = _DIAGRAM_BOX.findall(leaf_region)

    assert boxes, (
        "no leaf consumer boxes found below the REPLAY ARTIFACT node in the "
        "docs/EVIDENCE.md lifecycle diagram. The diagram must show the consumers "
        "reading the preserved artifact; if its shape changed, update this guard."
    )

    unknown = sorted({b for b in boxes if b not in _ALL_COMMANDS})
    assert not unknown, (
        f"lifecycle diagram in docs/EVIDENCE.md names non-command leaf nodes: "
        f"{unknown}. Every consumer box below the artifact node must be a real "
        f"CLI command -- this is the guard that locks out the stale 'archive' "
        f"node. Known commands: {sorted(_ALL_COMMANDS)}."
    )
