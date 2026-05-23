# Invisible character substitution: a reliability-pressure case study

> **One sentence**: when models migrate, *"semantically correct"* can be *"contractually broken"* — and the difference is sometimes a single invisible byte.

> **Evidence bundle**: [`data/case-study-replays.db`](data/case-study-replays.db) · SHA256 `88d8ced06cf5895e766fe3149ab7a9d404d0eccc9bdfd1577bc23c7b4e506e0f` · 8 sessions · see [`data/README.md`](data/README.md) for provenance.

> **What this is**: a worked tour of FalsifyAI's evidence infrastructure — `history`, `diff`, `inspect`, `replay` — over real preserved artifacts from a real validation campaign. Every command shown below runs against the bundle and reproduces the output verbatim.

---

## Setup

Two YAML specs were run against four Groq-hosted models during a validation campaign on May 21–22 2026. Each `falsifyai run` writes a `ReplayArtifact` to a SQLite store; the resulting 8 sessions are bundled in [`data/case-study-replays.db`](data/case-study-replays.db). The case study traces what those artifacts reveal when read through different consumer surfaces.

Models exercised across the `extraction` case:

- `groq/llama-3.1-8b-instant` (Meta Llama 3.1, 8B parameters)
- `groq/llama-3.3-70b-versatile` (Meta Llama 3.3, 70B parameters)
- `groq/openai/gpt-oss-20b` (OpenAI GPT-OSS, 20B parameters, open weights)
- `groq/openai/gpt-oss-120b` (OpenAI GPT-OSS, 120B parameters, open weights)

Two distinct model families. Four parameter scales. Same `extraction` case: model receives a short text containing a name + email, and must return the email. Invariant: `contains: [<the email>]`.

---

## 1. The systemic finding

Start with what `history` reveals across the bundle:

```text
$ falsifyai history extraction --store-path docs/case-studies/data/case-study-replays.db
falsifyai history | case: extraction
=================================================================
  dc4f624f  2026-05-22T22:45:08.925248+00:00  FRAGILE  0.00 (CI: 0.00-1.00)  worst: typo_noise
  4332c0d2  2026-05-22T08:36:20.359784+00:00  FRAGILE  0.00 (CI: 0.00-0.00)  worst: typo_noise
  7e512994  2026-05-22T08:36:11.379726+00:00  FRAGILE  0.00 (CI: 0.00-0.00)  worst: typo_noise
  4216f07e  2026-05-22T08:34:06.109802+00:00  FRAGILE  0.00 (CI: 0.00-0.00)  worst: typo_noise
  8ea9bb18  2026-05-22T08:33:56.141691+00:00  FRAGILE  0.00 (CI: 0.00-1.00)  worst: typo_noise
  7755b34f  2026-05-21T23:31:25.898229+00:00  FRAGILE  0.00 (CI: 0.00-0.00)  worst: typo_noise
  24336c21  2026-05-21T23:31:18.090587+00:00  FRAGILE  0.00 (CI: 0.00-1.00)  worst: typo_noise
=================================================================
7 sessions matched
```

Seven sessions. Four distinct models. Two model families. Same case, same perturbation family triggering the same brittleness in every one. The verdict is `FRAGILE` for every run; the worst-case perturbation is `typo_noise` for every run.

This is the systemic observation:

> Contracts that appear reliable under clean inputs can remain brittle under minor real-world perturbations.

The finding is *not* "these models are bad at extraction." Each of these models handles the *baseline* input correctly — extraction is solvable, and each model demonstrably solves it when the prompt arrives clean. The finding is about what happens at the boundary between the *clean input space* and the *actual inputs production systems receive*: a misspelled name, a stray character in a copy-pasted email — and the `contains` invariant fails.

Two implications:

1. **Reliability-contract design is not absorbed into model selection.** Choosing a larger model does not close this gap; the 120B-parameter model fails just as cleanly as the 8B-parameter one. The brittleness lives at the contract layer, not the capability layer.
2. **Cross-cutting perturbation testing reveals what benchmarks compress out.** Standard benchmarks score models on clean inputs; the brittleness only surfaces when the input distribution shifts a small but realistic distance. `history` is the surface that makes this *persistent failure class* visible across the temporal/model axis.

That is enough to motivate a contract-redesign conversation. But systemic patterns are useful in aggregate — and migrations fail one session at a time.

