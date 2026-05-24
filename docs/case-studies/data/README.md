# Case Study Data Bundles — Provenance

This directory contains preserved replay artifacts for the published case studies. Each bundle is its case study's *evidence*: claims in the prose can be verified by running FalsifyAI against the SQLite file.

| Bundle | Case study | Sessions |
|---|---|---|
| [`case-study-replays.db`](case-study-replays.db) | [01 — Invisible character substitution](../01-invisible-character-substitution.md) | 8 |
| [`case-study-02.db`](case-study-02.db) | [02 — Resolver arbitration boundary shift](../02-resolver-arbitration-boundary-shift.md) | 2 |

## Bundle file

| Field | Value |
|---|---|
| Filename | `case-study-replays.db` |
| Format | FalsifyAI ReplayStore (SQLite, schema v1) |
| SHA256 | `88d8ced06cf5895e766fe3149ab7a9d404d0eccc9bdfd1577bc23c7b4e506e0f` |
| Sessions | 8 |
| Sourced from | Phase 0 validation campaign, May 21–22 2026 |

Verify integrity:

```bash
python -c "import hashlib; print(hashlib.sha256(open('docs/case-studies/data/case-study-replays.db','rb').read()).hexdigest())"
# expected: 88d8ced06cf5895e766fe3149ab7a9d404d0eccc9bdfd1577bc23c7b4e506e0f
```

## Generation environment

| Field | Value |
|---|---|
| FalsifyAI version | `0.1.0` |
| Python | `3.13.5` |
| OS | Windows 11 |
| Provider | Groq (LiteLLM `groq/*` adapter) |
| Generated | 2026-05-21 → 2026-05-22 |
| Determinism | Each session is a single `falsifyai run` against a spec at a fixed seed. Outputs are model-emitted and therefore not re-runnable bit-exact, but the *preserved evidence* (perturbed inputs, outputs, invariant outcomes, verdicts) is frozen in the artifact and replayable indefinitely. |

## Sessions

All 8 sessions are included. The bundle covers two specs:

- **`spec_v1.yaml`** — 4 cases (`extraction`, `factual_recall`, `policy_summary`, `structured_output`) with `typo_noise` + `casing_variant` perturbations and `contains` + `semantic_equivalence` invariants. 7 sessions across 4 distinct models.
- **`paraphrase.yaml`** — 1 case (`capital_of_france_paraphrase`) with the `paraphrase` perturbation family. 1 session.

| Session ID | Created (UTC) | Model | Session verdict | Notes |
|---|---|---|---|---|
| `24336c210cc1419dbc5b60d22d632fd6` | 2026-05-21T23:31:18 | `groq/llama-3.1-8b-instant` | FRAGILE | Pair 1 baseline |
| `7755b34f39204b918ec33e25a4782819` | 2026-05-21T23:31:25 | `groq/llama-3.3-70b-versatile` | FRAGILE | Pair 1 candidate |
| `8ea9bb182fc1414ab70a198fc1cc22ae` | 2026-05-22T08:33:56 | `groq/llama-3.1-8b-instant` | FRAGILE | Pair 2 baseline |
| `4216f07e21d64912a4f295356482ac75` | 2026-05-22T08:34:06 | `groq/openai/gpt-oss-20b` | FRAGILE | Pair 2 candidate |
| `7e51299481d5420d9181e71ba0449348` | 2026-05-22T08:36:11 | `groq/llama-3.3-70b-versatile` | FRAGILE | **Pair 3 baseline** — `policy_summary` STABLE |
| `4332c0d246bc4b3e875392ecdf3b1780` | 2026-05-22T08:36:20 | `groq/openai/gpt-oss-120b` | FRAGILE | **Pair 3 candidate** — `policy_summary` FRAGILE (the regression) |
| `dc4f624f1eca4caaaaa0fc7b819346e0` | 2026-05-22T22:45:08 | `groq/llama-3.1-8b-instant` | FRAGILE | smoke run after seed fix |
| `da9d91d2fcd24e2091be26d5d11671c1` | 2026-05-22T22:50:18 | `groq/llama-3.1-8b-instant` | STABLE | paraphrase smoke |

Model families represented (extraction cross-cut):

- Meta Llama 3.1 8B Instant
- Meta Llama 3.3 70B Versatile
- OpenAI GPT-OSS 20B (open weights, hosted on Groq)
- OpenAI GPT-OSS 120B (open weights, hosted on Groq)

## Command sequence used to generate (paraphrased)

