# When the test deletes the question: a generation-layer self-falsification

> **One sentence**: hunting a genuine weak-model failure, the probe instead caught FalsifyAI corrupting its *own* experiment — a paraphrase that deleted the task's grounding slipped the cosine validity gate, drove the model to refuse, and the refusal was scored as `CONSISTENTLY_WRONG` over a model that is actually correct.

> **Evidence bundle**: [`data/probe-06.db`](data/probe-06.db) (before) · SHA256 `42fec34dd31d70484c19b54a124d4af8206ccbcf656ae11fcdc5ea9f59a81b66` — and [`data/probe-06-fixed.db`](data/probe-06-fixed.db) (after the fix) · SHA256 `6910cef689051570ba7917c9641693884136c8ac8af0e3d8da005dc718a7a7bc`. 1 case each, `llama-3.1-8b-instant`, `--nli`, produced under `falsifyai 0.6.3` + the fix in this PR. Spec: [`probe-06/candidate-extraction-8b.yaml`](probe-06/candidate-extraction-8b.yaml).

> **What this is**: the third member of the self-falsification trilogy, one per architectural layer. [Case study 03](03-evaluator-false-positive.md) caught the *interpretation* layer assigning a false verdict; [case study 05](05-confidence-floor-inversion.md) caught the *presentation* layer mislabeling a correct number; this catches the **evidence-generation** layer running an *invalid experiment*. The first two misread a valid run. This one is sharper: the falsification tool **falsified its own input**.

---

## Setup — a deliberately weaker model

[probe-03/RESULTS.md](probe-03/RESULTS.md) closed by naming the un-mined path to a *real* confidently-wrong model: re-probe a **weaker** model with tighter invariants. probe-06 does exactly that — the same access-policy extraction task that `llama-3.3-70b` aced (case study 03, candidate 3), now against `llama-3.1-8b-instant` (the same downgraded model that produced the genuine `CONSISTENTLY_WRONG` in [case study 04](04-overconfident-negation.md)). The hypothesis: the 8B model drops the "only administrators may delete" qualifier and emits well-formed-but-wrong JSON.

It didn't. It surfaced something more interesting.

---

## 1. The finding: a manufactured `CONSISTENTLY_WRONG` over a correct model

```text
case: access_policy_extraction_8b  verdict: CONSISTENTLY_WRONG  confidence: 0.00 (CI: 0.00-0.00)  perturbations: 11
```

`inspect` over the 11 perturbations splits cleanly in two:

- **Baseline + all 3 `typo_noise` [1–3]: the model is correct** — `{"allowed":["read"],"forbidden":["delete","export"]}`, `schema_match` PASS, `semantic_equivalence` cosine ~0.99. The 8B model keeps the admin-delete qualifier even with the input characters mangled.
- **All 8 `paraphrase` slots [4–11] are byte-identical** and read:

  > perturbed input: `For a standard (non-admin) user, based on this access policy, the output will be {"allowed":["read records"],"forbidden":["delete records","export records"]}`

  The paraphrase **deleted the access-policy body** ("All users may read records. Only administrators may delete records. No user may export records.") and embedded a fabricated answer in its place. Given a prompt that refers to "this access policy" but contains none, the model does the *reasonable* thing:

  > output: `It seems like you're describing an access control system. However, I don't see the access policy you're referring to…`

  Eight identical refusals, scored against the reference as eight stable failures → `CONSISTENTLY_WRONG` at a bootstrap CI that collapses to `0.00–0.00`.

The model never failed. The **experiment** failed — and the framework reported the experiment's corruption as the model's unreliability.

---

## 2. The mechanism: a topical gate cannot see an omission

[`paraphrase.py`](../../falsifyai/perturbation/paraphrase.py) validity-gates every rewrite, but with **embedding cosine similarity** (`is_valid = similarity >= 0.85`, `method="embedding_cosine"`). Cosine is *symmetric* and *topical*: the bad paraphrase keeps every salient token — *access policy, non-admin user, allowed, forbidden, read, delete, export* — so it embeds far above 0.85 to the original and passes, even though it dropped the clauses that make the task answerable.

