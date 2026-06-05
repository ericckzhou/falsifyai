# probe-05 — the grounding-verdict quartet

A probe that turns the **both-directions** scrutiny of case studies 03/04 on the
four verdicts the 0.6.0 release added but never battle-tested on real model
output: `INFORMATION_PRESENT`, `INFORMATION_NULL`, `ADVERSARIALLY_VULNERABLE`,
and `AMBIGUOUS`. CS-03/04 proved `CONSISTENTLY_WRONG` fires when it should and
stays silent when it shouldn't — and found a real bug doing it. These verdicts
have had no equivalent test. This probe is engineered to make each one fire on a
real model, and documents what the *other* outcome would mean so a run that
*doesn't* produce the target verdict is still informative.

> **STATUS (2026-06-05): RAN.** Executed live against Groq (A/B/C on
> `llama-3.3-70b-versatile`, D on `llama-3.1-8b-instant`); evidence bundled at
> [`../data/probe-05.db`](../data/probe-05.db) (provenance in
> [`../data/README.md`](../data/README.md#probe-05db--grounding-verdict-quartet)).
> **Outcome: 1 of 4 targets fired — `INFORMATION_PRESENT` (candidate A), and only
> after the probe caught a real perturbation-validity bug.** The other three are
> honest negatives: a capable 70B (and the 8B for D) resists the failure modes
> B/C/D were designed to elicit. The verdict-boundary table below was the
> *hypothesis*; [Run results](#run-results-2026-06-05) records what actually fired.

## Why these four

0.6.0 completed the 8-verdict taxonomy (plan.md §2), but only `CONSISTENTLY_WRONG`
and the original five have been exercised on live models (CS-01 through CS-04).
The four added verdicts are the **least-proven part of the epistemic core**, and
two of them (`INFORMATION_PRESENT`, `INFORMATION_NULL`) are reachable only through
the new oracle layer. A verdict you can trust is one demonstrated in *both*
directions; that demonstration is missing for these four. Closing it is squarely
the dogfooding discipline — evidence over assertion.

## The four candidates

| Spec | Target verdict | Mechanism | NLI? |
|------|----------------|-----------|------|
| [`candidate-a-grounded-fact.yaml`](candidate-a-grounded-fact.yaml) | **INFORMATION_PRESENT** | answer entailed by the grounding source, stable under perturbation | **yes** |
| [`candidate-b-stable-refusal.yaml`](candidate-b-stable-refusal.yaml) | **INFORMATION_NULL** | underspecified question → a *stable hedge* ("it depends") — consistent but empty | no |
| [`candidate-c-targeted-unicode.yaml`](candidate-c-targeted-unicode.yaml) | **ADVERSARIALLY_VULNERABLE** | `unicode` family breaks while `casing` family holds → a *targeted* shape | no |
| [`candidate-d-thin-evidence.yaml`](candidate-d-thin-evidence.yaml) | **AMBIGUOUS** | small N (count: 3) → bootstrap CI too wide to discriminate | no |

Each probes a distinct cell of the 2-D verdict grid, not one trick four ways:
the *grounded* cell, the *stable-but-empty* cell, the *targeted-instability*
cell, and the *thin-evidence* cell.

## Verdict-boundary hypotheses (the both-directions table)

Every row is traced to `falsifyai/verdict/resolver.py:_decide_verdict` (the
8-verdict priority chain) and the oracles it reads. "Silence direction" is the
outcome that proves the instrument is not over-firing — the half CS-03/04 showed
matters most.

| Candidate | Path to the target verdict | Silence direction (must NOT mis-fire) |
|-----------|----------------------------|----------------------------------------|
| A — grounded | stable band (worst-family CI low ≥ 0.95) **and** `GroundingOracle` finds reference ⊨ output (majority ENTAILMENT) → `INFORMATION_PRESENT` | without `--nli` the oracle is inert → plain `STABLE`; a stable-but-*wrong* answer would trip `HallucinationOracle` (CONSISTENTLY_WRONG), never grounding |
| B — hedge | stable band **and** `InformationNullOracle` finds a refusal/hedge marker in ≥ 50% of outputs → `INFORMATION_NULL` | a valid *terse* commitment ("Buy.") is **not** flagged null (the oracle keys on hedge markers, not length) → `STABLE` |
| C — targeted | instability band (worst-family CI low < 0.95) **and** `failure_shape == "targeted"` — `unicode` broken (CI low < 0.5) while `casing` holds (CI low ≥ 0.8) → `ADVERSARIALLY_VULNERABLE` | both families holding → `STABLE`/`INFORMATION_PRESENT`; both breaking → `FRAGILE` (diffuse, no holding family to contrast) |
| D — thin | instability band, **not** targeted, CI high ≥ 0.5 (wide CI from N=3) → `AMBIGUOUS` | raising `count` resolves it → `STABLE` (all pass) or `FRAGILE` (all fail). AMBIGUOUS must not persist once evidence is sufficient |

The discriminating insight: candidates C and D both enter the *instability band*,
yet must split — C into `ADVERSARIALLY_VULNERABLE` (a real, targeted attack
vector) and D into `AMBIGUOUS` (an evidence shortfall, not a model property). If
a run collapses both into `FRAGILE`, the stratified shape/CI machinery is not
discriminating and *that* is the finding.

## Run results (2026-06-05)

Ran live against Groq — A/B/C on `llama-3.3-70b-versatile`, D on
`llama-3.1-8b-instant` (temperature 0.0, seed 42; A with `--nli`). Evidence:
[`../data/probe-05.db`](../data/probe-05.db), 5 sessions.

| Candidate | Target | Actual | Read |
|-----------|--------|--------|------|
| A — grounded | `INFORMATION_PRESENT` | **`INFORMATION_PRESENT`** (1.00) | ✅ confirmed — *after* a perturbation-validity fix (below) |
| B — hedge | `INFORMATION_NULL` | `STABLE` (1.00) | honest negative — the 70B answered with a full both-sides breakdown closing on "…depends on various factors", not an information-empty hedge. `InformationNullOracle` correctly declined (it keys on bare non-answers, not answers that *mention* tradeoffs). Right verdict, wrong hypothesis. |
| C — targeted | `ADVERSARIALLY_VULNERABLE` | `STABLE` (1.00) | honest negative — the 70B was robust to the unicode confusables; both families held. Predicted in the caveats ("a finding about the model, not a flaw in the probe"). |
| D — thin | `AMBIGUOUS` | `STABLE` (1.00) | honest negative — even the 8B answered the author-surname question identically across N=3, so the pass rate was unanimous, not mixed. |

**The headline result is the bug candidate A caught.** As first written, A embedded
the grounding passage *in the perturbed input* ("…boils at **100** degrees
Celsius"), so `typo_noise` mutated the answer itself (`100` → `10l0`) and the model
faithfully echoed the corrupted digit — a **spurious** `contains:["100"]` failure (1
of 11 variants). That lone failure dropped the case out of the stable band into
`AMBIGUOUS` (session `c66e3de3…`, preserved as the "before"), and since
`GroundingOracle` only fires in the stable band (`resolver.py:236`), the gold-standard
verdict was unreachable. This violated the framework's own intent-preservation rule
(plan.md §9.3): a perturbation must not change the ground truth.

**Fix → confirmation.** Moving the grounding source into the un-perturbed
`expected.reference` and asking a self-contained, answer-free question restored
validity. All 11 variants then answered "100 degrees Celsius", the case cleared the
stable band, and `GroundingOracle` confirmed majority-ENTAILMENT against the
reference → **`INFORMATION_PRESENT`, confidence 1.00** (session `2f6e8a30…`). First
live end-to-end proof of both the gold-standard verdict and the `--nli` grounding
path on real model output.

**Net:** `INFORMATION_PRESENT` is demonstrated; `INFORMATION_NULL`,
`ADVERSARIALLY_VULNERABLE`, and `AMBIGUOUS` remain designed-but-not-yet-fired —
open work that needs prompts eliciting genuine refusals, a model that actually
misreads confusables, or genuinely mixed evidence at small N.

## How each verdict is produced (resolver references)

- **INFORMATION_PRESENT** — `resolver.py:236`. Stable band, then the
  `GroundingOracle` contribution (`oracles/grounding.py`): `majority_relation`
  with `premise = expected.reference`, `hypotheses = outputs`; ENTAILMENT with
  support ≥ 0.5 ⇒ grounded. In the MVP `expected.reference` doubles as the
  grounding source (the resolver does not yet populate `OracleContext.context_text`).
- **INFORMATION_NULL** — `resolver.py:233`, checked *before* INFORMATION_PRESENT.
  `InformationNullOracle` (`oracles/information_null.py`) fires on a refusal/hedge
  lexicon (incl. "it depends", "i'm not sure") in ≥ 50% of outputs. No backend.
- **ADVERSARIALLY_VULNERABLE** — `resolver.py:222`. Instability band +
  `failure_shape == "targeted"` (`stratify.py:87`): ≥ 2 families, one broken
  (CI low < 0.5) and one holding (CI low ≥ 0.8). No backend.
- **AMBIGUOUS** — `resolver.py:229`. Instability band, not targeted, and CI high
  ≥ `fragile_threshold` (0.5). The "wide CI / small N" honest-uncertainty path.

## Running the probe

Target **Groq `llama-3.3-70b-versatile`** (the CS-03 model) by default; candidate
D defaults to `llama-3.1-8b-instant` because thin-evidence flakiness is easier to
surface on the smaller model (the CS-03 → CS-04 "downgrade the model" technique).
Set `GROQ_API_KEY` first. Only candidate A needs the NLI extra
(`pip install "falsifyai[nli]"`); B/C/D resolve with no backend.

```bash
# Candidate A needs --nli (grounding is an NLI verdict); B/C/D do not.
falsifyai run docs/case-studies/probe-05/candidate-a-grounded-fact.yaml    --nli --store-path docs/case-studies/data/probe-05.db
falsifyai run docs/case-studies/probe-05/candidate-b-stable-refusal.yaml         --store-path docs/case-studies/data/probe-05.db
falsifyai run docs/case-studies/probe-05/candidate-c-targeted-unicode.yaml       --store-path docs/case-studies/data/probe-05.db
falsifyai run docs/case-studies/probe-05/candidate-d-thin-evidence.yaml          --store-path docs/case-studies/data/probe-05.db

# For candidate D, demonstrate the verdict moving as evidence accumulates:
#   edit count: 3 -> count: 20 and re-run; AMBIGUOUS should resolve to STABLE or FRAGILE.

# Inspect the per-output text + oracle reasoning behind any verdict:
falsifyai inspect <session_id> --full --store-path docs/case-studies/data/probe-05.db
```

## Keep / discard criterion

Keep a candidate that **cleanly produces its target verdict** with a crisp
`inspect` story — and record candidates that *don't* (a 70B too robust to break
on unicode, or too decisive to hedge) as the informative negative they are. As in
CS-03, the negative result is publishable: it bounds where the verdict does and
does not fire on a real model.

## Promotion (after a run)

1. Commit the bundled store at `docs/case-studies/data/probe-05.db` with a
   provenance entry in [`../data/README.md`](../data/README.md) (SHA256, env,
   session → model → verdict mapping), mirroring the CS-04 bundle pattern.
2. Write the prose write-up `docs/case-studies/05-<slug>.md` and add its row to
   the index in [`../README.md`](../README.md).
3. Fold any instrument bug the probe surfaces into a patch release with a
   regression test pinning the boundary (the CS-03 → 0.6.1 pattern).

## Caveats (honest, before you run)

- **The four verdicts have different reliability of triggering.** A and B are
  largely under the prompt's control (a grounded fact entails; an underspecified
  question hedges). C and D are **empirical** — whether the model breaks on
  unicode while holding on casing (C), or lands on a mixed pass rate at N=3 (D),
  is exactly the open question. Downgrading the model raises the odds for both.
- **`candidate-c` strictness.** `contains: ["Au"]` is `case_sensitive: true` on
  the canonical symbol — deliberately strict so a genuine homoglyph misread fails
  it. If the 70B proves robust to confusables, both families hold and the verdict
  is `STABLE`; that is a finding about the model, not a flaw in the probe.
- **`candidate-b` stable band depends on hedge self-similarity.** At temperature
  0 the hedge is near-identical across perturbation, so `semantic_equivalence`
  should keep it in the stable band; if a model varies its hedge enough to drop
  below 0.80 it would read as instability instead. Note it on inspect.
- **Real NLI required for A.** `MockNLIBackend` (the default/test backend) is a
  keyword stub, not an entailment model — candidate A's grounding signal is only
  meaningful under the real `[nli]` backend.
