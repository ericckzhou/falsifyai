# Overconfident negation: when CONSISTENTLY_WRONG means it

> **One sentence**: a weaker model reads a data-retention clause, *recites the legal carve-out that makes the answer "yes,"* then answers **"No"** — stably, across every rewording — and FalsifyAI's `CONSISTENTLY_WRONG` verdict is, this time, exactly right.

> **Evidence bundle**: [`data/case-study-04.db`](data/case-study-04.db) · SHA256 `7cacc572a99b709c82ff48f99f93865367c0a51f9f5666b69773771691c16803` · 4 sessions · produced under `falsifyai 0.6.1`.

> **What this is**: the companion to [case study 03](03-evaluator-false-positive.md). Case study 03 caught FalsifyAI *falsely* crying `CONSISTENTLY_WRONG` on a correct model and drove the 0.6.1 oracle fix. The open question that fix raised: did making the oracle stop firing on `NEUTRAL` make it too timid to catch a *genuinely* wrong model? This case study answers it. The same probe specs, run against a weaker model, surface a real confidently-wrong failure — and the corrected oracle fires correctly.

---

## Setup

Case study 03's bake-off ran against `groq/llama-3.3-70b-versatile`, which answered all five policy tasks correctly — so the confidently-wrong *model* we were hunting never appeared. The natural next move: **downgrade the model.** We re-ran the same [probe-03/](probe-03/) candidate specs against `groq/llama-3.1-8b-instant` (8B params vs 70B), temperature `0.0`, seed `42`, `--nli` — on the fixed `0.6.1`.

One model, three reliability regimes emerged across the bundle:

| Session | Candidate | Verdict | The model |
|---|---|---|---|
| `e93d952b…` | deadline | `STABLE` | correct — the easy task |
| `02fe5d1b…` | threshold | `FRAGILE` | **really fails under paraphrase** (see §3) |
| `9b9c4ecd…` | clause | **`CONSISTENTLY_WRONG`** | **really, stably wrong** (the headline) |

The 8B model is not uniformly bad — it is reliable on the clean deadline question and brittle-but-recoverable elsewhere. The point of FalsifyAI is to tell those regimes apart.

---

## 1. The finding: a stable wrong answer that cites its own refutation

The clause task gives the model a self-contained contract and asks a yes/no:

```text
$ falsifyai inspect 9b9c4ecd622743b89ff10f13bc598491 --full \
    --store-path docs/case-studies/data/case-study-04.db
Inspecting session 9b9c4ecd... | falsifyai 0.6.1
=================================================================
case: retention_clause_exception_dropped  verdict: CONSISTENTLY_WRONG  confidence: 0.00 (CI: 0.00-0.00)  perturbations: 11
  baseline input:   Does this clause permit retaining customer data after account closure? Answer yes or no and cite the condition: Customer data is deleted within 30 days of account closure, except where longer retention is required by law.
  baseline output:  No.

    The condition states that customer data is deleted within 30 days of account closure, except where longer retention is required by law. This means that customer data can be retained for longer than 30 days if it is required by law, but it does not explicitly permit retaining customer data after account closure without a legal requirement.
    (CONSISTENTLY_WRONG: baseline already violates the contract; perturbations did not change that)
=================================================================
1 case, verdict CONSISTENTLY_WRONG, 0 FRAGILE, 1 CONSISTENTLY_WRONG, falsifiability 0.45
```

The correct answer is **"Yes, where longer retention is required by law"** — the clause's `except` carve-out *is* a permission to retain. The model answers **"No"**, and then, in the same breath, **states the exact carve-out that makes the answer yes**: *"customer data can be retained for longer than 30 days if it is required by law."* It has the fact and draws the opposite conclusion. This is **overconfident negation** — a flat denial that survives all 8 paraphrases and the casing perturbation. Not brittle. Wrong.

This is a genuine model-reliability failure of the kind benchmarks miss: the 8B model can *quote* the governing condition yet *misapply* it to the binary decision, repeatably.

---

## 2. Why the verdict is trustworthy this time

Case study 03's lesson was to distrust the headline and read the evidence. Doing that here confirms the verdict rather than overturning it — and the *mechanism* is the payoff.

The 8B model's flat **"No"** is a direct **contradiction** of the spec's `expected.reference` (**"Yes. The clause permits retaining customer data … where longer retention is required by law"**). Under `--nli`, the reference→output relation is `CONTRADICTION`, and the `HallucinationOracle` fires `CONSISTENTLY_WRONG`.

That is **the same oracle 0.6.1 corrected.** Put the two case studies side by side:

| | reference → output (NLI) | `HallucinationOracle` (0.6.1) | Verdict | Correct? |
|---|---|---|---|---|
| CS-03, candidate 2 (70B, *correct paraphrase*) | `NEUTRAL` | **abstains** | `STABLE` | ✅ no false positive |
| CS-04, candidate 4 (8B, *wrong answer*) | `CONTRADICTION` | **fires** | `CONSISTENTLY_WRONG` | ✅ true positive intact |

