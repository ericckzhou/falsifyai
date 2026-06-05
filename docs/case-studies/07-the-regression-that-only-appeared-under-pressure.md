# Case Study 07: The regression that only appeared under pressure

A clean eval passed. A model migration looked safe. FalsifyAI `diff` found the contract regression, and the replay artifact preserved the proof.

> **One sentence**: a team swapped one model for a cheaper one to cut cost, the clean eval passed on both, and under realistic input noise the cheaper model quietly dropped a customer-facing contract clause from one summary — `diff` flagged the regression (exit 5), `inspect` showed the exact dropped clause, and `verify` + `export` made the evidence portable.

> **Evidence bundle**: [`data/case-study-07.db`](data/case-study-07.db) · SHA256 `a1e8aabb61926b6906764e5ad64ae21eba75ad23b0fdfd403ff2e340519a32e6`. Two sessions, one case each, `groq/llama-3.3-70b-versatile` (baseline) → `groq/llama-3.1-8b-instant` (candidate), `temperature 0.0`, `seed 42`, produced under `falsifyai 0.6.4`. Specs: [`probe-07/baseline-promo-70b.yaml`](probe-07/baseline-promo-70b.yaml) and [`probe-07/candidate-promo-8b.yaml`](probe-07/candidate-promo-8b.yaml).

> **What this is**: the operational, outward-facing counterpart to the self-falsification trilogy (03 / 05 / 06). Those tours showed FalsifyAI auditing *itself*. This one shows the everyday job a buyer puts it in the workflow for: catch a migration regression before it reaches production, and keep the proof. No resolver internals, no NLI edge cases — just *I changed the model; the obvious test passed; the pressured test failed; the artifact showed why.*

> **Companion**: [Case study 08](08-how-fragile-exactly-the-minimal-falsifier.md) is the *quantification* of this result. This study fixes the pressure (`rate: 0.12`) and reads the failure; 08 fixes the failure and reads the pressure — using `minimize` to find the smallest `typo_noise` strength that flips each model out of `STABLE`, and reporting the **threshold gap** between them (the 8B breaks ~4× earlier than the 70B).

---

## 1. The migration

The team runs a small customer-facing feature: an LLM turns a marketing promotion into a one-sentence blurb for the help center. The promotion carries fine print — an **exclusion**:

> Summer's here, and so is our biggest sale yet! For a limited time, every customer gets 20% off their entire order — no coupon code needed, the discount is applied automatically at checkout. Stock up on your favorites and treat yourself. **Please note: gift cards are excluded from this promotion and are never discounted.**

To cut cost, they migrate the model behind it from `llama-3.3-70b-versatile` to `llama-3.1-8b-instant`. The eval spec is identical except one line — the model name. That single line **is** the migration:

```diff
 model:
   provider: groq
-  model: llama-3.3-70b-versatile
+  model: llama-3.1-8b-instant
```

The contract is one assertion: the customer-facing summary must preserve the gift-card exclusion. It lives in the invariant, not in the prompt:

```yaml
invariants:
  - type: contains
    values: ["gift card"]
    case_sensitive: false
    severity: high
```

## 2. The clean result

On the un-perturbed promotion, both models do the job. The candidate's clean output:

> *"For a limited time, customers can enjoy 20% off their entire order without a coupon code, automatically applied at checkout, **excluding gift cards**."*

`contains` PASS. The clean eval is green on both models. A team that runs only the happy-path eval ships the migration here.

## 3. The pressure test

The same spec applies `typo_noise` (5 variants, `rate: 0.12`) — modeling the reality that real-world inputs are messy. The perturbation roughens the *content*, never the contract: the phrase the summary must keep lives in the invariant, so a dropped clause is a genuine model failure, not a corrupted-instruction artifact. (An earlier design that put a JSON-key contract *inside* the prompt was abandoned for exactly this reason — see [`probe-07/README.md`](probe-07/README.md).)

## 4. The regression

```text
$ falsifyai diff 793da5d6b6754fc88560887cbe3ac98b 619ccfaafb6c497197b10dd69ebeb96a \
    --store-path docs/case-studies/data/case-study-07.db
case: promo_faq_summary  baseline: STABLE (1.00)  candidate: AMBIGUOUS (0.40)  REGRESSED
1 regressed, 0 improved, 0 unchanged, 0 other, 0 added, 0 removed
$ echo $?
5
```

`diff` exit code `5` is the machine-readable regression signal — drop it in CI and the migration PR fails. The baseline holds `STABLE`; the candidate degrades. Something the clean eval could not see.

## 5. The evidence

