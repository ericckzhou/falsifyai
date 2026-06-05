# When the confidence number lies: a presentation-layer self-falsification

> **One sentence**: the same `probe-03.db` bundle that exposed the framework's *verdict* false positives (case study 03) was hiding a fifth false signal in plain sight — the `confidence` number itself, which reads `0.00` exactly when a verdict is *most* severe and best-supported.

> **Evidence bundle**: [`data/probe-03.db`](data/probe-03.db) · SHA256 `5a6c77ba6231c260209ac0669b6fc9206381f02ca2f48f9f9a24de947ece6e62` · 5 sessions · produced under `falsifyai 0.6.0`. Same bundle as [case study 03](03-evaluator-false-positive.md) — this is a *second reading* of preserved evidence, not a new run.

> **What this is**: a *self-falsification* case study, in the lineage of 03 and 04. Where 03 caught the interpretation layer assigning a wrong *verdict*, this catches the **presentation layer** mislabeling a *correct* number. No model was run; no Groq spend. The finding and its fix live entirely in how FalsifyAI renders what it already computed.

---

## Setup

No new campaign. Case study 03 left a table where, read carefully, every instability-band verdict carries the same suffix:

| # | Candidate | Stored verdict (conf) |
|---|-----------|-----------------------|
| 1 | refund omission | ADVERSARIALLY_VULNERABLE (**0.00**) |
| 3 | extraction schema | FRAGILE (**0.00**) |
| 4 | clause exception | ADVERSARIALLY_VULNERABLE (**0.00**) |
| 5 | threshold anchor | ADVERSARIALLY_VULNERABLE (**0.00**) |

03's thesis was that these verdicts are false positives. This case study asks a narrower, orthogonal question that survives even if a verdict were a *true* positive: **what is that `0.00` confidence actually saying, and does it say it honestly?**

---

## 1. The systemic finding: the confidence field inverts for fragility verdicts

`falsifyai 0.6.2` rendered candidate 1 like this:

```text
case: refund_summary_exception_omission  verdict: ADVERSARIALLY_VULNERABLE  confidence: 0.00 (CI: 0.00-0.62)
```

A reader parses `confidence: 0.00` as *"the framework is not confident this is adversarially vulnerable."* The opposite is true. The number is the **stability floor**, and a near-zero floor is the *strongest* possible evidence of fragility. The more broken the case, the lower the "confidence" reads — a direct inversion of meaning at the most decision-critical moment.

This is not one bad row. It is structural: **every** `ADVERSARIALLY_VULNERABLE` / `FRAGILE` / `AMBIGUOUS` verdict in any store inherits it.

---

## 2. The mechanism: `verdict_confidence = ci_low`, surfaced without its band

Two lines of [`verdict/resolver.py`](../../falsifyai/verdict/resolver.py) produce the inversion. First, the case "confidence" *is* the stability bootstrap CI lower bound:

```python
verdict_confidence=ci_low,  # semantic continuity with PR #8 era artifacts
```

Second, the instability-band verdicts are entered **precisely when that floor fails the stable bar**:

```python
if stability_ci_low < stable_threshold:
    if shape == "targeted":
        return Verdict.ADVERSARIALLY_VULNERABLE
    if stability_ci_high < fragile_threshold:
        return Verdict.FRAGILE
    return Verdict.AMBIGUOUS
```

So for exactly these verdicts, `verdict_confidence` is guaranteed to sit below `stable_threshold`, collapsing toward `0.00` as the failing family collapses. The resolver is *correct* — `ci_low` is the right statistic. The defect is that [`cli/render.py`](../../falsifyai/cli/render.py) labeled it `confidence` regardless of band, so a number that means "stability floor = rock bottom → high severity" was printed under a header that reads as "low certainty."

For a stable-band verdict the same field reads correctly (`confidence: 0.92` = "confident it's stable"). The label is only honest for half the verdict space.

---

## 3. Why it matters (and why it is *not* a resolver bug)

This is orthogonal to case study 03. 03's verdicts were wrong; fix the oracle and the verdict flips. Here the **verdict and the number are both correct** — only the *word* in front of the number is wrong. Even a genuinely adversarially-vulnerable model (a true positive) would be mislabeled `confidence: 0.00`, training the reader to discount the framework's most important findings.

It is a **consumer-surface** defect, and the fix respects FalsifyAI's hardest guardrail: *expand the consumer surface, not the verdict logic.* The verdict resolver is byte-identical after this PR. No new heuristic, threshold, or verdict class entered the epistemic core — the change is purely in how a preserved value is named on screen.

---

## 4. The fix: a band-aware label

[`render.py`](../../falsifyai/cli/render.py) now selects the metric's name from the verdict's band. Instability-band verdicts surface the value as `stability floor`; stable-band verdicts keep `confidence`. Replaying the *same* stored session under the patched renderer:

```text
$ falsifyai replay 4be3d5f293914fbda313324bb0dfdcc3 \
    --store-path docs/case-studies/data/probe-03.db
case: refund_summary_exception_omission  verdict: ADVERSARIALLY_VULNERABLE  stability floor: 0.00 (CI: 0.00-0.62)
1 case, verdict ADVERSARIALLY_VULNERABLE, 0 FRAGILE, 0 CONSISTENTLY_WRONG, falsifiability 0.39
```

`stability floor: 0.00` reads the way the evidence actually points: the worst-case stability bottoms out at zero. The stored artifact is untouched — only the reading of it changed.

### The label, swept across every consumer surface

`render.py` powers `run` / `replay` / `diff`, but it is not the only place a reader meets this number. A follow-up audited the four other consumer surfaces that read preserved evidence:

| Surface | Before | After |
|---|---|---|
| `inspect` | `confidence: 0.00 (CI: …)` per case | `stability floor: 0.00 (CI: …)` — same band-aware label as `replay` |
| `history` | `0.00 (CI: …)` — an **unlabeled** number that both duplicated the CI floor and, by convention, read as confidence | `(CI: …)` only — the redundant number dropped; the band (history's documented `CI` column) carries the floor honestly |
| `matrix` | worst-case per-family **stability** | unchanged — already honest (higher = more robust, never called confidence) |
| `timeline` | `CIlow=0.00` + a stability sparkline | unchanged — already honest (labeled `CIlow`, never confidence) |

The same discipline that produced the fix produced the audit: a presentation defect is structural, so the question is never "is this one row wrong?" but "everywhere this value is read, is it read honestly?" Two surfaces inherited the inversion; two had already escaped it. None of the four touches the resolver.

---

## Reproduction

```bash
# The pre-fix label is preserved in this case study; reproduce the post-fix
# reading against the bundled store (no model calls — replay is read-only):
falsifyai replay 4be3d5f293914fbda313324bb0dfdcc3 \
    --store-path docs/case-studies/data/probe-03.db

# The same inversion existed for the FRAGILE and other AV sessions:
#   3 (FRAGILE):  c42633a103fe4c078e31d82e7760e733
#   4 (AV):       db7d00a5cf684e88b82f1bad4868acde
#   5 (AV):       0efc23e3b975455ba5c7adfdb3eb5d5b
```

---

## Synthesis

One preserved evidence substrate; many readings. Case study 03 read the *verdicts* in `probe-03.db` and found a false positive in the interpretation layer. This case study read the *confidence numbers* in the same bundle and found a false signal in the presentation layer — invisible until you ask what the number means, not just what it is. Both were caught the same way the framework asks its users to work: **inspect the preserved evidence; do not trust the headline.** The discipline applies recursively, and a falsification framework earns credibility only by surviving it.
