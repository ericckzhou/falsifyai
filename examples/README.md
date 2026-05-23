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
| [`model_migration.yaml`](model_migration.yaml) | regression (exit 5) | Model-migration safety: run twice with different models, then `falsifyai diff <session_A> <session_B>` flags regressions. The Phase 0 launch wedge per [plan §22.1](../plan.md). |
| [`paraphrase.yaml`](paraphrase.yaml) | `STABLE` (exit 0) | Paraphrase perturbation family (Phase B): LLM-generated semantic-preserving rewrites with embedding-similarity validity gating. Tests semantic robustness as an axis orthogonal to character-level typo/casing. |

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

## Comparing two sessions (model migration)

The `model_migration.yaml` example is designed for the differential-testing
workflow:

```bash
# Run once with model A; note the session_id printed at the end.
falsifyai run examples/model_migration.yaml

# Switch model providers / versions in your config, then run again.
falsifyai run examples/model_migration.yaml

# Diff the two sessions. Exit code 5 if any case regressed.
falsifyai diff <session_A_id> <session_B_id>
```

The regression criterion is **verdict-class downgrade**:
`STABLE → FRAGILE`, `STABLE → CONSISTENTLY_WRONG`, or
`FRAGILE → CONSISTENTLY_WRONG`. Same-verdict transitions (even with
stability drops) do not trigger exit 5; the binary criterion is
predictable by design.

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

## Inspecting evidence in a stored session

When `replay` tells you a case is `FRAGILE` but you want to see *why*,
`falsifyai inspect` surfaces the underlying evidence:

```bash
# Default: per-case verdict + count + worst-perturbation evidence
falsifyai inspect <session_id>

# Drill into one case to see every perturbation
falsifyai inspect <session_id> --case <case_id>

# Disable output truncation (default truncates long outputs)
falsifyai inspect <session_id> --case <case_id> --full
```

The default render shows the perturbed input, model output excerpt, and
failing invariant for the worst perturbation in each non-STABLE case —
enough to reconstruct verdict reasoning without consulting docs. Like
`replay`, `inspect` is strictly read-only and never re-resolves a
verdict.

## Tracking a case across sessions

When you've run an eval multiple times (different models, different
days, different prompt revisions), `falsifyai history` compresses how a
single case has behaved across the store:

```bash
# Newest-first; default --limit 20
falsifyai history extraction

# All matching sessions (no cap)
falsifyai history extraction --limit 0

# Different replay store
falsifyai history extraction --store-path /path/to/replays.db
```

Each row shows session id prefix, timestamp, verdict, CI, and (for
FRAGILE rows) the worst perturbation family. The reader sees the raw
timeline; `history` deliberately does not aggregate, average, or infer
trends — that discipline lets the verdicts stay defensible as preserved
evidence rather than as inferred metrics.

## Writing your own

The spec language is locked for Phase 0; see
[`plan.md` §6](../plan.md) for the full schema. The shortest valid spec is
[`tests/fixtures/specs/minimal.yaml`](../tests/fixtures/specs/minimal.yaml).
