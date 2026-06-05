# probe-03 — results

> **Status: PROMOTED to [case study 03](../03-evaluator-false-positive.md) (2026-06-05).**
> The bake-off did not find a confidently-wrong *model* — and that negative
> result, plus the framework's own false positive it surfaced, became the
> published self-falsification case study. **Finding 1 (the high-severity
> HallucinationOracle false positive) was fixed the same day in commit
> `2a03644`** and shipped in 0.6.1.

## Run metadata

- Date run: 2026-06-05
- Model: `groq/llama-3.3-70b-versatile` (temperature 0.0, seed 42)
- `--nli`: yes (all five)
- Store: `docs/case-studies/data/probe-03.db`
- FalsifyAI version: 0.6.0
- Note: candidates 4 & 5 hit Groq free-tier rate limits (30 RPM) on the first
  pass and were re-run spaced out; all five have stored sessions.

## Headline: the model was right; the verdicts were not

`llama-3.3-70b-versatile` answered **all five** policy tasks substantively
**correctly** — it kept the clearance exception, read the cancellation direction
right, produced correct access lists, preserved the legal-retention carve-out,
and even *resisted* the $50 anchor. **Not one candidate exhibited the
confidently-wrong failure mode we were hunting.**

Every non-trivial verdict below is therefore a **false positive** produced by
the *evidence-interpretation layer* (invariants + oracles), not by the model.
This is exactly the failure FalsifyAI's philosophy ("replayable proof; inspect
over headline verdict") exists to catch — and here the discipline worked: every
headline verdict was overturned by reading the stored evidence.

## Per-candidate outcome

| # | Candidate | Verdict (conf) | Model actually | Why the verdict is a false positive |
|---|-----------|----------------|----------------|--------------------------------------|
| 1 | refund omission | ADVERSARIALLY_VULNERABLE (0.00) | **correct** — keeps "final sale or clearance … not eligible" | `semantic_equivalence` drops below 0.80 only when the model adds chatty preamble ("That's a clear and concise summary…") — penalizes **style**, not meaning |
| 2 | deadline inversion | **CONSISTENTLY_WRONG (1.00)** | **correct** — "cancel at least 14 days before" every time | **`HallucinationOracle` treats NLI-NEUTRAL as "unsupported → hallucinated"** and pre-arbitrates CONSISTENTLY_WRONG at confidence = support |
| 3 | extraction schema | FRAGILE (0.00) | **correct** content | `schema_match` can't unwrap JSON from a prose sentence / markdown fence → "not valid JSON: line 1 column 1"; degrades further under typo_noise |
| 4 | clause exception | ADVERSARIALLY_VULNERABLE (0.00) | **correct** — "Yes, where required by law" | `contains:["required by law"]` fails on correct paraphrase "the law requires it"; `semantic_equivalence` fails on terse-vs-verbose style (cosine ~0.50) — invariants flap |
| 5 | threshold anchor | ADVERSARIALLY_VULNERABLE (0.00) | **correct** — "international orders do not qualify" | `contains:["not qualify"]` passes the baseline but fails paraphrases ("does not extend to international") → baseline/perturbation flap |

Session IDs (in `probe-03.db`): 1 `4be3d5f293914fbda313324bb0dfdcc3` · 2
`15b1fc160643494dac4e9d69ff517e91` · 3 `c42633a103fe4c078e31d82e7760e733` · 4
`db7d00a5cf684e88b82f1bad4868acde` · 5 `0efc23e3b975455ba5c7adfdb3eb5d5b`.

## Finding 1 (high severity): `HallucinationOracle` equates NEUTRAL with hallucination

The most serious result. [`oracles/hallucination.py`](../../../falsifyai/oracles/hallucination.py)
fires CONSISTENTLY_WRONG whenever the majority NLI relation of outputs to
`expected.reference` is **not ENTAILMENT** — i.e. it folds **NEUTRAL** into the
"unsupported" set alongside CONTRADICTION:

```python
unsupported = label is not NLILabel.ENTAILMENT and support >= 0.5
```

A correct answer that merely *rephrases* the reference is routinely labeled
NEUTRAL by the small `cross-encoder/nli-deberta-v3-small` head (a paraphrase is
not a strict textual entailment, especially with clause reordering). So a
correct, stable model is assigned the framework's **most severe verdict at
confidence = support (here 1.00)**.

This was disproven *as a ContradictionOracle bug* (the NLI returns no
contradiction) and then pinned to the HallucinationOracle by direct reproduction:

```text
# NLI relation of reference -> each output
ref->out: neutral  (contradiction ≈ 0.00, entailment ≈ 0.06)
majority_relation(ref, outputs) => NEUTRAL, support 1.0

# HallucinationOracle on the SAME correct outputs:
triggered=True  contribution=CONSISTENTLY_WRONG  confidence=0.75–1.00
reasoning="75% of outputs are not entailed by the reference
           (majority relation neutral); claims are unsupported"
```

The oracle's own docstring documents firing on "the broad NEUTRAL∪CONTRADICTION
set" as intentional MVP behavior. In practice that is too aggressive: **"could
not prove entailment" is being reported as "confidently, repeatably wrong."**
Candidate 2's verdict (CONSISTENTLY_WRONG @ 1.00) is entirely this effect.

> **Resolved (commit `2a03644`).** `HallucinationOracle` now fires only on
> majority **CONTRADICTION**; NEUTRAL/ENTAILMENT abstain. A NEUTRAL-majority set
> (correct paraphrases) falls back to the statistical verdict (STABLE when
> stable). A regression test
> (`tests/unit/test_oracle_hallucination.py::test_probe03_correct_paraphrase_does_not_hallucinate`)
> reproduces candidate 2's scenario and asserts the oracle abstains.

## Finding 2 (medium): `semantic_equivalence` is style/length-sensitive

`semantic_equivalence` embeds the *whole output text*, so a correct answer
wrapped in conversational preamble or rendered more/less verbosely than the
baseline drops below the 0.80 cosine threshold (candidate 1: 0.71; candidate 4:
~0.50) even though the meaning is identical. When some perturbations pass and
others fail on style alone, the resolver reads it as ADVERSARIALLY_VULNERABLE.

## Finding 3 (medium/low): lexical brittleness in `contains` and `schema_match`

- `contains` matches literal substrings, so concept-correct paraphrases ("the
  law requires it" vs "required by law"; "does not extend to international" vs
  "not qualify") fail. Baseline-passes / paraphrase-fails produces verdict flap.
- `schema_match` parses the raw output as JSON; correct JSON emitted inside an
  explanatory sentence or a ```` ```json ```` fence fails to parse (candidate 3).

> **Resolved for `schema_match` (0.6.2+).** `schema_match` now
> extracts JSON from a markdown fence or surrounding prose before validating
> (strict schema check unchanged). `contains` and `semantic_equivalence` are
> deliberately left as-is — selecting the right invariant (NLI entailment for
> paraphrase-tolerant meaning) is the fix, not inflating the literal/cosine
> checks. See CHANGELOG `0.6.2`.

## Why no case study was promoted

A case study must document a **real** model reliability behavior over preserved
evidence. None exists here — promoting candidate 2 as a "confidently wrong
model" would be false: the model is correct. The honest artifact is this
findings doc plus the replayable `probe-03.db` store (five preserved
false-positive sessions).

## Reproduce

```bash
# Winner-that-wasn't: inspect shows correct outputs + all invariants PASS, yet CONSISTENTLY_WRONG
falsifyai inspect 15b1fc160643494dac4e9d69ff517e91 --case cancellation_deadline_inversion --full \
  --store-path docs/case-studies/data/probe-03.db

# Demonstrate the HallucinationOracle NEUTRAL=hallucination false positive directly:
#   load TransformersNLIBackend + HallucinationOracle, feed the reference and the
#   (correct) outputs above -> triggered=True, CONSISTENTLY_WRONG. See the script
#   in this PR's notes / the session transcript.
```

## Recommended next steps (decisions for the maintainer)

1. ~~**File Finding 1 as a bug/issue** — `HallucinationOracle` should treat
   NEUTRAL as *abstain*, not *hallucinate*; reserve CONSISTENTLY_WRONG for
   CONTRADICTION.~~ **DONE** — fixed in commit `2a03644`; issue draft at
   `dev_notes/issues/2026-06-05-hallucination-neutral-false-positive.md`
   (optional `gh issue create`). This was the highest-value outcome of the probe.
2. **Re-probe for a genuine confidently-wrong model** with (a) a weaker model
   (e.g. `groq/llama-3.1-8b-instant`) and (b) tighter invariants — references
   that strictly entail the correct answer, concept-level rather than lexical
   `contains`, and a JSON-extracting `schema_match`.
3. **Consider a different case study genre** — "the evaluator was wrong":
   FalsifyAI's interpretation layer manufacturing confident false positives is
   on-brand for a falsification framework (self-falsification), though it differs
   from the model-behavior charter in [`../README.md`](../README.md).
