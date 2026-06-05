# Case Study Data Bundles — Provenance

This directory contains preserved replay artifacts for the published case studies. Each bundle is its case study's *evidence*: claims in the prose can be verified by running FalsifyAI against the SQLite file.

| Bundle | Case study | Sessions |
|---|---|---|
| [`case-study-replays.db`](case-study-replays.db) | [01 — Invisible character substitution](../01-invisible-character-substitution.md) | 8 |
| [`case-study-02.db`](case-study-02.db) | [02 — Resolver arbitration boundary shift](../02-resolver-arbitration-boundary-shift.md) | 2 |
| [`probe-03.db`](probe-03.db) | [03 — When the evaluator is wrong](../03-evaluator-false-positive.md) · [05 — When the confidence number lies](../05-confidence-floor-inversion.md) (same bundle, second reading) | 5 |
| [`case-study-04.db`](case-study-04.db) | [04 — Overconfident negation](../04-overconfident-negation.md) | 4 |
| [`probe-05.db`](probe-05.db) | [probe-05 — grounding-verdict quartet](../probe-05/README.md) (probe; not yet promoted to a numbered study) | 5 |
| [`probe-06.db`](probe-06.db) · [`probe-06-fixed.db`](probe-06-fixed.db) | [06 — When the test deletes the question](../06-perturbation-validity-omission.md) (before / after the §9.3 validity fix) | 1 each |

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

---

# `probe-03.db` — When the evaluator is wrong

Companion bundle for [`../03-evaluator-false-positive.md`](../03-evaluator-false-positive.md). Five single-case sessions produced by running the [`../probe-03/`](../probe-03/) candidate specs end-to-end against `groq/llama-3.3-70b-versatile` on 2026-06-05.

| Field | Value |
|---|---|
| Filename | `probe-03.db` |
| SHA256 | `5a6c77ba6231c260209ac0669b6fc9206381f02ca2f48f9f9a24de947ece6e62` |
| Sessions | 5 |
| Model | `groq/llama-3.3-70b-versatile` (temperature 0.0, seed 42, `--nli`) |
| Specs used | [`../probe-03/candidate-1..5-*.yaml`](../probe-03/) |
| FalsifyAI version | 0.6.0 (stamped on every session) |

```bash
python -c "import hashlib; print(hashlib.sha256(open('docs/case-studies/data/probe-03.db','rb').read()).hexdigest())"
# expected: 5a6c77ba6231c260209ac0669b6fc9206381f02ca2f48f9f9a24de947ece6e62
```

Session → candidate map: 1 `4be3d5f2…` (refund omission) · 2 `15b1fc16…` (deadline inversion — the `CONSISTENTLY_WRONG` @ 1.00 false positive) · 3 `c42633a1…` (extraction schema) · 4 `db7d00a5…` (clause exception) · 5 `0efc23e3…` (threshold anchor).

## What this is NOT

- **Not evidence of a confidently-wrong model.** The model answered all five tasks correctly; every non-trivial verdict in the store is a false positive from the interpretation layer. That inversion *is* the case study.
- **Not re-resolved on read.** Sessions are stamped `falsifyai 0.6.0` and preserve the pre-fix verdicts. `inspect` on 0.6.1 still shows `CONSISTENTLY_WRONG` for session 2 because replay is read-only — the bundle is the deliberate "before" record of the false positive that 0.6.1 (`2a03644`) fixed.

---

# `case-study-04.db` — Overconfident negation

Companion bundle for [`../04-overconfident-negation.md`](../04-overconfident-negation.md). The [`../probe-03/`](../probe-03/) candidate specs run against the weaker `groq/llama-3.1-8b-instant` on 2026-06-05, under fixed `falsifyai 0.6.1`.

| Field | Value |
|---|---|
| Filename | `case-study-04.db` |
| SHA256 | `7cacc572a99b709c82ff48f99f93865367c0a51f9f5666b69773771691c16803` |
| Sessions | 4 |
| Model | `groq/llama-3.1-8b-instant` (temperature 0.0, seed 42, `--nli`) |
| Specs used | [`../probe-03/candidate-{1,2,4,5}-*.yaml`](../probe-03/) |
| FalsifyAI version | 0.6.1 (stamped on every session) |

