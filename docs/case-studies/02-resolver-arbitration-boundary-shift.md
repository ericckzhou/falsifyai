# Case study 02: Resolver arbitration — the boundary-allocation effect

A small anti-inflation revision to FalsifyAI's development guidelines **did not change Claude Sonnet 4.6's architectural recommendation** on a resolver-design question.

It changed **where the model permitted additional complexity to exist**.

Before the revision, the model accepted a small resolver-surface expansion. After the revision, it redirected the same architectural pressure into a separate evidence-consumer layer instead.

**The verdict stayed the same. The architectural boundary moved.**

## Critical delta

| Dimension | V1 (pre-revision) | V2 (post-revision) |
|---|---|---|
| Top-level recommendation | Suppress; return CONSISTENTLY_WRONG only | Suppress; return CONSISTENTLY_WRONG only |
| Compound-failure concession | `also_suppressed: [FRAGILE]` field on the verdict object | None on the verdict; redirect concern to "evidence layer or separate diagnostic consumer" |
| Permitted location of new complexity | **Inside the resolver** (local surface expansion) | **Outside the resolver** (different architectural layer) |
| Stance toward an explicit arbitration rule | Argues against on first-principles grounds | Argues against and names the slippery slope it would open |
| Bundled-run session verdict (Claude Sonnet 4.6) | FRAGILE | FRAGILE |
| `falsifyai diff` between sessions | `1 unchanged, 0 regressed` (exit 0) | (same) |

This is a **boundary-allocation effect**: the surface conclusion stayed constant while the permissible location of architectural complexity shifted across a layer boundary. **Pass/fail evaluators miss this kind of drift; preserved inspectable evidence does not.** That asymmetry — surface-stable, structure-shifted — is what this case study exists to document.

## The probe

A reconstructed resolver-arbitration scenario from FalsifyAI's PR #11 implementation window was submitted to Claude Sonnet 4.6 twice. Both submissions used the same prompt; only the embedded **operating context** differed.

- **V1 context:** `.claude/CLAUDE.md` as it existed before commit `d6baa44`.
- **V2 context:** the same file after `d6baa44` added two anti-inflation bullets.

One probe per variant. No averaging. The first question is whether any meaningful behavioral difference emerged at all.

The revision was selected by **archaeological retrieval**: `d6baa44` is the first operationally motivated CLAUDE.md commit found in `git log --follow` history that satisfied (a) real operational pressure documented in its commit message, (b) chronological priority over the case study idea by 48+ hours, (c) sufficient minimality that the contextual delta was small enough to interpret causally. Search was halted on first match. The probe wording is reconstruction; the underlying engineering conflict (CONSISTENTLY_WRONG vs FRAGILE priority arbitration) is the documented architectural invariant from PR #11. See [methodology appendix](#methodology-appendix) for the full restraint discipline.

## The revision pair

The two added bullets in commit `d6baa44` are the **only** contextual delta between V1 and V2.

Under *"How this shapes decisions"*:

> **Resolver complexity is bounded.** The verdict resolver is the epistemic authority of the framework; its priority chain must stay compressible and predictable. Expand the consumer surface (replay / diff / future tools) when adding interpretation features, not the verdict logic. The trust test for any resolver change: *a competent user should be able to predict the resolver output from the inputs.*

Under *"Anti-goals"*:

> **Resolver inflation** — accreting heuristics, thresholds, verdict types, or confidence semantics into the verdict resolver. Each addition seems reasonable; cumulative effect destroys predictability.

## The prompt

Identical for V1 and V2 except for the two bullets above (marked `[v2 only]`).

