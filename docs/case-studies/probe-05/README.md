# probe-05 — the grounding-verdict quartet

A probe that turns the **both-directions** scrutiny of case studies 03/04 on the
four verdicts the 0.6.0 release added but never battle-tested on real model
output: `INFORMATION_PRESENT`, `INFORMATION_NULL`, `ADVERSARIALLY_VULNERABLE`,
and `AMBIGUOUS`. CS-03/04 proved `CONSISTENTLY_WRONG` fires when it should and
stays silent when it shouldn't — and found a real bug doing it. These verdicts
have had no equivalent test. This probe is engineered to make each one fire on a
real model, and documents what the *other* outcome would mean so a run that
*doesn't* produce the target verdict is still informative.

> **STATUS (2026-06-05): NOT YET RUN.** Designed and statically validated only —
> all four specs parse and materialize offline (model-free perturbation families),
> and each verdict path below is traced to the resolver source. No model calls
> have been made: the environment this was authored in has no `GROQ_*` key. The
> verdict-boundary table is a **hypothesis**, not a result. Run it where a key is
> available, then promote the outcome per [Promotion](#promotion-after-a-run).

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
