# FalsifyAI Architecture

The deep-dive companion to [`README.md`](../README.md). The README teaches
the **workflow**; this document teaches the **architecture** the workflow
sits on.

If you're trying to extend FalsifyAI (new perturbation family, new
invariant, new CLI command, new verdict resolver tweak), this is the
document to read first. The architectural constraints described here are
load-bearing — they're what keep the project coherent as it grows.

For the **protocol semantics** of the replay artifact itself — what
guarantees it makes, what its verdicts mean as claims, what
"replayability" operationally implies — see
[`EVIDENCE.md`](EVIDENCE.md). This document describes how the code is
organized to produce that artifact; that document describes what the
artifact *is*.

---

## What kind of system is this?

FalsifyAI is **evidence infrastructure for reliability claims about
stochastic systems**. The conceptual lineage:

| Domain | Evidence infrastructure |
|---|---|
| Software supply chain | SBOM (CycloneDX, SPDX) |
| Static analysis findings | SARIF |
| Build provenance | Sigstore / in-toto |
| Security events | Audit logs |
| **Stochastic-system reliability** | **FalsifyAI replay artifact** |

The novelty isn't *that* we preserve evidence — many tools do — it's
*what* we preserve and what we guarantee about it: the full materialized
spec, every perturbed input, every model output, every invariant
judgment, the verdict assigned at run time, and the cryptographic
identity (`spec_hash`, `materialized_hash`, `session_id`) that ties them
into one inspectable record.

The CLI compresses; **the artifact preserves the receipts**. Every
architectural decision in this document is in service of producing an
artifact that holds up under inspection — by a future engineer
revisiting the migration, by a teammate reviewing the regression, or
(in compliance-sensitive contexts) by an auditor reading the evidence
six months later.

The framework is **protocol** at the preservation layer (replay
artifact semantics, identity, guarantees — see
[`EVIDENCE.md`](EVIDENCE.md)) and **implementation** at the generation
and interpretation layers (perturbations, invariants, the resolver).
That distinction matters strategically: protocols standardize;
implementations iterate. The replay artifact is the part that's
positioned to stabilize over time.

---

## The core terms

The system is organized around three concepts. Naming them explicitly
prevents the architecture from drifting away from what it actually is.

**Stochastic software** can produce meaningfully different outputs
for equivalent requests due to probabilistic inference, retrieval
variability, tool interactions, or adaptive behavior. LLMs are the
common case today; future AI systems extend the category.

**A reliability claim** is a bounded statement about how a stochastic
system behaves under specified perturbation pressure, judged by
specified invariants. *"This case is STABLE under typo_noise and
casing"* is a reliability claim. *"This model is reliable"* is not —
unfalsifiable and unbounded.

**Reliability evidence** is the preserved, replayable proof
supporting a reliability claim. Without evidence, claims are
anecdotes. With evidence, claims become inspectable. The replay
artifact is reliability evidence in physical form.

Operational consequences for the architecture:

- **Perturbations** generate reliability evidence (in service of a
  claim that doesn't yet exist).
- **Invariants + resolver** derive a reliability claim from generated
  evidence.
- **The replay artifact** preserves the claim alongside its evidence,
  so the claim can be re-rendered, inspected, or falsified later.
- **`replay`** re-presents preserved evidence without re-deriving the
  claim.
- **`diff`** compares two preserved (claim + evidence) pairs.
- **`inspect`** (Phase 1) will expand the preserved evidence on
  demand for legibility.

Perturbation engines are **replaceable** evidence generators.
Different families (paraphrase, retrieval, ordering) all feed the
same preservation protocol. The artifact is the layer intended to
evolve most conservatively over time — generation iterates around a
stable preservation core.

---

## The three-layer separation

The codebase is organized into **three layers, separated by design**. Every
piece of behavior lives in exactly one of them.

| Layer | What it does | Where it lives |
|---|---|---|
| **Evidence generation** | Produces inputs and observations from a spec. | `falsifyai.spec.materializer`, `falsifyai.perturbation`, `falsifyai.execution` |
| **Evidence interpretation** | Judges observations and compresses them into a verdict (which is *a claim about the evidence*). | `falsifyai.invariants`, `falsifyai.verdict`, `falsifyai.falsifiability`, `falsifyai.cli.render` |
| **Evidence preservation** — *the durable product* | Persists the full evidence trail so it outlives the run. The replay artifact is the system's central object; the other two layers exist to produce and feed it. | `falsifyai.replay` (artifact, store, serializer) |

The CLI subcommands (`falsifyai run` / `replay` / `diff`) are **consumers
of these layers**, not a fourth layer:

- `run` orchestrates generation → interpretation → preservation.
- `replay` reads preservation and feeds it back through interpretation
  for rendering (never re-resolves).
- `diff` reads two preserved artifacts and compares their interpretation
  outputs.

### The line to hold

**A future feature touches exactly one layer.**

When a PR proposes touching two at once, that's the decomposition signal.
Concretely:

- *"Adaptive evidence collection"* sounds like generation but it's
  **interpretation** — it decides when collection is sufficient based on
  judged data. It belongs near `verdict/resolver.py`, not in
  `perturbation/`.
- *"A new perturbation family"* is pure **generation**. It doesn't get to
  define its own verdict semantics; the existing invariants and resolver
  judge whatever it produces.
- *"A new verdict shape"* is **interpretation**. The artifact format may
  gain a field but no preservation logic changes.
- *"Permalinkable replay artifacts in a web UI"* is a new **consumer of
  preservation** (read-only). It doesn't change the artifact schema; it
  reads what's already there.

The separation is what keeps the resolver explainable as the project
grows. See *"The resolver as inference engine"* below.

---

## Data flow

The full pipeline, end-to-end:

```
   spec.yaml                              ┌─── falsifyai run ──┐
       │                                  │                     │
       ▼                                  │                     ▼
   load_spec ──▶ (Spec, spec_hash)        │              ReplayArtifact ──▶ ReplayStore
       │                                  │                     ▲                │
       ▼                                  │                     │                │
   materialize ──▶ MaterializedSpec       │   resolve_session   │                │
       │           (per-case seeds +       │           │         │                │
       │            realized perturbations)│           │         │                │
       │                                  │           │         │                │
       ▼                                  │   resolve_case ◀────┤                │
   execute (LiteLLMAdapter + cache) ──┐   │           │         │                │
       │                              │   │           │         │                │
       │  ┌────── original ───────────┘   │   stratify + CI     │                │
       │  └────── perturbed × N           │           ▲         │                │
       │                                  │           │         │                │
       ▼                                  │   invariant.check  ─┤                │
   Execution records  ───────────────────▶│           ▲         │                │
                                          │           │         │                │
                                          │  build_invariant(spec)  ─────────────┘
                                          │
                                          └───── falsifyai render (CLI)
                                                          │
                                                          ▼
                                                    stdout + exit code

   ┌─── falsifyai replay <session_id> ────────────┐
   │                                              │
   │   ReplayStore.load_session(id) ──▶ artifact  │
   │                                       │      │
   │                                       ▼      │
   │              falsifyai render (with loaded_from)
   │                                              │
   └──────────────────────────────────────────────┘

   ┌─── falsifyai diff <baseline> <candidate> ────────────────┐
   │                                                          │
   │   ReplayStore.load_session × 2  ──▶ baseline, candidate  │
   │                                            │              │
   │                                            ▼              │
   │   compute_diff(baseline, candidate)  ──▶ DiffReport       │
   │                                            │              │
   │                                            ▼              │
   │   falsifyai render_diff  ──▶ stdout + exit code           │
   │                                                          │
   └──────────────────────────────────────────────────────────┘
```

Notice the asymmetry:

- **Generation flows forward only.** `spec → materialize → execute` is a
  one-way pipeline; nothing later in the chain can rewrite anything
  earlier. That's what makes the materialized spec a stable artifact
  identity.
- **Interpretation is invoked once per run.** `resolve_case` and
  `resolve_session` produce the verdict; the verdict is then preserved.
  Replay does NOT re-invoke the resolver; it reads the verdict that was
  assigned at run time.
- **Preservation is read-only after save.** A `ReplayArtifact` saved by
  PR-N's resolver is preserved as-is forever. PR #6's `schema_meta.version`
  refuses to open databases newer than the current build understands.

---

## Identity model

Three hashes anchor identity. Each answers a different question.

| Hash | Anchored on | Answers |
|---|---|---|
| `spec_hash` | sha256 of the source YAML bytes | *"Is this the same on-disk spec file?"* |
| `materialized_hash` | sha256 of the realized perturbation strings + lineage | *"Did materialization produce the same inputs?"* |
| `session_id` (UUID4) | UUID generated at save time | *"Which specific run am I looking at?"* |

The split matters. Two runs of the same spec at different times produce:

- The **same** `spec_hash` (file bytes unchanged).
- The **same** `materialized_hash` (same seed → same perturbations).
- **Different** `session_id`s (different UUIDs at save time).
- **Different** `created_at` timestamps.

That distinguishes "same evaluation, different invocation" from "different
evaluation" in a single glance.

For the `case_id → seed` derivation: case seeds are
`sha256(session_seed:case_id)`. Reordering cases in the YAML does NOT
change any individual case's seed; only the case's identity affects its
seed.

---

## The replay artifact as central object

The replay artifact is the system's *durable product*. The generation
and interpretation layers exist to produce one. Every architectural
decision in those layers — the materialized spec, the priority-chain
verdict resolver, the stratified per-family CI — is in service of
producing an artifact that holds up under later inspection.

What the artifact preserves (canonically — see
[`EVIDENCE.md`](EVIDENCE.md) for the protocol-semantics version):

- **Identity** — `session_id` (UUID), `spec_hash`, `materialized_hash`,
  `created_at_iso`, FalsifyAI version
- **The full materialized spec** — every realized perturbation string
  with its seed and lineage, sufficient to reconstruct the exact inputs
  even if the source YAML changes later
- **Every model output** — original and perturbed, raw, no
  post-processing
- **Every invariant judgment** — invariant name, target output, pass /
  fail, evidence details, severity
- **The verdict** — assigned at run time by the deterministic priority
  chain, never re-resolved on read
- **Per-perturbation-family stability distributions** — stratified
  bootstrap CI per family, so the worst-case CI is attributable

The artifact is the thing the CLI compresses *from*, not the thing it
produces incidentally. Treating it as the system's primary output (and
the verdict as one compressed view of it) is what makes the project
*evidence infrastructure* rather than another eval framework.

