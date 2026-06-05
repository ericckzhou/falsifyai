"""Verdict enum for the falsificationist evaluation taxonomy.

The full 8-verdict taxonomy (per plan.md section 2.2) plus the two cross-cutting
meta-verdicts. The 0.6.0 milestone adds the four remaining classes
(``INFORMATION_PRESENT``, ``ADVERSARIALLY_VULNERABLE``, ``INFORMATION_NULL``,
``AMBIGUOUS``) to the 0.5.0 set.

Note on layering: a verdict member existing here is not the same as the resolver
*emitting* it. The semantic oracles (PR-J) contribute these verdicts as evidence;
the resolver branches that turn that evidence into an emitted verdict land in
PR-K. The branch-count meta-test (``tests/meta/test_resolver_branch_count.py``)
polices the resolver, not this enum.

Persistence note: string values are part of the public on-disk format for the
replay store (see falsifyai/replay/sqlite_store.py) and must not change once
the store is in use. Add new members; do not rename or repurpose existing
ones.
"""

from enum import Enum


class Verdict(Enum):
    """The 8-verdict falsificationist taxonomy (plan.md section 2.2).

    Stability axis (how much behavior varies under perturbation) crossed with the
    grounding axis (are outputs factually/safely correct), plus two cross-cutting
    meta-verdicts.

    - ``INFORMATION_PRESENT``: high stability AND confirmed grounding -- the gold
      standard. STABLE plus a grounding oracle confirming the outputs are
      supported by the reference.
    - ``STABLE``: outputs are consistent under perturbation; no grounding claim.
    - ``CONSISTENTLY_WRONG``: outputs are consistent but contradict the provided
      ground truth; the most dangerous production case (a confidently
      hallucinating model that v1 frameworks would mark STABLE).
    - ``ADVERSARIALLY_VULNERABLE``: a *targeted* failure shape -- one perturbation
      family collapses while the others hold (a known attack vector), as opposed
      to FRAGILE's diffuse instability.
    - ``FRAGILE``: outputs vary materially under perturbation; reliability claim
      falsified, with no single dominating failure family.
    - ``INFORMATION_NULL``: outputs structurally consistent but semantically empty
      (noise, refusals, hedging) with no grounding claim.
    - ``AMBIGUOUS``: ran the eval but the evidence is too thin to discriminate
      (CI too wide, or a real-but-sub-INVALID_EVAL oracle disagreement). Distinct
      from ``INSUFFICIENT`` (a *structural* gap: no perturbations / no invariants).
    - ``INSUFFICIENT``: not enough structure to run a meaningful eval.
    - ``INVALID_EVAL``: the evaluation itself is broken (oracles disagree,
      invariants malformed, >50% perturbations invalid, etc.). Sole source is
      the meta-oracle.
    """

    INFORMATION_PRESENT = "information_present"
    STABLE = "stable"
    CONSISTENTLY_WRONG = "consistently_wrong"
    ADVERSARIALLY_VULNERABLE = "adversarially_vulnerable"
    FRAGILE = "fragile"
    INFORMATION_NULL = "information_null"
    AMBIGUOUS = "ambiguous"
    INSUFFICIENT = "insufficient"
    INVALID_EVAL = "invalid_eval"
