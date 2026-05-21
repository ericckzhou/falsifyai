# Falsify — Project Context for Claude

> Project-scoped instructions. Extends, does not replace, user-global `~/.claude/CLAUDE.md`.

## What this project is

**Falsify** is a falsification-first reliability testing framework for AI systems. Status: **pre-MVP scaffold**. No implementation code yet — only directory layout and configuration. Full design lives in [plan.md](../plan.md).

## Naming (locked — do not change without confirmation)

| Layer | Value |
|---|---|
| PyPI package | `falsifyai` |
| Python import | `import falsifyai` |
| CLI binary | `falsify` (e.g. `falsify run eval.yaml`) |
| Brand / prose name | "Falsify" |
| Repo / folder | `falsifyai` |
| Plugin entry-point groups | `falsifyai.perturbations`, `falsifyai.invariants`, `falsifyai.oracles`, `falsifyai.adapters`, `falsifyai.reporters`, `falsifyai.stores` |
| Replay cache dir | `.falsify/` (matches CLI name, like `.git` / `.pytest_cache`) |

## Toolchain

- **Python:** 3.13+ (locked in `.python-version` and `pyproject.toml`)
- **Package manager:** `uv` (not pip directly)
- **Build backend:** `hatchling`
- **Test:** `pytest` + `pytest-cov`
- **Lint/format:** `ruff` (line-length 100, target py313)
- **License:** Apache-2.0

The `uv` binary lives at `C:\Users\Eric\AppData\Roaming\Python\Python313\Scripts\uv.exe`. PATH is configured. If a shell can't find `uv`, prepend that directory to `$env:PATH`.

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
- **`falsify diff` is a Phase 1 deliverable**, not Phase 2 — see [plan.md §14](../plan.md).
- **Storage behind `ReplayStore` protocol** — SQLite default, no SQLite-specific code in core — see [plan.md §18](../plan.md).
- **Falsifiability scoring is required** for every invariant — see [plan.md §15](../plan.md).

## Scope discipline

- **Phase 0 MVP is locked**: 3 weeks, single launch as `falsifyai==0.1.0`. See [plan.md §22.1](../plan.md). Includes `falsify diff`, `CONSISTENTLY_WRONG`, falsifiability scoring, and dogfooding from Week 1. Compression around the differentiator, not expansion of timeline.
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