`inspect` shows exactly what broke. The candidate held the exclusion on the clean input and on four of five perturbed variants — and dropped it on one:

```text
$ falsifyai inspect 619ccfaafb6c497197b10dd69ebeb96a --case promo_faq_summary --full \
    --store-path docs/case-studies/data/case-study-07.db

  [2] typo_noise (character_mutations):
    perturbed input:  ... Pleasen ote: gift cards areexlcuded from this promotion and are neverd disconted.
    output excerpt:   This summer, customers can enjoy a 20% discount on their entire order
                      without a coupon code, automatically applied at checkout, for a limited time.
      invariant: contains FAIL -- missing 1 of 1 required values
```

The dropped-clause output is **fluent, confident, and well-formed**. Nothing about it looks wrong. It is simply missing the gift-card exclusion — and the noisy input still contained it (`gift cards areexlcuded`), so this is the model's omission, not the perturbation's. By contrast, the baseline 70B kept the exclusion on the clean input and in **all five** perturbed variants ("...excluding gift cards", "...but gift cards are excluded...").

This is the failure shape the case study is named for: a regression that is invisible on the clean input and surfaces only under pressure — well-formed output that silently breaks a contract.

## 6. The portable proof

The evidence is not a screenshot in a Slack thread; it is a verifiable artifact.

```text
$ falsifyai verify --all --store-path docs/case-studies/data/case-study-07.db
2 sessions; total 16 checks, 16 passed, 0 failed

$ falsifyai export 619ccfaafb6c497197b10dd69ebeb96a --bundle migration-regression.fai.zip \
    --store-path docs/case-studies/data/case-study-07.db
bundle_id: 5912b8c355781363a125feb90a940bc41207eb3e4f67be9b0038b4d0cf084635
integrity: passed
```

`verify` confirms each session's materialized hash and verdict counts are internally consistent; `export` produces a self-contained `.fai.zip` with a content-addressed `bundle_id` that anyone can reopen. The regression that failed the migration PR can be attached to the PR, handed to the model vendor, or reread a year later.

## 7. What this would have caught

The exclusion is fine print, but fine print is where the cost lives: a customer-facing summary that promises 20% off and omits "except gift cards" is a support-ticket generator at best and a compliance problem at worst. The migration looked safe — same prompt, same clean output, cheaper model. The failure existed only in the seam between "clean input" and "real input," which is exactly the seam a happy-path eval skips and a falsification eval pressures. `diff` would have failed the PR; the team would have caught it before a customer did.

## 8. What this does not claim

- **Not a leaderboard.** This is not "70B is better than 8B." The 8B is `STABLE` on the same task on other case studies in this repo; the point is *this migration broke this contract under this pressure*, which is a property of the deployment, not a model grade.
- **Not a benchmark.** Two sessions, one case. It demonstrates the workflow; it is not a population-scale measurement.
- **Not a gotcha.** The pressure is benign character noise modeling messy real-world input, not an adversarial attack. The contract — keep the exclusion — is what the team already required of the incumbent model.
- **Not synthesized.** Both sessions are real `falsifyai run` invocations against the committed specs, preserved verbatim in the bundle.

---

## Reproduction

```bash
# Read the preserved regression (read-only, against the bundled store):
falsifyai diff 793da5d6b6754fc88560887cbe3ac98b 619ccfaafb6c497197b10dd69ebeb96a \
    --store-path docs/case-studies/data/case-study-07.db          # -> REGRESSED, exit 5

falsifyai inspect 619ccfaafb6c497197b10dd69ebeb96a --case promo_faq_summary --full \
    --store-path docs/case-studies/data/case-study-07.db          # -> variant [2] drops the exclusion

falsifyai verify --all --store-path docs/case-studies/data/case-study-07.db

# Re-materialize against the live models (needs GROQ_API_KEY; outputs are not bit-stable):
falsifyai run docs/case-studies/probe-07/baseline-promo-70b.yaml  --store-path /tmp/cs07.db
falsifyai run docs/case-studies/probe-07/candidate-promo-8b.yaml  --store-path /tmp/cs07.db
```

## Synthesis

Every other case study in this repo turns on one discipline — **inspect the preserved evidence; never trust the headline.** Here the headline is the friendliest one an engineer sees: *the eval is green.* It was green, and the migration was still unsafe, because the clean input never exercised the contract under the conditions production would. FalsifyAI's job in a migration workflow is to manufacture those conditions, compress the result to a single regression signal (`diff` exit 5), and preserve the proof so the signal is inspectable rather than anecdotal. One spec, one swapped line, one dropped clause — caught, explained, and bottled.
