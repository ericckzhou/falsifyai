# FalsifyAI — Evidence Protocol

The replay artifact is the system's primary product. The CLI, the
perturbations, the resolver, the diff command — all of them exist to
either produce one or consume one. This document specifies what the
artifact *is*: what it preserves, what guarantees it makes, what its
verdicts mean as claims, and what "replayability" operationally
implies.

> This is a **protocol-semantics** document, not an architecture
> document. For *how the code is organized to produce the artifact*,
> see [`ARCHITECTURE.md`](ARCHITECTURE.md). For *the workflow that
> uses the artifact*, see [`../README.md`](../README.md). For the
> evidence-density philosophy that the artifact enacts, see
> [`../.claude/CLAUDE.md`](../.claude/CLAUDE.md) and
> [`../CONTRIBUTING.md`](../CONTRIBUTING.md).
>
> The contract described here is what the artifact *is*. The format
> stabilizes carefully across releases; consumer surfaces iterate
> freely.

---

## 1. What the replay artifact is

The replay artifact is a **self-contained evidentiary record of one
falsification run**: one execution of one spec against one model
configuration, with the full evidence trail preserved.

It is *not*:

- A metric snapshot ("the model scored 0.87")
- A tracing log ("here are the API calls we made")
- A dashboard backend ("here's the data my charts read from")
- An audit log in the security sense ("here's who did what")

It *is*:

- A claim ("this case is FRAGILE under typo_noise")
- The full evidence the claim rests on (every perturbed input, every
  output, every invariant judgment)
- The exact configuration that produced the evidence (the materialized
  spec, with seed-determined perturbation strings preserved verbatim)
- The deterministic identity that ties the above together
  (`spec_hash`, `materialized_hash`, `session_id`)

One run produces one artifact. One artifact preserves one run forever.

> For *why* this preservation model is structurally different from capability scoring — and why the gap matters operationally — see [`THE-EVIDENCE-GAP.md`](THE-EVIDENCE-GAP.md).

---

## 2. The core terms

Three definitions anchor everything else in this document. The
[`ARCHITECTURE.md`](ARCHITECTURE.md) "Core terms" section carries the
same definitions for the system-design audience; they are restated
here because this document is intentionally self-contained.

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
anecdotes; with evidence, claims become inspectable. The replay
artifact is reliability evidence in physical form.

The operations of the system divide cleanly into **producers** (which
generate, derive, and preserve evidence) and **read-only consumers**
(which re-present preserved evidence without re-deriving the claim).

Producers — the forward pipeline that mints an artifact:

- **Perturbations** generate reliability evidence
- **Invariants + resolver** derive a reliability claim from generated
  evidence
- **The replay artifact** preserves the (claim + evidence) pair

`run` drives this pipeline; `minimize` is a producer variant that
searches for a smaller perturbation set reproducing the same verdict.

Read-only consumers — they read a preserved artifact and never
re-derive the claim:

- **`replay`** re-presents the original run output verbatim
- **`inspect`** expands preserved evidence on demand for legibility
- **`diff`** compares two preserved (claim + evidence) pairs
- **`history`** / **`timeline`** / **`matrix`** present preserved
  artifacts across runs
- **`verify`** / **`export`** check and package a preserved artifact

(`doctor` is an environment diagnostic, not an evidence-protocol
operation.) This producer/consumer split is the load-bearing boundary:
preservation is read-only after save, so no consumer can mutate the
claim it reads. The exact command surface is enumerated in
[`ARCHITECTURE.md`](ARCHITECTURE.md); this document names the
operations only to the depth the protocol semantics require.

Perturbation engines are **replaceable** evidence generators —
different families (paraphrase, retrieval, ordering) all feed the
same preservation protocol. The artifact is the layer intended to
evolve most conservatively over time — generation iterates around a
stable preservation core.

---

## 3. The canonical lifecycle

The artifact is produced by a single linear pipeline. Naming the
stages explicitly clarifies which inputs flow into the artifact and
where the claim is derived:

```
                ┌──────────┐
                │   spec   │   (authored YAML)
                └────┬─────┘
                     ▼
        ┌────────────────────────┐
        │ materialized           │   evidence
        │ perturbations          │   generation
        │ (seed-determined)      │
        └────────────┬───────────┘
                     ▼
        ┌────────────────────────┐
        │ execution evidence     │
        │ (raw model outputs)    │
        └────────────┬───────────┘
                     ▼
        ┌────────────────────────┐
        │ invariant evaluation   │   evidence
        │ (per-output judgments) │   interpretation
        └────────────┬───────────┘
                     ▼
        ┌────────────────────────┐
        │ resolver verdict       │   ← the reliability claim
        │ (priority chain)       │
        └────────────┬───────────┘
                     ▼
        ┌────────────────────────┐
        │   REPLAY ARTIFACT      │   evidence
        │   (the durable record) │   preservation
        └────────────┬───────────┘
                     ▼
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
   ┌───────┐   ┌──────────┐   ┌─────────┐
   │ diff  │   │ inspect  │   │ archive │
   └───────┘   └──────────┘   └─────────┘
```

Generation flows forward only. Preservation is read-only after save.
The arrow from artifact into `diff`/`inspect`/`archive` represents
consumers reading the preserved evidence — they do not re-derive the
claim, they re-present it.

---

## 4. What it preserves

The canonical contents of an artifact, by category:

### 4.1 Identity

- `session_id` — UUID4 assigned at save time. Uniquely identifies *this
  invocation*.
- `spec_hash` — sha256 of the source YAML file bytes. Identifies *the
  spec file as it existed at run time*.
- `materialized_hash` — sha256 of the realized perturbation strings and
  lineage. Identifies *the inputs that were actually executed*.
- `created_at_iso` — UTC timestamp of save.
- `falsifyai_version` — the framework version that produced the
  artifact. Required for forward compatibility decisions.

Provenance — *which command produced this artifact* — is carried by
`cli_invocation` (descriptive, not part of the deterministic identity).
Its semantic boundary is defined once in §6: it records the normalized
invocation, **not** a guarantee that re-running reproduces the outputs
(replay determinism lives in `materialized_hash` and `bundle_id`).

The three hashes are deliberately split. They answer three different
audit questions: *"is this the same file?"* / *"did materialization
produce the same inputs?"* / *"which specific invocation am I looking
at?"*. Two runs of the same spec at different times produce identical
`spec_hash` and `materialized_hash` but different `session_id`s. That
distinguishes *"same evaluation, different invocation"* from
*"different evaluation"* in one glance.

### 4.2 The materialized spec

The full set of realized perturbations and their lineage:

- The original case input
- Every perturbation that was applied (family, parameters, seed,
  resulting input string)
- The materialization order (the order is part of the identity)

For meaning-preserving families gated by validity (the `paraphrase`
family under bidirectional NLI), the lineage also preserves the
validity evidence for each accepted perturbation: `validity_score` and
`validity_method` are stamped into the perturbation's parameters. This
keeps the *reason a rewrite was admitted* inspectable — a reader can
audit not just that a paraphrase was used, but that it cleared the
validity gate and by what measure.

The materialized spec is preserved *as data*, not as a reference to the
source YAML. This is intentional: the source YAML may be deleted,
edited, or renamed; the artifact must remain self-contained. A reader
six months later, with only the artifact, must be able to reconstruct
exactly what inputs the model saw.

### 4.3 Observations

For every input (original and each perturbation) the model produced:

- The exact model output, raw, no post-processing
- The execution metadata (timing, retries if any, error if the call
  failed)
- The cache-hit status, when relevant

Observations are immutable. They are what the model *did*, not what we
think it should have done.

### 4.4 Judgments

For every observation, every invariant that was configured:

- The invariant name and parameters
- The output the invariant judged
- Pass / fail
- The invariant's evidence string (substring matched, similarity score,
  contradiction detected, etc.)
- The severity (FATAL / MAJOR / MINOR — see invariant docs)

Judgments are *interpretive*: the same observation could be judged
differently by a different invariant. The artifact preserves which
invariant was used and what it returned, so a reader can audit the
judgment, not just accept it.

