# FalsifyAI — Project Context for Claude

> Project-scoped instructions. Extends, does not replace, user-global `~/.claude/CLAUDE.md`.

## What this project is

**FalsifyAI** is a falsification-first reliability testing framework for AI systems. Status: **v0.6.4** — perturbation-validity integrity (bidirectional-NLI paraphrase gate rejects lossy rewrites under `--nli`; case study 06) atop semantic-judgment depth (NLI oracle layer + full 8-verdict resolver) and the shipped artifact-infrastructure (0.2–0.4) / capability-breadth (0.5) tracks. The pipeline runs end-to-end (spec → materialize → execute → judge → resolve → save → CLI) with dogfooded examples for every verdict; release history in [CHANGELOG.md](../CHANGELOG.md).

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
- **Scope restraint.** The 0.1.0 MVP shipped just 2 perturbation families, 2 invariants, 5 verdicts ([plan.md §22.1](../plan.md)) because *that was enough to tell the story*. The discipline — not the specific counts — is the lesson; the 0.x line grew only by orthogonal failure mode.
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

The 0.1.0 MVP shipped a deliberately small, locked surface ([plan.md §22.1](../plan.md)) — 2 perturbation families, 2 invariants, 5 verdicts, `falsifyai diff`, falsifiability scoring, dogfooded from Week 1. The 0.x line has since expanded that surface (current state below), always by orthogonal failure mode, never by accretion. The discipline is permanent even though the counts grew:

- **Verdicts**: the full taxonomy — 9 enum members (the 8-verdict 2D stability×grounding space plus `INSUFFICIENT`). Authoritative source: [`falsifyai/verdict/models.py`](../falsifyai/verdict/models.py). (MVP shipped 5.)
- **Perturbations**: `typo_noise`, `casing_variant`, `unicode_chars`, `paraphrase` (the last gated by bidirectional NLI for validity). (MVP shipped the first 2.)
- **Invariants**: `contains`, `semantic_equivalence`, `schema_match`, plus the `falsifyai.invariants` plugin entry-point group. (MVP shipped the first 2.)
- **Spec language**: locked. New fields require a spec version bump and a migration plan.
- Do not add features beyond what the spec demands. Do not invent abstractions for hypothetical extensions.
- Do not change naming without explicit user confirmation.
- Do not deviate from the flat package layout without asking.
- A new surface (verdict / perturbation / invariant) needs an architecture review and must justify *what orthogonal failure mode or better decision it enables* — not breadth.

## What to NOT do

- Don't add `src/` layout.
- Don't add a `setup.py` or `setup.cfg`. `pyproject.toml` is the only build config.
- Don't install pytest/ruff via pip directly — use `uv add --dev`.
- Don't pre-create files for sections of the plan that aren't being implemented yet. Empty `__init__.py` is the current correct state.
- Don't enable the CLI script entry-point in `pyproject.toml` until `falsifyai/cli/main.py` actually exists.
