# Release Checklist

The maintainer-facing process for cutting a new FalsifyAI release. Releases
are infrequent enough that the steps will be forgotten between them; this
is the canonical reference.

## Versioning convention

FalsifyAI follows [Semantic Versioning 2.0.0](https://semver.org/).

| Version part | When to bump |
|---|---|
| **MAJOR** (1.0.0 → 2.0.0) | Breaking change to spec language, replay artifact schema, or verdict semantics. |
| **MINOR** (0.1.0 → 0.2.0) | New feature, new verdict, new perturbation family. Spec language extensions that add fields. |
| **PATCH** (0.1.0 → 0.1.1) | Bug fixes, dependency updates, docs improvements. No new fields, no new verdicts, no new behavior. |

**Pre-1.0 (current).** Internal APIs may evolve between MINOR bumps. The
public CLI surface and spec language are stable within a MINOR line
(0.1.x), as noted in the README. Once 1.0.0 ships, the major-version
bump rules apply strictly.

## Pre-release checklist

Run through every item before tagging. CI doesn't catch all of these.

1. **All tests green.**
   ```bash
   uv run pytest
   ```

2. **Coverage ≥ 80% baseline.**
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

7. **README badges + status line current.** The status line at the top
   should reflect the version being released.

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

## Tag

```bash
# Create an annotated tag matching the version.
git tag -a v0.1.0 -m "Release 0.1.0"

# Push the tag.
git push origin v0.1.0
```

## Upload

PyPI credentials live in `~/.pypirc` or as `TWINE_USERNAME` +
`TWINE_PASSWORD` env vars. Use `__token__` as the username with an API
token for the password (recommended over basic auth).

```bash
# Test on TestPyPI first if it's a meaningful release.
uv run twine upload --repository testpypi dist/*

# Real upload.
uv run twine upload dist/*
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
3. Choose the tag you just pushed (`v0.1.0`).
4. Title: `0.1.0 — Phase 0 MVP` (or equivalent thematic name).
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

2. **Bump version to next dev marker.** If this is the start of work
   toward 0.2.0:
   - `pyproject.toml`: `version = "0.2.0.dev0"`
   - `falsifyai/__init__.py`: `__version__ = "0.2.0.dev0"`
   - Open a PR titled `chore: bump version to 0.2.0.dev0`.

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
