# Plan — Case Study 07: schema-contract migration (adoption-facing)

> Committed probe-07 planning doc. Written 2026-06-05. Self-contained so a fresh
> (cold) agent can execute without re-deriving context.
>
> **⚠️ SUPERSEDED (design evolved during execution).** The `schema_match` /
> order-extraction design below was abandoned: a JSON-key contract must live
> inside the prompt, and `typo_noise` corrupts the developer's own schema keys
> (the baseline echoed `order_id` → `odr_id` and came out non-`STABLE` on
> artifacts). The study shipped as a representative **`contains`** exception-
> omission migration instead. See [`README.md`](README.md) for what actually ran
> and the full rationale. This file is kept as the planning record.

## Why this case study exists (the strategic gap)

The 01–06 arc is strong but **inward-facing**: 01/02 read subtle model/prompt
behavior; 03/05/06 are the self-falsification trilogy (framework falsifies its
own interpretation / presentation / generation layers). That proves FalsifyAI is
honest and self-correcting. It does **not** yet answer the buyer/operator
question: *why would I put this in my migration workflow?*

CS-07 is the **operational adoption story**, deliberately boring:

> A normal engineering migration looked safe on a clean eval, but broke one
> structured-output contract under pressure. FalsifyAI's `diff` caught it,
> `inspect` showed exactly which field, and the replay artifact preserved the
> proof.

The reader should need **zero** resolver / NLI / framework-internals knowledge.
*I changed the model. The obvious test passed. The pressured test failed. The
artifact showed why.*

## Hard constraint (from `docs/case-studies/README.md`)

**"The evidence already exists in a ReplayStore from a real run — never
synthesize."** CS-07 is NOT prose. It is a real baseline run + real candidate run
producing a genuine `diff` exit 5. Every command shown must reproduce verbatim
against the bundled SQLite store. **If the hunt does not produce the shape, we
document the honest result — we do not fabricate the regression.**

## The migration scenario (locked design intent)

A team runs a **structured extraction** task — pull a machine-readable record out
of a free-text customer message and emit JSON that a downstream system consumes.
They migrate the model to cut cost:

| Role | Model | Story |
|---|---|---|
| Baseline | `groq/llama-3.3-70b-versatile` | the incumbent |
| Candidate | `groq/llama-3.1-8b-instant` | the cheaper downgrade |

(Model pair pinned by user.) A cost-saving downgrade is the most realistic
migration shape. The clean eval passes for **both** — the 8B answers the
un-perturbed task correctly. Under perturbation pressure, the 8B breaks the
**schema contract** (drops a required key / emits prose instead of JSON) while
the 70B holds.

### The contract (`schema_match`, structural only — no `--nli`)

The user's avoid-list rules out oracle/resolver/NLI edge cases — CS-07 stays
purely structural. One invariant carries the story: `schema_match` with several
required keys, so dropping one is a clean, inspectable failure. Proposed schema
(order extraction — an API contract a downstream system depends on):

```yaml
invariants:
  - type: schema_match
    schema:
      type: object
      required: ["order_id", "status", "items", "total"]
      properties:
        order_id: { type: string }
        status:   { type: string }
        items:    { type: array }
        total:    { type: number }
```

Four required keys → `falsifiability_contribution = min(1, 4*0.2) = 0.8` (a
genuinely restrictive contract, not "parses as JSON").

### Perturbation (benign, well-understood)