### 4.5 The verdict

For each case:

- The assigned verdict — one of the nine taxonomy members:
  `INFORMATION_PRESENT`, `STABLE`, `CONSISTENTLY_WRONG`,
  `ADVERSARIALLY_VULNERABLE`, `FRAGILE`, `INFORMATION_NULL`,
  `AMBIGUOUS`, `INSUFFICIENT`, `INVALID_EVAL` (the claim shape of each
  is tabled in §7)
- The stratified per-perturbation-family stability distribution that
  drove the verdict
- The bootstrap confidence interval per family
- The "worst case" family that determined the headline number

And one session-level verdict, derived deterministically from the
per-case verdicts via the documented priority chain.

The verdict is *the claim*. The rest of the artifact is *what the
claim rests on*.

**Semantic-oracle effects are preserved through the verdict, not as a
separate payload.** The grounding, information-null, and meta oracles
contribute their signals *into* verdict resolution; the artifact does
not store a distinct "oracle results" record alongside the verdict.
What an oracle concluded is recoverable from the assigned verdict (an
`INFORMATION_PRESENT` verdict *is* the grounding oracle's affirmative
signal made durable) together with the existing per-case and
per-judgment fields above. This is deliberate: a second stored copy of
oracle output would be redundant with the verdict it already produced,
and redundancy invites drift between the two.

### 4.6 Falsifiability scoring

The suite falsifiability score and per-case contributions. This is a
meta-property of the spec: how restrictive is the set of invariants?
A 0.36 score means "the contracts in this spec are permissive — a
real failure mode could slip past them." The score is preserved as
evidence about the *spec's own discriminating power*, not just the
model's behavior.

---

## 5. What the artifact guarantees

Four protocol-level guarantees make the evidence *evidence* rather
than *opinion*. These are load-bearing — they are what makes the
artifact stand on its own.

### 5.1 Immutability after save

Once saved, the artifact is never modified. Verdicts are not
re-resolved on read. Outputs are not re-judged on read. Replay shows
exactly what was assigned at run time, even if the framework version
that reads the artifact would have judged differently.

This is enforced architecturally: the `replay` command reads
verdict-as-stored, not verdict-as-computed. The
[`ARCHITECTURE.md`](ARCHITECTURE.md) section on the resolver explains
why this matters.

### 5.2 Self-containment

The artifact contains everything needed to reconstruct the run's
evidence trail. It does not depend on:

- The source YAML file still existing or being unchanged
- The model API still being available or producing the same outputs
- Any external configuration, secrets, or environment

A reader with only the artifact and the FalsifyAI version that
produced it can render the original `falsifyai run` output verbatim
and inspect every input, output, and judgment.

### 5.3 Deterministic identity

`spec_hash` and `materialized_hash` are deterministic functions of
inputs. Two runs with the same source YAML and the same `run.seed`
produce the same hashes. This is what makes `falsifyai diff` a
meaningful operation: identity is anchored on the inputs, not on the
wall-clock invocation.

### 5.4 Resolver predictability

The verdict assigned to a case is deterministically derivable from
the case's invariant results and falsifiability contributions, via a
documented priority chain. A reader with the artifact alone can
re-derive the verdict by hand and arrive at the same answer.

This is the **trust test** elevated from a coding discipline to an
evidence-system guarantee:

> *A competent reader of the artifact must be able to reconstruct the
> resolver's reasoning from the evidence alone.*

If the resolver becomes a black box, the artifact stops being
defensible by a careful reader, and the entire evidence claim
collapses into "trust us." The discipline described in
[`ARCHITECTURE.md`](ARCHITECTURE.md) — no hidden thresholds, no
opaque heuristics, priority chain fits on one screen — exists to keep
this guarantee true.

---

## 6. Portability infrastructure (not core guarantees)

The four guarantees in section 5 are **load-bearing** semantics —
what makes the evidence trustworthy *within* a single team, repo, or
CI system. They are the core of what the artifact *is*.

