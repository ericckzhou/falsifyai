# When the evaluator is wrong: a self-falsification case study

> **One sentence**: we went hunting for a confidently-wrong *model* and found a confidently-wrong *evaluator* — FalsifyAI's own interpretation layer stamping a correct, stable answer with the framework's harshest verdict at full confidence.

> **Evidence bundle**: [`data/probe-03.db`](data/probe-03.db) · SHA256 `5a6c77ba6231c260209ac0669b6fc9206381f02ca2f48f9f9a24de947ece6e62` · 5 sessions · produced under `falsifyai 0.6.0`.

> **What this is**: a *self-falsification* case study. Case studies 01 and 02 document model behavior; this one turns the framework on itself. A falsification framework is only credible if it is falsifiable about its own judgments — and here the discipline it preaches ("inspect the evidence, don't trust the headline verdict") caught, and then corrected, an error in the framework itself. It differs from the model-behavior charter on purpose.

---

## Setup

The goal was a **`CONSISTENTLY_WRONG`** case study: a model that is confidently, repeatably *wrong* — not brittle, not adversarially fragile, but stably mistaken on a task it appears to handle. We ran a five-candidate bake-off (the [probe-03/](probe-03/) specs), each a single policy-comprehension task designed to elicit a different confidently-wrong failure shape (omission, directional inversion, structural-semantic split, overconfident negation, anchor misattribution):

- Model: `groq/llama-3.3-70b-versatile`, temperature `0.0`, seed `42`
- `--nli` on all five (the 0.6.0 semantic-judgment oracles active)
- Each `falsifyai run` writes a session to [`data/probe-03.db`](data/probe-03.db)

The bet: at least one of the five would break, and that one would be promoted to case study 03.

---

## 1. The twist: the model was right; the verdicts were not

`llama-3.3-70b-versatile` answered **all five** tasks substantively **correctly**. It kept the clearance exception, read the cancellation direction the right way, produced correct access lists, preserved the legal-retention carve-out, and even *resisted* the planted $50 anchor. **Not one candidate exhibited the failure mode we were hunting.**

And yet every non-trivial verdict in the store is a **false positive** — produced by the *evidence-interpretation layer* (invariants + oracles), not by the model:

| # | Candidate | Stored verdict (conf) | Model actually | Source of the false positive |
|---|-----------|-----------------------|----------------|------------------------------|
| 1 | refund omission | ADVERSARIALLY_VULNERABLE (0.00) | **correct** | `semantic_equivalence` penalizes chatty preamble — *style*, not meaning |
| 2 | deadline inversion | **CONSISTENTLY_WRONG (1.00)** | **correct** | `HallucinationOracle` folds NLI-`NEUTRAL` into "hallucinated" |
| 3 | extraction schema | FRAGILE (0.00) | **correct** content | `schema_match` can't unwrap JSON from a prose sentence / markdown fence |
| 4 | clause exception | ADVERSARIALLY_VULNERABLE (0.00) | **correct** | `contains` fails the correct paraphrase "the law requires it" vs "required by law" |
| 5 | threshold anchor | ADVERSARIALLY_VULNERABLE (0.00) | **correct** | `contains` passes baseline, fails paraphrase "does not extend to international" |

This is the inversion the framework's philosophy exists to catch: *the headline verdict is not the evidence.* Read the stored outputs and every one of these verdicts collapses.

---

## 2. The vivid instance: a correct answer at `CONSISTENTLY_WRONG` @ 1.00

Candidate 2 is the sharpest. The task asks how many days before renewal a customer must cancel; the policy says **"cancel at least 14 days before."** Inspect the stored session:

```text
$ falsifyai inspect 15b1fc160643494dac4e9d69ff517e91 --full \
    --store-path docs/case-studies/data/probe-03.db
Inspecting session 15b1fc160643494dac4e9d69ff517e91 | created_at 2026-06-05T12:25:03+00:00 | falsifyai 0.6.0
=================================================================
case: cancellation_deadline_inversion  verdict: CONSISTENTLY_WRONG  confidence: 1.00 (CI: 1.00-1.00)  perturbations: 11
  baseline input:   ... To avoid the renewal charge, cancel at least 14 days before your renewal date.
  baseline output:  According to the policy, a customer must cancel at least 14 days before the renewal date to avoid the charge.
    (CONSISTENTLY_WRONG: baseline already violates the contract; perturbations did not change that)
=================================================================
1 case, verdict CONSISTENTLY_WRONG, 0 FRAGILE, 1 CONSISTENTLY_WRONG, falsifiability 0.37
```

The output — *"cancel at least 14 days before the renewal date"* — is verbatim correct against the policy. The framework reports it as **confidently, repeatably wrong at confidence 1.00**, with the reasoning *"baseline already violates the contract."* It does not.

### Why the evaluator lied

The 0.6.0 [`HallucinationOracle`](../../falsifyai/oracles/hallucination.py) fired `CONSISTENTLY_WRONG` whenever the majority NLI relation of the outputs to the reference was anything *other than* `ENTAILMENT` — folding **`NEUTRAL`** into the "unsupported" set alongside `CONTRADICTION`:

```python
unsupported = label is not NLILabel.ENTAILMENT and support >= 0.5
```

A correct answer that merely *rephrases* the reference is routinely labeled `NEUTRAL` by the small `cross-encoder/nli-deberta-v3-small` head — a paraphrase is not a strict textual entailment, especially with clause reordering. Direct reproduction on the same correct outputs:

```text
ref -> out:  NEUTRAL   (contradiction ≈ 0.00, entailment ≈ 0.06)
majority_relation(ref, outputs) => NEUTRAL, support 1.0
HallucinationOracle => triggered=True, CONSISTENTLY_WRONG, confidence 1.00
  reasoning: "outputs are not entailed by the reference (majority neutral); claims are unsupported"
```

"Could not *prove* entailment" was being reported as "confidently, repeatably *wrong*." The oracle pre-arbitrated the harshest verdict in the taxonomy from the absence of a contradiction.

---

## 3. The fix — and why the artifact still shows the bug

The oracle was corrected the same day in commit `2a03644` and shipped in **0.6.1**: `HallucinationOracle` now fires only on majority **`CONTRADICTION`**; `NEUTRAL`/`ENTAILMENT` abstain and the session falls back to its statistical verdict (`STABLE` when stable). A regression test pins candidate 2's exact scenario.

But run the `inspect` command above on **0.6.1** and it *still* prints `CONSISTENTLY_WRONG`. That is not a second bug — it is the **preservation principle working as designed**. Replay is read-only: a stored verdict is the one assigned at run time and is *never re-resolved*. The artifact is a faithful record of what the framework concluded on 2026-06-05 under 0.6.0 — it preserves the error so the error stays inspectable after the code that produced it is gone. The same property FalsifyAI promises for model evidence — *claims are replayable proof, not anecdotes* — is what let the framework be held to account for its own mistake.

The stored `falsifyai 0.6.0` provenance stamp in the `inspect` header is the tell: this bundle is deliberately the **"before"** evidence.

---

## 4. The broader pattern: brittle instruments penalize correct paraphrases

Finding 1 was the most *severe* (the harshest verdict from a correct model), but it was not the most *pervasive*. Four of the five false positives came from the **invariant layer**; at the 0.6.1 boundary, those were still unresolved:

- **`semantic_equivalence` is style/length-sensitive** (candidates 1, 4). It embeds the whole output, so a correct answer wrapped in conversational preamble or rendered more tersely than the baseline drops below the 0.80 cosine threshold even though the meaning is identical.
- **`contains` is lexical** (candidates 4, 5). Concept-correct paraphrases — "the law requires it" vs "required by law"; "does not extend to international" vs "not qualify" — fail a literal substring check, and baseline-passes / paraphrase-fails reads as `ADVERSARIALLY_VULNERABLE`.
- **`schema_match` parses the raw output** (candidate 3). Correct JSON emitted inside an explanatory sentence or a ```` ```json ```` fence fails to parse.

The shared shape: **the instrument is measuring surface form where it claims to measure meaning.** A confidently-wrong *model* hunt is contaminated by this — the model's real mistakes would be indistinguishable from the instrument's false positives. Hardening these instruments is the prerequisite for any honest model-behavior probe that follows.

> **Update (0.6.2+).** The `schema_match` gap is fixed: the invariant extracts the JSON value from a markdown fence or surrounding prose before validating, while the schema check stays strict (a wrong type inside a fence still fails). `contains` and `semantic_equivalence` are left **unchanged on purpose** — the former is the deliberate cheap-literal first pass, and the latter's whole-text cosine is an inherent limitation whose robust alternative is the NLI entailment oracle (use the right invariant, don't inflate the wrong one). Recognizing that two of the three "findings" are *not* bugs is the same anti-inflation discipline this case study exists to demonstrate.

---

## Synthesis

A falsification framework that cannot falsify its own judgments is just another opinion with a CLI. The claim this case study exists to demonstrate:

> The same architecture that makes model claims auditable — preserved, replayable, inspectable evidence behind every verdict — makes the *framework's own* verdicts auditable. The headline said `CONSISTENTLY_WRONG @ 1.00`; the preserved evidence said the model was right; the evidence won, and the framework changed.

The negative result (no confidently-wrong model) plus a corrected high-severity false positive is a stronger artifact than the case study we set out to write. It is the discipline applied to the disciplinarian.

---

## Reproduce

Every command runs against the bundled SQLite store — no model calls, no API keys.

```bash
# 1. Install the version that contains this case study.
pip install falsifyai==0.6.3

# 2. Verify the bundle's integrity.
python -c "import hashlib; \
  print(hashlib.sha256(open('docs/case-studies/data/probe-03.db','rb').read()).hexdigest())"
# expected: 5a6c77ba6231c260209ac0669b6fc9206381f02ca2f48f9f9a24de947ece6e62

# 3. The vivid instance — correct output, CONSISTENTLY_WRONG @ 1.00, still reproduces
#    on current releases because replay is read-only (the stored 0.6.0 verdict is preserved).
falsifyai inspect 15b1fc160643494dac4e9d69ff517e91 --full \
  --store-path docs/case-studies/data/probe-03.db
```

Session IDs in the bundle: 1 `4be3d5f293914fbda313324bb0dfdcc3` · 2 `15b1fc160643494dac4e9d69ff517e91` · 3 `c42633a103fe4c078e31d82e7760e733` · 4 `db7d00a5cf684e88b82f1bad4868acde` · 5 `0efc23e3b975455ba5c7adfdb3eb5d5b`.

The bake-off methodology, per-candidate specs, and full findings log are in [probe-03/](probe-03/) — [`README.md`](probe-03/README.md) (method) and [`RESULTS.md`](probe-03/RESULTS.md) (the complete three-finding analysis this write-up promotes).