**This framing has architectural consequences.** Any future work should
ask: *does this strengthen the artifact, or does it bypass it?* New
consumers (`inspect`, `history`, eventual standardized exporters) read
from the artifact. New generation layers (paraphrase, retrieval) feed
into it. The artifact's schema and guarantees evolve carefully and
backward-compatibly; consumer surfaces can iterate freely.

---

## The resolver as inference engine

After PR #11, the verdict resolver is the **epistemic authority** of the
framework. It is the layer that says *"this case is FRAGILE,"* and the
credibility of every downstream claim (replay, diff, CI gate, model
migration decision) rests on that judgment.

The verdict is *a claim about the evidence*. The artifact is the
evidence the claim rests on. The resolver is what makes the second into
the first — and its discipline is what determines whether the claim is
defensible.

That role creates predictable pressure to push more into the resolver:

- More heuristics ("weight CI by recency")
- More metrics (`average_stability` alongside `worst_case_stability`)
- More thresholds (`stable_threshold` + `fragile_threshold` + per-family +
  per-tag + per-environment)
- More verdict types (graduated FRAGILE-1 / FRAGILE-2 / FRAGILE-3)
- More confidence semantics (Bayesian posteriors, ensembles)

Each addition looks reasonable. The **cumulative** effect destroys what
makes the current resolver trustworthy: it stops fitting in one screen,
then in one head, then stops being explainable at all.

### The trust test

**One operational question, applied before any resolver change lands:**

> *"A competent user should be able to predict the resolver output from
> the inputs."*

If a careful engineer reading the spec, the perturbations, the
executions, and the invariant results can reasonably anticipate the
verdict — the resolver is still legible. If they can't, it has become a
black box, regardless of how technically correct its internals are.

This test is the operational defense against resolver inflation. It is
the question to ask **before** the PR is reviewed, not after.

### The healthy expansion pattern

When tempted to touch `falsifyai/verdict/resolver.py`, ask:

1. **Could this live in a consumer?** New CLI subcommand, new render
   path, new `--strict` flag — these grow the consumer surface without
   touching the resolver.
2. **Could this be a new field on the artifact?** A per-case
   "confidence_bias" or per-family lineage detail can live as a stored
   field that consumers read. The resolver's priority chain stays the
   four-step shape.
3. **Does the priority chain still fit on one screen?** A 5-step chain
   is still legible; a 25-step chain isn't.
4. **Does the trust test still pass?** If a user couldn't have predicted
   the output before this change, document why or back out.

PRs #13 (replay) and #14 (diff) are the proof points. Both added
significant new functionality. Neither touched the resolver. The pattern
holds.

### Why this matters

FalsifyAI's product positioning — *"evidence infrastructure for
reliability claims about stochastic systems"* — depends on the resolver
staying explainable. Predictability is what makes the artifact's
claims *defensible by a careful reader*. An opaque resolver produces
unfalsifiable claims; a predictable one produces claims that stand on
their own evidence. The discipline is in service of the artifact, not
vice-versa.

The moment users can't predict the verdict from the inputs, the
framework stops being *disciplined* and starts being *opinionated*.
Those are different products. A careful reader of the artifact — a
future engineer revisiting the migration, a teammate reviewing the
regression, an auditor in a compliance-sensitive context — must be
able to reconstruct the verdict's reasoning from the inputs alone.
That's what makes the artifact stand on its own.

This is the single biggest entropy risk in the codebase between 0.1.0 and
1.0. Naming it here is the operational defense.

---

## Evidence density

The system optimizes for **maximum useful signal**, not maximum data.
More evidence is not inherently better evidence.

Four pillars:

- **Minimal meaningful evidence.** Run the smallest experiment that
  meaningfully increases confidence in a verdict — no more. Adaptive
  evidence collection is the long-term ideal.