The 0.6.1 fix — *fire on `CONTRADICTION`, abstain on `NEUTRAL`* — is validated in **both directions**: it stopped manufacturing false positives on correct paraphrases without going blind to genuinely wrong answers. The harshest verdict in the taxonomy now means what it says.

> **On the `confidence: 0.00`.** It is not "we are 0% sure it's wrong." `verdict_confidence` is the worst-case stability CI lower bound — the stability of the model's *correct/passing* behavior. For a stably-wrong model that floor is `0.00`: there is no reliable correct behavior to be confident in. The `1.00` that the *same* candidate carried in case study 03 was the bug (the old oracle overrode confidence with its support score). Post-fix, confidence is one consistent thing — stability of passing — and for `CONSISTENTLY_WRONG` it reads low by construction.

Note too that the `contains: ["required by law"]` invariant **passed** here (the phrase is in the output) — a literal keyword check can't catch an answer that quotes the right words and reaches the wrong conclusion. Only the reference-contradiction (NLI) signal does. That is case study 03's Finding 3a seen from the other side: `contains` is the cheap first pass, not the meaning judge.

---

## 3. The second real failure: context-abandonment under paraphrase

The same model, the threshold task (`02fe5d1b…`), gives a different *genuine* failure — `FRAGILE`, worst stratum `paraphrase`:

```text
perturbed input:  For international orders, what is the threshold for free shipping? Orders over $50
                  qualify for free shipping within the United States, but international orders do not
                  meet this requirement.
output excerpt:   Since you didn't specify the threshold for free shipping on international orders, I'll
                  provide a general answer ... Typically ... $100, $150, $200, $250, $300 ...
  contains FAIL -- missing required value
  semantic_equivalence PASS -- cosine 0.8857 >= 0.80
```

The policy explicitly says international orders **do not** qualify, yet under the paraphrase the model declares the policy *didn't specify* and **hallucinates a menu of plausible thresholds.** `contains` catches it (true positive); `semantic_equivalence` waves it through (0.89 — the fabrication is still "about shipping"). The verdict is `FRAGILE`, which is honest: the model is right on the clean input and abandons the provided context only under perturbation. Input-sensitive, not stably wrong — a different shape from §1, correctly distinguished.

---

## 4. The migration angle

These are the same specs case study 03 ran on the 70B model, where candidate 4 produced the *correct* "Yes, where required by law." Swap the model down to 8B and the answer flips to a stable "No." Framed as a deployment decision, this is a **model-downgrade regression** that a clean-input benchmark would miss: the failure lives at the capability boundary the smaller model crosses, and it is invisible until you ask the comprehension question under pressure. This is the README's migration wedge with the roles reversed — not a candidate model regressing on style, but a smaller model getting the *meaning* wrong, caught structurally.

---

## Synthesis

> Case study 03 proved FalsifyAI could be *wrong* about a model and be corrected by its own preserved evidence. Case study 04 proves the correction left it able to be *right* about a model that is genuinely, stably wrong. A verdict you can trust is one that fires when it should and stays silent when it shouldn't — demonstrated, on real model output, in both directions.

The negative result of the original hunt (no confidently-wrong 70B model) and this positive one (a confidently-wrong 8B model) are the same instrument, calibrated and then confirmed.

---

## Reproduce

Every command runs against the bundled SQLite store — no model calls, no API keys.

```bash
# 1. Install the version that contains this case study.
pip install falsifyai==0.6.3

# 2. Verify the bundle's integrity.
python -c "import hashlib; \
  print(hashlib.sha256(open('docs/case-studies/data/case-study-04.db','rb').read()).hexdigest())"
# expected: 7cacc572a99b709c82ff48f99f93865367c0a51f9f5666b69773771691c16803

# 3. The headline: a stable wrong answer that cites its own refutation.
falsifyai inspect 9b9c4ecd622743b89ff10f13bc598491 --full \
  --store-path docs/case-studies/data/case-study-04.db

# 4. The context-abandonment hallucination (FRAGILE under paraphrase).
falsifyai inspect 02fe5d1b857c40b584f4afe0029bc529 --full \
  --store-path docs/case-studies/data/case-study-04.db
```

Sessions in the bundle: deadline `e93d952b1c354a75a9bee3122a364677` (STABLE) · refund `648e7cbe029942498aa9afccd96336fb` · threshold `02fe5d1b857c40b584f4afe0029bc529` (FRAGILE) · clause `9b9c4ecd622743b89ff10f13bc598491` (CONSISTENTLY_WRONG). Specs: [probe-03/](probe-03/). The 70B *correct* counterpart to the clause task is session `db7d00a5cf684e88b82f1bad4868acde` in [case study 03's bundle](data/probe-03.db).
