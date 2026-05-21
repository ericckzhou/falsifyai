# Changelog

All notable changes to FalsifyAI are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-05-21

**Phase 0 MVP.** First public release. Spec language and verdict semantics
are locked for the 0.1.x line.

### Highlights

- **The launch wedge:** `falsifyai diff <baseline> <candidate>` returns exit
  code 5 (REGRESSION) when any case's verdict regressed between two runs.
  This is the project's defining wedge.
- **The investigation workflow:** `run` → `replay` → `diff` is one
  falsification workflow, not three commands. Same mental model end-to-end.
- **Replayable evidence:** every `falsifyai run` saves a self-contained
  `ReplayArtifact` (full materialized spec + every execution + every
  invariant judgment) that survives across model versions and OS reboots.
- **Honest confidence numbers:** stratified bootstrap CI per perturbation
  family. The worst-case CI lower bound is the confidence number;
  per-family stability is preserved in the artifact for downstream tooling.
- **`CONSISTENTLY_WRONG` verdict:** catches the most dangerous production
  case — a model that confidently and consistently outputs the same wrong
  answer to every perturbation. Without this verdict, that pattern would
  be reported as `STABLE`.

### Architecture (PRs #2–#11)

- **Spec language** (PR #2). Pydantic v2 YAML loader with `extra="forbid"`,
  discriminated unions for perturbation/invariant types, content-hash
  identity (`spec_hash` = sha256 of file bytes). Sync LiteLLM execution
  adapter with a temperature-gated in-memory cache.
- **Perturbation runtime** (PR #3). `Perturbation` Protocol + two MVP
  families (`typo_noise`, `casing_variant`) + dispatch registry. Every
  perturbation emitting multiple outputs stamps `params["sample_index"]`
  for replay determinism.
- **Spec materializer** (PR #4). Turns a `Spec` into a `MaterializedSpec`
  with every perturbation realized up-front. `materialized_hash` anchors
  the realized inputs; per-case seeds derived from
  `sha256(session_seed:case_id)` so reordering cases doesn't change any
  case's seed.
- **Invariant runtime** (PR #5). `Invariant` Protocol + two MVP types
  (`contains`, `semantic_equivalence`) + `EmbeddingBackend` Protocol for
  test-time injection of `MockEmbedder`. `sentence-transformers` is lazy-
  loaded on first real `.embed()` call.
- **Replay store** (PR #6). `ReplayStore` Protocol with two
  implementations: file-backed `SQLiteStore` (default, WAL mode,
  transactional saves, schema versioning) and ephemeral `InMemoryStore`
  (test double + ephemeral run support). Artifact-scoped JSON
  serialization; no generic recursive serializer.
- **Brand rename** (PR #7). Package + CLI + cache dir renamed to
  `falsifyai` / `.falsifyai/` to resolve the collision with
  `studio-11-co/falsify`.
- **`falsifyai run` CLI** (PR #8). The first end-to-end command: load
  spec → materialize → execute → judge → save → render → exit code. Plain-
  text output; one row per case; exit codes 0/1/2/3/4 per
  [plan §16.1](plan.md).
- **Dogfooded examples** (PR #9). `examples/stable.yaml` +
  `examples/fragile.yaml` + dogfood tests that run them in the default
  pytest suite via MockAdapter injection.
- **Design philosophy codified** (PRs #10 + #12). The "evidence density
  over evidence volume" principle, the four pillars, the three-layer
  architectural separation, and the "resist resolver inflation" anti-
  pattern committed to `.claude/CLAUDE.md`.

### Verdicts (PR #11)

- **Real verdict resolver** with stratified bootstrap CI per perturbation
  family, lightweight `CONSISTENTLY_WRONG` detection via
  `expected.contains` / `not_contains`, and per-suite falsifiability
  scoring. Replaces the PR #8 placeholder.
- **5-verdict MVP set:** `STABLE`, `FRAGILE`, `CONSISTENTLY_WRONG`,
  `INSUFFICIENT`, `INVALID_EVAL`. String values stable for on-disk
  serialization.
- **Stability evidence persisted in the artifact:** `stability_ci_low`,
  `stability_ci_high`, `per_family_stability`, `worst_case_family`. These
  fields make `falsifyai diff`'s per-family analysis possible without
  re-running.
- **Falsifiability warning:** suite-level mean falsifiability below 0.5
  prints a stderr warning. Exit code 6 (LOW_FALSIFIABILITY) reserved for
  Phase 1 once the threshold is calibrated.

### Replay + Diff CLI (PRs #13 + #14)

- **`falsifyai replay <session_id>`** (PR #13). Loads a stored session and
  re-renders it. Read-only; never modifies the artifact; never re-resolves
  the verdict. `--latest` flag for the dominant "show me what I just ran"
  case. Exit codes mirror `run`.
- **`falsifyai diff <baseline> <candidate>`** (PR #14). Compares two
  artifacts case-by-case. Regression criterion is binary verdict-class
  downgrade (`STABLE → FRAGILE`, `STABLE → CONSISTENTLY_WRONG`,
  `FRAGILE → CONSISTENTLY_WRONG`); exit code 5 on regression. ADDED /
  REMOVED cases are informational, not regression.
- **Compressed diff output:** only transitions ≠ UNCHANGED appear as rows;
  full counts in the footer. Evidence-density principle applied to the
  diff surface.

### Examples (PRs #9 + #11 + #14)

- `examples/stable.yaml` — STABLE under perturbation (PR #9).
- `examples/fragile.yaml` — FRAGILE under perturbation (PR #9).
- `examples/consistently_wrong.yaml` — confident hallucination (PR #11).
- `examples/model_migration.yaml` — the run-twice-then-diff workflow
  (PR #14).

All four are verified in CI via `tests/integration/test_examples.py`.

### Tooling

- **Python 3.13+** required.
- **`uv`** for dependency management.
- **`ruff`** for lint + format (line-length 100, target py313).
- **`pytest`** + **`pytest-cov`** for testing.
- **CI:** GitHub Actions on every push to `main` + `dev` and every PR
  targeting `main`.
- **303 tests** at this release, with **94% coverage** on
  `falsifyai.cli` + **100%** on `falsifyai.verdict` and
  `falsifyai.falsifiability`.

### Documentation

- Full README rewrite (this release): narrative-first, walks the migration
  investigation as one workflow.
- `CONTRIBUTING.md`: development workflow + the resolver-bound trust test
  any resolver-touching PR must pass.
- `docs/ARCHITECTURE.md`: three-layer separation + the resolver as
  inference engine + the user-question taxonomy.
- `docs/RELEASE.md`: the launch checklist (build, validate, upload,
  announce).
- `docs/DEMO.md`: instructions for capturing the ~30-second migration
  demo with `asciinema`.

### Known limitations

- **`semantic_equivalence`** invariant requires `sentence-transformers`,
  which is an **optional install** (pulls PyTorch, ~1GB):
  `pip install "falsifyai[semantic]"`. Core `pip install falsifyai` stays
  small; users hitting the semantic path without the extra get a friendly
  ImportError with the install hint. The first real-LiteLLM run with a
  semantic invariant additionally downloads the `all-MiniLM-L6-v2` model
  (~80MB) lazily on the first `.embed()` call.
- **`CONSISTENTLY_WRONG`** detection is currently string-match-only
  (`expected.contains` / `not_contains`). Embedding-based contradiction
  detection ships with the full `ConsistencyOracle` in Phase 1.
- **Bootstrap CI** is unweighted percentile bootstrap. Bias-corrected
  variants land in Phase 1 if real-world signals demand them.
- **`--latest-baseline` / `--latest-candidate`** flags on `diff` are not
  shipped; users pass explicit session ids. Phase 1 candidate.

[0.1.0]: https://github.com/ericckzhou/falsifyai/releases/tag/v0.1.0