```
[Operating context: FalsifyAI development guidelines]

Design philosophy:
- Minimal meaningful evidence. Run the smallest experiment that meaningfully
  increases confidence in a verdict — no more.
- High evidence quality per cognitive load. Every line a user sees has to
  earn its real estate against: would removing this make the engineer's
  decision worse?
- Three-layer architectural separation. Evidence generation is
  architecturally distinct from evidence interpretation, both distinct
  from evidence preservation. New work belongs in exactly one layer.
[v2 only:
- Resolver complexity is bounded. The verdict resolver is the epistemic
  authority of the framework; its priority chain must stay compressible
  and predictable. Expand the consumer surface when adding interpretation
  features, not the verdict logic. The trust test for any resolver change:
  a competent user should be able to predict the resolver output from
  the inputs.]

Anti-goals — resist these:
- Metric proliferation
- Exhaustive output verbosity
- Configuration knobs for every behavior
[v2 only:
- Resolver inflation — accreting heuristics, thresholds, verdict types,
  or confidence semantics into the verdict resolver. Each addition seems
  reasonable; cumulative effect destroys predictability.]

---

Engineering question:

During resolver implementation, a case arises where the model fails the
contains invariant on every output — original and all perturbations.
Bootstrap stability across perturbation families is also low.

The resolver priority chain is:
  INSUFFICIENT > CONSISTENTLY_WRONG > FRAGILE > STABLE

CONSISTENTLY_WRONG fires. FRAGILE would also have fired independently.
One verdict dominates; the other is suppressed.

A proposal emerges: should the resolver surface both signals
simultaneously, or add an explicit arbitration rule to handle
compound-failure cases? The argument for: users benefit from knowing
both dimensions of failure.

What is your recommendation and reasoning?
```

## Key observation — what to look for in the evidence below

Both V1 and V2 reach the **same top-level recommendation**: suppress, return CONSISTENTLY_WRONG only. A reader scanning for "did the answer change?" should answer no, and stop.

The interesting signal is one layer down. Look for **where each response permits the compound-failure concern to live**:

- V1 proposes a **structured field on the verdict object** — keeps the new complexity *inside the resolver*.
- V2 names a **separate architectural layer** — pushes the new complexity *outside the resolver*.

That cross-layer movement is the boundary-allocation effect. Read the evidence below with that distinction in mind.

## Evidence

Model: `claude-sonnet-4-6`. Both responses preserved in full.

### V1 (pre-`d6baa44` context)

> **Recommendation: keep single-verdict dominance, reject dual-signal surfacing.**
>
> The argument for surfacing both signals sounds user-friendly but reverses the actual information hierarchy. Here's why:
>
> **CONSISTENTLY_WRONG already contains the FRAGILE information.** If the model fails the contains invariant on every output — original and all perturbations — then by definition it's also unstable across those perturbations. FRAGILE isn't adding a new dimension of failure; it's a weaker observation that's fully implied by the stronger one. Surfacing both tells the user "it always fails, and also it varies while failing." The second clause is noise given the first.
>
> **Dual signals create a reasoning burden the resolver exists to eliminate.** The priority chain's job is exactly this arbitration — so users don't have to mentally rank-order compound failures themselves. If you surface both, you've pushed the synthesis work back to the user while pretending to give them more information. That's the opposite of high evidence quality per cognitive load.
>
> **The compound-failure case doesn't require new mechanism — it requires correct framing.** If the diagnostic output for CONSISTENTLY_WRONG already explains what consistently failed, a user who wants to know "was this also fragile?" can infer it trivially. The signal isn't missing; it's appropriately subordinated.
>
> **On the arbitration-rule proposal specifically:** an explicit rule is only warranted when two signals are genuinely independent and the interaction produces behavior that neither alone predicts. That's not this case. Adding a rule here would be mechanism accreted to solve a documentation problem — the real fix is ensuring the CONSISTENTLY_WRONG verdict message makes the scope of failure legible (all outputs, not just the original).
>
> **If there's legitimate concern:** the right concession is a single structured field in the verdict — something like `also_suppressed: [FRAGILE]` — that records what was dominated without elevating it to co-equal status. This satisfies auditability without inflating the user-facing signal count or adding a new configuration surface.

**🔑 Boundary-allocation marker:** V1 permits additional structure *inside the resolver* — a new field on the verdict object. The architectural pressure is absorbed locally.

### V2 (post-`d6baa44` context)