For evidence transferred *across* organizational boundaries — handed
to an external reader, archived for cross-quarter retention,
exchanged between teams that don't share infrastructure — additional
supporting infrastructure helps the core artifact travel:

- **Cryptographic signatures** so a recipient can verify the artifact
  came from a specific producer (deferred until an external trust-boundary
  use case pulls it forward)
- **A bundled export format** (`.fai.zip` recommended) packaging the
  artifact with its lineage for portability (shipped in v0.3.0)
- **Content-addressable identity** so the artifact's content participates
  in its identity via `bundle_id` (shipped in v0.3.0)

**Important framing: signing does not define the artifact's value.**
The four core guarantees in section 5 do. Signing makes the evidence
portable across trust boundaries; it does not make it evidence in the
first place. A reliability claim with predictable semantics is the
contract; cryptographic provenance strengthens portability of that
contract.

The artifact-infrastructure track is **complete** (3 of 3 shipped) as of
v0.4.0:

- `falsifyai verify <session_id>` (integrity check) — eight checks
  including materialized-hash recomputation and per-case CI bound
  validation. Exit 7 on failure.
- `falsifyai export <session_id> --bundle <output>.fai.zip`
  (deterministic portable evidence bundle) — content-addressed
  `bundle_id`, per-file SHA256s, reserved `attestations: []` and
  `signature_slots: []` for future signing.
- **`ReplayArtifact.cli_invocation`** (descriptive provenance for the
  command that produced the artifact) — closes the "what was actually
  run" loop required by Annex IV §2(g). Captures normalized argv plus
  the runtime `falsifyai_version`; deliberately excludes environment,
  cwd, identity, and machine metadata. Semantic boundary: records what
  command produced the artifact, NOT a guarantee that re-running will
  produce identical outputs (replay determinism still lives in
  `materialized_hash` and `bundle_id`).

Identity is **strong but deterministic**: sha256 anchors on every layer
(artifact-internal hashes, bundle-level content addressing). Signing
itself is still deferred — Sigstore-style attestation is layered on
when artifacts need to cross trust boundaries (e.g., regulatory
submission). With the artifact-infrastructure track now closed, the
next pull on the project is **driven by external pressure** (real user
friction with verify/export, second case study, first compliance-buyer
ask for signing, first external bundle consumer), not by an internal
roadmap continuation.

---

## 7. The verdict as a claim

Each verdict is *a claim*, with a specific epistemic shape. The
artifact preserves the basis for the claim; the verdict preserves the
claim itself.

| Verdict | Claim made | Basis required |
|---|---|---|
| `INFORMATION_PRESENT` | "Every perturbation left every invariant satisfied *and* a grounding oracle confirmed the outputs are supported by the provided reference." | Universal positive over perturbations × invariants, plus an affirmative grounding signal. |
| `STABLE` | "Every perturbation in this case left every invariant satisfied." | Universal positive over all perturbations × all invariants. |
| `CONSISTENTLY_WRONG` | "The baseline (original input) already fails the invariants, and the perturbations don't change that." | Baseline failure plus correlated perturbation failures. |
| `ADVERSARIALLY_VULNERABLE` | "One perturbation family collapses the contract while the others hold — a targeted, reproducible failure vector." | A single dominating failing family against otherwise-passing families. |
| `FRAGILE` | "At least one perturbation produced an invariant failure that doesn't reflect the baseline (original) behavior." | Existence of a failing perturbation paired with a passing baseline. |
| `INFORMATION_NULL` | "Outputs are structurally consistent under perturbation but semantically empty (noise, refusals, hedging)." | Cross-output consistency with an emptiness/refusal signal and no grounding claim. |
| `AMBIGUOUS` | "The eval ran, but the evidence is too thin to discriminate between the states above." | Wide bootstrap CI or a sub-`INVALID_EVAL` oracle disagreement — *not* a structural gap. |
| `INSUFFICIENT` | "There are not enough perturbations to produce a defensible stability claim." | Configured perturbation budget below threshold. |
| `INVALID_EVAL` | "The evaluation itself is internally contradictory or structurally broken." | Meta-oracle detection (e.g., invariants disagree in a way that means no claim can be made). |