---

## 2. The migration regression

Suppose you are considering swapping the production model `groq/llama-3.3-70b-versatile` for the candidate `groq/openai/gpt-oss-120b` — a larger model, presumed more capable on reasoning-heavy cases like `policy_summary`. Same spec, two runs:

```text
$ falsifyai diff 7e51299481d5420d9181e71ba0449348 4332c0d246bc4b3e875392ecdf3b1780 \
    --store-path docs/case-studies/data/case-study-replays.db
Diff: baseline 7e51299481d5420d9181e71ba0449348 -> candidate 4332c0d246bc4b3e875392ecdf3b1780
Store: docs/case-studies/data/case-study-replays.db
=================================================================
case: policy_summary  baseline: STABLE (1.00)  candidate: FRAGILE (0.00)  REGRESSED
=================================================================
1 regressed, 0 improved, 3 unchanged, 0 other, 0 added, 0 removed
```

The command exits with code 5: `REGRESSION`. The `policy_summary` case dropped from STABLE (1.00 confidence) to FRAGILE (0.00 confidence) when the model changed. Three other cases — `extraction`, `factual_recall`, `structured_output` — held steady. (`extraction` was already FRAGILE on both, consistent with the systemic finding above; `diff` correctly reports it as `unchanged`.)

`diff` tells you the contract that held before has stopped holding. It does not tell you *why*. To learn why, ask `inspect`.

---

## 3. Expanding the evidence

```text
$ falsifyai inspect 4332c0d246bc4b3e875392ecdf3b1780 --case policy_summary \
    --store-path docs/case-studies/data/case-study-replays.db
Inspecting session 4332c0d246bc4b3e875392ecdf3b1780 | created_at 2026-05-22T08:36:20.359784+00:00 | falsifyai 0.1.0 | store docs/case-studies/data/case-study-replays.db
=================================================================
case: policy_summary  verdict: FRAGILE  confidence: 0.00 (CI: 0.00-0.00)  perturbations: 5  worst: typo_noise
  baseline input:   Summarize this refund policy in one sentence: Customers can request a refund within 30 days if the item is unused and the receipt is provided.
  baseline output:  Customers may receive a refund within 30 days of purchase if they return the unused item with a receipt.
  [1] typo_noise (character_mutations):
    perturbed input:  Summarize this revund policy in one sentence: Cutmoersl can request a refund within 30 days if the item is unused and the receipt is provided.
    output excerpt:   Customers can request a refund within 30\u202fdays, provided the item is unused and they present a receipt.
      invariant: contains FAIL -- missing 1 of 3 required values
  [2] typo_noise (character_mutations):
    perturbed input:  Summarize this refund polgcy in one sentence: Customers can rquest a refunxd withi 30 days if the itkm is unused and the receipt is prvoivded.
    output excerpt:   Customers may receive a refund within 30\u202fdays, provided the item is unused and they present a receipt.
      invariant: contains FAIL -- missing 1 of 3 required values
  [3] casing (upper):
    perturbed input:  SUMMARIZE THIS REFUND POLICY IN ONE SENTENCE: CUSTOMERS CAN REQUEST A REFUND WITHIN 30 DAYS IF THE ITEM IS UNUSED AND THE RECEIPT IS PROVIDED.
    output excerpt:   Customers may receive a refund within 30 days if they return an unused item with a receipt.
      invariant: contains PASS -- all required values present
  [4] casing (lower):
    perturbed input:  summarize this refund policy in one sentence: customers can request a refund within 30 days if the item is unused and the receipt is provided.
    output excerpt:   Customers may receive a refund within 30\u202fdays of purchase, provided the item is unused and they present a receipt.
      invariant: contains FAIL -- missing 1 of 3 required values
  [5] casing (title):
    perturbed input:  Summarize This Refund Policy In One Sentence: Customers Can Request A Refund Within 30 Days If The Item Is Unused And The Receipt Is Provided.
    output excerpt:   Customers may receive a refund within 30 days of purchase if the item is unused and they provide a receipt.
      invariant: contains PASS -- all required values present
=================================================================
4 cases, verdict FRAGILE, 2 FRAGILE, 0 CONSISTENTLY_WRONG, falsifiability 0.36
```

