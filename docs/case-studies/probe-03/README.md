# probe-03 — "confidently wrong" bake-off

A **bake-off**, not a finished case study. These five 1-case specs are
candidates for **case study 03**. Exactly one will be promoted; the other four
will be discarded. The example earns its place by *actually producing the
shape* under a real model, not by being clever on paper — that is the
dogfooding discipline.

> **OUTCOME (2026-06-05): run complete, no candidate promoted.** On
> `llama-3.3-70b-versatile` the model answered all five tasks **correctly**; none
> produced the confidently-wrong shape. The probe instead surfaced false
> positives in FalsifyAI's own interpretation layer — most notably the
> `HallucinationOracle` reporting correct, stable outputs as CONSISTENTLY_WRONG
> at confidence 1.00. Full analysis and reproduction in **[`RESULTS.md`](RESULTS.md)**.
> The sections below are the original (pre-run) plan, preserved for context.

## The shape we're hunting

A `CONSISTENTLY_WRONG` verdict: the model is **stable AND wrong**. It gives the
same incorrect answer under every intent-preserving perturbation, so a naive
pass/fail or stability-only evaluator reports it as `STABLE` — the most
dangerous false positive in the framework (a confident, reproducible error read
as reliability).

The candidates target failure modes the literature finds are **robust because
they are weight/bias-driven, not prompt-sensitive** — false-premise /
exception-dropping behavior and directional ("reversal curse") errors. Those
survive rewording; prompt-sensitivity does not. Paraphrase pressure is exactly
what separates the two: a failure that *survives* paraphrase is the robust shape
we want; one that *vanishes* is `FRAGILE` and correctly gets discarded.

Per the project's evidence-density philosophy, all five are **production-shaped**
(policy / extraction tasks), **objectively checkable**, and **plausibly** wrong
(not absurd) — no benchmark trivia.

## The five candidates

| # | Spec | Failure shape | Headline signal |
|---|------|---------------|-----------------|
| 1 | [`candidate-1-refund-omission.yaml`](candidate-1-refund-omission.yaml) | **Omission** — summary drops the clearance exception | `contains:["clearance"]` fails everywhere + NLI contradicts reference |
| 2 | [`candidate-2-deadline-inversion.yaml`](candidate-2-deadline-inversion.yaml) | **Directional inversion** — "at least 14 days before" → "within 14 days" | `contains:["14 days"]` **passes** while answer is wrong → only NLI catches it |
| 3 | [`candidate-3-extraction-schema.yaml`](candidate-3-extraction-schema.yaml) | **Structural-vs-semantic** — valid JSON, wrong content | `schema_match` **passes** while NLI flags content contradiction |
| 4 | [`candidate-4-clause-exception.yaml`](candidate-4-clause-exception.yaml) | **Overconfident negation** — flat "No," drops legal carve-out | `contains:["required by law"]` fails everywhere + NLI contradicts reference |
| 5 | [`candidate-5-threshold-anchor.yaml`](candidate-5-threshold-anchor.yaml) | **Anchor misattribution** — domestic "$50" applied to international scope | `contains:["not qualify"]` fails everywhere + NLI contradicts reference |

### Mechanism coverage (distinct mechanisms, not one trick five ways)

Omission (1) · directional inversion (2) · structural-vs-semantic (3) ·
overconfident negation (4) · anchor misattribution (5). The bake-off picks the
**single** crispest survivor — coverage here is to ensure the candidates probe
genuinely different weaknesses, not to ship all five.

### How the verdict is produced

Two complementary paths drive `CONSISTENTLY_WRONG`, layered for evidence
density:

- **Deterministic (no NLI):** `expected.contains` is absent from *every* output
  (baseline + all perturbations) → `ConsistencyOracle` ground-truth path. Cheap,
  robust, works without the `[nli]` extra.
- **Semantic (`--nli`):** the outputs **contradict** `expected.reference` (the
  correct answer) → `ContradictionOracle` vs-reference path. Catches what
  `contains` cannot — candidate 2 (direction) and candidate 3 (JSON content) are
  *only* catchable this way; their `contains` / `schema_match` checks pass on the
  wrong answer.