The claims are *intentionally narrow*. `STABLE` does not assert
"the model is correct" — it asserts "perturbations of the kind we
tried did not break the invariants we configured." A reader who wants
to know about *other* failure modes must run *other* invariants and
perturbations. The artifact is honest about what it tested.

`FRAGILE` does not assert "the model is bad" — it asserts "this
specific contract drifts under this specific kind of pressure." A
reader can decide whether that drift matters for their use case.

This narrowness is *the discipline*. A vague verdict like "score:
0.73" would be easier to compute but impossible to inspect carefully.
A precise claim with preserved evidence is harder to fake.

---

## 8. Claim boundaries

A reliability claim is bounded by the configuration that produced it.
Stating those boundaries explicitly is the anti-overclaim discipline
that makes the claim defensible.

A `STABLE` verdict on a case asserts the claim:

- Under **the perturbations configured** (and no others)
- Judged by **the invariants configured** (and no others)
- Within **the sampling budget configured** (and no further sampling)
- For **the model configuration specified** in the spec
- **At the time of the run** (the artifact preserves the timestamp
  and the materialized inputs verbatim)

It does NOT assert:

- *"The model is universally safe."*
- *"The model is correct on this task in general."*
- *"This case will hold under future perturbations we haven't tested."*
- *"This claim is invariant to model updates or provider changes."*
- *"The invariants used are complete or sufficient for this task."*

Similarly, `FRAGILE` does NOT assert:

- *"The model is unusable."*
- *"This task is impossible for the model."*
- *"All inputs of this shape will fail."*

It asserts only: *"this specific contract drifts under this specific
kind of pressure, in this specific configuration, at this specific
time."*

Naming the boundaries is what makes the artifact honest. The verdict
says what it says and no more. A reader who needs a stronger claim
must configure stronger invariants or more diverse perturbations and
generate new evidence. The artifact does not silently extrapolate
beyond what it tested.

---

## 9. What "replayable" operationally means

"Replayable" is a specific operational guarantee, not a vague
synonym for "saved."

The replay artifact supports three operations:

### 9.1 Re-rendering

`falsifyai replay <session_id>` reproduces the original
`falsifyai run` console output byte-for-byte (modulo timestamps that
get formatted at render time). The verdicts shown are the verdicts
assigned at run time. The same exit code is returned.

This works without re-executing the model. It does not require API
access. It works after the model has been deprecated or the provider
has been changed. The artifact is sufficient.

### 9.2 Inspection

`falsifyai inspect <session_id>` surfaces the per-case deep-dive:
every perturbed input, every model output, every invariant judgment.
This is the consumer surface that makes the preserved evidence
*legible*. The artifact already contains the data; the inspect view is
presentation.

Default render shows the verdict + perturbation count for every case,
plus the worst-perturbation evidence for non-STABLE cases. `--case
<case_id>` expands one case to every perturbation; `--full` disables
output truncation. Per the no-synthesis rule: if a field is missing in
the preserved payload, inspect names the gap (`<no invariant results
preserved>`) rather than fabricating a default.

Before `inspect` shipped, this data was reachable only via direct
query of the replay store. With `inspect`, the artifact became a
first-class evidentiary document a human can read.

### 9.3 Diff

`falsifyai diff <baseline_id> <candidate_id>` compares two
artifacts case-by-case. The regression criterion is a **binary
verdict-class downgrade** — no thresholds, no weighted scores, no
hidden heuristics. A reader can predict the exit code from the two
verdicts alone.

Diff is what makes the artifact actionable in CI. The exit code 5
(REGRESSION) is the operational consequence of a verdict-class
change preserved as evidence.

---

## 10. What the artifact is NOT (anti-scope)

The artifact deliberately excludes things it could plausibly contain
but shouldn't:

### 10.1 No metric aggregations

The artifact stores per-family stability distributions and per-case
verdicts. It does *not* store "overall reliability score" or
"weighted composite" or "fragility index." Aggregating these into a
single number would obscure the per-family attribution that makes
the verdict legible.

A consumer who wants a single number can compute one. The artifact
doesn't bake one in.