> **A note on rendering**: the `\u202f` you see in three of the five output excerpts above is what your terminal will show when its encoding cannot represent the actual character literally — for example, Windows `cp1252` consoles. FalsifyAI uses `backslashreplace` error handling on its output streams so the byte is always *visible* somehow. On a UTF-8 terminal the same command renders the character as an actual narrow space, in which case the substitution becomes invisible on screen but is still present in the bytes. The artifact bytes are identical either way — that is what `replay` and `inspect` are reading from. Section 4 explains what the byte is and why it matters.

Look at the diff between the baseline output and perturbation [1]:

- **Baseline output** (no perturbation): `Customers may receive a refund within 30 days of purchase...`
- **Perturbation [1] output**: `Customers can request a refund within 30\u202fdays, provided...`

Reading the perturbation output aloud, the meaning is correct — same answer, same time window, same conditions. A human reviewer, an LLM judge, even a `semantic_equivalence` invariant would all agree: same meaning. But the `contains` invariant, checking for the literal string `"30 days"`, fails.

The reason is `\u202f`.

---

## 4. The invisible character

`\u202f` is **NARROW NO-BREAK SPACE** (U+202F). Visually indistinguishable from a regular space in most fonts. Conceptually distinct: it is a typographic character intended to prevent line breaks between paired tokens — numbers and units, currency and amounts, abbreviations and their referents. Byte-wise it is three bytes in UTF-8 (`0xE2 0x80 0xAF`) versus one byte for an ASCII space.

The candidate model — `groq/openai/gpt-oss-120b` — sometimes emits U+202F between `"30"` and `"days"` when its output is summarizing a time span. Three of the five perturbations in the session trigger it (rows [1], [2], [4]); the other two do not (rows [3], [5]). It is not strictly deterministic, and it is not always present — it appears more often under perturbation than under clean input. The baseline output (no perturbation) does not contain it.

The baseline model — `groq/llama-3.3-70b-versatile` — does not exhibit this behavior. Its outputs use regular ASCII space throughout, which is why `policy_summary` was STABLE in the baseline session.

The downstream impact, made concrete:

- `output.contains("30 days")` returns `False`.
- A regex `\d+ days` misses on most engines unless `\s` is configured to match Unicode space classes.
- A search index built on substring matches will not index the phrase.
- A localization layer mapping `"30 days"` to a translation will fall through to a default.
- A compliance check verifying a stated time window against a stored policy string will report mismatch.

This is the dual-modality of stochastic systems: the visible answer is correct, the byte-level contract is broken. The model has not lied. It has rendered the correct meaning in a slightly different representation, and the representation difference is invisible to the eye and load-bearing to every downstream consumer that treats text as bytes.

---

## 5. Why semantic matching would miss this

This is the section the case exists for.

Consider three approaches to checking the model's policy summary:

1. **Literal `contains`** (what this spec uses): looks for the exact byte sequence `30 days`. *Fails* on the candidate because `30\u202fdays` ≠ `30 days`.
2. **LLM-judge semantic match**: passes the output to a stronger model and asks "does this answer the question?" *Passes* on the candidate because the answer is semantically correct.
3. **Embedding cosine similarity** (e.g., `semantic_equivalence` invariant): embeds both strings and compares. *Passes* on the candidate because embedding distance is dominated by the semantic content, not the single-character difference.

Reading the same evidence, the three approaches return three different verdicts. *The model's behavior did not change between approaches; the contract being checked did.*

A common reaction to this is "approach 2 or 3 is correct; the model gives the right answer." That reaction is reasonable for a *help-system* output, where the human reader is the consumer. It is incorrect for a *contract* with downstream systems. Consider any of these realistic downstream consumers:

- A regex extractor pulling structured fields out of generated summaries
- A search index built on substring matches
- A telemetry pipeline counting occurrences of `"30 days"` to surface refund-policy mentions
- A localization layer mapping `"30 days"` to a translated equivalent
- An automated compliance check verifying that a stated time window matches a stored policy

Every one of those breaks silently on `30\u202fdays`. The output passes any *human* check, passes any *semantic* check, and fails the *contractual* check that the downstream system actually performs. The bug is invisible at every layer humans look at, and present at every layer machines read.

**The pedagogical point**: reliability contracts are not validated by asking *"is this correct?"* They are validated by asking *"does this satisfy the constraint downstream systems depend on?"* A literal `contains` invariant checks the latter. Semantic checks check the former. Both are useful; neither replaces the other; they answer different questions.