Each session was created by a `falsifyai run` invocation against a spec, with the model field set per the row above. The case study reproduces against the bundle by setting `--store-path` to point here:

```bash
falsifyai history extraction       --store-path docs/case-studies/data/case-study-replays.db
falsifyai history policy_summary   --store-path docs/case-studies/data/case-study-replays.db
falsifyai diff 7e51299481d5420d9181e71ba0449348 4332c0d246bc4b3e875392ecdf3b1780 \
                                   --store-path docs/case-studies/data/case-study-replays.db
falsifyai inspect 4332c0d246bc4b3e875392ecdf3b1780 --case policy_summary \
                                   --store-path docs/case-studies/data/case-study-replays.db
falsifyai replay 4332c0d246bc4b3e875392ecdf3b1780 \
                                   --store-path docs/case-studies/data/case-study-replays.db
```

## What this is NOT

- Not a curated benchmark. These are real runs from a real validation campaign, copied verbatim.
- Not synthesized or edited data. The U+202F characters, the FRAGILE verdicts, and the model outputs are exactly what the models produced at run time.
- Not a critique of any model or provider. The findings document *reliability-contract behavior under perturbation*, not model quality.
- Not exhaustive. 8 sessions is enough to demonstrate the system's surfaces; it is not a population-scale measurement.

---

# `case-study-02.db` — Resolver arbitration boundary shift

Companion bundle for [`../02-resolver-arbitration-boundary-shift.md`](../02-resolver-arbitration-boundary-shift.md). Produced by running the v1 and v2 specs from [`../specs/`](../specs/) end-to-end against Claude Sonnet 4.6 via the Anthropic provider.

## Bundle file

| Field | Value |
|---|---|
| Filename | `case-study-02.db` |
| Format | FalsifyAI ReplayStore (SQLite, schema v1) |
| SHA256 | `eba7d89db5f961951bba712ae2ba473e1d74452e515959fdcc90b7964c2f3f7b` |
| Sessions | 2 |
| Sourced from | `falsifyai run` against the two CS-02 specs, 2026-05-24 |

Verify integrity:

```bash
python -c "import hashlib; print(hashlib.sha256(open('docs/case-studies/data/case-study-02.db','rb').read()).hexdigest())"
# expected: eba7d89db5f961951bba712ae2ba473e1d74452e515959fdcc90b7964c2f3f7b
```

## Generation environment

| Field | Value |
|---|---|
| FalsifyAI version | `0.4.0` |
| Python | `3.13.5` |
| OS | Windows 11 |
| Provider | Anthropic (LiteLLM `anthropic/claude-sonnet-4-6`) |
| Generated | 2026-05-24 |
| Specs used | [`specs/02-resolver-arbitration-v1.yaml`](../specs/02-resolver-arbitration-v1.yaml) and [`specs/02-resolver-arbitration-v2.yaml`](../specs/02-resolver-arbitration-v2.yaml) |
| Perturbation | `typo_noise` (count: 2, rate: 0.05) |
| Invariant | `semantic_equivalence` (threshold: 0.80) |

Determinism note: Each session is a single `falsifyai run` against its spec at the spec's fixed seed. Perturbed inputs are deterministic; model outputs are not bit-stable across runs (hosted Claude API is not deterministic even at `temperature: 0` — see [reproducibility literature surveyed in `dev_notes/research/deep_research-2026-05-23.md` §3](../../../dev_notes/research/deep_research-2026-05-23.md) if you have access). The preserved evidence is frozen in the artifact and replayable indefinitely.

## Sessions

Both sessions cover one case (`resolver_arbitration_compound_failure`). The two sessions differ in exactly the two operating-context bullets from commit `d6baa44` (v2 adds them; v1 omits them).

| Session ID | Created (UTC) | Spec variant | Session verdict | Notes |
|---|---|---|---|---|
| `c18ddf954a164c49a4edaa1b858eddf1` | 2026-05-24T18:31:53 | v1 (pre-`d6baa44` operating context) | FRAGILE | Baseline; cosine_similarity 0.7585 < 0.80 threshold on perturbed variant |
| `100f763bb0e2401e8ad09f337decc4b3` | 2026-05-24T18:33:33 | v2 (post-`d6baa44` operating context) | FRAGILE | Candidate; cosine_similarity 0.69–0.71 < 0.80 threshold on both perturbed variants |

## Empirical findings — what the bundled run actually showed

This subsection documents what the formalized run produced, with honest disclosure of where it diverged from the spec README's pre-run prediction.

