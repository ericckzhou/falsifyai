# Case Study Data Bundle — Provenance

This directory contains the preserved replay artifacts referenced by [`../01-invisible-character-substitution.md`](../01-invisible-character-substitution.md). The bundle is the case study's *evidence*: every claim in the prose can be verified by running FalsifyAI against this SQLite file.

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