`typo_noise` at low rate on the **input message** (the document being extracted),
**not** the JSON contract instruction. Per the probe-03 candidate-3 note: casing
corrupts JSON key casing and is avoided; typo_noise at low default rate keeps
braces intact. The contract instruction is phrased in **prose** ("return a JSON
object with fields order_id, status, items, total") so typo-noising the message
is real pressure without mangling a literal `{...}` template. `casing_variant` is
held in reserve as a strength lever only if the 8B does not break under typo
alone.

`temperature: 0.0`, `seed: 42` — matches every other probe.

## Deliverables (match the 01–06 pattern exactly)

1. `docs/case-studies/probe-07/baseline-order-70b.yaml` — baseline spec
   (`llama-3.3-70b-versatile`).
2. `docs/case-studies/probe-07/candidate-order-8b.yaml` — candidate spec, byte-
   identical except `model:` (the migration = swap one line).
3. `docs/case-studies/probe-07/README.md` — probe rationale + run commands
   (supersedes this PLAN.md once the run is done).
4. `docs/case-studies/data/case-study-07.db` — one ReplayStore, two sessions
   (baseline + candidate). SHA256 computed and recorded.
5. `docs/case-studies/07-the-regression-that-only-appeared-under-pressure.md` —
   the case study (title/subtitle/structure below).
6. `docs/case-studies/README.md` — add row 07 to the index table.
7. `docs/case-studies/data/README.md` — add the `case-study-07.db` provenance
   section + index row.
8. Root `README.md` case-studies index — add CS-07 (commit 639c49b added CS-06
   there; mirror it). Sweep other doc indices (`AGENTS.md`, `.claude/CLAUDE.md`)
   for a case-study list and update if present.
9. `dev_notes/summaries/` + `dev_notes/walkthroughs/` per convention (these stay
   local-only; only the case-study artifacts above are committed).

### Case study file — title, subtitle, structure (from user)

```md
# Case Study 07: The regression that only appeared under pressure

A clean eval passed. A model migration looked safe. FalsifyAI `diff` found the
contract regression, and the replay artifact preserved the proof.
```

Sections (boringly operational, in this order):
1. **The migration** — baseline 70B → candidate 8B, same spec, one line changed.
2. **The clean result** — both pass the un-perturbed case.
3. **The pressure test** — same spec, `typo_noise` applied.
4. **The regression** — `falsifyai diff` reports exit 5.
5. **The evidence** — `inspect` shows the exact perturbed input, candidate
   output, and the missing required field.
6. **The portable proof** — `verify` (integrity) and `export --bundle`
   (bundle_id) show the evidence reopens and travels.
7. **What this would have caught** — a real migration failure before prod.
8. **What this does NOT claim** — not a leaderboard; not "70B > 8B"; only: *this
   migration broke this contract under this pressure.* (Protects evidence
   discipline; mirrors the README "What case studies are NOT".)

## Evidence chain to run (the product demo, end-to-end)

```bash
falsifyai run docs/case-studies/probe-07/baseline-order-70b.yaml \
    --store-path docs/case-studies/data/case-study-07.db          # baseline
falsifyai run docs/case-studies/probe-07/candidate-order-8b.yaml \
    --store-path docs/case-studies/data/case-study-07.db          # candidate
falsifyai diff <baseline_sid> <candidate_sid> \
    --store-path docs/case-studies/data/case-study-07.db          # expect exit 5
falsifyai inspect <candidate_sid> --case <id> --full \
    --store-path docs/case-studies/data/case-study-07.db          # missing field
falsifyai verify --all --store-path docs/case-studies/data/case-study-07.db
falsifyai export <candidate_sid> --bundle /tmp/migration-regression.fai.zip \
    --store-path docs/case-studies/data/case-study-07.db          # bundle_id
```

`diff` exit codes confirmed in `falsifyai/cli/diff.py`: `regressed_count > 0 ->
5` (verdict-class downgrade, e.g. STABLE -> FRAGILE). Exit 5 is the headline.

## Execution sequence + decision gates

- **A. Write both specs + probe README.** Cheap, no API.
- **B. Run baseline (70B).** GATE: must be **STABLE** (schema holds clean AND
  under typo pressure). If 70B is itself fragile on this schema, the migration
  story has no clean baseline → harden the message/schema so the strong model is
  unambiguously clean before touching the candidate.
- **C. Run candidate (8B).** GATE: must show a **schema-contract regression**
  under pressure (≥1 perturbation fails `schema_match`: missing key or non-JSON),
  landing FRAGILE/worse while clean passes. If the 8B also holds:
    - lever 1: raise typo rate / add `casing_variant`;
    - lever 2: richer schema (more required keys) or a noisier source message;
    - if it *still* holds after honest tuning → **STOP. Document the negative.**
      Do not synthesize. Re-route to a different domain (policy-summary exception
      omission, or extraction incompleteness) or report back.
- **D. Evidence chain.** `diff` exit 5, `inspect` the failing perturbation,
  `verify --all` clean, `export --bundle` → bundle_id. Capture verbatim output.
- **E. Preserve.** Bundle DB is already at the data path; compute SHA256, record
  session→model map + environment.
- **F. Write docs.** Case study md (verbatim command output only), provenance
  README section, all index updates.
- **G. Ship.** dev_notes summary + walkthrough; topic branch off `dev` →
  squash-PR to `dev`. **Docs-only — no version bump.** No attribution footers.
  Run the `pr-review` skill before opening the PR.

## Risks

- **HIGH — empirical:** the 8B may not break the contract under benign pressure.
  Owned by gate C (tuning levers + honest-negative stop). This is a hunt, not a
  guaranteed result.
- **MEDIUM — baseline contamination:** typo_noise mangling the contract
  instruction could fail the 70B spuriously. Mitigated by prose contract framing
  + low typo rate + the §B gate.
- **LOW — framing:** must read as reliability pressure-testing, not "8B is dumb."
  Owned by the explicit §8 "does NOT claim" section + neutral prose.
- **LOW — cost:** real Groq calls, 2 sessions. Groq is cheap; negligible.

## Guardrails (from `.claude/CLAUDE.md` + memory)

- Three-layer separation respected: this is pure **evidence preservation +
  generation**; the resolver/interpretation layer is untouched (no `--nli`).
- Evidence density over volume: one case, one invariant, one perturbation family.
- Name by **failure shape**, not model/artifact; do not formalize a taxonomy.
- Branch: topic off `dev`, squash-merge to `dev`; `dev → main` is separate. No
  PR/commit attribution footers. Dev notes are local-only per-PR records.
- Never synthesize evidence (the §B/§C honest-negative gates enforce this).