### 10.2 No telemetry payload

The artifact is not designed to feed an observability platform. It
contains evidence about one run, not a stream of events. Tools that
want continuous reliability monitoring should *consume* artifacts
over time; they should not treat the artifact as a data point in a
time-series.

**To be clear: this is not anti-observability.** Production
observability is valuable and the artifact composes with it — a
governance platform or compliance dashboard is a *natural consumer*
of artifacts over time. The point is that the artifact itself is
*per-run preserved evidence*, not a streaming primitive. Different
layer.

### 10.3 No external state

The artifact does not contain customer-identifiable data beyond what
the spec puts into the input. It does not log API keys, credentials,
environment variables, or filesystem paths. The materialized spec
contains the inputs the model saw — nothing about the operator who
ran the test.

### 10.4 No model weights

The artifact identifies the model by `provider` + `model` string. It
does not preserve the model itself. If the model is later
deprecated, the artifact remains valid as evidence of *what that
model did* at the time of the run, but it cannot resurrect the model
to re-test against.

This is by design. The artifact's claim is about a *specific
historical observation*, not a *reproducible model behavior*. Two
runs against the same model name on different days may produce
different outputs; the artifact preserves what one specific run
produced.

---

## 11. Format evolution and stability

The artifact format evolves under the following discipline:

### 11.1 Within a major version (0.x.y, 1.x.y)

- Adding fields is backward-compatible. Old readers skip unknown
  fields gracefully.
- Removing or repurposing fields is a breaking change and requires a
  major version bump.
- The hash semantics (`spec_hash`, `materialized_hash`) are stable
  within a major version — two builds of the same major version
  produce identical hashes for identical inputs.

### 11.2 Across major versions

- The `falsifyai_version` field is required so readers can detect
  format generations and refuse incompatible artifacts cleanly.
- The replay store includes a `schema_meta.version` that prevents
  older builds from reading newer-format artifacts. Newer builds
  may choose to read older artifacts with caveats.

### 11.3 What changes carefully vs. freely

- **Changes carefully:** verdict semantics, priority chain, hash
  derivation, the set of preserved fields, what counts as a
  regression in `diff`, the claim shape of each verdict.
- **Changes freely:** the CLI rendering of the verdict, the
  formatting of the diff output, new consumer commands (`inspect`,
  `history`), additional optional invariants and perturbations.

The rule of thumb: anything that affects what a verdict *means* is a
careful change. Anything that affects how the verdict is *displayed*
is a free change.

---

## 12. Future: standardization aspirations

The replay artifact is positioned to become a standardizable format
for AI reliability evidence — the stochastic-systems analogue of
SBOM (CycloneDX, SPDX) for software supply chain, or SARIF for
static analysis findings.

The conditions for that standardization to be useful:

1. **Schema stability** — the format must reach a state where it
   can be locked across at least one major version cycle without
   breaking-change pressure.
2. **Multiple producers** — at least one other tool besides
   FalsifyAI must adopt the format, demonstrating the schema is
   useful beyond a single implementation.
3. **Cryptographic provenance** — signed bundles with verifiable
   identity, suitable for cross-organization transfer (see section
   6).
4. **A reference specification** — a numbered, citable document that
   describes the format precisely enough that an independent
   implementer can produce conformant artifacts.

This document, in its current form, is the *precursor* to that
specification. The artifact format is intentionally documented at
the protocol level so it can evolve into a referenceable standard
without requiring a ground-up rewrite.

Standardization is not a 0.1.x goal. It is a 2.x aspiration. The
discipline that makes it possible is being established now.

---

## 13. See also

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — *how the code is organized to
  produce the artifact*. The structural counterpart to this document.
- [`../README.md`](../README.md) — the workflow that produces and
  consumes the artifact.
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — the architectural
  discipline that protects the artifact's guarantees.
- [`../.claude/CLAUDE.md`](../.claude/CLAUDE.md) — the
  evidence-density philosophy this protocol enacts.
- [`../plan.md`](../plan.md) — the original design plan; older but
  more detailed in places.
