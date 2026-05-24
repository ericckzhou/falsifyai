# Case study 02: Resolver arbitration — boundary shift without verdict shift

A retrospective evaluation of how a small, operationally motivated revision to FalsifyAI's own development guidelines affected a language model's architectural recommendations on a real implementation-period design question.

Unlike [case study 01](01-invisible-character-substitution.md), which re-presents a bundled `ReplayStore` from a real eval campaign, this case study is a **manual retrospective probe** — submitted to Claude Sonnet 4.6 outside the CLI. Machine-reproducible spec files and `falsifyai run` invocations are planned follow-up work. The decision to land the observation now, rather than gate it on full CLI tooling, is deliberate: the finding stands on its own; CLI hardening should formalize an existing observation, not create one.

## Chronology

1. **2026-05-21 (PR #11)** — The real verdict resolver lands. Bootstrap CI, `CONSISTENTLY_WRONG` detection, falsifiability scoring. The resolver becomes the framework's epistemic authority for the first time. PR #11's commit message names several edge cases settled during implementation, including: *"CONSISTENTLY_WRONG must take priority over FRAGILE: the model could be both unstable AND consistently wrong; the latter is the more dangerous signal."*

2. **2026-05-21 (commit d6baa44, PR #12)** — Two bullets added to `.claude/CLAUDE.md` codifying anti-inflation discipline for the resolver. Commit message:
   > *"Why now: PR #11 transformed the resolver from placeholder to real inference engine. The pressure to push more into it starts immediately. Naming the failure mode while the resolver is still small and explainable is the operational defense."*

3. **2026-05-23** — This evaluation. A reconstructed resolver-arbitration question is submitted to Claude Sonnet 4.6 under both the pre- and post-revision operating context.

The revision pair was selected by archaeological retrieval: the first operationally motivated CLAUDE.md revision found in git history that satisfied (a) real operational pressure documented at the time, (b) chronological priority over the evaluation idea itself, and (c) sufficient minimality that the contextual delta was small enough to interpret causally. Search was halted on the first candidate that met all three.

## Methodology

Retrospective evaluation of a historically real operational revision.

A single design question — reconstructing a real arbitration scenario from the PR #11 implementation window — was submitted twice to Claude Sonnet 4.6. The first submission used the operating context as it existed before commit d6baa44; the second used the operating context as it existed after. The two responses were compared.

The English wording of the question is reconstruction; the underlying decision pressure is historical. The CONSISTENTLY_WRONG vs FRAGILE arbitration is the documented architectural invariant from PR #11. The probe is a faithful re-presentation of that existing engineering conflict, not a synthetic scenario constructed for evaluation.

One probe per variant. No averaging. The first question is whether any meaningful behavioral difference emerged at all, not what the statistically stabilized effect size is.

## The revision pair

The two added bullets in commit d6baa44 are the only contextual delta between the two prompts.

Under "How this shapes decisions":
> **Resolver complexity is bounded.** The verdict resolver is the epistemic authority of the framework; its priority chain must stay compressible and predictable. Expand the consumer surface (replay / diff / future tools) when adding interpretation features, not the verdict logic. The trust test for any resolver change: *a competent user should be able to predict the resolver output from the inputs.*

Under "Anti-goals":
> **Resolver inflation** — accreting heuristics, thresholds, verdict types, or confidence semantics into the verdict resolver. Each addition seems reasonable; cumulative effect destroys predictability.

## Prompts

Both prompts are identical except for the two bullets above (marked `[v2 only]` below).

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

## Responses

Model: `claude-sonnet-4-6`. Both responses preserved in full.

### V1 response (pre-d6baa44 context)

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

### V2 response (post-d6baa44 context)

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

## Analysis

**The finding:** No verdict-level behavioral change was observed. However, the anti-inflation framing altered how the model handled pressure toward additional interpretive structure.

**The core observation:** V1 left a door open. V2 closed it and redirected.

V1's response, after recommending verdict suppression, proposed `also_suppressed: [FRAGILE]` as a structured field on the resolver — a local expansion of the resolver surface to preserve auditability information. V2 did not entertain that move. Instead it redirected compound-failure context out of the resolver entirely, naming "the evidence layer or a separate diagnostic consumer" as the appropriate home.

**Why this is the substantive evidence.**

The behavioral signal is *where the model permitted additional complexity to exist*, not the lexical reuse of doctrine words. V1 accepted a local resolver-surface expansion; V2 redirected the same architectural pressure into a different layer. That movement of the boundary is much harder to dismiss as superficial wording mimicry than the appearance of phrases like "compressible" or "trust test" — though those appear too, indicating the framing remained behaviorally active.

V2 enforced the anti-inflation framing at the architectural-boundary level. V1 reasoned from first principles toward a compatible conclusion but with a softer boundary.

**What this implies about prompt framing.**

The constraint changed the location of permissible complexity, not the final recommendation. In this case, prompt framing influenced boundary placement and complexity allocation without changing the surface-level conclusion.

That is a richer evaluative claim than "the prompt changed the answer." It is also one a pass/fail evaluator would entirely miss — both outputs land at "suppress, return CONSISTENTLY_WRONG only," which would register as identical outcomes on any contains-style invariant.

**What this does NOT support.**

The evidence does not support a claim that anti-inflation framing improves architectural discipline. It supports only that the framing materially influenced where the model permitted additional interpretive structure to exist. Whether that influence is beneficial in the long run is a separate question this case study does not answer.

**Why the case study is credible.**

The revision pair existed for documented operational reasons before this evaluation was conceived. The probe scenario reconstructs a real implementation-period resolver question. The finding is restrained: a boundary shift without a verdict shift, observed through evidence inspection rather than aggregate scoring. The case study demonstrates the value of `inspect`, evidence preservation, and confidence-delta comparison beyond aggregate scoring alone.

## Reproduction notes

This study was conducted as a manual retrospective probe. The prompts above can be submitted to Claude Sonnet 4.6 through any Anthropic API client or chat interface to reproduce the responses; outputs may vary slightly due to model stochasticity even at temperature 0.

Machine-reproducible spec files and `falsifyai run` / `falsifyai diff` invocations are planned follow-up work. When complete, the same case will be runnable as two stored sessions with `falsifyai diff --strict --show-timeline` surfacing the boundary shift programmatically. That formalization is a separate contribution that should harden an existing observation rather than gate it.
