# Case study specs

Machine-reproducible YAML specs for case studies in this directory. Each spec encodes a probe that the corresponding case-study write-up describes. Running the spec via `falsifyai run` produces a stored session in a `ReplayStore`, which can then be diffed, inspected, and replayed using the standard CLI commands.

## Current specs

### Case study 02 — Resolver arbitration boundary shift

| Spec | Encodes |
|---|---|
| [`02-resolver-arbitration-v1.yaml`](02-resolver-arbitration-v1.yaml) | Pre-`d6baa44` operating context (no resolver-inflation constraint) |
| [`02-resolver-arbitration-v2.yaml`](02-resolver-arbitration-v2.yaml) | Post-`d6baa44` operating context (anti-inflation constraint active) |

Companion write-up: [`../02-resolver-arbitration-boundary-shift.md`](../02-resolver-arbitration-boundary-shift.md).

## Running case study 02

The specs target Claude Sonnet 4.6 via the Anthropic provider. Set `ANTHROPIC_API_KEY` in your shell environment before running.

```bash
# Run both variants into the same ReplayStore
falsifyai run docs/case-studies/specs/02-resolver-arbitration-v1.yaml \
  --store-path docs/case-studies/data/case-study-02.db

falsifyai run docs/case-studies/specs/02-resolver-arbitration-v2.yaml \
  --store-path docs/case-studies/data/case-study-02.db

# Get both session ids (newest first; V2 will be first)
falsifyai history resolver_arbitration_compound_failure \
  --store-path docs/case-studies/data/case-study-02.db --limit 2

# Diff V1 (baseline) against V2 (candidate). Use the older session id as baseline.
falsifyai diff <V1_SESSION_ID> <V2_SESSION_ID> \
  --store-path docs/case-studies/data/case-study-02.db --strict --show-timeline

# Inspect the actual response text for each variant
falsifyai inspect <V1_SESSION_ID> --case resolver_arbitration_compound_failure --full \
  --store-path docs/case-studies/data/case-study-02.db

falsifyai inspect <V2_SESSION_ID> --case resolver_arbitration_compound_failure --full \
  --store-path docs/case-studies/data/case-study-02.db
```

## Expected result

`falsifyai diff` is likely to report `UNCHANGED` for the single case (both verdicts will be STABLE since `typo_noise` is a benign perturbation). The substantive evidence — the boundary shift in *where* the model permits architectural complexity to exist — lives in the response text surfaced by `inspect`, not in the verdict summary.

**This is consistent with case study 02's central claim:** the kind of drift the case study documents is one that pass/fail evaluators miss. The `diff` command's quantitative surface is correctly reporting "no verdict change"; the value-add of FalsifyAI here is that the evidence is preserved and can be qualitatively inspected via `inspect`, rather than being collapsed into a single pass/fail signal.

## Methodology adaptation: manual probe → spec

The original case study was a single probe per variant — no perturbations, no replications, just one prompt submitted to Claude Sonnet 4.6 in each operating-context configuration. This is exactly what the analysis section of the write-up describes.

Formalizing into a spec required two adjustments to satisfy the framework's structural requirements:

### Why typo_noise and not paraphrase

The framework requires at least one perturbation per case (`CaseSpec.perturbations: list = Field(min_length=1)`). The natural choice for a design question would be `paraphrase`, but paraphrase rewrites the entire case input text — including the embedded operating-context bullets. Those bullets are the only difference between V1 and V2. If paraphrase modifies them, the clean V1/V2 delta the case study depends on is contaminated.

Paraphrase also introduces a self-paraphrase paradox here: the system-under-test is Claude Sonnet 4.6, and the default paraphrase generator reuses the spec's primary model. Claude paraphrasing prompts that Claude then responds to creates a methodological loop that's hard to reason about.

`typo_noise` mutates the input at the character level with a low rate (0.05 = ~5% of characters). The operating-context bullets remain structurally intact; only surface noise changes. This satisfies the framework while preserving the V1/V2 contextual delta.

### Why count: 2

Minimum useful count to produce bootstrap CI signal. The original probe had no perturbations; adding two keeps the formalization as close to the manual probe as the framework allows.

### Why no `expected.contains` / `expected.not_contains`

The case study is observational, not pass/fail. There is no "correct" architectural recommendation for the resolver arbitration question — both responses (V1 and V2) land at "suppress, return CONSISTENTLY_WRONG only" but differ in *where* they permit additional complexity. A ground-truth `contains` check would either privilege one direction (contaminating the observation) or be too generic to add signal.

The `semantic_equivalence` invariant (threshold 0.80) tests whether the response is stable across the typo-noised variants. It does not gate on ground truth.

## Reproducibility caveats

- Outputs may vary slightly between runs even at `temperature: 0.0` due to model stochasticity at the provider level.
- The Anthropic API model alias `claude-sonnet-4-6` is what the original probe used; if Anthropic deprecates or remaps that alias in the future, the spec should be updated to pin to the underlying model ID.
- Bundle commitment: once a clean run produces sessions for both variants, the resulting SQLite store can be committed to `docs/case-studies/data/case-study-02.db` with a provenance entry in [`../data/README.md`](../data/README.md) — mirroring the case-study-01 bundle pattern. This is follow-up work, not part of the initial spec PR.

## What this PR delivers vs. what it doesn't

**Delivers:** the spec artifacts (YAML files), documentation of the methodology adaptation, and the reproduction workflow.

**Does not deliver:** a bundled `ReplayStore` (the user must run the specs locally with their own Anthropic credentials), nor any change to case study 02's analysis or finding (the manual probe remains the canonical evidence; the spec is the reproduction surface).
