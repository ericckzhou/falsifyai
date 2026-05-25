# The Evidence Gap

> Capability scores tell you whether a model *can* do something.
> Reliability evidence tells you whether it *kept doing it* under realistic pressure.
> Production failures answer the second question.

---

## 1. The shape of a capability score

HumanEval, MMLU, MT-Bench, G-Eval, pass@k, and the rest of the modern eval stack share a structure: take a fixed benchmark, run the model against it, return a number. That number is a **capability snapshot** — a useful answer to *"can this model, today, on this curated set of inputs, produce outputs that satisfy this scoring function?"*

What gets preserved at the end of a run:

- A score (a float, a percentile, or a leaderboard row)
- Optionally, a per-task breakdown

What gets discarded:

- The exact inputs the model was given (often gone the moment the run completes)
- The exact outputs the model produced
- The judgments that converted those outputs into pass/fail
- Any evidence of *how close* the model came to failing

The score survives. The evidence that produced the score usually does not.

---

## 2. Three production failure modes a capability score doesn't catch

Each of the three below points at a real artifact in this repository's [case-study replay store](case-studies/data/case-study-replays.db). Every claim is reproducible.

### Silent regression under model migration

You switch providers. CI re-runs the eval suite. Both runs pass. A week later, a customer flags a wrong refund summary. The eval suite, re-run by hand, still passes — but the model's actual behavior has drifted on a contract the eval doesn't probe.

In FalsifyAI session `4332c0d246bc4b3e875392ecdf3b1780`, the candidate model's `policy_summary` output drifted under a `typo_noise` perturbation the baseline shrugged off. The artifact preserves the perturbed input verbatim, the model's output containing a U+202F (narrow no-break space) between `"30"` and `"days"`, and the `contains: ["30 days", ...]` invariant's `FAIL — missing 1 of 3 required values` judgment. The diff against the baseline session emits exit code 5. See [case study 01](case-studies/01-invisible-character-substitution.md).

A capability score would have shown both models at 100% on this case.

### Stable verdict, shifted behavior

A model's top-level recommendation stays the same across a benign context revision, but the *shape* of the reasoning shifts — where the model permits complexity to live, how it allocates trust between layers, what it deprioritizes. A pass/fail evaluator scores both responses as passing because the surface-level answer is unchanged.

[Case study 02](case-studies/02-resolver-arbitration-boundary-shift.md) preserves two such sessions and walks through the *boundary-allocation effect* — the kind of subtle drift that pass/fail scoring is structurally unable to surface.

### Faded evidence

The most common production failure mode: a customer reports a bad output a week after it happened. The eval still passes when re-run. The original bad output cannot be reproduced, because stochastic systems don't produce stable failures — they produce drift. You have nothing to point at.

Capability scoring is designed around the assumption that running the eval *again* answers the question. For stochastic systems that's a false assumption — *the run* is the question.

---

## 3. What reliability evidence preserves

A FalsifyAI replay artifact preserves, per run:

- **Perturbed inputs** — verbatim, byte-identical
- **Model outputs** — raw, no post-processing, every character including invisibles
- **Invariant judgments** — pass/fail per invariant per output, with evidence strings
- **The verdict** — assigned at run time by a deterministic priority chain, never re-resolved on read
- **Provenance** — `spec_hash`, `materialized_hash`, `falsifyai_version`, `cli_invocation`, and a deterministic content-addressed `bundle_id`

Six months later, with only the artifact and the FalsifyAI version that produced it, anyone can re-open the run, see exactly what the model did, and decide whether it still matters. The full protocol semantics live in [`EVIDENCE.md`](EVIDENCE.md).

---

## 4. Why this is a category gap, not a feature gap

The gap is **temporal**.

Capability scores survive. The evidence that produced them usually does not.

This is the same structural problem other engineering categories already solved by inventing an evidence layer to sit alongside the metric:

| Domain | Metric / signal | Evidence layer |
|---|---|---|
| Software supply chain | "the build succeeded" | **SBOM** (CycloneDX, SPDX) |
| Static analysis | "0 errors" | **SARIF** |
| Build provenance | "released by CI" | **Sigstore / in-toto** |
| Distributed systems | "latency p95 = 200ms" | **OpenTelemetry traces** |
| **Stochastic systems** | **"eval score = 0.87"** | **FalsifyAI replay artifact** |

In each row, both columns are useful. The metric tells you *whether to look*; the evidence tells you *what to look at*. Neither replaces the other. The novelty FalsifyAI proposes isn't that we preserve evidence — many tools do — it's *what* we preserve about stochastic-system behavior, and what guarantees we make about its persistence.

A capability score is to a FalsifyAI artifact what a unit-test pass count is to an SBOM: a useful summary that doesn't, by itself, support the operational claims people want to make from it.

---

## 5. What this is not

The Evidence Gap is not a critique of capability scoring. Capability scoring answers capability questions — *"is this model good at code?"*, *"is it competitive with last year's model on factual recall?"* — and the leaderboards do that job well. FalsifyAI doesn't replace HumanEval; it answers the orthogonal question: *"did this specific contract hold up under realistic pressure, and do we still have the evidence?"*

Two questions, two evidence shapes, two preservation models.

The argument is not *"throw away your evals."* It's *"the evidence you'd want a week after the regression is the evidence the score discards."* If that asymmetry matters for your production use case, the gap is worth closing — and the close is structural, not incremental.

---

## See also

- [`README.md`](../README.md) — what FalsifyAI actually does, with verbatim-captured terminal output
- [`EVIDENCE.md`](EVIDENCE.md) — the replay artifact protocol: what it preserves, what guarantees it makes, what the verdicts mean as claims
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — three-layer separation (generation / interpretation / preservation) and why the artifact is the central object
- [`case-studies/`](case-studies/) — worked tours over the bundled replay artifacts referenced in §2
- [`COMPLIANCE.md`](COMPLIANCE.md) — EU AI Act Annex IV §2(g) field-by-field mapping
