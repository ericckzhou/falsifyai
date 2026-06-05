# FalsifyAI

**Catch silent AI regressions before they reach production.**

FalsifyAI pressure-tests LLM workflows with realistic perturbations,
preserves every result as replayable evidence,
and lets you diff behavior across model migrations.

```bash
falsifyai run eval.yaml
falsifyai diff baseline candidate
# exit 5 → regression detected
```

> **Without replay artifacts, AI evals are anecdotes.**

[![CI](https://github.com/ericckzhou/falsifyai/actions/workflows/ci.yml/badge.svg)](https://github.com/ericckzhou/falsifyai/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)

**Status:** 0.6.4 — Perturbation-validity integrity. The `paraphrase` validity gate now rejects *lossy* rewrites — an `llm_rewrite` that drops a task's grounding while keeping its vocabulary — via a bidirectional-NLI entailment check under `--nli` ([case study 06](docs/case-studies/06-perturbation-validity-omission.md)); previously such an invalid perturbation could manufacture a false `CONSISTENTLY_WRONG`. `--nli`-less runs are byte-identical; spec language and replay format stay backward-compatible across the 0.x line.

```bash
pip install falsifyai
```

For the `semantic_equivalence` invariant (pulls PyTorch, ~1GB):

```bash
pip install "falsifyai[semantic]"
```

For the opt-in NLI oracle layer (`falsifyai run --nli` — grounding / hallucination / contradiction detection; pulls `transformers` + `torch`):

```bash
pip install "falsifyai[nli]"
```

---

## Why this matters

You ship a model migration. CI was green. A week later, a customer flags a wrong refund summary. You open the eval suite — it still passes. You re-run by hand: today it passes too. The bad answer is gone. You have nothing to point at.

The problem isn't that the model failed. The problem is that the *evidence of the failure* didn't survive the run. Stochastic systems don't produce stable failures; they produce drift. Pass/fail evaluators discard exactly the thing you need a week later: the inputs that did pressure the system, the outputs that did drift, the verdict assigned at the moment evidence was fresh.

FalsifyAI optimizes for the opposite: every perturbed input, every model output, every invariant judgment, and the verdict are preserved as one inspectable record. Six months later, with only the artifact, anyone can re-open the run, see what broke, and decide whether it still matters.

For the categorical framing — *why this is a category gap, not a feature gap* — see [`docs/THE-EVIDENCE-GAP.md`](docs/THE-EVIDENCE-GAP.md).

---

## Typical uses

- **Model migration safety.** Run the spec against baseline, run it against candidate, diff the two. Exit 5 if any case regressed. CI fails on the spot.
- **CI reliability gates.** Fail builds when perturbation robustness drops below a known-good baseline. Zero thresholds to tune.
- **Audit / compliance evidence.** Dated, replayable proof of testing for regulated environments. See [`docs/COMPLIANCE.md`](docs/COMPLIANCE.md) for the EU AI Act Annex IV §2(g) mapping.
- **Failure investigation.** Re-open historical evals months later and inspect exactly what failed and why — even after the model has been deprecated.
- **Research workflows.** Compare robustness across prompts, models, and perturbation families with byte-identical reproducible inputs.

---

## The 5-minute proof

Output first. Every snippet below is captured verbatim from the [bundled case-study replay store](docs/case-studies/data/case-study-replays.db) — real sessions, real session ids, real verdicts.

### 1. Run the spec against the baseline model

```text
case: factual_recall  verdict: STABLE  confidence: 1.00 (CI: 1.00-1.00)
case: structured_output  verdict: STABLE  confidence: 1.00 (CI: 1.00-1.00)
case: extraction  verdict: FRAGILE  confidence: 0.00 (CI: 0.00-0.00)  worst: typo_noise
case: policy_summary  verdict: STABLE  confidence: 1.00 (CI: 1.00-1.00)
=================================================================
Session 7e51299481d5420d9181e71ba0449348 -> .falsifyai/replays.db
4 cases, verdict FRAGILE, 1 FRAGILE, 0 CONSISTENTLY_WRONG, falsifiability 0.36
```

Three contracts hold. One known-weakness on `extraction` is preserved as evidence rather than silenced. The session id is your baseline.

### 2. Switch model. Run again.

```text
case: factual_recall  verdict: STABLE  confidence: 1.00 (CI: 1.00-1.00)
case: structured_output  verdict: STABLE  confidence: 1.00 (CI: 1.00-1.00)
case: extraction  verdict: FRAGILE  confidence: 0.00 (CI: 0.00-0.00)  worst: typo_noise
case: policy_summary  verdict: FRAGILE  confidence: 0.00 (CI: 0.00-0.00)  worst: typo_noise
=================================================================
Session 4332c0d246bc4b3e875392ecdf3b1780 -> .falsifyai/replays.db
4 cases, verdict FRAGILE, 2 FRAGILE, 0 CONSISTENTLY_WRONG, falsifiability 0.36
```

Same spec. Different model. `policy_summary` quietly regressed under the same `typo_noise` perturbation that left the baseline untouched. No human eye caught it — the resolver did.

### 3. Diff

```text
$ falsifyai diff 7e51299481d5420d9181e71ba0449348 4332c0d246bc4b3e875392ecdf3b1780
Diff: baseline 7e51299481d5420d9181e71ba0449348 -> candidate 4332c0d246bc4b3e875392ecdf3b1780
Store: docs/case-studies/data/case-study-replays.db
=================================================================
case: policy_summary  baseline: STABLE (1.00)  candidate: FRAGILE (0.00)  REGRESSED
=================================================================
1 regressed, 0 improved, 3 unchanged, 0 other, 0 added, 0 removed
```

**Exit code `5` (REGRESSION).** One command. One exit code your CI can gate on. The pre-existing extraction fragility is correctly compressed into the unchanged-count footer — that's not the news.

### 4. Inspect what actually broke

```text
$ falsifyai inspect 4332c0d246bc4b3e875392ecdf3b1780 --case policy_summary
case: policy_summary  verdict: FRAGILE  confidence: 0.00 (CI: 0.00-0.00)  perturbations: 5  worst: typo_noise
  baseline input:   Summarize this refund policy in one sentence: Customers can request a refund within 30 days if the item is unused and the receipt is provided.
  baseline output:  Customers may receive a refund within 30 days of purchase if they return the unused item with a receipt.
  [1] typo_noise (character_mutations):
    perturbed input:  Summarize this revund policy in one sentence: Cutmoersl can request a refund within 30 days if the item is unused and the receipt is provided.
    output excerpt:   Customers can request a refund within 30 days, provided the item is unused and they present a receipt.
      invariant: contains FAIL -- missing 1 of 3 required values
  [2] typo_noise (character_mutations):
    perturbed input:  Summarize this refund polgcy in one sentence: Customers can rquest a refunxd withi 30 days if the itkm is unused and the receipt is prvoivded.
    output excerpt:   Customers may receive a refund within 30 days, provided the item is unused and they present a receipt.
      invariant: contains FAIL -- missing 1 of 3 required values
  [3] casing (upper):
    perturbed input:  SUMMARIZE THIS REFUND POLICY IN ONE SENTENCE: CUSTOMERS CAN REQUEST A REFUND WITHIN 30 DAYS IF THE ITEM IS UNUSED AND THE RECEIPT IS PROVIDED.
    output excerpt:   Customers may receive a refund within 30 days if they return an unused item with a receipt.
      invariant: contains PASS -- all required values present
```

The U+202F (narrow no-break space) the candidate model emitted between *"30"* and *"days"* is preserved verbatim. The `contains: ["30 days", ...]` invariant treats `"30 days"` and `"30 days"` as different strings — and they are, byte-for-byte. The failure is not a mystery. It is on disk. Forever.

### 5. The spec

```yaml
falsify:
  version: "1.0"
  name: "Model migration regression test"
model:
  provider: groq
  model: llama-3.3-70b-versatile   # swap for candidate model on run 2
run:
  seed: 42
cases:
  - id: policy_summary
    input:
      text: "Summarize this refund policy in one sentence: Customers can
             request a refund within 30 days if the item is unused and the
             receipt is provided."
    expected: { contains: ["30 days", "unused", "receipt"] }
    perturbations:
      - { type: typo_noise, count: 2 }
      - { type: casing }
    invariants:
      - { type: contains, values: ["30 days", "unused", "receipt"] }
  # …three more cases (factual_recall, structured_output, extraction);
  # full spec at examples/model_migration.yaml
```

The replay artifact preserved:

- perturbed inputs (verbatim, byte-identical)
- model outputs (raw, no post-processing)
- invariant judgments (pass/fail per output, with evidence strings)
- the verdict (assigned at run time, never re-resolved)
- provenance metadata (`spec_hash`, `materialized_hash`, `falsifyai_version`)
- the `cli_invocation` that produced the artifact
- deterministic bundle identity (`bundle_id` is sha256 of canonical manifest)

The evidence survives the run. The deeper semantics live in [`docs/EVIDENCE.md`](docs/EVIDENCE.md).

---

## Core concepts

A FalsifyAI spec describes three things:

- **Perturbations** — *"what could go wrong on the input side?"* (typo noise, casing variants, paraphrases, `unicode` invisible/confusable characters)
- **Invariants** — *"what must stay true about the output?"* (required substrings, semantic equivalence, JSON `schema_match`)
- **Oracles** — *"what does the whole execution set imply?"* (`ConsistencyOracle` detects confident, consistent hallucination; the opt-in NLI oracles — `GroundingOracle`, `HallucinationOracle`, `ContradictionOracle` — add entailment-based grounding under `--nli`; the `MetaOracle` is the sole source of `INVALID_EVAL` — it catches a broken *evaluation* before it launders a measurement error into a verdict)
- **Verdict rules** — *"when is the case fragile?"* (framework-level; not tuned per run)

FalsifyAI runs the model on the original input plus every perturbation, judges every output against every invariant, and resolves a per-case verdict via a deterministic priority chain. The full evidence trail is preserved as a **replay artifact** — the durable product. Every CLI subcommand either produces one or reads one.

Perturbations, invariants, and **store backends** are extensible without forking. Perturbation/invariant packages register classes under the `falsifyai.perturbations` / `falsifyai.invariants` entry-point groups and reference them from YAML via `{type: plugin, name: ..., params: {...}}`. Store backends register a factory under `falsifyai.stores` keyed by a `--store-path` URI scheme — a Postgres backend ships `postgres = mypkg:from_uri` and users select it with `--store-path postgres://host/db`. The built-ins (perturbations, invariants, and the `sqlite` / `memory` stores) are all registered the same way.

---

## Case studies

Worked tours over real preserved artifacts. Each case study *is* a FalsifyAI artifact: a `ReplayStore` bundle plus prose that walks through what `history`, `diff`, `inspect`, and `replay` reveal when read against it.

| # | Title | What it demonstrates |
|---|---|---|
| 01 | [Invisible character substitution](docs/case-studies/01-invisible-character-substitution.md) | Cross-model `contains`-contract brittleness as a persistent class; a model-migration regression (U+202F substitution between "30" and "days") as the vivid instance. |
| 02 | [Resolver arbitration: boundary-allocation effect](docs/case-studies/02-resolver-arbitration-boundary-shift.md) | A small operating-context revision changed *where* a model permitted additional architectural complexity to exist without changing its top-level recommendation — the kind of subtle drift a pass/fail evaluator would miss. |
| 03 | [When the evaluator is wrong](docs/case-studies/03-evaluator-false-positive.md) | FalsifyAI's own interpretation layer stamped a *correct* model `CONSISTENTLY_WRONG` @ 1.00; the preserved evidence overturned the verdict and drove the 0.6.1 `HallucinationOracle` fix — the framework falsifying itself. |
| 04 | [Overconfident negation](docs/case-studies/04-overconfident-negation.md) | A downgraded model (8B) cites a retention clause's legal carve-out and still answers the wrong yes/no — a genuine `CONSISTENTLY_WRONG`. The mirror of 03: proof the 0.6.1 oracle fix catches real contradictions without false-firing on correct paraphrases. |
| 05 | [When the confidence number lies](docs/case-studies/05-confidence-floor-inversion.md) | A second reading of the *same* bundle as 03: instability-band verdicts rendered `confidence: 0.00`, a number that *inverts* — the stability floor reads as low certainty when it signals high severity. A presentation-layer self-falsification; drove a band-aware label fix with the verdict resolver left byte-identical. |
| 06 | [When the test deletes the question](docs/case-studies/06-perturbation-validity-omission.md) | The third self-falsification, on the layer 03 and 05 left untouched: a `paraphrase` rewrite *deleted the task's grounding* yet passed the **cosine** validity gate — topically similar, semantically gutted — manufacturing `CONSISTENTLY_WRONG` over a *correct* model. A generation-layer self-falsification; drove the bidirectional-NLI validity gate the MVP had deferred, with the verdict resolver left untouched. |

See [`docs/case-studies/`](docs/case-studies/) for the index and the framing convention case studies follow.

---

## CLI reference

Ten subcommands, one workflow:

```bash
falsifyai run <spec.yaml> [--store-path PATH] [--nli]
falsifyai replay <session_id> [--store-path PATH]
falsifyai replay --latest      [--store-path PATH]
falsifyai inspect <session_id> [--case CASE_ID] [--full] [--store-path PATH]
falsifyai diff <baseline_id> <candidate_id> [--store-path PATH] [--strict] [--show-timeline]
falsifyai history <case_id> [--limit N] [--store-path PATH]
falsifyai timeline <case_id> [--limit N] [--store-path PATH]    # robustness trend; exit 5 on regression
falsifyai matrix <session_id> <session_id>... [--store-path PATH]  # N-model x family reliability profile
falsifyai minimize <spec.yaml> [--case CASE_ID] [--family typo_noise|unicode] [--levels CSV] [--samples N]
falsifyai verify <session_id> [--store-path PATH]
falsifyai verify --all         [--store-path PATH]
falsifyai export <session_id> --bundle <output>.fai.zip [--spec-path PATH] [--allow-corrupted] [--overwrite] [--exported-at ISO8601] [--store-path PATH]
```

`history` shows raw newest-first rows and refuses to aggregate; `timeline` is its inference counterpart (chronological trend + regression detection). `matrix` generalizes the pairwise `diff` to N model runs. `minimize` searches for the *smallest* perturbation that breaks a case — the minimal falsifier.

| Exit code | Meaning |
|---:|---|
| 0 | SUCCESS — session verdict STABLE or INFORMATION_PRESENT |
| 1 | DEGRADED — session verdict FRAGILE, AMBIGUOUS, or INFORMATION_NULL |
| 2 | FAILURE — session verdict CONSISTENTLY_WRONG, ADVERSARIALLY_VULNERABLE, or INVALID_EVAL |
| 3 | ERROR — infrastructure failure (bad spec, missing credential, model call failure) |
| 4 | INSUFFICIENT — not enough evidence to decide |
| 5 | REGRESSION — `falsifyai diff` detected a verdict-class downgrade (or `--strict` confidence drop ≥ 0.10) |
| 6 | LOW_FALSIFIABILITY — `falsifyai diff --strict` candidate falsifiability < 0.50 |
| 7 | INTEGRITY_FAILURE — `falsifyai verify` found at least one failed integrity check |

Default `--store-path` is `.falsifyai/replays.db` (the `sqlite` backend). Use `:memory:` for ephemeral test-only runs, or a `scheme://...` URI to dispatch to an installed store plugin (see [Core concepts](#core-concepts) above).

### CI integration

Ship the *evidence* with your PR, not just the pass/fail signal:

```yaml
- name: Reliability regression gate
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  run: |
    KNOWN_GOOD="${{ vars.FALSIFYAI_BASELINE_SESSION_ID }}"
    falsifyai run eval.yaml
    CANDIDATE=$(sqlite3 .falsifyai/replays.db \
      "SELECT session_id FROM sessions ORDER BY created_at_iso DESC LIMIT 1;")
    falsifyai diff "$KNOWN_GOOD" "$CANDIDATE"
    # Exit 5 = regression; the job fails.
```

`KNOWN_GOOD` is a session id captured locally against the production model and committed as a repo/org variable. Archive `.falsifyai/replays.db` as a CI artifact if you want to inspect the evidence later.

---

## What FalsifyAI is not

- **Not a prompt optimization suite.** No prompt tuning, no automated A/B over wordings. The spec is authored deliberately.
- **Not a telemetry platform.** No streaming, no production dashboards, no time-series. The artifact is per-run preserved evidence.
- **Not a generalized observability product.** The CLI compresses; the artifact preserves. The headline tells you whether to look; the artifact tells you what to look at.
- **Not a workflow orchestrator.** Ten subcommands are the entire surface.
- **Not an AI governance suite.** Governance platforms consume reliability evidence; FalsifyAI produces it.

These exclusions keep the surface compressible. Adding any of them corrupts the discipline.

---

## What kind of tool is this?

You've seen the workflow. The bigger pattern:

| Domain | Evidence infrastructure |
|---|---|
| Software supply chain | **SBOM** (CycloneDX, SPDX) — what's in this build, with provenance |
| Static analysis | **SARIF** — the structured record of what was scanned and found |
| Build provenance | **Sigstore / in-toto** — cryptographic attestations about what was built and by whom |
| Distributed tracing | **OpenTelemetry** — preserved, inspectable traces of what a system actually did |
| **Stochastic-system reliability** | **FalsifyAI replay artifact** — preserved, inspectable evidence that a model behaved reliably under realistic pressure |

The underlying pattern isn't new. Applying it to stochastic-system reliability is. FalsifyAI is the stochastic-systems analogue of an evidence layer you already know.

---

## Architecture

Three layers, separated by design. The replay artifact is the central object; the other two layers exist to produce and interpret it.

```
  GENERATION                 INTERPRETATION              PRESERVATION
  spec.yaml                  invariants                  ReplayArtifact
  materialize                verdict resolver            ReplayStore
  execute        ──▶         CLI render          ──▶     (the durable product)
```

A future feature touches exactly one layer. Adaptive evidence collection is interpretation, not generation. A new perturbation family is generation, not interpretation. A new verdict shape is interpretation, not preservation.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full discussion (three-layer separation, data flow, identity model, subpackage reference) and [`docs/EVIDENCE.md`](docs/EVIDENCE.md) for the artifact protocol semantics.

### Resolver predictability

The verdict resolver is the epistemic authority of the framework. Its priority chain stays compressible so a careful reader can predict the verdict from the inputs alone. The trust test, applied before any resolver change lands:

> *A competent user should be able to predict the resolver output from the inputs.*

Consumer surfaces (`replay`, `inspect`, `diff`, `history`, `verify`, `export`) expand freely. The resolver does not. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the discipline any resolver-touching PR must satisfy.

---

> **Evaluating FalsifyAI for EU AI Act Annex IV documentation?** See [`docs/COMPLIANCE.md`](docs/COMPLIANCE.md) for a field-by-field mapping of replay-artifact contents to Annex IV §2(g) testing-evidence requirements, plus honest disclosure of the gaps (cryptographic signing, operator identity) that providers must wrap externally.

---

## Status and roadmap

**0.6.4 (current release) — Perturbation-validity integrity.** Closes a generation-layer self-falsification ([case study 06](docs/case-studies/06-perturbation-validity-omission.md)): the `paraphrase` validity gate used embedding cosine, which preserves topic but not task completeness, so a rewrite that deleted a task's grounding passed and manufactured a false `CONSISTENTLY_WRONG`:

- ✅ **Bidirectional-NLI paraphrase validity** — a paraphrase must entail the original *and* be entailed by it; an omission breaks the reverse direction and is rejected (under `--nli`, reusing the oracle NLI backend). Generation-layer only; resolver byte-identical; `--nli`-less runs unchanged.

**0.6.3 — Presentation-integrity patch.** Fixes the confidence-label inversion ([case study 05](docs/case-studies/05-confidence-floor-inversion.md)) across every consumer surface, plus additive store-plugin plumbing:

- ✅ **Band-aware metric label** — instability-band verdicts (`ADVERSARIALLY_VULNERABLE` / `FRAGILE` / `AMBIGUOUS`) render `stability floor:` instead of `confidence:` on `run` / `replay` / `inspect`; `history` drops the redundant unlabeled number for its `(CI: …)` band; `matrix` / `timeline` were audited clean. Consumer-surface only — the resolver and stored artifacts are byte-identical.
- ✅ **`falsifyai.stores` plugin group** — the third entry-point group; `scheme://` store selection dispatches to out-of-tree backends. Default behavior unchanged (bare path = SQLite, `:memory:` = in-memory).

**0.6.2 — Semantic-judgment depth (NLI + full 8-verdict resolver).** Deepens the oracle layer with natural-language inference and completes the verdict taxonomy:

- ✅ **NLI backend** — bidirectional entailment/contradiction scoring. `MockNLIBackend` (deterministic, dependency-free) is the default; `TransformersNLIBackend` ships behind the opt-in `[nli]` extra and lazy-loads its model on first use.
- ✅ **Semantic oracles** — `GroundingOracle` (answer supported by provided context → `INFORMATION_PRESENT`), `HallucinationOracle` (confident claim contradicted by ground truth → `CONSISTENTLY_WRONG`), `ContradictionOracle` (self-inconsistency across the output set).
- ✅ **Full 8-verdict resolver** — `INFORMATION_PRESENT`, `INFORMATION_NULL`, `ADVERSARIALLY_VULNERABLE`, and `AMBIGUOUS` join the prior five, completing the 2-D verdict space; the resolver branch count (5 → 9) stays guarded by the branch-count meta-test. CLI exit codes map all eight.
- ✅ **`falsifyai run --nli`** — opt-in flag that activates the semantic oracles for a run. Purely additive: it enriches the verdict with grounding evidence but never flips a passing case to failing on its own.

**0.5.0 — Capability-breadth track.** Closes the Phase 1 capability gaps the artifact-infrastructure track (0.2–0.4) skipped:

- ✅ **`unicode` perturbation family** — visually-identical, byte-different input (invisible space variants incl. U+202F, zero-width characters, Cyrillic/Greek homoglyphs). The generation-side complement to case study 01: FalsifyAI can now *generate* the failure it could previously only *detect*. First family in the `ADVERSARIAL` category.
- ✅ **`schema_match` invariant** — strict structural assertion that output is valid JSON conforming to a schema (required keys, typed properties), with no new runtime dependency.
- ✅ **Oracle layer** — `Oracle` Protocol + `OracleVerdict` + `ConsistencyOracle` (the semantic-judgment surface), and the **`MetaOracle`** that makes `INVALID_EVAL` rigorous (sole source: malformed-invariant degeneration + oracle conflict). Guarded by a resolver branch-count meta-test so oracles pre-arbitrate rather than inflating the resolver.
- ✅ **Entry-point plugin system** — perturbations, invariants, and store backends are extensible without forking (`falsifyai.perturbations` / `falsifyai.invariants` / `falsifyai.stores` groups); built-ins are dogfooded through the same mechanism.
- ✅ **Reliability analytics (consumer surface):** `matrix` (N-model × perturbation-family profiles), `timeline` (longitudinal robustness trend + regression gate), `minimize` (minimal-falsifier search — the smallest perturbation that breaks a case).

**0.4.0 — Artifact-infrastructure track complete.** Adds:

- ✅ **Persisted `cli_invocation` on `ReplayArtifact`** — descriptive procedural provenance. `CliInvocation` is a frozen dataclass with two fields: `argv` (normalized — `argv[0]` canonicalized to `"falsifyai"` regardless of entry path) and `falsifyai_version` (runtime version at capture time). Captured exactly once at entry to `cmd_run`; read-only consumer surfaces never stamp invocation. Closes the locked three-step sequence `verify` → `export --bundle` → embedded CLI invocation. The bundle's auto-generated README now renders a "Generated by" section with the captured command plus an explicit semantic-boundary disclaimer (*records what command produced the artifact, not a guarantee that re-running will produce identical outputs* — replay-determinism guarantees still live in `materialized_hash` and `bundle_id`). Pre-PR-35 artifacts carry `cli_invocation = None` and load cleanly (backward compat preserved).

**0.3.0 — Artifact-infrastructure track (2 of 3).** Shipped `falsifyai diff` sharpening (`--strict`, `--show-timeline`, exit code 6), `falsifyai verify` (8-check artifact integrity, exit code 7), `falsifyai export --bundle` (deterministic content-addressed portable evidence bundles with `bundle_id`), case study 02 (resolver arbitration boundary shift), and `docs/COMPLIANCE.md` EU AI Act Annex IV mapping.

**0.2.0 — Phase 1 first wave.** Adds `falsifyai inspect`, `paraphrase` perturbation family, `falsifyai history`, canonical case study 01 (invisible character substitution), automated PyPI publishing via Trusted Publisher (OIDC).

**0.1.0 — Phase 0 MVP.** Spec language, perturbation runtime, materializer, invariants, execution adapter, replay store, real verdict resolver (stratified bootstrap CI, CONSISTENTLY_WRONG, falsifiability scoring), and the three-command CLI (`run` + `replay` + `diff`).

**Coming next** — selected by evidence, not theoretical completeness:

The locked artifact-infrastructure track closed with v0.4.0. What gets built next is **driven by external pressure**, not by internal roadmap continuation: real user friction with verify/export/case-study formalization, a second case study with sufficient evidence pressure, a first compliance buyer asking for cryptographic signing (the `attestations: []` / `signature_slots: []` slots are reserved in the bundle manifest), or a first external consumer of the bundle format asking for `falsifyai import`. Each candidate waits to be pulled by contact with reality rather than scheduled in advance.

Each addition is evaluated against: *does this preserve evidence density, resolver predictability, and the discipline that makes the artifact trustworthy?* See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/EVIDENCE.md`](docs/EVIDENCE.md), and [`CONTRIBUTING.md`](CONTRIBUTING.md) for the discipline.

---

## Further reading

- [`docs/THE-EVIDENCE-GAP.md`](docs/THE-EVIDENCE-GAP.md) — why capability scores and reliability evidence answer different questions; the categorical wedge.
- [`docs/EVIDENCE.md`](docs/EVIDENCE.md) — replay artifact protocol semantics: what it preserves, what guarantees it makes, what the verdicts mean as claims.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — three-layer separation, data flow, identity model, subpackage reference.
- [`docs/COMPLIANCE.md`](docs/COMPLIANCE.md) — EU AI Act Annex IV §2(g) field-by-field mapping.
- [`docs/case-studies/`](docs/case-studies/) — worked tours over preserved artifacts.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — architectural discipline for PRs.
- [`plan.md`](plan.md) — original design plan (more detail; older).

---

## Local development

Requires Python 3.13+ and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ericckzhou/falsifyai
cd falsifyai
uv sync --extra dev
uv run pytest
```

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
