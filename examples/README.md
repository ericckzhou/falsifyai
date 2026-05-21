# Examples

Dogfooded specs that exercise FalsifyAI's full pipeline. Every example in
this directory is verified in CI via the dogfood tests in
[`tests/integration/test_examples.py`](../tests/integration/test_examples.py).

## Available now

| Example | Verdict | What it demonstrates |
|---|---|---|
| [`stable.yaml`](stable.yaml) | `STABLE` (exit 0) | A sane model under typo + casing perturbations; both MVP invariants (`contains` + `semantic_equivalence`). |
| [`fragile.yaml`](fragile.yaml) | `FRAGILE` (exit 1) | Model drift under typo perturbation: baseline correct, perturbations wrong. |

## Coming in Week 2

| Example | Verdict | Blocking feature |
|---|---|---|
| `consistently_wrong.yaml` | `CONSISTENTLY_WRONG` (exit 2) | `ConsistencyOracle` |
| `model_migration.yaml` | regression (exit 5) | `falsifyai diff` |

These two complete the [Phase 0 acceptance gate](../plan.md) example
checklist. They ship alongside the features that consume them.

## Running locally

After `pip install falsifyai` (or `uv sync` for development):

```bash
falsifyai run examples/stable.yaml
falsifyai run examples/fragile.yaml --store-path :memory:
```

A real model provider is required (env var, e.g. `OPENAI_API_KEY`). The
dogfood tests in CI bypass the real model by injecting a `MockAdapter`
through a test seam — see
[`tests/integration/test_examples.py`](../tests/integration/test_examples.py).

## Writing your own

The spec language is locked for Phase 0; see
[`plan.md` §6](../plan.md) for the full schema. The shortest valid spec is
[`tests/fixtures/specs/minimal.yaml`](../tests/fixtures/specs/minimal.yaml).
