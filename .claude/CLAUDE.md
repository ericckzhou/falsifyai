# FalsifyAI — Project Context for Claude

> Project-scoped instructions. Extends, does not replace, user-global `~/.claude/CLAUDE.md`.

## What this project is

**FalsifyAI** is a falsification-first reliability testing framework for AI systems. Status: **active Phase 0 implementation toward `falsifyai==0.1.0`**. Core pipeline is shipped (spec → materialize → execute → judge → save → CLI) with two dogfooded examples; remaining Phase 0 work in [plan.md §22.1](../plan.md).

## Design philosophy (load-bearing)

FalsifyAI optimizes for **evidence density over evidence volume**.

```
minimal meaningful evidence
+ high evidence quality per cognitive load
+ diverse perturbation categories
+ replayable proof
= better falsification of AI / LLM systems
```

The goal is **maximum useful signal**, not maximum data. More evidence is not inherently better evidence.

### Four pillars

- **Minimal meaningful evidence.** Run the smallest experiment that meaningfully increases confidence in a verdict — no more. Adaptive evidence collection is the long-term ideal.
- **High evidence quality per cognitive load.** Every line / artifact a user sees has to earn its real estate against: *would removing this make the engineer's decision worse?*
- **Diverse perturbation categories (orthogonal pressure).** The admission criterion for a new perturbation family is *what new failure mode does this expose?* — not breadth. `typo_noise_v2` ≠ a new family; `paraphrase` is.
- **Replayable proof.** Replay artifacts are the system's promise that claims are inspectable evidence, not anecdotes. CLI compresses; artifact preserves.

### How this shapes decisions

- **CLI output.** One row per case + one-line summary. Not a dashboard.
- **Verdict design.** Compress evidence into actionable conclusions; don't enumerate it.
- **Perturbation families.** Each must contribute orthogonal reliability information, not duplicate noise.
- **Replay artifacts.** Self-contained; carry the full materialized spec so they outlive the YAML file on disk.
- **MVP scope.** 2 perturbation families, 2 invariants, 5 verdicts — locked in [plan.md §22.1](../plan.md) because *that is enough to tell the story*.
- **Three-layer architectural separation.** *Evidence generation* (perturbation / materialization / execution) is architecturally distinct from *evidence interpretation* (invariants / verdict resolver / CLI compression), and both are distinct from *evidence preservation* (replay artifacts / stores). New work belongs in exactly one layer; don't let interpretation leak into generation under pressure.
- **Resolver complexity is bounded.** The verdict resolver is the epistemic authority of the framework; its priority chain must stay compressible and predictable. Expand the consumer surface (replay / diff / future tools) when adding interpretation features, not the verdict logic. The trust test for any resolver change: *a competent user should be able to predict the resolver output from the inputs.*

### Anti-goals / anti-entropy infrastructure

FalsifyAI is **not** optimizing for any of these. When pressure pulls toward them, resist:

- Maximal perturbation volume
- Maximal telemetry / metrics
- Dashboard density
- Benchmark quantity
- Metric proliferation
- Exhaustive output verbosity
- Configuration knobs for every behavior
- **Resolver inflation** — accreting heuristics, thresholds, verdict types, or confidence semantics into the verdict resolver. Each addition seems reasonable; cumulative effect destroys predictability.

The signal to watch: *does this addition help an engineer make a better decision, or does it crowd the surface where the actual decision lives?* If the latter, defer or rework.

## Naming (locked — do not change without confirmation)

| Layer | Value |
|---|---|
| PyPI package | `falsifyai` |
| Python import | `import falsifyai` |
| CLI binary | `falsifyai` (e.g. `falsifyai run eval.yaml`) |
| Brand / prose name | "FalsifyAI" |
| Repo / folder | `falsifyai` |
| Plugin entry-point groups | `falsifyai.perturbations`, `falsifyai.invariants`, `falsifyai.oracles`, `falsifyai.adapters`, `falsifyai.reporters`, `falsifyai.stores` |
| Replay cache dir | `.falsifyai/` (matches CLI name, like `.git` / `.pytest_cache`) |

**Background on the rename**: the original plan used `falsify` for the CLI binary, the `.falsify/` cache dir, and "Falsify" in prose. That collided with the existing `studio-11-co/falsify` project in the AI eval space. Renamed to `falsifyai` / `.falsifyai/` / "FalsifyAI" for full namespace consistency before any public release.

## Toolchain

- **Python:** 3.13+ (locked in `.python-version` and `pyproject.toml`)
- **Package manager:** `uv` (not pip directly)
- **Build backend:** `hatchling`
- **Test:** `pytest` + `pytest-cov`
- **Lint/format:** `ruff` (line-length 100, target py313)
- **License:** Apache-2.0

The `uv` binary lives at `C:\Users\Eric\AppData\Roaming\Python\Python313\Scripts\uv.exe`. PATH is configured. If a shell can't find `uv`, prepend that directory to `$env:PATH`.

## Branch workflow

Layered: `main` ← `dev` ← topic branches. The two arrows are different PRs.