This is what FalsifyAI means by *orthogonal pressure*: the `contains` and `semantic_equivalence` invariants exert different reliability pressure on the same output. A model can satisfy one and fail the other, and the difference is operationally meaningful.

---

## 6. Reproducing this from the bundle

Every command shown above runs against the bundled SQLite. No model calls, no API keys, no external dependencies — just the preserved artifacts. The bundle is the case study's *evidence*.

```bash
# 1. Install FalsifyAI
pip install falsifyai==0.1.0

# 2. Verify the bundle's integrity
python -c "import hashlib; \
  print(hashlib.sha256(open('docs/case-studies/data/case-study-replays.db','rb').read()).hexdigest())"
# expected: 88d8ced06cf5895e766fe3149ab7a9d404d0eccc9bdfd1577bc23c7b4e506e0f

# 3. Reproduce the systemic finding (Section 1)
falsifyai history extraction \
    --store-path docs/case-studies/data/case-study-replays.db

# 4. Reproduce the migration regression (Section 2; exit code 5)
falsifyai diff 7e51299481d5420d9181e71ba0449348 4332c0d246bc4b3e875392ecdf3b1780 \
    --store-path docs/case-studies/data/case-study-replays.db

# 5. Reproduce the evidence expansion (Sections 3-4)
falsifyai inspect 4332c0d246bc4b3e875392ecdf3b1780 --case policy_summary \
    --store-path docs/case-studies/data/case-study-replays.db

# 6. Re-render the full session
falsifyai replay 4332c0d246bc4b3e875392ecdf3b1780 \
    --store-path docs/case-studies/data/case-study-replays.db
```

Each command reads only the preserved artifact. None re-resolves a verdict; none calls a model; none aggregates or infers trend. They read what was preserved at run time.

This is the recursion the project's positioning rests on: the claim that FalsifyAI's evidence is replayable is itself demonstrated by an artifact you can replay.

---

## 7. Synthesis — one evidence substrate, multiple consumer surfaces

The four CLI surfaces used in this case study read the *same preserved evidence* — the rows in [`case-study-replays.db`](data/case-study-replays.db) — and answer different questions:

| Surface | Question it answers | What it shows |
|---|---|---|
| `falsifyai history <case_id>` | Is this brittleness a persistent class? | Compressed timeline of the case across sessions. |
| `falsifyai diff <a> <b>` | Did anything regress between two specific sessions? | Per-case verdict transitions; exit 5 on regression. |
| `falsifyai inspect <session> --case <id>` | What evidence supports the verdict? | Per-perturbation inputs, outputs, invariant outcomes. |
| `falsifyai replay <session>` | What did this session verdict-out as? | The session re-rendered exactly as saved. |

None of these surfaces produced new evidence. None aggregated, averaged, or inferred trends. None re-resolved a verdict. They are *readers* of preserved evidence — each compressing the artifact along a different axis to answer a different operational question.

This is the architectural point the case study exists to demonstrate:

> Reliability claims about a stochastic system are only defensible if the evidence supporting them is preserved and replayable. FalsifyAI's job is to produce that preserved evidence — and then to provide consumer surfaces that compress it along the axes operators actually need.

The U+202F substitution is memorable; the cross-model extraction brittleness is rigorous. Both are real findings from one real campaign. The point is not either finding in isolation — it is that *one preserved evidence substrate* surfaces both, and the consumer surfaces over it answer the operational questions a team will actually ask: *is this a pattern? did something regress? what is the evidence? show me the run.*

---

## Reproduction checklist

- [ ] `pip install falsifyai==0.1.0`
- [ ] Clone this repository or download [`case-study-replays.db`](data/case-study-replays.db) (SHA256 above)
- [ ] Run each command in Section 6
- [ ] Confirm that every output matches what is shown in this document

If any command's output differs from what is shown here, please [file an issue](https://github.com/ericckzhou/falsifyai/issues) — the bundle is the test.

## Related reading

- [`README.md`](../../README.md) — top-level project README
- [`docs/EVIDENCE.md`](../EVIDENCE.md) — evidence-infrastructure positioning
- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) — three-layer architecture (generation / interpretation / preservation)
- [`docs/case-studies/data/README.md`](data/README.md) — bundle provenance and session-to-model mapping
- [`plan.md`](../../plan.md) — full project plan