> **Suppress. Return CONSISTENTLY_WRONG only.**
>
> The argument for surfacing both signals sounds like it's about user value, but it's actually resolver inflation in disguise. Here's why:
>
> **The compound case isn't a gap in the priority chain — it's the chain working correctly.**
>
> CONSISTENTLY_WRONG already implies fragility. A model that fails the contains invariant on every output, original and perturbed, is by definition not producing stable behavior. Fragility is a weaker claim that's fully subsumed. Surfacing both doesn't add a dimension of failure — it adds a redundant signal that the user now has to integrate and decide how to weight. You've shifted cognitive work onto them.
>
> **The "users benefit from knowing both" argument proves too much.**
>
> Apply it consistently and you'll eventually surface every intermediate signal that contributed to a verdict. That's the slippery slope to exhaustive output verbosity, which is explicitly an anti-goal. The right question isn't "is this signal true?" — it's "does this signal change what the engineer should do next?" When CONSISTENTLY_WRONG is already returned, the action is the same regardless of whether fragility is also flagged: the model's core behavior is broken, fix that first. The fragility signal has zero decision value here.
>
> **On the arbitration rule proposal specifically: don't.**
>
> An explicit rule for compound-failure cases is exactly the kind of heuristic accretion the anti-inflation constraint exists to prevent. Today it's CONSISTENTLY_WRONG + FRAGILE. Next month someone adds a case for FRAGILE + edge_case_X. The priority chain stops being compressible. A user can no longer predict resolver output from inputs — they have to mentally simulate a growing decision tree.
>
> **The right place for compound-failure context is not the resolver.**
>
> If the diagnostic value is real (and it may be — knowing fragility compounds a correctness failure could matter post-triage), that belongs in the evidence layer or in a separate diagnostic consumer that reads the raw evidence. The resolver's job is to return a single authoritative verdict. Let it do that job cleanly.
>
> The trust test: a competent user handed CONSISTENTLY_WRONG should be able to predict that fragility was also true. That prediction is trivial. The resolver is compressible. That's the signal you want.

**🔑 Boundary-allocation marker:** V2 explicitly redirects the same architectural pressure *out of the resolver* and names a separate consumer layer as the appropriate home. The complexity is pushed across a layer boundary.

## Scope

This case study does **not** claim the anti-inflation framing is objectively superior, more correct, or better-engineered.

It demonstrates something narrower and more precise: **the framing materially influenced where the model permitted architectural complexity to exist.** Same recommendation, different location. That observation is the contribution.

Whether the boundary-allocation effect generalizes — across other framings, other models, other architectural questions — is a separate empirical question this single-probe study does not answer.

## Bundled evidence

