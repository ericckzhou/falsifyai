# Case Study 08: How fragile, exactly? The minimal falsifier

[Case study 07](07-the-regression-that-only-appeared-under-pressure.md) proved the cost-saving migration *drops a contract clause under pressure*. This one measures **how much pressure it takes** — and finds the cheaper model breaks at a far lower threshold than the incumbent.

> **One sentence**: `falsifyai minimize` sweeps `typo_noise` from low to high and stops at the smallest strength that flips a case out of `STABLE` — the *minimal falsifier* — and on the same promo-summary contract from CS-07 the 8B candidate first leaves `STABLE` at `0.05` in every run while the 70B baseline holds `STABLE` through `0.1` in every run and doesn't break until `0.2–0.4`: a 4× (up to 8×) fragility-threshold gap that the clean eval, and even CS-07's single fixed-pressure run, could not quantify.

> **What this is**: the explicit *quantification companion* to CS-07 — the same relationship 04 and 05 have to 03. CS-07 showed *that* the migration breaks the gift-card-exclusion contract under `rate: 0.12` noise; it picked one pressure level and showed a regression there. The obvious next question for an adopter is **"how close to the edge was the incumbent, and how much closer did the migration move us?"** `minimize` answers it by reporting the *threshold* instead of a scatter of pass/fail points. This is pillar-#1 — evidence density — made literal: the single smallest falsifier is the maximally informative fact about a case's fragility.

> **Form**: unlike 01 and 03–07, this case study has **no frozen evidence bundle**. `minimize` is an *orchestrator* (like `run`), not a consumer of stored artifacts (like `diff` / `inspect`): it generates, executes, resolves, and **prints** a report — it does not write a `ReplayStore`. So CS-08 follows the [case study 02](02-resolver-arbitration-boundary-shift.md) pattern: **reproducible from the committed spec**, with the reports captured verbatim below. The specs are CS-07's, unchanged — [`probe-07/candidate-promo-8b.yaml`](probe-07/candidate-promo-8b.yaml) and [`probe-07/baseline-promo-70b.yaml`](probe-07/baseline-promo-70b.yaml), case `promo_faq_summary`, contract `contains: ["gift card"]`, `groq` at `temperature 0.0`, `seed 42`, `falsifyai 0.6.4`.

---

## 1. The question CS-07 left open

CS-07 is a *yes/no* result at a *fixed* pressure: at `typo_noise` `rate: 0.12`, the 70B holds `STABLE` and the 8B degrades to `AMBIGUOUS`, so `diff` reports a regression (exit 5). That is the right shape for *catching* a migration in CI. It is the wrong shape for *characterizing* one. `0.12` was a chosen number; it tells you the candidate is worse *there*, not where the cliff actually is for either model.

The reliability question an adopter actually has is about the **margin**: real-world input noise is not a dial you set to 0.12, it is whatever your users type. So: at what noise level does each model first stop being stable? The distance between those two levels is the migration's true cost in robustness, and it is invisible to any single-pressure test.

## 2. The two minimal falsifiers

`minimize` sweeps the default ladder `0.02, 0.05, 0.1, 0.2, 0.4, 0.8` with 5 samples per level, ascending, and stops at the first strength that resolves to a non-`STABLE` verdict — so the reported strength is genuinely the smallest among the tested levels, and the search costs no more model calls than it must.

The candidate — `llama-3.1-8b-instant`, the cost downgrade — first leaves `STABLE` at the second rung of the ladder:

```text
$ falsifyai minimize docs/case-studies/probe-07/candidate-promo-8b.yaml --family typo_noise
falsifyai minimize | case: promo_faq_summary | family: typo_noise
============================================================
  strength 0.02   ->  STABLE
  strength 0.05   ->  AMBIGUOUS  <-- minimal falsifier
============================================================
minimal falsifier: typo_noise strength=0.05 -> AMBIGUOUS
```

The baseline — `llama-3.3-70b-versatile`, the incumbent — walks three more rungs up the same ladder before it breaks:

```text
$ falsifyai minimize docs/case-studies/probe-07/baseline-promo-70b.yaml --family typo_noise
falsifyai minimize | case: promo_faq_summary | family: typo_noise
============================================================
  strength 0.02   ->  STABLE
  strength 0.05   ->  STABLE
  strength 0.1    ->  STABLE
  strength 0.2    ->  AMBIGUOUS  <-- minimal falsifier
============================================================
minimal falsifier: typo_noise strength=0.2 -> AMBIGUOUS
```

## 3. The threshold gap — the finding

The reports above are each one representative run. The thresholds are produced live against a hosted API, so they are not bit-stable, and the study was run repeatedly to read the *band* rather than a point. Across three runs per model:

| Model | Run 1 | Run 2 | Run 3 | Observed minimal falsifier | Stable through |
|---|---|---|---|---|---|
| Candidate `8B` | `0.05` | `0.05` | `0.05` | **`0.05`** (3/3 identical) | `0.02` |
| Baseline `70B` | `0.2` | `0.2` | `0.4` | **`0.2–0.4`** | `0.1` (every run) |

The candidate's threshold is unusually sharp — every run breaks at exactly `0.05`. The baseline's wanders between `0.2` and `0.4`, which is the expected non-determinism of a live model near its own boundary. But the wander never threatens the finding, because the two bands **do not touch**: in every run, the candidate had already left `STABLE` at a strength where the baseline was still solidly `STABLE`. Reading the gap conservatively — the candidate's `0.05` against the baseline's *earliest* break at `0.2` — the migration **cut the fragility threshold by 4×** (and by 8× against the baseline's `0.4` runs). Same task, same contract, same perturbation family; the only change is the one line CS-07 called the migration, and the model's tolerance for messy input fell by at least four-fold.

Note what is *not* different: the verdict. Both models, once they break, break to the same `AMBIGUOUS` — the contract loses worst-case stability the same way. `minimize` isolates the fragility axis (how much pressure) from the failure-mode axis (what breaks). CS-07 fixed the pressure and read the failure mode; CS-08 fixes the failure mode and reads the pressure. The migration did not introduce a new way to fail — it moved the existing failure much closer to ordinary input.

## 4. Why the threshold is the load-bearing evidence

A naïve robustness report dumps the whole grid: *fails at 5%, and 10%, and 20%, and 40%...* for each model, and asks the engineer to find the cliff in the noise. The cliff is the only part that carries a decision. Everything above the threshold is redundant (you already know it breaks); everything below is reassurance you did not need to enumerate. The minimal falsifier compresses the grid to its one load-bearing number — and `minimize`'s ascending-with-early-stop search means the tool spends model calls only on the rungs that earn their place, never past the answer.

That is the evidence-density principle as an executable: *report the threshold, not the scatter.* The headline of this case study is a single comparison — `0.05` vs `0.2–0.4` — and it is enough to tell an adopter exactly what the migration cost them in margin. More data points would not have made the decision better; they would have crowded the surface where the decision lives.

## 5. What this does not claim

- **Not a benchmark.** One case, one contract, one perturbation family. `0.05` and `0.2` are not "the fragility" of these models — they are this contract's thresholds under this noise, measured to expose the *gap*, which is the only quantity claimed.
- **Not a stable absolute.** The baseline's threshold was observed at both `0.2` and `0.4`; the absolute number wobbles by design (live API). The finding is the **separation between the two bands**, which held in every run, not either endpoint.
- **Not a leaderboard.** This is not "70B beats 8B." The 8B is `STABLE` on other tasks elsewhere in this repo. The claim is about *this deployment's margin* and how a specific migration eroded it — a property of the choice, not a grade of the model.
- **Not a frozen artifact.** `minimize` prints; it does not preserve a `ReplayStore`. Reproducibility here comes from the committed spec, not a bundled `.db` — re-running the commands below re-materializes the search live.

---

## Reproduction

```bash
# Needs GROQ_API_KEY. minimize re-materializes live; outputs are not bit-stable,
# so run each 2-3x and read the band, not a single point (see §3).
falsifyai minimize docs/case-studies/probe-07/candidate-promo-8b.yaml --family typo_noise
#   -> minimal falsifier ~0.05 (3/3 runs)
falsifyai minimize docs/case-studies/probe-07/baseline-promo-70b.yaml --family typo_noise
#   -> minimal falsifier 0.2-0.4; STABLE through 0.1 every run
```

The default sweep is `--levels 0.02,0.05,0.1,0.2,0.4,0.8 --samples 5`; narrow it (e.g. `--levels 0.1,0.2`) to confirm the decision boundary in fewer calls.

## Synthesis

CS-07 caught the migration; CS-08 measures it. The same one-line change that dropped a gift-card exclusion under `0.12` noise is, viewed through `minimize`, a four-fold collapse of the input-noise margin: the incumbent tolerated character corruption up to `0.1` comfortably, the downgrade started failing at `0.05`. The decision the adopter faces — *is the cost saving worth it?* — is now priced in the currency that matters, the distance to the cliff, expressed as the single smallest number that reaches it. That compression from a robustness grid to one threshold is not a presentation choice; it is the framework's thesis that the minimal falsifier is the densest evidence a fragility claim can carry.
