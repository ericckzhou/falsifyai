# probe-06 — weak-model extraction re-probe

A single-spec probe that became [**case study 06 — When the test deletes the
question**](../06-perturbation-validity-omission.md).

## Origin

[probe-03/RESULTS.md](../probe-03/RESULTS.md) closed by naming the un-mined path
to a genuine confidently-wrong *model*: re-probe a **weaker** model with tighter
invariants. The access-policy extraction task that `llama-3.3-70b` aced (probe-03
candidate 3) is re-aimed here at `llama-3.1-8b-instant` — the same downgraded
model that produced the real `CONSISTENTLY_WRONG` in case study 04.

**Hypothesis:** the 8B model drops the "only administrators may delete" qualifier
and emits well-formed-but-wrong JSON.

## Outcome

> **The model was correct; the *experiment* was not.** The 8B model answered the
> extraction task correctly on the baseline and all `typo_noise` variants. The
> `paraphrase` perturbation, however, produced an `llm_rewrite` that **deleted
> the access-policy body** and embedded a fabricated answer — an invalid
> perturbation that slipped the cosine validity gate and drove the model to
> refuse. Eight identical refusals scored as `CONSISTENTLY_WRONG @ 0.00`.

That manufactured false positive — and the generation-layer fix it drove (the
§9.3 `BidirectionalNLIValidator`) — is the published [case study 06](../06-perturbation-validity-omission.md).

## Files

| File | What |
|---|---|
| [`candidate-extraction-8b.yaml`](candidate-extraction-8b.yaml) | The probe spec (access-policy extraction, `llama-3.1-8b-instant`, `--nli`). |
| [`../data/probe-06.db`](../data/probe-06.db) | **Before** the fix: `CONSISTENTLY_WRONG @ 0.00`, 11 perturbations (8 invalid paraphrases). Session `197d4b5606f44d32bbb97ff200ef866a`. |
| [`../data/probe-06-fixed.db`](../data/probe-06-fixed.db) | **After** the fix: `STABLE @ 1.00`, 3 perturbations (8 invalid paraphrases rejected and dropped). Session `ff713ddffa3643ae856f4cc7ae73c732`. |

## Reproduce

```bash
# Before (read-only over the preserved store):
falsifyai inspect 197d4b5606f44d32bbb97ff200ef866a --case access_policy_extraction_8b --full \
    --store-path docs/case-studies/data/probe-06.db

# After (live; needs GROQ_API_KEY):
falsifyai run docs/case-studies/probe-06/candidate-extraction-8b.yaml --nli \
    --store-path /tmp/probe-06-repro.db
```
