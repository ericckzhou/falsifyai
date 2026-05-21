---
name: pr-review
description: Use this skill before committing, pushing, opening a PR, merging, or starting implementation from a locked plan in the FalsifyAI repo. It performs a pre-flight self-review against the three-layer architecture, evidence-density principle, resolver-inflation guardrail, replay-preservation expectations, dogfood/example requirements, and release/readiness gates.
---

# pr-review — FalsifyAI pre-flight self-review

This skill runs **before** a destination-bound action: a commit, a push, opening a PR, merging a PR, or starting implementation from a locked plan. It is not a code-review pass on someone else's work — it is *your* checklist for whether the change you're about to ship clears FalsifyAI's architectural gates.

## STOP clause (load-bearing)

**If any gate below fails, stop.** Do not commit. Do not push. Do not continue implementation. Surface the failing gate to the user verbatim and ask whether to:

1. **Split** the change (most common — usually means the PR is touching multiple layers),
2. **Revise** the change to clear the gate, or
3. **Explicitly accept the risk** (rare; requires the user to name what they're accepting).

A skill that does not stop on failure is decoration. This one stops.

## When to invoke

Auto-invoke when the immediate intent is clearly:

- about to `git commit` or `git push`
- about to open a PR (`gh pr create`)
- about to merge a PR
- about to start implementation from a plan the user has approved

Do **not** auto-invoke for:

- casual discussion, brainstorming, or design exploration
- README copy edits, typo fixes, doc-only formatting
- exploratory reads / Q&A about the codebase

## The six gates

For each gate: state the answer in one sentence. If unclear or "no," that is a failure — stop and surface it.

### Gate 1 — Which layer does this touch?

FalsifyAI separates **evidence generation** (perturbation / materialization / execution) from **evidence interpretation** (invariants / verdict resolver / CLI compression) from **evidence preservation** (replay artifacts / stores). See [`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md) and [`.claude/CLAUDE.md`](../../CLAUDE.md#design-philosophy-load-bearing).

**Answer in one of**: generation, interpretation, preservation, consumer surface (CLI / diff / replay).

### Gate 2 — Does it touch more than one layer?

If yes: should it be split into separate commits or PRs? Cross-layer changes are the most common source of architectural drift. The default answer is *split it*; the exception requires a one-line justification.

### Gate 3 — Does it inflate the resolver?

The verdict resolver is the epistemic authority of the framework. Its priority chain must stay compressible and predictable.

**Trust test** (authoritative copy in [`CONTRIBUTING.md`](../../../CONTRIBUTING.md)): *A competent user should be able to predict the resolver output from the inputs.*

If this change adds heuristics, thresholds, new verdict types, new confidence semantics, new knobs, or new metrics that the resolver consults — the trust test must still pass after the change. If it does not, the work belongs in the **consumer surface** (replay, diff, future tools), not the resolver.

### Gate 4 — Evidence density or evidence volume?

FalsifyAI optimizes for **evidence density**, not volume. See the four pillars in [`.claude/CLAUDE.md`](../../CLAUDE.md#four-pillars).

Ask: *would removing this output / field / row make the engineer's decision worse?* If the answer is no, the addition is volume, not density — cut it.

### Gate 5 — Are replay artifacts preserved, not recomputed?

Replay is read-only. Verdicts shown by `falsifyai replay` are the ones assigned at run time and never re-resolved. If this change reads from a stored artifact and then re-judges, re-resolves, or recomputes a verdict — that is a preservation violation. Move the logic to *run-time* (write path) or to a new consumer surface command that is explicitly not `replay`.

### Gate 6 — Examples dogfooded if user-facing behavior changed?

If this change alters CLI behavior, spec language, verdict semantics, or output shape: at least one example under [`examples/`](../../../examples/) and the matching dogfood test in [`tests/integration/test_examples.py`](../../../tests/integration/test_examples.py) must demonstrate the new behavior end-to-end. Examples are the canonical user-facing spec surface — if the parser or resolver no longer accepts something the examples use, CI must fail immediately.

## How to surface a failing gate

When stopping, write one short paragraph in this shape:

> **Stopping before [commit/push/PR/implementation].** Gate N (*one-line gate name*) failed: *one sentence on why*. Options: split / revise / accept-risk. Which?

Do not enumerate every gate that passed. Surface only the failing one. The user already knows what the gates are.

## Scope notes

- This skill is a pre-flight self-check, not a substitute for the `code-reviewer` agent on substantive changes — invoke that separately when the change is non-trivial.
- This skill is project-specific to FalsifyAI. Generic code-quality concerns (file size, naming, error handling) are covered by user-global rules and are not duplicated here.
- Authoritative philosophy lives in [`.claude/CLAUDE.md`](../../CLAUDE.md), authoritative architecture in [`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md), authoritative resolver trust test in [`CONTRIBUTING.md`](../../../CONTRIBUTING.md). If a gate here drifts from those docs, the docs win — update the skill, not the doc.
