# Contributing to FalsifyAI

Thanks for considering a contribution. This document is the operating manual
for the project — what to build, how to build it, and (importantly) what
*not* to build.

## Setup

Requires **Python 3.13+** and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ericckzhou/falsifyai
cd falsifyai
uv sync --extra dev
uv run pytest
```

If `pytest` is green, your environment is ready.

## Branch workflow

- **`dev` is the active development branch.** All PRs target `main` *from*
  `dev` (or a topic branch off `dev`). Do not commit directly to `main`.
- **CI gates PRs to `main`**, not `dev`. A push to `dev` runs CI but
  doesn't block other work.
- **One conceptual unit per PR.** A PR that touches the perturbation
  runtime *and* tweaks the CLI render is two PRs.
- **Squash-merge.** Every PR becomes one conventional commit on `main`.

## Commit messages

Conventional Commits format:

```
<type>: <short imperative summary>

<optional body explaining why, not what>
```

Types we use: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `perf`,
`ci`.

## Code style

- **Type annotations on every public function signature.**
- **Frozen dataclasses for value records.** Mutation post-construction is a
  bug.
- **`Protocol` for behavioral interfaces.** Use `@runtime_checkable` when
  tests need `isinstance` checks.
- **Lazy imports for heavy deps.** Pattern: import `sentence_transformers`
  inside `.embed()`, not at module load.
- **`extra="forbid"` on all Pydantic spec models.** Unknown YAML keys fail
  loudly.
- **`ruff check` + `ruff format` clean before merge.** CI enforces this.

## Test conventions

- **`pytest` is the framework.** No other test runners.
- **`tests/unit/`** for fast, isolated tests. **`tests/integration/`** for
  cross-subpackage end-to-end tests. Both run in the default `pytest`
  invocation; we do not gate integration tests behind a marker (they're
  fast — MockAdapter-driven, no network).
- **No real network in tests.** `MockAdapter` injects via the
  `falsifyai.cli.run.build_adapter` seam; `MockEmbedder` (or a hash-based
  patch on `SentenceTransformerBackend.embed`) replaces the real model.
- **Harvest, don't hardcode, perturbation outputs.** Tests that need to
  know the realized perturbation strings should call `materialize()` at
  setup time and read them off, never hardcode the expected strings.
- **Coverage target: 80% baseline, 95%+ on new subpackages.** Coverage is
  not the goal; meaningful tests are. But sub-80% on new code is a smell.

## Architectural constraints (non-negotiable)

These exist because the project's coherence depends on them. A PR that
violates one of these is not landing without an architecture-level
conversation first.

### Three-layer separation

The codebase is organized into three layers. Each new feature belongs in
exactly one of them.

| Layer | Belongs here |
|---|---|
| **Evidence generation** | `falsifyai.perturbation`, `falsifyai.spec.materializer`, `falsifyai.execution` |
| **Evidence interpretation** | `falsifyai.invariants`, `falsifyai.verdict`, `falsifyai.falsifiability`, `falsifyai.cli.render` |
| **Evidence preservation** | `falsifyai.replay` (artifacts, stores, serialization) |

A PR that proposes touching two layers at once should stop and decompose.
Adaptive evidence collection is *interpretation*, not generation. A new
verdict shape is *interpretation*, not preservation. A new perturbation
family is *generation*, not interpretation.

### Resolver complexity is bounded

The verdict resolver (`falsifyai/verdict/resolver.py`) is the **epistemic
authority of the framework.** Its priority chain must stay compressible
and predictable.

**The trust test** for any proposed resolver change:

> A competent user should be able to predict the resolver output from the
> inputs.

If a careful engineer reading the spec, the perturbations, the executions,
and the invariant results can reasonably anticipate what verdict the
resolver will return — the resolver is still legible. If they can't, it
has become a black box, regardless of how technically correct its
internals are.

**Healthy expansion:** add fields to the artifact (consumer surface
grows); add new CLI subcommands (`falsifyai history`, `falsifyai inspect`,
etc. — consumer surface grows); leave the resolver's priority chain
alone.

**Resolver inflation** — accreting heuristics, thresholds, verdict types,
or confidence semantics into the resolver until it stops being predictable
— is an explicit anti-goal. PR #12 codified it; PRs #13–#14 demonstrated
it under real pressure. Future PRs should continue the pattern.

### Evidence density over evidence volume

FalsifyAI optimizes for **maximum useful signal**, not maximum data. More
evidence is not inherently better evidence. Concretely:

- **CLI output** is one row per case + a one-line summary. Not a
  dashboard.
- **Verdict design** compresses evidence into actionable conclusions;
  doesn't enumerate it.
- **Perturbation families** each contribute orthogonal reliability
  information. `typo_noise_v2` ≠ a new family; `paraphrase` is.
- **Replay artifacts** preserve detailed evidence behind the scenes so
  the CLI can stay compressed. The CLI compresses; the artifact preserves
  the receipts.

When a PR proposes adding "just one more knob" / "just one more metric" /
"just one more chart" — read the public guidance in
[`.claude/CLAUDE.md`](.claude/CLAUDE.md) under *Anti-goals / anti-entropy
infrastructure* and push back.

### MVP scope is locked for the 0.1.x line

- **Perturbations:** `typo_noise` + `casing_variant` only.
- **Invariants:** `contains` + `semantic_equivalence` only.
- **Verdicts:** `STABLE`, `FRAGILE`, `CONSISTENTLY_WRONG`, `INSUFFICIENT`,
  `INVALID_EVAL` (5 of the planned 8; full set lands in Phase 1).
- **Spec language:** locked. New fields require a spec version bump and
  a migration plan.

Phase 1 expands these. Until 0.2.0 ships, additions to any of the locked
surfaces need an architecture review.

## Planning a PR

For anything larger than a one-file fix, please plan before writing code.
The project uses a local-only `dev_notes/` convention:

```
dev_notes/
├── plans/PR-<N>-<slug>.md          # forward-looking; surfaces decisions
├── summaries/PR-<N>-<slug>.md      # short post-PR record
└── walkthroughs/PR-<N>-<slug>.md   # deep dive for future readers
```

These files are **gitignored** (via `.git/info/exclude`). They are
personal planning artifacts for your local workflow, not project
deliverables. If you'd like to share a plan during a PR review, paste it
into the PR description.

The scaffolder helps:

```bash
python scripts/scaffold_dev_notes.py <PR_NUMBER> <slug>
```

Structure for plans and walkthroughs follows
[`dev_notes/STRUCTURE.md`](dev_notes/STRUCTURE.md) if you've adopted that
convention locally. (It's also gitignored — your local docs, your local
rules.)

## What to expect from review

Reviews emphasize:

1. **Architectural fit.** Does this belong in the three-layer model?
   Does it inflate the resolver?
2. **Evidence density.** Does this addition help the user make a better
   decision, or does it crowd the surface?
3. **Spec / verdict / artifact stability.** Does this break the on-disk
   format or the locked spec language?
4. **Tests + coverage.** Is the failure mode this change addresses tested?
   Did coverage drop?
5. **Style + clarity.** `ruff` clean; idiomatic Python; clear naming.

PRs that pass the architectural and test gates land quickly. PRs that
don't get a respectful conversation about why; we'd rather decompose than
revert.

## Release process

See [`docs/RELEASE.md`](docs/RELEASE.md) for the maintainer release
checklist (`uv build`, `twine check`, `twine upload`, tag, announce).

## License

Apache 2.0. Contributions are accepted under the same license — see
[LICENSE](LICENSE).