- **Active development branch is `dev`.** Never commit directly to `main`.
- **Topic branches branch off `dev` and PR back to `dev`** (squash-merge on completion). Small, focused changes can commit directly on `dev`; larger or riskier changes earn a topic branch.
- **`main` ← `dev` is a separate PR**, opened at strategic moments: tagged releases, public repositioning, milestone shipping. It is not a per-PR event. Work can accumulate on `dev` across multiple topic-branch merges before a single `dev → main` promotion ships them all.
- **After every `dev → main` squash-merge, reset `dev` to match `main` before starting the next topic branch:** `git checkout dev && git fetch origin && git reset --hard origin/main && git push --force-with-lease origin dev`. This prevents *ghost-history conflicts* on subsequent `dev → main` PRs. The squash collapses many dev commits into one main commit, but git can't see the content-equivalence without help — the unreset dev keeps the individual commits which then collide with main's squashed version on the next promotion attempt. Not losing work; the granular history is already preserved in `dev_notes/{plans,summaries,walkthroughs}/`.
- CI runs on PRs to both `dev` and `main`. `main` is what the public README shows; `dev` is the working integration branch.
- If you find yourself on `main` mid-session, switch to `dev` before staging changes.

## Common commands

```bash
uv sync --extra dev          # install runtime + dev deps into .venv
uv run pytest                # run tests
uv run ruff check .          # lint
uv run ruff format .         # format
uv run python -c "import falsifyai; print(falsifyai.__version__)"
```

## Layout (flat, not src/)

Package directory is at repo root, not under `src/`. See [plan.md §4](../plan.md). When the plan says `falsifyai/cli/main.py`, that means `<repo>/falsifyai/cli/main.py`.

```
falsifyai/                    ← repo root
├── pyproject.toml
├── falsifyai/                ← Python package
│   ├── cli/  spec/  session/  perturbation/  execution/
│   ├── invariants/  oracles/  statistical/  falsifiability/
│   ├── verdict/  replay/  differential/  reporting/
├── tests/
│   ├── unit/  integration/  fixtures/  meta/
└── examples/
```

All subpackages have empty `__init__.py` files only — no implementation yet.

## Design anchors (when implementing, do not reinvent)

- **8 verdicts in 2D space:** `STABLE`, `INFORMATION_PRESENT`, `CONSISTENTLY_WRONG`, `ADVERSARIALLY_VULNERABLE`, `FRAGILE`, `INFORMATION_NULL`, `AMBIGUOUS`, `INVALID_EVAL` — see [plan.md §2](../plan.md).
- **Worst-case stratified stability**, not aggregate — see [plan.md §12](../plan.md).
- **Spec materialization** separates intention (YAML) from instance (realized perturbations) — see [plan.md §8](../plan.md).
- **Meta-oracle is the sole source of `INVALID_EVAL`** — see [plan.md §11.2](../plan.md).
- **Perturbation validity is required** (bidirectional NLI default) — see [plan.md §9.3](../plan.md).
- **`falsifyai diff` is a Phase 1 deliverable**, not Phase 2 — see [plan.md §14](../plan.md).
- **Storage behind `ReplayStore` protocol** — SQLite default, no SQLite-specific code in core — see [plan.md §18](../plan.md).
- **Falsifiability scoring is required** for every invariant — see [plan.md §15](../plan.md).

## Scope discipline

- **Phase 0 MVP is locked**: 3 weeks, single launch as `falsifyai==0.1.0`. See [plan.md §22.1](../plan.md). Includes `falsifyai diff`, `CONSISTENTLY_WRONG`, falsifiability scoring, and dogfooding from Week 1. Compression around the differentiator, not expansion of timeline.
- **MVP verdict set**: `STABLE`, `FRAGILE`, `CONSISTENTLY_WRONG`, `INSUFFICIENT`, `INVALID_EVAL` (5 verdicts; full 8 in Phase 1).
- **MVP perturbations**: `typo_noise` + `casing_variant` only (2 families — required for honest bootstrap CI).
- **MVP invariants**: `contains` + `semantic_equivalence`.
- **8-item acceptance gate** ([plan.md §22.1.1](../plan.md)) must pass before tagging 0.1.0. PyPI publication is deployment, not validation.
- Do not add features beyond what the spec demands. Do not invent abstractions for hypothetical extensions.
- Do not change naming without explicit user confirmation.
- Do not deviate from the flat package layout without asking.
- Cuts from MVP that may feel tempting: rich/colored terminal output (defer), heavyweight NLI for ConsistencyOracle (use embeddings for MVP, NLI in Phase 1), full 8-verdict resolver (5 verdicts for MVP).

## What to NOT do

- Don't add `src/` layout.
- Don't add a `setup.py` or `setup.cfg`. `pyproject.toml` is the only build config.
- Don't install pytest/ruff via pip directly — use `uv add --dev`.
- Don't pre-create files for sections of the plan that aren't being implemented yet. Empty `__init__.py` is the current correct state.
- Don't enable the CLI script entry-point in `pyproject.toml` until `falsifyai/cli/main.py` actually exists.