[plan.md §9.3](../../plan.md) specified the default validity check as a `BidirectionalNLIValidator` — *"original entails perturbed AND perturbed entails original."* That direction is exactly what catches an omission: the perturbed text does **not** entail the original's deleted clauses, so the reverse direction falls out of ENTAILMENT and the paraphrase is rejected. But `validity.py` **was never built** — cosine was the MVP stand-in, and the NLI gate was an unimplemented design anchor. Compounding it: the run *had* an NLI backend (this is a `--nli` run), but `--nli` provisioned it only for the interpretation-layer oracles, never for the generation-layer validity gate.

A secondary defect rides along: all 8 paraphrase slots are **identical** (the paraphrase LLM runs at temperature 0, so `sample_index` 0–7 produce the same rewrite). `count: 8` bought one distinct paraphrase repeated eightfold — and eight identical "wrong" samples is what collapsed the CI to `0.00–0.00`, amplifying the false positive from a wobble into a verdict.

---

## 3. Why it matters

03 and 05 each misread a *valid* experiment — the perturbations were sound and the model's behavior was real; only the verdict (03) or the label (05) was wrong. Here the perturbation itself is invalid, so there is no real experiment to read. This is the most dangerous failure of the three because it is invisible at the headline: a `CONSISTENTLY_WRONG @ 0.00` is indistinguishable from a true positive until you `inspect` the perturbed inputs and notice the question is gone. A falsification framework that silently falsifies its own inputs cannot be trusted to falsify a model's.

---

## 4. The fix: build the gate the plan specified

This PR creates [`perturbation/validity.py`](../../falsifyai/perturbation/validity.py) — the `BidirectionalNLIValidator` from §9.3 — and routes the **already-provisioned** `--nli` backend into the paraphrase gate. A cosine-passing paraphrase must now *also* entail and be entailed by the original; an omission fails the reverse direction and is rejected. The NLI logic lives in the perturbation package (generation layer); the resolver is untouched. Default (`--nli`-less) runs keep the cosine-only gate **byte-identical** — no behavior change where the NLI backend was never loaded.

Re-running the *same* spec with the fix:

```text
# before (cosine-only gate):
case: access_policy_extraction_8b  verdict: CONSISTENTLY_WRONG  confidence: 0.00  perturbations: 11

# after (bidirectional NLI gate):
case: access_policy_extraction_8b  verdict: STABLE  confidence: 1.00 (CI: 1.00-1.00)  perturbations: 3
```

The 8 invalid paraphrases are rejected and dropped (`max_attempts` exhausted on a degenerate rewrite); the 3 valid `typo_noise` perturbations remain, all correct, and the model is assessed as what it is — **STABLE**. The paraphrase family's documented promise that *"returning fewer than count is a legitimate honest signal"* now holds: an unreliable perturbation method shrinks the evidence instead of poisoning the verdict.

---

## Reproduction

```bash
# Before: the manufactured verdict is preserved in the bundled store (read-only):
falsifyai inspect 197d4b5606f44d32bbb97ff200ef866a --case access_policy_extraction_8b --full \
    --store-path docs/case-studies/data/probe-06.db
#   → CONSISTENTLY_WRONG; paraphrase slots [4-11] have the policy body deleted.

# After: re-materialize against the live 8B model with the fix in place:
falsifyai run docs/case-studies/probe-06/candidate-extraction-8b.yaml --nli \
    --store-path /tmp/probe-06-repro.db
#   → STABLE; the 8 invalid paraphrases are rejected, 3 valid typo_noise remain.
#   (Needs GROQ_API_KEY; the after-store ff713ddf… is bundled as probe-06-fixed.db.)
```

---

## Synthesis

One probe, aimed at a model, hit the framework instead — for the third time, and on the one layer the first two left untouched. The generation layer's job is to manufacture *valid* pressure; here it manufactured a question with no content and then graded the model for not answering it. The cosine gate was never wrong about similarity — the bad paraphrase *is* topically similar — it was asked to certify a property (intent preservation) that similarity cannot express. The fix is not a smarter threshold; it is the right relation: entailment, both directions, exactly as the plan specified before the MVP cut deferred it. The discipline that caught this is the same one every case study turns on — **inspect the preserved evidence; never trust the headline** — applied now to the framework's own inputs.
