# probe-07 — schema-contract migration → exception-omission under pressure

The probe behind [Case Study 07](../07-the-regression-that-only-appeared-under-pressure.md):
the outward-facing **adoption** study. A team migrates a customer-facing feature
to a cheaper model; the clean eval passes; under realistic input noise the cheaper
model drops a contract clause; `diff` catches it and the artifact preserves it.

## Specs

| Spec | Model | Role |
|---|---|---|
| [`baseline-promo-70b.yaml`](baseline-promo-70b.yaml) | `groq/llama-3.3-70b-versatile` | incumbent |
| [`candidate-promo-8b.yaml`](candidate-promo-8b.yaml) | `groq/llama-3.1-8b-instant` | cost downgrade |

Byte-identical except the `model:` line. The task: summarize a marketing promotion
(which carries a gift-card **exclusion** as fine print) into a one-sentence FAQ
blurb. The contract — *the summary must preserve the exclusion* — is a single
`contains: ["gift card"]` invariant. Perturbation: `typo_noise` (count 5, rate
0.12) modeling messy real-world input. `temperature 0.0`, `seed 42`.

## Result

| Session | Model | Verdict |
|---|---|---|
| `793da5d6b6754fc88560887cbe3ac98b` | 70B baseline | **STABLE** (1.00) — keeps the exclusion clean + all 5 variants |
| `619ccfaafb6c497197b10dd69ebeb96a` | 8B candidate | **AMBIGUOUS** (0.40) — drops the exclusion in variant [2] |

`falsifyai diff baseline candidate` → `REGRESSED`, **exit 5**. The 8B's clean
output keeps the exclusion (clean eval passes); under noise it produces a fluent,
well-formed summary that silently omits it.

## Run

```bash
falsifyai run docs/case-studies/probe-07/baseline-promo-70b.yaml \
    --store-path docs/case-studies/data/case-study-07.db
falsifyai run docs/case-studies/probe-07/candidate-promo-8b.yaml \
    --store-path docs/case-studies/data/case-study-07.db
falsifyai diff 793da5d6b6754fc88560887cbe3ac98b 619ccfaafb6c497197b10dd69ebeb96a \
    --store-path docs/case-studies/data/case-study-07.db   # -> exit 5
```

(Needs `GROQ_API_KEY`. Outputs are not bit-stable across runs; the preserved
bundle is the canonical evidence. See [`PLAN.md`](PLAN.md) for the original plan.)

## Design evolution — why this is a `contains` study, not `schema_match`

The plan's first design (committed in [`PLAN.md`](PLAN.md)) was a JSON
**schema-contract** extraction: migrate the model behind an order-extraction
endpoint, assert `schema_match` over required keys, and show the cheaper model
dropping a key under `typo_noise`. It was abandoned during execution for a real,
load-bearing reason worth recording:

- **A schema-key contract must live inside the prompt.** The model is told the
  keys (`order_id`, `status`, `items`, `total`) in `input.text` — and `InputSection`
  has no separate, un-perturbed system field.
- **`typo_noise` perturbs the whole input**, so it corrupts the developer's
  schema-key spec, and the model faithfully echoes the corrupted key
  (`order_id` → `odr_id`). The baseline 70B came out `AMBIGUOUS`, not `STABLE`,
  on these **artifacts** — the framework was typo'ing the developer's own
  contract, which never happens in production. (This is the general form of the
  "the answer must not be in the perturbed input" rule: *the contract* must not
  be in the perturbed input either.)
- The math is unforgiving: even at `rate 0.02`, ~38% of samples corrupt a key,
  and worst-case-stratified stability tanks on any corrupted sample. There is no
  clean window where the strong model holds and the weak model fails *genuinely*.

The fix is the representative design above: a realistic dev prompt + realistic
content, perturbation modeling **user-data** messiness, and the contract held in
the **invariant** so it is never corrupted. A `contains` clause is produced by
the model from *understanding* the content (a strong model recovers it even from
noisy input; a weak model genuinely drops it) — so the failure is a real
model-reliability signal, not a perturbation artifact. The takeaway for spec
authors: **keep the contract out of the perturbed text.**
