# Case studies

Worked tours of FalsifyAI's evidence infrastructure over real preserved artifacts. Each case study is itself a FalsifyAI artifact: a `ReplayStore` bundle plus prose that walks through what `history`, `diff`, `inspect`, and `replay` reveal when read against it.

> **Recursion principle**: claims about a stochastic system's reliability are only defensible if the evidence supporting them is preserved and replayable. The case studies below are written *in FalsifyAI's own format* — every command shown runs against a bundled SQLite store and reproduces the displayed output verbatim.

For the categorical framing the case studies operationalize — *why capability scores and reliability evidence answer different questions* — see [`../THE-EVIDENCE-GAP.md`](../THE-EVIDENCE-GAP.md).

## Index

| # | Title | What it demonstrates | Tools used |
|---|---|---|---|
| 01 | [Invisible character substitution](01-invisible-character-substitution.md) | Cross-model `contains`-contract brittleness as a persistent class; a model-migration regression (U+202F substitution between "30" and "days") as the vivid instance. | `history`, `diff`, `inspect`, `replay` |
| 02 | [Resolver arbitration: boundary shift without verdict shift](02-resolver-arbitration-boundary-shift.md) | An operationally motivated CLAUDE.md revision changed *where* a model permitted additional architectural complexity to exist without changing its top-level recommendation — the kind of subtle drift a pass/fail evaluator would miss. Manual retrospective probe; reproduction specs at [`specs/`](specs/). | manual probe + machine-reproducible [`specs/`](specs/) |
| 03 | [When the evaluator is wrong: a self-falsification study](03-evaluator-false-positive.md) | A *correct, stable* model assigned the framework's harshest verdict (`CONSISTENTLY_WRONG` @ 1.00) by FalsifyAI's own interpretation layer; the preserved evidence overturned every false-positive verdict and drove the 0.6.1 `HallucinationOracle` fix. Self-falsification — differs from the model-behavior charter on purpose. | `inspect` over the bundled [`probe-03/`](probe-03/) store |

## How to read a case study

Each case study has the same shape:

1. **Setup** — what was run, against what models, with what spec.
2. **A systemic finding** (the thesis) — what `history` shows across multiple sessions.
3. **A specific instance** (the vivid proof) — what `diff` and `inspect` reveal in one session; typically 1–3 sub-sections detailing the regression, the evidence, and the failure mechanism.
4. **Why it matters** — the operational point that makes the evidence load-bearing (e.g. why semantic matching wouldn't catch this).
5. **Reproduction** — exact commands the reader runs against the bundled store.
6. **Synthesis** — the architectural claim the case study exists to demonstrate (typically: one preserved evidence substrate, multiple consumer surfaces).

The bundle lives in [`data/`](data/) and has a [provenance README](data/README.md) recording SHA256, environment, and session-to-model mappings.

## What case studies are NOT

- Not benchmarks or leaderboards (no model ranking).
- Not marketing posts or launch announcements.
- Not tutorials (tutorials teach how-to; case studies preserve what-happened).
- Not critiques of any model or provider — they document *reliability-contract behavior under perturbation*, not model quality.
- Not synthesized data. The artifacts bundled here are real runs from real campaigns, copied verbatim.

## Adding a new case study

The pattern that makes a case study load-bearing:

1. The evidence already exists in a `ReplayStore` from a real run — never synthesize.
2. There is a systemic finding *and* a specific instance — neither alone is strong enough.
3. The bundle is included so every command shown is verifiable.
4. The prose passes the framing test: would a careful reader interpret this as *reliability pressure testing* or as *adversarial gotcha*? Only the former is acceptable.
5. The synthesis names the architectural claim the case study exists to demonstrate.

If you have a real run that meets all five, propose a case study by opening an issue with the session ID(s) and the architectural claim you'd be demonstrating.