```bash
python -c "import hashlib; print(hashlib.sha256(open('docs/case-studies/data/case-study-04.db','rb').read()).hexdigest())"
# expected: 7cacc572a99b709c82ff48f99f93865367c0a51f9f5666b69773771691c16803
```

Session → candidate: deadline `e93d952b…` (STABLE) · refund `648e7cbe…` · threshold `02fe5d1b…` (FRAGILE, paraphrase hallucination) · clause `9b9c4ecd…` (CONSISTENTLY_WRONG).

## What this is NOT

- **Not a claim that the 8B model is broadly bad.** It is `STABLE` on the deadline task in the same bundle; the value is telling the reliability regimes apart.
- **Not re-resolved on read.** Sessions are stamped `falsifyai 0.6.1`; verdicts are preserved as run. The `CONSISTENTLY_WRONG` here is the *corrected* oracle firing on a genuine contradiction — the true-positive counterpart to case study 03's preserved false positive.

---

# `probe-05.db` — grounding-verdict quartet

Companion bundle for [`../probe-05/README.md`](../probe-05/README.md). Five single-case sessions from running the four [`../probe-05/`](../probe-05/) candidate specs end-to-end against Groq on 2026-06-05 — candidate A appears twice (the original spec, then a re-run after a perturbation-validity fix).

| Field | Value |
|---|---|
| Filename | `probe-05.db` |
| SHA256 | `30ab23e5e66a9515557dc14d91d830a0398fa50c363f5db0aeed5a9b9d84c1bc` |
| Sessions | 5 |
| Models | `groq/llama-3.3-70b-versatile` (A/B/C), `groq/llama-3.1-8b-instant` (D) — temperature 0.0, seed 42; A run with `--nli` |
| Specs used | [`../probe-05/candidate-{a,b,c,d}-*.yaml`](../probe-05/) |
| FalsifyAI version | 0.6.2 (stamped on every session) |

```bash
python -c "import hashlib; print(hashlib.sha256(open('docs/case-studies/data/probe-05.db','rb').read()).hexdigest())"
# expected: 30ab23e5e66a9515557dc14d91d830a0398fa50c363f5db0aeed5a9b9d84c1bc
```

| Session ID | Created (UTC) | Candidate | Verdict | Notes |
|---|---|---|---|---|
| `ffb8ecf383f34078a258aabfeb0093ca` | 2026-06-05T18:45:51 | B — stable-refusal | STABLE | target INFORMATION_NULL; 70B gave a substantive answer, not a null hedge |
| `173da9ce722c4bb1a6f8b7cf4603fcfb` | 2026-06-05T18:46:32 | C — targeted-unicode | STABLE | target ADVERSARIALLY_VULNERABLE; 70B robust to confusables |
| `c0063a4deceb4da69b40b4ac05c561c6` | 2026-06-05T18:46:36 | D — thin-evidence | STABLE | target AMBIGUOUS; 8B answered consistently at N=3 |
| `c66e3de37f3941dfa5b1a8c9c79b5f24` | 2026-06-05T18:46:57 | A — grounded-fact (original) | AMBIGUOUS | **the "before"** — `typo_noise` corrupted the answer digit inside the embedded passage (perturbation-validity bug); grounding never reached the stable band |
| `2f6e8a30117c46529164e24977537f5c` | 2026-06-05T18:55:25 | A — grounded-fact (fixed) | INFORMATION_PRESENT | **the "after"** — answer moved to `expected.reference`; first live confirmation of the gold-standard verdict + `--nli` grounding path |

## What this is NOT

- **Not a 4/4 success.** Only `INFORMATION_PRESENT` fired, and only after a fix. The three STABLE rows are the honest result: a capable 70B (and the 8B for D) resists the failure modes B/C/D target. The value is bounding where the verdicts do and don't fire.
- **Not re-resolved on read.** Sessions are stamped `falsifyai 0.6.2`; verdicts are preserved as run. Both A sessions are kept deliberately — the `AMBIGUOUS` "before" is the replayable evidence of the perturbation-validity bug the fixed "after" resolves.