- **High evidence quality per cognitive load.** Every line / artifact a
  user sees has to earn its real estate against: *"would removing this
  make the engineer's decision worse?"*
- **Diverse perturbation categories (orthogonal pressure).** The
  admission criterion for a new perturbation family is *"what new failure
  mode does this expose?"* — not breadth. `typo_noise_v2` is not a new
  family; `paraphrase` is.
- **Replayable proof.** Replay artifacts are the system's promise that
  claims are inspectable evidence, not anecdotes. The CLI compresses;
  the artifact preserves the receipts.

### Anti-goals

When the gravity pulls toward these, **resist**:

- Maximal perturbation volume
- Maximal telemetry / metrics
- Dashboard density
- Benchmark quantity
- Metric proliferation
- Exhaustive output verbosity
- Configuration knobs for every behavior
- **Resolver inflation** (see above)

The signal to watch: *"does this addition help an engineer make a better
decision, or does it crowd the surface where the actual decision lives?"*
If the latter, defer or rework.

### What compression is *not*

"Evidence compression" does not mean *less data* or *less visibility*.
The artifact preserves the full evidence trail — every perturbed input,
every output, every judgment. What the CLI compresses is the *decision
surface*: one row per case, one summary per session, one exit code per
run. The headline tells you *whether to look*; the artifact tells you
*what to look at*. This is **prioritized visibility**, not reduced
visibility.

Operationally, the win is:

- Faster decisions in CI gates (one exit code, no thresholds to tune)
- Lower cognitive load on engineers reviewing migration regressions
- Bounded inspection surfaces — a careful reader knows where to look
  and roughly how long it will take
- The deep view exists when needed (`replay` today, `inspect` Phase 1);
  it just doesn't crowd the moment of decision

---

## The user-question taxonomy

The "Popperian vs statistical" tension is real, but it isn't solved by
picking a side. It's resolved by recognizing that **different user
questions demand different evidence strategies**, and the system has to
know which question is being asked.

| User question | Evidence strategy |
|---|---|
| *"Can this break?"* | Falsification-first — one strong fail ends the run with FRAGILE. |
| *"How often does it break?"* | Statistical estimation — sample wide enough for a meaningful bootstrap CI. |
| *"Did migration regress?"* | Comparative evidence — `falsifyai diff` across two runs. |
| *"Is this reliable enough for CI?"* | Threshold confidence — boolean gate against a configured threshold. |
| *"What should I inspect?"* | Evidence compression — surface the few perturbations that drove the verdict. |

These are not the same epistemic problem. The MVP `falsifyai run` answers
*"Is this stable?"* (falsification-first). `falsifyai diff` answers *"Did
migration regress?"* (comparative). Future commands (`history`,
`inspect`) will address the others.

**Architectural implication:** don't prematurely encode this as a CLI
surface split (e.g., `run` vs `measure-fragility`). The strategy may be
inferable from the spec (`expected.contains` present → falsification-
first; only `semantic_equivalence` → statistical) or from a flag layer
on top of one command. Let real usage tell us where the UX boundary
belongs.

---

## Subpackage reference

A one-line orientation for each subpackage:

| Subpackage | Role |
|---|---|
| `falsifyai.spec` | Pydantic models + YAML loader + `materialize()` |
| `falsifyai.perturbation` | `Perturbation` Protocol + `typo_noise` + `casing_variant` + registry |
| `falsifyai.execution` | `ModelAdapter` Protocol + `LiteLLMAdapter` + `ExecutionEngine` + `InMemoryCache` |
| `falsifyai.invariants` | `Invariant` Protocol + `contains` + `semantic_equivalence` + `EmbeddingBackend` |
| `falsifyai.verdict` | `Verdict` enum + `resolver` (priority chain) + `stratify` + `consistency` |
| `falsifyai.falsifiability` | Per-case + suite-level falsifiability scoring |
| `falsifyai.replay` | `ReplayStore` Protocol + `SQLiteStore` + `InMemoryStore` + artifact + serializer |
| `falsifyai.cli` | `main` (argparse) + `run` + `replay` + `diff` + `render` + `errors` |

A new contributor should be able to find any feature in <30 seconds using
this table.

---

## Further reading

- [`EVIDENCE.md`](EVIDENCE.md) — protocol semantics for the replay
  artifact: what it preserves, what guarantees it makes, what its
  verdicts mean as claims. The companion to this document; this one
  describes *how the code is organized*, that one describes *what the
  artifact is*.
- [`plan.md`](../plan.md) — the full design plan (more detail than this
  document; older).
- [`README.md`](../README.md) — the workflow walkthrough.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — code style + architectural
  constraints for PRs.
- [`.claude/CLAUDE.md`](../.claude/CLAUDE.md) — design philosophy in
  contributor-readable form.
