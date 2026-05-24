# FalsifyAI

**Catch silent AI regressions before they reach production.**

FalsifyAI pressure-tests LLM workflows with realistic perturbations (typos, casing, paraphrases), preserves every result as replayable evidence, and lets you diff behavior across model migrations.

```bash
falsifyai run eval.yaml
falsifyai diff baseline candidate
# exit 5 → regression detected
```

> **Without replay artifacts, AI evals are anecdotes.** FalsifyAI preserves the evidence trail.

[![CI](https://github.com/ericckzhou/falsifyai/actions/workflows/ci.yml/badge.svg)](https://github.com/ericckzhou/falsifyai/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)

**Status:** 0.4.0 — Artifact-infrastructure track **complete** (3 of 3 shipped). Adds persisted `cli_invocation` on `ReplayArtifact` — descriptive procedural provenance closing the locked sequence `verify` → `export --bundle` → embedded CLI invocation. After v0.4.0, the artifact answers four questions without external bookkeeping: what happened, how it was evaluated, what was exported, and what command produced it. Spec language and verdict semantics remain locked for the 0.x line.

```bash
pip install falsifyai
```

For the `semantic_equivalence` invariant (pulls PyTorch, ~1GB):

```bash
pip install "falsifyai[semantic]"
```

---

## The 5-minute proof

Three commands. One terminal. Real models. Replayable session IDs at the end.

### 1. Run the evaluation against your baseline model

```bash
$ falsifyai run examples/model_migration.yaml
case: factual_recall     verdict: STABLE   confidence: 1.00 (CI: 1.00-1.00)
case: structured_output  verdict: STABLE   confidence: 1.00 (CI: 1.00-1.00)
case: extraction         verdict: FRAGILE  confidence: 0.00 (CI: 0.00-0.00)  worst: typo_noise
case: policy_summary     verdict: STABLE   confidence: 1.00 (CI: 1.00-1.00)
=================================================================
Session 7e51299481d5420d9181e71ba0449348 -> .falsifyai/replays.db
4 cases, verdict FRAGILE, 1 FRAGILE, 0 CONSISTENTLY_WRONG, falsifiability 0.36
```

Three contracts hold. One known weakness (extraction) is preserved as evidence. The session id is your **baseline evidence artifact** — commit it if you want it durable.

### 2. Switch to the candidate model. Run again.

```bash
$ falsifyai run examples/model_migration.yaml   # candidate model
case: factual_recall     verdict: STABLE   confidence: 1.00 (CI: 1.00-1.00)
case: structured_output  verdict: STABLE   confidence: 1.00 (CI: 1.00-1.00)
case: extraction         verdict: FRAGILE  confidence: 0.00 (CI: 0.00-0.00)  worst: typo_noise
case: policy_summary     verdict: FRAGILE  confidence: 0.00 (CI: 0.00-0.00)  worst: typo_noise
=================================================================
Session 4332c0d246bc4b3e875392ecdf3b1780 -> .falsifyai/replays.db
4 cases, verdict FRAGILE, 2 FRAGILE, 0 CONSISTENTLY_WRONG, falsifiability 0.36
```

Same spec. Different model. **A quietly-introduced regression on `policy_summary`** under the same typo perturbation that left the baseline untouched.

### 3. Diff the two artifacts

```bash
$ falsifyai diff 7e51299481d5420d9181e71ba0449348 4332c0d246bc4b3e875392ecdf3b1780
case: policy_summary  baseline: STABLE (1.00)  candidate: FRAGILE (0.00)  REGRESSED
=================================================================
1 regressed, 0 improved, 3 unchanged, 0 other, 0 added, 0 removed
```

**Exit code `5` (REGRESSION).** One command. One exit code your CI can gate on. The pre-existing extraction fragility is correctly compressed into the unchanged-count footer — that's not the news.

### 4. Inspect what actually broke

```bash
$ falsifyai inspect 4332c0d246bc4b3e875392ecdf3b1780 --case policy_summary --full
# Shows: original prompt, original response, every perturbed input, every model
# output, every invariant judgment, the verdict and its evidence trail.
# Re-openable six months from now. No external bookkeeping required.
```

The pattern that caused the regression — for example, a U+202F invisible-character substitution between *"30"* and *"days"* in the candidate's response — is preserved verbatim and inspectable. See [Case study 01](docs/case-studies/01-invisible-character-substitution.md) for the full walkthrough.

### 5. The YAML that produced it

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

Four cases. One sanity anchor (factual recall) plus three production-shaped contracts: structured output, extraction, grounded policy summarization. The mix is deliberate — a migration regression then looks like a behavioral pattern across contract types, not a single anecdote.

---

## The lifecycle

```
                                                    ┌─────────────────┐
   spec.yaml                                        │ replay          │
       │                                            │ inspect         │
       ▼                                            │ diff            │
   perturbations  ──▶  model execution  ──▶         │ history         │
                                                    │ verify          │
       │                       │                    │ export --bundle │
       └───────┬───────────────┘                    └────────▲────────┘
               ▼                                             │
           invariants  ──▶  verdict  ──▶  ReplayArtifact  ───┘
```

`run` builds a `ReplayArtifact` end-to-end. The other six commands are **read-only consumers** of artifacts that already exist. The artifact is the durable thing; the commands are how you produce it and how you read it later.

---

## The core idea

FalsifyAI tests whether an AI workflow stays reliable under realistic pressure.

You define three things in a spec:

- **Perturbations** — *"what could go wrong on the input side?"* (typo noise, casing variants, paraphrases)
- **Invariants** — *"what must stay true about the output?"* (required substrings, semantic equivalence)
- **Verdict rules** — *"when is the case fragile?"* (framework-level; not tuned per run)

FalsifyAI runs the model on the original input plus every perturbation, judges every output against every invariant, and resolves a per-case verdict. The full evidence trail — every perturbed input, every model output, every invariant judgment, the verdict, and the identity that ties them together — is preserved as a **replay artifact**.

The replay artifact is the product. Everything else exists to produce, interpret, or consume one.

For the formal definitions (*stochastic software*, *bounded reliability claim*, *reliability evidence*), see [`docs/EVIDENCE.md`](docs/EVIDENCE.md).

---

## Typical uses

- **Model migration safety.** Detect regressions before switching providers or model versions. Exit code 5 fails CI.
- **CI reliability gates.** Fail builds when perturbation robustness drops below a known-good baseline.
- **Audit / compliance evidence.** Preserve dated, replayable proof of testing for regulated environments. See [`docs/COMPLIANCE.md`](docs/COMPLIANCE.md) for the EU AI Act Annex IV §2(g) mapping.
- **Failure investigation.** Re-open historical evals months later and inspect exactly what failed and why, even after the model is deprecated.
- **Research workflows.** Compare robustness across prompts, models, and perturbation families with byte-identical reproducible inputs.

---

## What's in the evidence

The replay artifact preserves:

- **Identity** — `session_id`, `spec_hash`, `materialized_hash` (sha256 of realized perturbations), `created_at`, FalsifyAI version
- **The materialized spec** — every realized perturbation string with its seed and lineage; inputs are exactly reproducible
- **Every model output** — original and perturbed, raw, no post-processing
- **Every invariant judgment** — pass/fail per invariant per output, with evidence strings
- **The verdict** — assigned at run time using a deterministic priority chain; never re-resolved on read
- **Per-perturbation-family stability** — stratified bootstrap CI per family; worst-case attributable
- **The invocation** — normalized `falsifyai run …` command and version captured at `cmd_run` entry

The CLI compresses this into one row per case + a session summary. The artifact preserves the receipts.

---

## CLI reference

Seven subcommands, one workflow:

```bash
falsifyai run <spec.yaml> [--store-path PATH]
falsifyai replay <session_id> [--store-path PATH]
falsifyai replay --latest      [--store-path PATH]
falsifyai inspect <session_id> [--case CASE_ID] [--full] [--store-path PATH]
falsifyai diff <baseline_id> <candidate_id> [--store-path PATH] [--strict] [--show-timeline]
falsifyai history <case_id> [--limit N] [--store-path PATH]
falsifyai verify <session_id> [--store-path PATH]
falsifyai verify --all         [--store-path PATH]
falsifyai export <session_id> --bundle <output>.fai.zip [--spec-path PATH] [--allow-corrupted] [--overwrite] [--exported-at ISO8601] [--store-path PATH]
```

| Exit code | Meaning |
|---:|---|
| 0 | SUCCESS — session verdict STABLE |
| 1 | DEGRADED — session verdict FRAGILE |
| 2 | FAILURE — session verdict CONSISTENTLY_WRONG or INVALID_EVAL |
| 3 | ERROR — infrastructure failure (bad spec, missing credential, model call failure) |
| 4 | INSUFFICIENT — not enough evidence to decide |
| 5 | REGRESSION — `falsifyai diff` detected a verdict-class downgrade (or `--strict` confidence drop ≥ 0.10) |
| 6 | LOW_FALSIFIABILITY — `falsifyai diff --strict` candidate falsifiability < 0.50 |
| 7 | INTEGRITY_FAILURE — `falsifyai verify` found at least one failed integrity check |

Default `--store-path` is `.falsifyai/replays.db`. Use `:memory:` for ephemeral test-only runs.

---

## CI integration

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

`KNOWN_GOOD` is a session id captured locally against the production model and committed as a repo/org variable. **Zero thresholds to tune; the regression criterion is the verdict-class downgrade.** Archive `.falsifyai/replays.db` as a CI artifact if you want to inspect the evidence later.

---

## Examples

Four dogfooded specs, all verified in CI:

| Example | Verdict | What it demonstrates |
|---|---|---|
| [`examples/stable.yaml`](examples/stable.yaml) | `STABLE` (exit 0) | A sane model under perturbation; both perturbation families + both invariants. |
| [`examples/fragile.yaml`](examples/fragile.yaml) | `FRAGILE` (exit 1) | Model drift: baseline correct, perturbations wrong. |
| [`examples/consistently_wrong.yaml`](examples/consistently_wrong.yaml) | `CONSISTENTLY_WRONG` (exit 2) | Confident hallucination: same wrong answer under every perturbation. |
| [`examples/model_migration.yaml`](examples/model_migration.yaml) | regression (exit 5) | The launch wedge — run twice, diff, exit 5 if any case regressed. |

```bash
falsifyai run examples/stable.yaml
```

A real provider key is required at runtime (`OPENAI_API_KEY`, `GROQ_API_KEY`, etc.). CI bypasses real model calls via a `MockAdapter` test seam — see [`tests/integration/test_examples.py`](tests/integration/test_examples.py).

---

## Case studies

Worked tours over real preserved artifacts. Each case study is itself a FalsifyAI artifact: a `ReplayStore` bundle plus prose that walks through what `history`, `diff`, `inspect`, and `replay` reveal when read against it.

| # | Title | What it demonstrates |
|---|---|---|
| 01 | [Invisible character substitution](docs/case-studies/01-invisible-character-substitution.md) | Cross-model `contains`-contract brittleness as a persistent class; a model-migration regression (U+202F substitution between "30" and "days") as the vivid instance. |
| 02 | [Resolver arbitration: boundary-allocation effect](docs/case-studies/02-resolver-arbitration-boundary-shift.md) | A small operating-context revision changed *where* a model permitted additional architectural complexity to exist without changing its top-level recommendation — the kind of subtle drift a pass/fail evaluator would miss. |

See [`docs/case-studies/`](docs/case-studies/) for the index, the [bundled replay artifact](docs/case-studies/data/case-study-replays.db), and the framing convention case studies follow.

---

## What kind of tool is this?

You've seen the workflow above. The bigger pattern:

| Domain | Evidence infrastructure |
|---|---|
| Software supply chain | **SBOM** (CycloneDX, SPDX) — what's in this build, with provenance |
| Static analysis | **SARIF** — the structured record of what was scanned and found |
| Build provenance | **Sigstore / in-toto** — cryptographic attestations about what was built and by whom |
| Distributed tracing | **OpenTelemetry** — preserved, inspectable traces of what a system actually did |
| **Stochastic-system reliability** | **FalsifyAI replay artifact** — preserved, inspectable evidence that a model behaved reliably under realistic pressure |

The underlying pattern isn't new. Applying it to stochastic-system reliability is. FalsifyAI is the stochastic-systems analogue of an evidence layer you already know.

The novelty isn't *that* we preserve evidence — it's *what* we preserve: every perturbed input, every model output, every invariant judgment, the verdict, the materialized spec, and the identity that ties them together. The CLI compresses; **the artifact preserves the receipts.**

---

## What FalsifyAI is not

- **Not a prompt optimization suite.** No prompt tuning, no automated A/B over wordings. The spec is authored deliberately.
- **Not a telemetry platform.** No streaming, no production dashboards, no time-series. The artifact is per-run preserved evidence.
- **Not a generalized observability product.** The CLI compresses; the artifact preserves. The headline tells you whether to look; the artifact tells you what to look at.
- **Not a workflow orchestrator.** Seven subcommands are the entire surface.
- **Not an AI governance suite.** Governance platforms consume reliability evidence; FalsifyAI produces it.

These exclusions keep the surface compressible. Adding any of them corrupts the discipline.

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

The separation is what keeps the resolver explainable as the project grows. The architectural discipline — *resolver predictability*, *resist resolver inflation*, *three-layer separation* — is enforced by tests, not just convention. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full discussion, and [`CONTRIBUTING.md`](CONTRIBUTING.md) for the trust test any resolver-touching PR must pass.

---

## Writing your own spec

The shortest valid spec ([`tests/fixtures/specs/minimal.yaml`](tests/fixtures/specs/minimal.yaml)):

```yaml
falsify:
  version: "1.0"
  name: "minimal"
model:
  provider: openai
  model: gpt-4o-mini
run:
  seed: 42
cases:
  - id: hello
    input:
      text: "Say hi."
    perturbations:
      - type: typo_noise
    invariants:
      - type: contains
        values: ["hi"]
```

The full spec schema is in [`plan.md` §6](plan.md). Spec language is locked for the 0.x line.

---

## Local development

Requires Python 3.13+ and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ericckzhou/falsifyai
cd falsifyai
uv sync --extra dev
uv run pytest
```

Contributions follow [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

> **Evaluating FalsifyAI for EU AI Act Annex IV documentation?** See [`docs/COMPLIANCE.md`](docs/COMPLIANCE.md) for a field-by-field mapping of replay-artifact contents to Annex IV §2(g) testing-evidence requirements, plus honest disclosure of the gaps (cryptographic signing, operator identity) that providers must wrap externally.

---

## Status and roadmap

**0.4.0 (current release) — Artifact-infrastructure track complete.** Adds:

- ✅ **Persisted `cli_invocation` on `ReplayArtifact`** — descriptive procedural provenance. `CliInvocation` is a frozen dataclass with two fields: `argv` (normalized — `argv[0]` canonicalized to `"falsifyai"` regardless of entry path) and `falsifyai_version` (runtime version at capture time). Captured exactly once at entry to `cmd_run`; read-only consumer surfaces never stamp invocation. Closes the locked three-step sequence `verify` → `export --bundle` → embedded CLI invocation. The bundle's auto-generated README now renders a "Generated by" section with the captured command plus an explicit semantic-boundary disclaimer (*records what command produced the artifact, not a guarantee that re-running will produce identical outputs* — replay-determinism guarantees still live in `materialized_hash` and `bundle_id`). Pre-PR-35 artifacts carry `cli_invocation = None` and load cleanly (backward compat preserved).

**0.3.0 — Artifact-infrastructure track (2 of 3).** Shipped `falsifyai diff` sharpening (`--strict`, `--show-timeline`, exit code 6), `falsifyai verify` (8-check artifact integrity, exit code 7), `falsifyai export --bundle` (deterministic content-addressed portable evidence bundles with `bundle_id`), case study 02 (resolver arbitration boundary shift), and `docs/COMPLIANCE.md` EU AI Act Annex IV mapping.

**0.2.0 — Phase 1 first wave.** Adds `falsifyai inspect`, `paraphrase` perturbation family, `falsifyai history`, canonical case study 01 (invisible character substitution), automated PyPI publishing via Trusted Publisher (OIDC).

**0.1.0 — Phase 0 MVP.** Spec language, perturbation runtime, materializer, invariants, execution adapter, replay store, real verdict resolver (stratified bootstrap CI, CONSISTENTLY_WRONG, falsifiability scoring), and the three-command CLI (`run` + `replay` + `diff`).

**Coming next** — selected by evidence, not theoretical completeness:

The locked artifact-infrastructure track closed with v0.4.0. What gets built next is **driven by external pressure**, not by internal roadmap continuation: real user friction with verify/export/case-study formalization, a second case study with sufficient evidence pressure, a first compliance buyer asking for cryptographic signing (the `attestations: []` / `signature_slots: []` slots are reserved in the bundle manifest), or a first external consumer of the bundle format asking for `falsifyai import`. Each candidate waits to be pulled by contact with reality rather than scheduled in advance.

Each addition is evaluated against: *does this preserve evidence density, resolver predictability, and the discipline that makes the artifact trustworthy?* See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/EVIDENCE.md`](docs/EVIDENCE.md), and [`CONTRIBUTING.md`](CONTRIBUTING.md) for the discipline.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
