<!--
Thanks for the PR! This template mirrors FalsifyAI's local dev_notes
summary format. Fill out what's relevant; delete what's not.

For non-trivial changes, see CONTRIBUTING.md for the architectural
constraints (especially: resolver complexity is bounded; three-layer
separation is non-negotiable).
-->

## Headline

<!-- One sentence: what does this PR do? -->

## Problem pressure

<!-- 1-2 sentences: what gap does this close? Why now? -->

## Abstraction shipped

<!-- The new contract / Protocol / module / behavior, named explicitly. -->

## Alternatives rejected

<!-- Bullet list, one line each, with one-line reasoning per alternative.
     High-signal for future engineers who hit the same decision fork. -->

-

## Architectural invariants

<!-- System-level contracts this PR establishes or preserves. NOT coding
     style. If this PR touches the verdict resolver, include an
     explicit answer to the trust test from CONTRIBUTING.md:
     "Can a competent user still predict the resolver output from the
     inputs?" -->

-

## Test plan

<!-- - [x] specific tests added
     - [ ] manual smoke
     - [ ] `uv run pytest` passes
     - [ ] `uv run ruff check . && uv run ruff format --check .` clean
     - [ ] CI green on `dev`
     - [ ] CI green on PR target `main`
-->

- [ ] `uv run pytest` passes
- [ ] `uv run ruff check .` clean
- [ ] `uv run ruff format --check .` clean

## Architectural fit (self-check)

- [ ] Touches exactly **one** of the three layers (generation /
  interpretation / preservation), or is a pure consumer.
- [ ] If touching `falsifyai/verdict/resolver.py`: the trust test still
  passes (a competent user can predict the output from the inputs).
- [ ] Does not introduce new spec language fields, verdict types, or
  configurable thresholds without a separate architectural conversation.