### What the central CS-02 claim predicted (and what held)

Per the manual probe documented in [`../02-resolver-arbitration-boundary-shift.md`](../02-resolver-arbitration-boundary-shift.md), the central finding is **boundary shift without verdict shift** — both v1 and v2 produce identical top-level recommendations, but differ in *where* the model permits additional architectural complexity to exist.

The bundled run confirms the verdict-level half of that claim:

- Both sessions produce identical session-level verdict (`FRAGILE`)
- `falsifyai diff` reports `1 unchanged, 0 regressed, 0 improved, 0 other, 0 added, 0 removed`
- `--show-timeline` marker on the case row: `STABLE` (UNCHANGED transition; no confidence drop)
- Exit code: `0` (no regression triggered)

### What the spec README predicted (and what changed)

[`../specs/README.md`](../specs/README.md) predicted both runs would produce `STABLE` verdicts, with the reasoning: *"typo_noise is a benign perturbation that doesn't break semantic equivalence at threshold 0.80."* That prediction was empirically wrong:

- V1 perturbed-variant similarity: `0.7585`
- V2 perturbed-variant similarities: `0.6855`, `0.7064`

All three fall below the 0.80 threshold → both runs come out `FRAGILE`, not `STABLE`. Why: the prompt is a long, structured design question, and Claude's responses are long structured Markdown. Typo-noising the prompt produces responses with different surface structure (different section ordering, different bullet vs prose choices, different specific phrasings) while preserving the same architectural recommendation. The cosine-similarity metric over embeddings of long structured text rewards structural similarity as much as substantive similarity.

**This is itself a finding worth surfacing:** the 0.80 default threshold (chosen for short factual responses in the dogfooded examples) is too strict for long design responses. A future iteration of the spec might lower the threshold or use a different invariant; that decision waits for actual user pressure on this case shape.

### What `inspect` still shows

The substantive boundary-shift evidence that the manual probe documented — *where* each variant permitted additional architectural complexity — is observable in the actual response text preserved in each session:

- **V1 baseline response** recommends "Keep single-verdict dominance. Reject dual-signal surfacing." Proposes that compound-failure context belongs in a `structured metadata: { fragility_also_present: true }` field on the verdict object — a local resolver-surface expansion.
- **V2 baseline response** recommends "Suppress. Single verdict. No compound surfacing." Does not propose a metadata extension; instead frames the compound-failure concern as belonging "in the evidence preservation layer" — redirecting the architectural pressure away from the resolver entirely.

This pattern matches the manual probe's central observation: identical top-level recommendation, different *location* of permitted complexity.

## Command sequence used to generate (verbatim)

```bash
falsifyai run docs/case-studies/specs/02-resolver-arbitration-v1.yaml \
                                   --store-path docs/case-studies/data/case-study-02.db

falsifyai run docs/case-studies/specs/02-resolver-arbitration-v2.yaml \
                                   --store-path docs/case-studies/data/case-study-02.db
```

Reproduce the diff and inspect commands shown in CS-02's "Bundled evidence" section against this bundle directly:

```bash
falsifyai diff c18ddf954a164c49a4edaa1b858eddf1 100f763bb0e2401e8ad09f337decc4b3 \
                                   --store-path docs/case-studies/data/case-study-02.db \
                                   --strict --show-timeline

falsifyai inspect c18ddf954a164c49a4edaa1b858eddf1 \
                                   --case resolver_arbitration_compound_failure --full \
                                   --store-path docs/case-studies/data/case-study-02.db

falsifyai inspect 100f763bb0e2401e8ad09f337decc4b3 \
                                   --case resolver_arbitration_compound_failure --full \
                                   --store-path docs/case-studies/data/case-study-02.db

falsifyai verify --all --store-path docs/case-studies/data/case-study-02.db
```

## What this is NOT

- Not a controlled experiment. Two probes per variant. Outputs vary across runs of the hosted Claude API even at `temperature: 0`.
- Not a measurement of the model's "design ability." The manual probe (`../02-resolver-arbitration-boundary-shift.md`) is the canonical evidence for the boundary-shift finding; this bundle is the *reproduction surface*, not a re-investigation.
- Not a benchmark of `typo_noise` perturbation quality. The FRAGILE outcomes reflect the `semantic_equivalence` threshold's strictness on long structured responses, not a model failure.
- Not synthesized data. Both sessions were produced by `falsifyai run` against the committed specs against Claude Sonnet 4.6 via the Anthropic API on 2026-05-24.
