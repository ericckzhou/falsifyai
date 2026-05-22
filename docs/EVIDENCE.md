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

---

## 2. The core terms

Three definitions anchor everything else in this document. The
[`ARCHITECTURE.md`](ARCHITECTURE.md) "Core terms" section carries the
same definitions for the system-design audience; they are restated
here because this document is intentionally self-contained.

**Stochastic software** produces meaningfully different outputs under
identical inputs due to probabilistic inference, retrieval
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

The five operations of the system, stated in these terms:

- **Perturbations** generate reliability evidence
- **Invariants + resolver** derive a reliability claim from generated
  evidence
- **The replay artifact** preserves the (claim + evidence) pair
- **`replay`** re-presents preserved evidence without re-deriving the
  claim
- **`diff`** compares two preserved (claim + evidence) pairs
- **`inspect`** (Phase 1) will expand preserved evidence on demand

Perturbation engines are **replaceable** evidence generators —
different families (paraphrase, retrieval, ordering) all feed the
same preservation protocol. The artifact is the part that's
positioned to stabilize.

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
   │ diff  │   │ inspect* │   │ archive │
   └───────┘   └──────────┘   └─────────┘

* inspect is Phase 1.
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

- The assigned verdict (`STABLE`, `FRAGILE`, `CONSISTENTLY_WRONG`,
  `INSUFFICIENT`, `INVALID_EVAL`)
- The stratified per-perturbation-family stability distribution that
  drove the verdict
- The bootstrap confidence interval per family
- The "worst case" family that determined the headline number

And one session-level verdict, derived deterministically from the
per-case verdicts via the documented priority chain.

The verdict is *the claim*. The rest of the artifact is *what the
claim rests on*.

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

## 6. Supporting infrastructure for cross-org evidence transfer *(intended, Phase 1)*

The four guarantees in section 5 are **load-bearing** semantics —
what makes the evidence trustworthy *within* a single team, repo, or
CI system. They are the core of what the artifact *is*.

For evidence transferred *across* organizational boundaries — handed
to an external reader, archived for cross-quarter retention,
exchanged between teams that don't share infrastructure — additional
supporting infrastructure is planned:

- **Cryptographic signatures** so a recipient can verify the artifact
  came from a specific producer
- **A bundled export format** (`.falsifyai-bundle`) packaging the
  artifact with its lineage for portability
- **Content-addressable identity** so the artifact's content alone
  determines its identity

This work is planned for Phase 1.

**Important framing: signing does not define the artifact's value.**
The four core guarantees in section 5 do. Signing makes the evidence
portable across trust boundaries; it does not make it evidence in the
first place. A reliability claim with predictable semantics is the
contract; cryptographic provenance strengthens portability of that
contract.

Today (0.1.0), the artifact has strong *deterministic* identity
(sha256 hashes) but is not signed. The current artifact is suitable
for use within a single trust boundary. This section will be revised
when the Phase 1 work lands.

---

## 7. The verdict as a claim

Each of the five verdicts is *a claim*, with a specific epistemic
shape. The artifact preserves the basis for the claim; the verdict
preserves the claim itself.

| Verdict | Claim made | Basis required |
|---|---|---|
| `STABLE` | "Every perturbation in this case left every invariant satisfied." | Universal positive over all perturbations × all invariants. |
| `FRAGILE` | "At least one perturbation produced an invariant failure that doesn't reflect the baseline (original) behavior." | Existence of a failing perturbation paired with a passing baseline. |
| `CONSISTENTLY_WRONG` | "The baseline (original input) already fails the invariants, and the perturbations don't change that." | Baseline failure plus correlated perturbation failures. |
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

### 9.2 Inspection *(Phase 1)*

`falsifyai inspect <session_id>` will surface the per-case
deep-dive: every perturbed input, every model output, every invariant
judgment. This is the consumer surface that makes the preserved
evidence *legible*. The artifact already contains the data; the
inspect view is presentation.

Without `inspect`, the data is reachable only via direct query of the
replay store. With `inspect`, the artifact becomes a first-class
evidentiary document a human can read.

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
