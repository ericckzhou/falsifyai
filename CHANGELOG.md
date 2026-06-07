# Changelog

All notable changes to FalsifyAI are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Tests

- **Consumer-side verdict-map coverage guard.** A new meta-test
  ([`tests/meta/test_verdict_consumer_coverage.py`](tests/meta/test_verdict_consumer_coverage.py))
  asserts that the two consumer tables which turn a `Verdict` into a CI signal
  stay total over the enum: `render._EXIT_CODES` must cover every verdict (so
  `exit_code_for` can never `KeyError` on a real verdict — the contract is "one
  exit code your CI can gate on", and a crash is not an exit code), every
  verdict must map to a documented verdict-derived code (`0`/`1`/`2`/`4`), and
  `diff._QUALITY_RANK` must partition the enum into ranked verdicts plus exactly
  the two deliberately off-ladder ones (`INVALID_EVAL`, `INSUFFICIENT`) — so a
  newly added verdict can't silently fall off the quality ladder and suppress a
  `diff` regression signal as `OTHER_CHANGE`. This closes the seam left by the
  existing producer-side guard (`test_resolver_branch_count.py`) and the
  frozen-enum guard (`test_verdict_models.py`): the enum could grow and the
  resolver emit a new class while a downstream map went silently out of sync.
  No runtime behavior changes.

### Documentation

- **Evidence-protocol-doc freshness.**
  [`docs/EVIDENCE.md`](docs/EVIDENCE.md) now reflects v0.6.4 artifact semantics:
  the verdict-preservation section (§4.5) carries all nine `Verdict` members
  instead of the stale pre-0.6 five; the system-operations framing (§2) is
  restated as the producer / read-only-consumer split (`run` / `minimize`
  produce; `replay`, `inspect`, `diff`, `history`, `timeline`, `matrix`,
  `verify`, `export` consume), replacing a mislabeled "five operations" list;
  the materialized-spec section (§4.2) documents that `paraphrase` lineage
  preserves `validity_score` / `validity_method`; identity (§4.1) cross-links
  `cli_invocation` provenance to its §6 semantic boundary; and §4.5 clarifies
  that semantic-oracle effects are preserved *through* the assigned verdict and
  existing case/judgment fields, not as a separate stored oracle-results
  payload. A coarse meta-test
  ([`tests/meta/test_evidence_doc_freshness.py`](tests/meta/test_evidence_doc_freshness.py))
  now guards the contract: every `Verdict` member and every read-only consumer
  must be named in the doc. No runtime behavior changes.

- **Architecture-doc freshness + preservation guardrails.**
  [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) now reflects the full
  11-command CLI surface (the read-only consumers `inspect`, `history`,
  `timeline`, `matrix`, `verify`, `export` alongside `run` / `replay` / `diff`
  and the `doctor` diagnostic) and the current perturbation (`unicode_chars`,
  `paraphrase`) and invariant (`schema_match`) families. Two anti-entropy guards
  now back the doc's claims with executable invariants: a single parametrized
  harness asserts every read-only consumer closes its `ReplayStore` (on normal
  return *and* on post-construction read failure), and the CLI import-hygiene
  guard now also forbids read-only commands from importing
  `falsifyai.verdict.resolver` — mechanizing the long-standing "consumers never
  re-resolve" guarantee and closing a gap where `replay` had no such check. No
  runtime behavior changes.

## [0.6.4] — 2026-06-05

Patch release. Closes a self-falsification in the *evidence-generation* layer
surfaced by [case study 06](docs/case-studies/06-perturbation-validity-omission.md):
the `paraphrase` validity gate used embedding cosine similarity, which preserves
*topic* but not *task completeness*, so an `llm_rewrite` that deleted a task's
grounding while keeping its vocabulary passed the gate, drove the model to refuse,
and the refusal was scored as a stable failure — manufacturing
`CONSISTENTLY_WRONG @ 0.00` over a *correct* `llama-3.1-8b-instant`. The
`BidirectionalNLIValidator` from [plan.md §9.3](plan.md) — entailment in both
directions — now rejects such lossy rewrites **under `--nli`**. This completes the
self-falsification trilogy across all three layers (03 interpretation, 05
presentation, 06 generation). `--nli`-less runs are byte-identical.

### Added

- **Bidirectional-NLI perturbation validity gate (`perturbation/validity.py`).**
  The `BidirectionalNLIValidator` that [plan.md §9.3](plan.md) specified as the
  *default* validity check — but which the MVP deferred in favor of cosine
  similarity — now exists. A paraphrase is valid only if it **entails the
  original and is entailed by it**; an omission (the perturbed text drops a
  load-bearing clause) breaks the reverse direction and is rejected. The gate is
  wired into the `paraphrase` perturbation and fed the *same* NLI backend
  `--nli` already provisions for the semantic oracles — generation-layer logic,
  resolver untouched. Surfaced by [case study 06](docs/case-studies/06-perturbation-validity-omission.md).

### Fixed

- **`paraphrase` validity no longer admits intent-destroying rewrites under
  `--nli`.** Cosine similarity is symmetric and topical: an `llm_rewrite` that
  deleted a task's grounding but kept its vocabulary embedded ≥ 0.85 to the
  original and passed, then drove the model to refuse — a refusal scored as a
  stable failure. On the bundled [probe-06](docs/case-studies/probe-06/) extraction
  case this manufactured `CONSISTENTLY_WRONG @ 0.00` over a *correct*
  `llama-3.1-8b-instant`; with the bidirectional gate the 8 invalid paraphrases
  are rejected and dropped, and the case resolves `STABLE @ 1.00`. **`--nli`-less
  runs are byte-identical** (cosine-only gate unchanged); the validity method
  used is now stamped into each paraphrase's replay lineage (`validity_method`).

### Documentation

- **Case study 06 — "When the test deletes the question."** The third
  self-falsification study, completing one per architectural layer (03 =
  interpretation, 05 = presentation, 06 = evidence generation). Before/after
  evidence bundles preserved under [`docs/case-studies/data/`](docs/case-studies/data/).

## [0.6.3] — 2026-06-05

Patch release. Fixes a presentation-layer self-falsification surfaced by
[case study 05](docs/case-studies/05-confidence-floor-inversion.md): the per-case
`confidence` number inverted its meaning for instability-band verdicts
(`ADVERSARIALLY_VULNERABLE` / `FRAGILE` / `AMBIGUOUS`), reading near `0.00`
exactly when a case was *most* broken and best-supported. The verdict resolver
and stored artifacts are byte-identical — the fix is consumer-surface only. This
release also lands the additive `falsifyai.stores` plugin group as internal
plumbing for future store backends; default behavior is byte-identical (a bare
path is still SQLite, `:memory:` is still the in-memory store).

### Fixed

- **Per-case confidence label is band-aware across every consumer surface.** For
  instability-band verdicts (`ADVERSARIALLY_VULNERABLE` / `FRAGILE` /
  `AMBIGUOUS`), `falsifyai run`, `replay`, and `inspect` now render
  `verdict_confidence` as `stability floor:` instead of `confidence:`. The value
  is the stability CI lower bound — near `0.00` exactly when a case is *most*
  broken — so the `confidence:` label inverted its meaning for precisely the
  verdicts that matter most. `falsifyai history` previously printed the same
  value as an *unlabeled* number beside the CI band, where it both duplicated the
  CI floor and read as confidence; that redundant number is dropped, leaving the
  honest `(CI: …)` band (history's documented column). `matrix` and `timeline`
  were audited and were already honest (worst-case stability and `CIlow=`,
  respectively). Stable-band verdicts are unchanged. **Consumer surface only: the
  verdict resolver and stored artifacts are byte-identical.** See case study 05.

### Added

- **`falsifyai.stores` entry-point discovery.** `falsifyai/replay/registry.py`
  exposes `discover_stores()` and `build_store()`, mirroring the perturbation
  and invariant registries one tier down (assembly/wiring, not an evidence
  layer). A store backend registers a factory callable `(uri: str) ->
  ReplayStore` keyed by a `--store-path` URI scheme; the built-in `sqlite` and
  `memory` backends are registered the same way and dogfood the mechanism.
- **`scheme://` store selection.** `--store-path postgres://host/db` dispatches
  to the plugin registered under `postgres`, which receives the full URI. Bare
  paths (including Windows drive-letter paths) and `:memory:` are unchanged.

### Changed

- **`_build_store` consolidated.** The nine identical per-command copies of the
  `:memory:`/SQLite selection helper across the CLI (`run`, `replay`, `inspect`,
  `diff`, `history`, `timeline`, `matrix`, `verify`, `export`) are replaced by
  the single shared `build_store()`. No behavioral change; one source of truth
  for store construction.

### Documentation

- **Case study 05 — "When the confidence number lies."** A presentation-layer
  self-falsification over the *same* `probe-03.db` bundle as case study 03: the
  confidence number, not the verdict, was the false signal. Documents the
  inversion above and its band-aware fix.

## [0.6.2] — 2026-06-05

Patch release. Hardens the `schema_match` invariant against a false structural
failure surfaced by dogfooding case study 03 — correct JSON wrapped in a
markdown fence or embedded in prose was being scored as a shape failure. No new
fields, verdicts, or spec-language changes; extraction never relaxes the strict
schema check.

### Fixed

- **`schema_match` extracts JSON before validating.** The invariant previously
  ran `json.loads` on the entire model output, so correct JSON wrapped in a
  markdown fence (```` ```json … ``` ````) or embedded in a sentence was scored
  as a shape failure. It now extracts the JSON value (whole string → first
  fenced block → first balanced `{`/`[` value via `raw_decode`) before applying
  the unchanged strict schema check — extraction never relaxes validation. This
  is one of the three interpretation-layer findings from
  [case study 03](docs/case-studies/03-evaluator-false-positive.md) (Finding 3);
  the other two (`contains` literalness, `semantic_equivalence` style-sensitivity)
  are deliberately left as by-design spec-selection choices, not bugs.

## [0.6.1] — 2026-06-05

Patch release. Corrects a false-positive in the NLI `HallucinationOracle`
surfaced by dogfooding the probe-03 "confidently wrong" bake-off — where all
five candidate model outputs were in fact correct, yet one was being scored as a
confident falsehood. No new fields, verdicts, or spec-language changes; default
(non-`--nli`) behavior is byte-identical to 0.6.0.

### Fixed

- **`HallucinationOracle` treats NLI `NEUTRAL` as abstain, not wrong.** An
  output the NLI backend can neither entail nor contradict against the ground
  truth (relation `NEUTRAL`) is unsupported, not false — it no longer
  contributes a spurious `CONSISTENTLY_WRONG` signal. Previously a correct
  answer whose phrasing diverged from the reference enough to read as `NEUTRAL`
  was mislabeled a hallucination. The oracle now fires only on genuine
  `CONTRADICTION`. Regression tests pin the `NEUTRAL`→abstain boundary. See
  [`docs/case-studies/probe-03/RESULTS.md`](docs/case-studies/probe-03/RESULTS.md)
  (Finding 1) for the discovery and replay artifact.

## [0.6.0] — 2026-06-05

Semantic-judgment depth. Deepens the oracle layer with natural-language
inference (NLI) and completes the 8-verdict taxonomy the 5-verdict MVP
deferred. The NLI machinery is an opt-in extra (`pip install
"falsifyai[nli]"`); the default install and the 5-verdict behavior are
unchanged, so existing specs and replay artifacts read identically. The
four new verdicts are reachable only when grounding context and/or the NLI
oracles are supplied.

### Added

- **NLI backend primitive** — `NLIBackend` Protocol with bidirectional
  entailment/contradiction scoring. `MockNLIBackend` (deterministic,
  dependency-free) backs tests and default behavior; `TransformersNLIBackend`
  ships behind the opt-in `[nli]` extra, lazy-loaded so the model downloads
  only on the first `classify()` call, never at construction.
- **Semantic oracles** — `GroundingOracle` (answer supported by provided
  context → `INFORMATION_PRESENT`), `HallucinationOracle` (confident claim
  contradicted by ground truth → `CONSISTENTLY_WRONG`), and
  `ContradictionOracle` (self-inconsistency across the output set, with a
  vs-reference path). Aggregation helpers reduce per-output NLI labels to a
  single oracle signal.
- **Full 8-verdict resolver** — adds `INFORMATION_PRESENT`,
  `INFORMATION_NULL`, `ADVERSARIALLY_VULNERABLE`, and `AMBIGUOUS` to the prior
  five, completing the 2-D verdict space (§2). RAG-style grounding context is
  carried on `OracleContext`; failure-shape classification feeds the new
  branches. CLI exit codes map all nine verdicts.
- **`falsifyai run --nli`** — opt-in flag that constructs the NLI backend and
  activates the semantic oracles for a run. Purely additive: it adds
  grounding/hallucination evidence and can surface a richer verdict, but never
  turns a passing case into a failing one on its own.

### Notes

- Resolver verdict-branch count moved 5 → 9 (the four new verdict classes),
  still guarded by `tests/meta/test_resolver_branch_count.py`. This is the
  planned completion of the taxonomy, not resolver inflation — oracles continue
  to pre-arbitrate before the resolver.
- Default (no `--nli`) runs require no new dependencies and produce the same
  verdicts as 0.5.0; the heavyweight `transformers` + `torch` stack is pulled
  only by the `[nli]` extra.

## [0.5.0] — 2026-06-04

Capability-breadth track. Closes the Phase 1 capability gaps the
artifact-infrastructure track (0.2–0.4) skipped: the semantic-judgment
(oracle) layer, byte-level adversarial perturbation, structural assertion,
extensibility, and cross-run/cross-model analytics. Spec language is a
superset of 0.4.0 (new perturbation/invariant/plugin spec types); the
5-verdict set and replay format are unchanged (a new `invalid_eval_count`
field on `SessionVerdict` defaults for backward-compatible reads).

### Added

- **`unicode` perturbation family** (`ADVERSARIAL` category) — visually-identical,
  byte-different input: invisible space variants (incl. U+202F), zero-width
  characters, Cyrillic/Greek homoglyphs. The generation-side complement to case
  study 01; FalsifyAI now *generates* the failure it could previously only detect.
- **`schema_match` invariant** — strict structural assertion that output is valid
  JSON conforming to a declared schema (top-level type, required keys, typed
  properties), implemented over stdlib `json` with no new runtime dependency.
- **Oracle layer** — `Oracle` Protocol + `OracleVerdict` + `OracleContext` (the
  semantic-judgment surface), and a real `ConsistencyOracle` (ground-truth
  contradiction + optional embedding-agreement signal).
- **`MetaOracle`** — the sole, rigorous source of `INVALID_EVAL`: invariant
  degeneration (an invariant failing >95% of outputs including the clean baseline)
  and oracle conflict. Guarded by a resolver branch-count meta-test so oracles
  pre-arbitrate rather than inflating the verdict resolver.
- **Entry-point plugin system** — perturbations and invariants are extensible
  without forking via the `falsifyai.perturbations` / `falsifyai.invariants`
  entry-point groups and a generic `{type: plugin, name, params}` spec; built-ins
  are registered through the same mechanism (dogfooded).
- **`falsifyai matrix`** — cross-model reliability profiles: N sessions × perturbation
  families, each cell the model's worst-case stability in that family.
- **`falsifyai timeline`** — longitudinal robustness trend for one case (chronological
  `stability_ci_low` sparkline) with regression detection; exit 5 on a verdict-class
  downgrade. The inference counterpart to `history`.
- **`falsifyai minimize`** — minimal-falsifier search: the smallest perturbation
  strength that flips a case out of STABLE.

### Notes

- Resolver verdict-branch count moved 4 → 5 (the new `INVALID_EVAL` class), guarded
  by `tests/meta/test_resolver_branch_count.py`. Adding an oracle must not grow it.
- Consumer surfaces (`matrix`, `timeline`) are forbidden from importing the resolver
  (enforced by meta-tests); `minimize` is an orchestrator and legitimately resolves.

## [0.4.0] — 2026-05-24

Artifact-infrastructure track **complete** (3 of 3 locked items shipped).
Adds persisted `cli_invocation` on `ReplayArtifact` — descriptive
procedural provenance closing the locked sequence `verify` → `export
--bundle` → embedded CLI invocation. After v0.4.0, the artifact answers
four questions without external bookkeeping: what happened, how it was
evaluated, what was exported, and what command produced it. Spec language
and verdict semantics remain unchanged from 0.1.0.

### Added

- **`cli_invocation` field on `ReplayArtifact`** — descriptive provenance for
  the CLI command that produced the session. Captures normalized argv
  (program name canonicalized to `"falsifyai"` regardless of entry path) +
  the runtime `falsifyai_version`. Captured at entry into `cmd_run`;
  read-only consumer commands never stamp invocation. Pre-PR-35 artifacts
  carry `cli_invocation = None`; deserializer treats missing field as None
  (backward compat preserved). Bundle's auto-generated `README.md` renders
  a "Generated by" section when the field is present, with an explicit
  semantic-boundary disclaimer: *records what command produced the artifact,
  not a guarantee that re-running will produce identical outputs*. Replay
  determinism guarantees still live in `materialized_hash` and `bundle_id`.
  Closes the locked artifact-infrastructure sequence:
  `verify` ✅ → `export --bundle` ✅ → embedded CLI invocation ✅.

  Capture contract is deliberately narrow — `argv` + `falsifyai_version`
  only. **NOT captured by design:** environment variables, API keys,
  current working directory, hostname/username, shell history, file
  contents. Each exclusion is documented in `CliInvocation`'s docstring.

## [0.3.0] — 2026-05-24

Artifact-infrastructure track (2 of 3 locked items shipped). New `verify`
and `export --bundle` consumer surfaces, plus `diff` sharpening for CI
gating. EU AI Act Annex IV compliance mapping documented. Case study 02
adds a methodologically restrained second exemplar. Spec language and
verdict semantics remain unchanged from 0.1.0; every new surface is a
reader of preserved evidence, never a producer of new verdicts.

### Added

- **`falsifyai diff --strict`** — stricter exit criteria for CI gates: exits 5
  if any same-verdict case drops confidence by ≥ 0.10 (DECLINED signal), and
  exits 6 (`LOW_FALSIFIABILITY`) if the candidate session's falsifiability score
  is below 0.50. Exit 5 takes priority when both fire. The standard regression
  criterion (verdict-class downgrade → exit 5) is unchanged regardless of flag.

- **`falsifyai diff --show-timeline`** — renders every case as a row with a
  per-row direction marker: `REGRESSED`, `IMPROVED`, `DECLINED x.xx->y.yy (+dd)`,
  `RECOVERED x.xx->y.yy (+dd)`, or `STABLE`. Display-only; does not affect the
  exit code.

- **Exit code 6 (`LOW_FALSIFIABILITY`)** — new exit code for `diff --strict`;
  fires when candidate falsifiability < 0.50 and no exit-5 condition is present.

- **`falsifyai verify <session_id>`** — replay-artifact integrity validation.
  Runs 8 read-only checks against a stored `ReplayArtifact`: session_id format,
  tz-aware `created_at`, `materialized_hash` recomputation (load-bearing), and
  internal consistency of session-verdict roll-up counts, CI bound ordering,
  and falsifiability score range. Pure preservation-layer command; never
  re-resolves the verdict. Use `--all` to verify every session in the store.

- **Exit code 7 (`INTEGRITY_FAILURE`)** — new exit code for `verify`; fires
  when at least one integrity check fails on at least one artifact.

- **`falsifyai export <session_id> --bundle <output>`** — deterministic
  portable evidence bundle for the artifact-infrastructure track. Produces
  a `.fai.zip` containing `manifest.json` (with content-addressed
  `bundle_id`, per-file SHA256s, and provenance metadata), `artifact.json`,
  an optional `spec.yaml` (when `--spec-path` supplied), and an
  auto-generated `README.md`. Refuses to export corrupted artifacts by
  default; `--allow-corrupted` honors the request and records
  `exported_under_protest=true` in the manifest. Two exports of the same
  artifact with the same `--exported-at` produce byte-identical bundles
  and identical `bundle_id`s — the bundle is an addressable evidence
  object. Second step in the artifact-infrastructure sequence
  (verify → export → embedded CLI invocation).

## [0.2.0] — 2026-05-22

Phase 1 release. Three new consumer surfaces (`inspect`, `history`), one new
perturbation family (`paraphrase`), one canonical case study with bundled
replay artifact, and an automated PyPI publishing pipeline via Trusted
Publisher (OIDC). The artifact format, the spec language, and the resolver
behavior for `run` / `replay` / `diff` are unchanged from 0.1.0 — every
new surface is a reader of preserved evidence, never a producer of new
verdicts.

### Added

- **Canonical case study: "Invisible character substitution"** —
  [`docs/case-studies/01-invisible-character-substitution.md`](docs/case-studies/01-invisible-character-substitution.md).
  Asymmetric narrative: the cross-model `contains`-contract brittleness
  pattern (visible via `history`) is the thesis; the Pair 3 model
  migration regression (visible via `diff` + `inspect`, manifesting as
  a U+202F substitution between "30" and "days") is the vivid concrete
  proof. Ships with a bundled [`ReplayStore`](docs/case-studies/data/case-study-replays.db)
  containing all 8 sessions from the Phase 0 validation campaign, plus
  a [provenance README](docs/case-studies/data/README.md) recording
  SHA256, environment, and session-to-model mappings. Every CLI command
  shown in the case study runs against the bundle and reproduces the
  displayed output verbatim. Top-level [`README.md`](README.md) gains a
  Case studies section and a bridging link from the 5-minute proof.

  No code change; documentation + data only. Phase 1 content track —
  demonstrates `history`, `diff`, `inspect`, and `replay` as different
  consumer surfaces over one preserved evidence substrate.

- **`falsifyai history <case_id>`** — temporal view of one case across
  all saved sessions in the store. One row per session, newest-first,
  showing verdict + CI + worst perturbation family (when FRAGILE).
  Flags:
  - `--limit N` caps the number of sessions returned (default 20).
    `--limit 0` means unlimited.
  - `--store-path PATH` mirrors `run` / `replay` / `inspect` / `diff`.

  Exit codes:
  - `0` on render success (regardless of verdict mix — history is
    informational, not a CI gate)
  - `3` (ERROR) when the case_id matches zero sessions, or when an
    artifact contains the same case_id more than once (treated as
    malformed evidence; the row renders as `<malformed: N matches>`
    so the anomaly isn't silent)

  Phase C of the validation campaign. Pure consumer surface — reads
  `case.verdict` from preserved artifacts via
  `ReplayStore.query_sessions(case_id=...)`; never re-resolves, never
  aggregates, never infers trends. The reader sees raw timeline data
  and draws their own conclusions.

  No spec_hash filtering by default: case identity transcends spec
  evolution, which is what makes the temporal view interesting in the
  first place (a model migration that changed `spec.model` still
  produces sessions for the same case_ids).

- **`paraphrase` perturbation family** — LLM-driven semantic-preserving
  rewrites with embedding-similarity validity gating. Third perturbation
  family after `typo_noise` and `casing_variant`, but the first to test a
  *semantic* pressure axis rather than character-level. Phase B of the
  validation campaign — selected by evidence (Phase 0 found character-level
  perturbations saturating; semantic robustness was the next missing axis).

  Spec syntax:
  ```yaml
  perturbations:
    - type: paraphrase
      count: 3                       # default 3
      similarity_threshold: 0.85     # default 0.85
      max_attempts: 3                # default 3 retries per invalid sample
      model:                         # optional; defaults to spec.model
        provider: groq
        model: llama-3.1-8b-instant
  ```

  Behavior:
  - Each requested paraphrase is generated by one LLM call. Per-sample
    seed varies so adapters that honor `seed` see distinct calls.
  - Each generated paraphrase is validated via embedding cosine similarity
    vs the original. Failed paraphrases are dropped; the perturbation
    retries up to `max_attempts` times per sample. If a sample slot can't
    produce a valid paraphrase within budget, it is dropped (the result
    list can be shorter than the requested count).
  - Generation happens at materialization time; the realized paraphrases
    are persisted in `MaterializedCase.realized_perturbations`. Replay
    reads from there — never regenerates.
  - Lineage carries `sample_index`, `attempts_used`, `requested_count`,
    `similarity_threshold`, `model`, and `validity_score` so a reader can
    reconstruct how each paraphrase was produced.
  - The default embedder is `SentenceTransformerBackend` (same as
    `semantic_equivalence` invariant; install `pip install "falsifyai[semantic]"`).

  When the system-under-test is the spec's primary model, the paraphrase
  spec should override `model:` with an independent paraphraser to avoid
  the self-paraphrase paradox (in-distribution paraphrases bias the test).

- **`falsifyai inspect <session_id>`** — per-case deep-dive over a stored
  session's preserved evidence. Default render shows verdict + perturbation
  count for every case, plus worst-perturbation evidence (perturbed input,
  output excerpt, failing invariant) for non-STABLE cases. Flags:
  - `--case <case_id>` expands one case to show every perturbation
  - `--full` disables output truncation (default truncates outputs >400
    chars to head-200 + tail-100 with an explicit marker)
  - `--store-path PATH` mirrors `run` / `replay` / `diff`
  Exit codes mirror `replay`: STABLE→0, FRAGILE→1, CONSISTENTLY_WRONG→2,
  ERROR (missing session, unknown case_id)→3.
- Pre-PR-11 legacy artifacts render `(legacy)` instead of misleading
  zero-CI numbers (same heuristic as `replay`).
- cp1252-safe rendering: `inspect` reconfigures stdout to
  `errors='backslashreplace'` so model-emitted Unicode (e.g. ` `
  narrow no-break space) escapes rather than crashes on non-UTF-8
  terminals.
- **Automated PyPI publishing via Trusted Publisher (OIDC).**
  `.github/workflows/publish.yml` fires on any `v*` tag push: verifies
  tag-vs-`pyproject.toml` version match, re-runs the full test suite,
  builds sdist + wheel, validates with `twine check`, and publishes
  via `pypa/gh-action-pypi-publish`. No long-lived API tokens stored
  in the repo. Requires one-time PyPI-side Trusted Publisher
  configuration before first use — see
  [`docs/RELEASE.md`](docs/RELEASE.md). The manual `twine upload` flow
  remains available as a fallback.

### Notes

This is the first Phase 1 feature. Selected by evidence — the Phase 0
validation campaign produced its first regression (`policy_summary`
STABLE→FRAGILE on `openai/gpt-oss-120b` via Groq), and the immediate user
need was *"why did it regress?"* — a question the 0.1.0 CLI couldn't
answer. `inspect` makes the replay artifact's preserved evidence legible.

The artifact format, resolver behavior, and CLI subcommand contracts for
`run`/`replay`/`diff` are unchanged. `inspect` is pure consumer surface
(reads from the artifact, never re-resolves).

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

[0.6.4]: https://github.com/ericckzhou/falsifyai/releases/tag/v0.6.4
[0.6.3]: https://github.com/ericckzhou/falsifyai/releases/tag/v0.6.3
[0.6.2]: https://github.com/ericckzhou/falsifyai/releases/tag/v0.6.2
[0.6.1]: https://github.com/ericckzhou/falsifyai/releases/tag/v0.6.1
[0.6.0]: https://github.com/ericckzhou/falsifyai/releases/tag/v0.6.0
[0.5.0]: https://github.com/ericckzhou/falsifyai/releases/tag/v0.5.0
[0.4.0]: https://github.com/ericckzhou/falsifyai/releases/tag/v0.4.0
[0.3.0]: https://github.com/ericckzhou/falsifyai/releases/tag/v0.3.0
[0.2.0]: https://github.com/ericckzhou/falsifyai/releases/tag/v0.2.0
[0.1.0]: https://github.com/ericckzhou/falsifyai/releases/tag/v0.1.0
