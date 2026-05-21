# Examples

Dogfooded specs that exercise FalsifyAI's full pipeline. Every example in
this directory is verified in CI via the dogfood tests in
[`tests/integration/test_examples.py`](../tests/integration/test_examples.py).

## Available now

| Example | Verdict | What it demonstrates |
|---|---|---|
| [`stable.yaml`](stable.yaml) | `STABLE` (exit 0) | A sane model under typo + casing perturbations; both MVP invariants (`contains` + `semantic_equivalence`). |
| [`fragile.yaml`](fragile.yaml) | `FRAGILE` (exit 1) | Model drift under typo perturbation: baseline correct, perturbations wrong. |
| [`consistently_wrong.yaml`](consistently_wrong.yaml) | `CONSISTENTLY_WRONG` (exit 2) | Confident hallucination: model gives the same wrong answer under every perturbation. The most dangerous production case ([plan §2.3](../plan.md)). |

## Coming in Week 2

| Example | Verdict | Blocking feature |
|---|---|---|
| `model_migration.yaml` | regression (exit 5) | `falsifyai diff` |

This example completes the [Phase 0 acceptance gate](../plan.md) example
checklist. It ships alongside the differential-testing feature that
consumes it.

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

## Replaying a stored session

Every `falsifyai run` saves a `ReplayArtifact` to the configured store
(default `.falsifyai/replays.db`). To re-render a past session without
re-running the model:

```bash
# Re-render the most recent session
falsifyai replay --latest

# Re-render a specific session by id
falsifyai replay <session_id>
```

The replay command is **strictly read-only** — it never modifies the
stored artifact and never re-resolves the verdict. The verdict displayed
is the one assigned at `run` time. Exit codes mirror `run`, so you can
gate CI on a known-good session: `falsifyai replay <known-good-id>`
returns 0 if and only if the stored session was `STABLE`.

## Writing your own

The spec language is locked for Phase 0; see
[`plan.md` §6](../plan.md) for the full schema. The shortest valid spec is
[`tests/fixtures/specs/minimal.yaml`](../tests/fixtures/specs/minimal.yaml).