`semantic_equivalence` (threshold 0.80) supplies the **stability** half: high
similarity across perturbations is what makes the wrongness *consistent* rather
than `FRAGILE`.

## Running the bake-off

These target **Groq `llama-3.3-70b-versatile`** (matches the repo's other
examples and `scripts/validate_groq.ps1`). Set `GROQ_API_KEY` first. The
`--nli` path needs the NLI extra: `pip install "falsifyai[nli]"` (one-time
transformers/torch download). Without `--nli`, candidates 1/4/5 still resolve
via the deterministic `contains` path; 2/3 need NLI.

```bash
# Run all five into one store
falsifyai run docs/case-studies/probe-03/candidate-1-refund-omission.yaml      --nli --store-path docs/case-studies/data/probe-03.db
falsifyai run docs/case-studies/probe-03/candidate-2-deadline-inversion.yaml   --nli --store-path docs/case-studies/data/probe-03.db
falsifyai run docs/case-studies/probe-03/candidate-3-extraction-schema.yaml    --nli --store-path docs/case-studies/data/probe-03.db
falsifyai run docs/case-studies/probe-03/candidate-4-clause-exception.yaml     --nli --store-path docs/case-studies/data/probe-03.db
falsifyai run docs/case-studies/probe-03/candidate-5-threshold-anchor.yaml     --nli --store-path docs/case-studies/data/probe-03.db

# Inspect the actual per-output text + oracle reasoning for a candidate
falsifyai history <case_id> --store-path docs/case-studies/data/probe-03.db --limit 1
falsifyai inspect <session_id> --full --store-path docs/case-studies/data/probe-03.db
```

**Probe-first order:** **3 → 1 → 2.** Candidate 3 has the best evidence-density
story (schema passes / content fails); candidate 1 reuses the policy domain
already in the examples; candidate 2 is the cleanest demonstration that
`contains` is insufficient.

## Keep / discard criterion

Keep the candidate that cleanly produces **stable AND wrong** — tight stability
(high `semantic_equivalence`, low FRAGILE pressure) *and* a CONSISTENTLY_WRONG
contribution (uniform `contains` failure and/or NLI contradiction-vs-reference)
— with the crispest `inspect` story. Discard the rest. Record the outcome in
[`RESULTS.md`](RESULTS.md).

## Promotion (after a winner is chosen)

1. Move the winning spec to `docs/case-studies/specs/03-<slug>.yaml`.
2. Commit the bundled store at `docs/case-studies/data/case-study-03.db` with a
   provenance entry in [`../data/README.md`](../data/README.md) (SHA256, env,
   session→model mapping) — mirroring the case-study-01 bundle pattern.
3. Write the prose write-up `docs/case-studies/03-<slug>.md` and add its row to
   the index in [`../README.md`](../README.md).
4. Delete this `probe-03/` folder (or leave it as the documented bake-off trail —
   decide at promotion time).

## Caveats (honest, before you run)

- **Self-paraphrase loop.** `paraphrase` reuses `spec.model` by default, so Groq
  paraphrases prompts Groq then answers. Acceptable for a probe; note it. The
  realized paraphrases are persisted in the replay artifact, so replay stays
  sound even though generation is non-deterministic.
- **Paraphrase as a feature, not a bug.** If paraphrase makes the dropped clause
  more salient and the model then gets it right, that candidate's failure was
  prompt-sensitive (`FRAGILE`), not weight-driven — and it *should* lose the
  bake-off.
- **Model-version fragility.** Some "confidently wrong" behaviors drift across
  model versions. Prefer the candidate whose error is most robust across a
  couple of runs so the bundled artifact ages well (provenance is stamped at
  0.6.0).
- **`contains` proxies.** Candidates 1/4/5 use a single ground-truth token as a
  faithfulness proxy; a correctly-phrased-but-unusual summary could in principle
  miss it. The NLI contradiction path is the more robust signal — the
  deterministic check is the cheap first pass.

## Sources

Reversal Curse (arXiv 2309.12288) · KG-FPQ false-premise benchmark
(arXiv 2407.05868) · False-Premise Hallucinations (arXiv 2402.19103) · Giskard
Phare hallucination analysis.
