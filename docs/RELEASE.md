# Release Checklist

The maintainer-facing process for cutting a new FalsifyAI release. Releases
are infrequent enough that the steps will be forgotten between them; this
is the canonical reference.

> **Automation status (added 2026-05-22).** Publishing to PyPI is now
> automated by `.github/workflows/publish.yml` using PyPI Trusted Publisher
> (OIDC) — no API tokens are stored in the repo. The workflow fires on any
> `v*` tag pushed to the repo. The manual `twine upload` steps below are
> preserved as a fallback in case the automation needs to be bypassed.

## Versioning convention

FalsifyAI follows [Semantic Versioning 2.0.0](https://semver.org/).

| Version part | When to bump |
|---|---|
| **MAJOR** (1.0.0 → 2.0.0) | Breaking change to spec language, replay artifact schema, or verdict semantics. |
| **MINOR** (0.3.0 → 0.4.0) | New feature, new verdict, new perturbation family. Spec language extensions that add fields. |
| **PATCH** (0.1.0 → 0.1.1) | Bug fixes, dependency updates, docs improvements. No new fields, no new verdicts, no new behavior. |

**Pre-1.0 (current).** Internal APIs may evolve between MINOR bumps. The
public CLI surface and spec language are stable within a MINOR line
(0.1.x), as noted in the README. Once 1.0.0 ships, the major-version
bump rules apply strictly.

## Pre-release checklist

**One command runs the executable subset** (lint, format, coverage-gated tests,
build, `twine check`):

```bash
uv run python scripts/release_gate.py
```

It exits non-zero on the first failure. Run it first; the manual items below
cover what a script can't (CHANGELOG prose, version-string audit, smoke tests).

Run through every item before tagging. CI doesn't catch all of these.

1. **All tests green.**
   ```bash
   uv run pytest
   ```

2. **Coverage ≥ 90%.** Enforced by CI (`--cov-fail-under=90`) and by the
   release gate; this command shows the per-file gaps.
   ```bash
   uv run pytest --cov=falsifyai --cov-report=term-missing
   ```

3. **Lint + format clean.**
   ```bash
   uv run ruff check .
   uv run ruff format --check .
   ```

4. **All four example specs produce the expected verdicts.** The dogfood
   tests already cover this, but it's worth a manual smoke too.

5. **`CHANGELOG.md` updated.** A new `## [<version>] — YYYY-MM-DD` entry
   covers every PR landed since the last release, grouped thematically.

6. **Version bumped in both places.**
   - `pyproject.toml` `[project] version = "..."`
   - `falsifyai/__init__.py` `__version__ = "..."`
   - `tests/unit/test_version.py` (update the hardcoded assertion)

7. **Release-state metadata audit.** Several files contain a version
   string that means *"the current release"* — they MUST advance on
   every release. This is distinct from historical context references
   (e.g. *"unchanged from 0.1.0"*) which MUST NOT change. A blanket
   grep would produce both signals; the audit is a deliberate
   human-judgment pass, not an automated gate.

   Drift-prone files to check on every release:
   - [ ] `README.md` status banner (top of file) — names the version
     and the shipped feature wave for the public.
   - [ ] `README.md` "Status and roadmap" section — `(current release)`
     marker matches the new version; previous version stays as
     historical entry.
   - [ ] `CITATION.cff` — `version:` and `date-released:` fields
     (machine-readable; consumed by citation tools).
   - [ ] `docs/EVIDENCE.md` — the *"Today (X.Y.Z), the artifact has…"*
     paragraph in §6.2; this is a release-state claim about current
     guarantees.
   - [ ] `docs/case-studies/*.md` — `pip install falsifyai==X.Y.Z`
     commands in reproduction sections (so readers install the
     version that contains the case study itself).
   - [ ] `CHANGELOG.md` — new `[X.Y.Z]: <release URL>` link added
     under the existing `[N-1.Y.Z]` reference at the bottom.
   - [ ] `docs/RELEASE.md` (this file) — concrete example tag
     commands and the "next dev marker" example should reference the
     most recent release as their illustrative case.

   Files that *also* contain version strings but are historically
   accurate — do NOT change without specific reason:
   - `CHANGELOG.md` body lines mentioning prior versions in context
     (e.g. *"unchanged from 0.1.0"*).
   - `docs/case-studies/data/README.md` provenance — the FalsifyAI
     version recorded there reflects when the bundled artifacts were
     *generated*, not the current release.
   - `docs/ARCHITECTURE.md` discipline statements anchored to the
     0.1.0 baseline.

8. **Documentation links work.** Quick check that all
   `[link](docs/...)` references resolve on the branch you're tagging.

## Build + validate

```bash
# Clean previous artifacts.
rm -rf dist/

# Build wheel + sdist.
uv build

# Validate the packaged metadata.
uv run twine check dist/*
```

Expected output: `Checking dist/... PASSED` for both wheel and sdist.

If `twine check` fails, the most common causes are:

- Missing or malformed `[project.urls]` entries in `pyproject.toml`.
- Long-description encoding issues (rare with `readme = "README.md"`).
- Invalid classifiers.

## Tag (triggers automated publish)

```bash
# Create an annotated tag matching the version (substitute the new version below).
git tag -a v0.6.4 -m "Release 0.6.4"

# Push the tag. This fires .github/workflows/publish.yml.
git push origin v0.6.4
```

The workflow:

1. Verifies the tag version matches `pyproject.toml`'s declared version
   (fail-fast on mismatch — catches the "forgot to bump pyproject.toml"
   mistake).
2. Re-runs the full test suite on the tagged commit.
3. Builds sdist + wheel via `uv build`.
4. Validates the distributions with `twine check`.
5. Publishes to PyPI via Trusted Publisher OIDC (no API token needed).

Watch the run at
`https://github.com/ericckzhou/falsifyai/actions/workflows/publish.yml`.

### One-time PyPI Trusted Publisher setup

This needs to be done once on the PyPI side before the workflow can
publish. Repo maintainers only.

1. Go to https://pypi.org/manage/project/falsifyai/settings/publishing/.
2. "Add a trusted publisher" → GitHub.
3. Fill in:
   - **PyPI Project Name:** `falsifyai`
   - **Owner:** `ericckzhou`
   - **Repository name:** `falsifyai`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `pypi`
4. Optionally configure the `pypi` environment in GitHub repo settings
   (Settings → Environments → New environment → `pypi`) to require
   manual approval as an extra gate before each publish.

### Manual upload (fallback)

If the workflow is broken or needs to be bypassed, the manual path
still works. PyPI credentials live in `~/.pypirc` or as
`TWINE_USERNAME` + `TWINE_PASSWORD` env vars. Use `__token__` as the
username with an API token for the password.

```bash
# Test on TestPyPI first if it's a meaningful release.
uv run --with twine twine upload --repository testpypi dist/*

# Real upload.
uv run --with twine twine upload dist/*
```

After upload, verify:

```bash
# In a clean venv:
pip install falsifyai==<version>
falsifyai --help
```

## GitHub Release

1. Go to the [Releases page](https://github.com/ericckzhou/falsifyai/releases).
2. Click "Draft a new release."
3. Choose the tag you just pushed (e.g. `v0.4.0`).
4. Title: `<version> — <thematic name>` (e.g. `0.4.0 — Artifact-infrastructure track complete`).
5. Body: copy the matching section from `CHANGELOG.md` verbatim.
6. Publish.

## Announce (optional)

If the release warrants public attention:

- Hacker News (Show HN, link to the README walkthrough section directly).
- X / LinkedIn / Mastodon.
- The launch wedge framing — *"flag LLM model-migration regressions
  structurally with a single command"* — usually lands better than a
  feature-list announcement.

## Post-release hygiene

1. **Update local + remote `dev` branch.** Sync `dev` to the new `main`:
   ```bash
   git checkout main && git pull
   git checkout dev && git reset --hard origin/main
   git push --force-with-lease origin dev
   ```

2. **Bump version to next dev marker.** Optional but recommended when
   starting work toward the next release. For example, after `0.6.4`
   ships and the next planned release is `0.7.0`:
   - `pyproject.toml`: `version = "0.7.0.dev0"`
   - `falsifyai/__init__.py`: `__version__ = "0.7.0.dev0"`
   - `tests/unit/test_version.py`: update the asserted version string.
   - Open a PR titled `chore: bump version to <next>.dev0`.

3. **Open a `CHANGELOG.md` "## [Unreleased]" section** under the version
   header for the next release's entries.

## If something goes wrong

- **Bad upload (broken metadata, accidental private file, etc.):** PyPI
  does not allow re-uploading the same version. Yank the release on PyPI,
  bump to the next patch version, fix the issue, and re-release.
- **Bug discovered post-release:** bump patch, fix, release. Don't try
  to amend a tagged release.
- **Spec / artifact schema change shipped accidentally:** treat as a
  breaking change. Yank, communicate, plan the major version bump.