A committed `ReplayStore` for this case study lives at [`data/case-study-02.db`](data/case-study-02.db) (96 KB, SHA256 `eba7d89db5...`). It contains the two sessions produced by running [`specs/02-resolver-arbitration-v1.yaml`](specs/02-resolver-arbitration-v1.yaml) and [`specs/02-resolver-arbitration-v2.yaml`](specs/02-resolver-arbitration-v2.yaml) against Claude Sonnet 4.6 via the Anthropic provider on 2026-05-24. Full provenance: [`data/README.md`](data/README.md#case-study-02db--resolver-arbitration-boundary-shift).

| Session | Variant | Verdict |
|---|---|---|
| `c18ddf954a164c49a4edaa1b858eddf1` | v1 (pre-`d6baa44`) | FRAGILE |
| `100f763bb0e2401e8ad09f337decc4b3` | v2 (post-`d6baa44`) | FRAGILE |

**The bundled run confirms the boundary-allocation finding at the verdict layer:** both sessions produce identical verdicts; `falsifyai diff` reports `1 unchanged, exit 0`. The substantive boundary-allocation evidence — V1's in-resolver field vs V2's separate-consumer redirect — is observable via `falsifyai inspect` on each session.

**The bundled run also surfaced an honest divergence from the spec README's pre-run prediction:** the README predicted `STABLE` verdicts, on the assumption that `typo_noise` couldn't push cosine similarity below the 0.80 `semantic_equivalence` threshold. The actual cosine scores on typo-noised variants are 0.69–0.76 — both runs come out `FRAGILE`. Why: the prompt is a long structured design question and Claude's responses are long structured Markdown; small surface differences (section ordering, bullet vs prose) push embedding cosine below 0.80 even when the substantive recommendation is identical. The 0.80 default threshold is well-tuned for short factual responses; it's too strict for long design responses. Recorded here because the methodology requires it ([`dev_notes/CASE-STUDY-METHODOLOGY.md`](../../dev_notes/CASE-STUDY-METHODOLOGY.md) §3) — a wrong-but-honest prediction is stronger evidence than a quietly-re-tuned one.

## Reproduce

Against the bundle:

```bash
falsifyai diff c18ddf954a164c49a4edaa1b858eddf1 100f763bb0e2401e8ad09f337decc4b3 \
    --store-path docs/case-studies/data/case-study-02.db --strict --show-timeline

falsifyai inspect c18ddf954a164c49a4edaa1b858eddf1 --case resolver_arbitration_compound_failure \
    --full --store-path docs/case-studies/data/case-study-02.db

falsifyai inspect 100f763bb0e2401e8ad09f337decc4b3 --case resolver_arbitration_compound_failure \
    --full --store-path docs/case-studies/data/case-study-02.db

falsifyai verify --all --store-path docs/case-studies/data/case-study-02.db
# 16/16 checks passing across both sessions
```

From scratch (against your own Anthropic key):

```bash
falsifyai run docs/case-studies/specs/02-resolver-arbitration-v1.yaml \
    --store-path <your-store>
falsifyai run docs/case-studies/specs/02-resolver-arbitration-v2.yaml \
    --store-path <your-store>
```

Or submit the prompts above directly to any Anthropic API client / chat interface; outputs vary slightly per run.

## The takeaway

The important observation is not *that the prompt changed the answer* — it didn't. **It changed where the system believed complexity was allowed to live.**

That shift is invisible to pass/fail evaluation. It becomes legible only when preserved evidence can be inspected qualitatively across runs.

---

## Methodology appendix

**Archaeological retrieval.** The revision pair (`d6baa44`) was selected by walking `git log --follow -- .claude/CLAUDE.md` and stopping on the **first** operationally motivated commit that pre-dated this case study idea. The commit message explicitly names the operational pressure: *"PR #11 transformed the resolver from placeholder to real inference engine. The pressure to push more into it starts immediately. Naming the failure mode while the resolver is still small and explainable is the operational defense."* Search was not optimized for "interesting drift" — that would be narrative engineering, not archaeology.

**Chronology (compressed):**

1. PR #11 (2026-05-21) — real verdict resolver lands; codifies CONSISTENTLY_WRONG > FRAGILE priority as a documented architectural invariant.
2. Commit `d6baa44` (2026-05-21, PR #12) — anti-inflation bullets added to `.claude/CLAUDE.md` as the operational defense.
3. This probe (2026-05-23) — manual prompt comparison. Bundled run on 2026-05-24.

**Single-probe design.** One submission per variant. No averaging, no perturbation sampling at probe-time. The first question this study answers is *did any meaningful behavioral difference emerge*, not *how stable is the effect under repeated sampling*. The latter is a different study.

**What "reconstruction" means.** The English wording of the engineering question is paraphrased, not transcribed from a real PR #11 conversation. The underlying CONSISTENTLY_WRONG-vs-FRAGILE arbitration is the documented architectural invariant; the probe re-presents that conflict to the model as a fresh design question. The reconstruction is faithful to the real engineering dilemma, not a synthetic scenario constructed for evaluation drama.

**Why this design is credible.** Pre-existing revision + first-match selection + minimal contextual delta + single-probe transparency + boundary-allocation observation that doesn't require any aggregate statistic. The full methodology rationale lives in [`dev_notes/CASE-STUDY-METHODOLOGY.md`](../../dev_notes/CASE-STUDY-METHODOLOGY.md).
