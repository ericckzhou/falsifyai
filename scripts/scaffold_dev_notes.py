#!/usr/bin/env python3
"""Scaffold dev_notes/{plans,summaries,walkthroughs}/PR-N-slug.md stub files.

Creates three template markdown files for one PR, one in each dev_notes
subfolder, populated with the section headers documented in each folder's
README. Refuses to overwrite existing files unless --force is passed.

Usage:
    python scripts/scaffold_dev_notes.py <PR_NUMBER> <slug>
    python scripts/scaffold_dev_notes.py 5 invariant-runtime
    python scripts/scaffold_dev_notes.py 5 invariant-runtime --force

Run this BEFORE opening a feature PR so all three records exist as stubs
on disk. Skipping any of the three is what we are trying to make impossible.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEV_NOTES = REPO_ROOT / "dev_notes"


def _plan_template(n: int, slug: str, title: str) -> str:
    return f"""# PR #{n} Plan — {title}

> Status: drafting
> Target: `dev` -> `main`
> Paired summary: `dev_notes/summaries/PR-{n}-{slug}.md`
> Paired walkthrough: `dev_notes/walkthroughs/PR-{n}-{slug}.md`

## 1. Restated requirements

<what this PR sets out to do, in 1-2 paragraphs>

## 2. Background -- why this matters

<junior-friendly context: the problem space, why this is needed now>

## 3. Scope boundary

| In this PR | Deferred |
|---|---|
| | |

## 4. Decisions flagged for confirmation

<list open decisions A/B/C with recommendations; remove this section if no
open decisions>

## 5. File-by-file plan

### Production code

### Tests

## 6. Implementation order (TDD)

1.
2.

## 7. Risks

-

## 8. Acceptance / test plan

- [ ]

## 9. Estimated complexity

-

## 10. Branch + commit plan

-

---

## Decision recorded

**User: <name>, YYYY-MM-DD**

- <decision A>: <user pick>
- <decision B>: <user pick>
- **Overall:** <yes / no / modifications>
"""


def _summary_template(n: int, slug: str, title: str) -> str:
    return f"""# PR #{n} Summary — {title}

> Branch: `dev` -> `main` -- Squash commit: `<sha>` -- Merged: YYYY-MM-DD
> Paired plan: `dev_notes/plans/PR-{n}-{slug}.md`
> Paired walkthrough: `dev_notes/walkthroughs/PR-{n}-{slug}.md`

## Headline

<one sentence: what landed>

## Files touched

| File | Purpose |
|---|---|
| | |

## Stats

- Tests added:
- Total suite:
- Coverage:
- LOC:

## Conventions established

-

## Status

- Merged: YYYY-MM-DD
- Squash SHA on main: `<sha>`

## Next

-
"""


def _walkthrough_template(n: int, slug: str, title: str) -> str:
    return f"""# PR #{n} — {title}

> `<commit subject>`
> Branch: `dev` -> `main` -- Single commit: `<sha>` -- <N> tests -- <C>% module coverage
> Paired plan: `dev_notes/plans/PR-{n}-{slug}.md`
> Paired summary: `dev_notes/summaries/PR-{n}-{slug}.md`
>
> Junior-friendly walkthrough. Glossary at the bottom.

## 1. Overview

<1-2 paragraphs: what the PR does and where it sits in the roadmap>

## 2. Mental model

<how this fits the bigger picture; junior-friendly framing>

## 3. Concrete example

```python
# input -> output example
```

## 4. Files changed

| File | Purpose |
|---|---|
| | |

## 5. Architecture

```
<diagram>
```

## 6. Code walkthrough

### 6.1 <first file>

<explanation with snippets and inline definitions of non-obvious Python>

## 7. Design decisions

<non-obvious choices with rationale>

## 8. Test strategy

<what's tested, what isn't, why>

## 9. Conventions established

-

## 10. Risks / known limitations

-

## 11. What's next

<pointer to follow-up PRs>

---

## Glossary

| Term | One-line definition |
|---|---|
| | |
"""


def slug_to_title(slug: str) -> str:
    """Convert a kebab-slug to Title Case ('spec-materializer' -> 'Spec Materializer')."""
    return " ".join(part.capitalize() for part in slug.split("-"))


def write_stub(path: Path, content: str, *, force: bool) -> bool:
    """Write a stub file. Returns True if written, False if skipped (already exists)."""
    rel = path.relative_to(REPO_ROOT).as_posix()
    if path.exists() and not force:
        print(f"skip:    {rel}  (already exists; use --force to overwrite)")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"created: {rel}")
    return True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Scaffold dev_notes/{plans,summaries,walkthroughs}/PR-N-slug.md."
    )
    parser.add_argument("pr_number", type=int, help="PR number (positive integer)")
    parser.add_argument(
        "slug",
        type=str,
        help="Short kebab-case slug (e.g. 'invariant-runtime', 'sqlite-replay-store')",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files",
    )
    args = parser.parse_args(argv)

    if args.pr_number <= 0:
        print("error: PR number must be positive", file=sys.stderr)
        return 2
    if not args.slug or not all(c.isalnum() or c == "-" for c in args.slug):
        print("error: slug must be lowercase kebab-case (alnum + dash only)", file=sys.stderr)
        return 2

    title = slug_to_title(args.slug)
    n = args.pr_number
    slug = args.slug

    targets: list[tuple[Path, str]] = [
        (DEV_NOTES / "plans" / f"PR-{n}-{slug}.md", _plan_template(n, slug, title)),
        (DEV_NOTES / "summaries" / f"PR-{n}-{slug}.md", _summary_template(n, slug, title)),
        (DEV_NOTES / "walkthroughs" / f"PR-{n}-{slug}.md", _walkthrough_template(n, slug, title)),
    ]

    written = 0
    for path, content in targets:
        if write_stub(path, content, force=args.force):
            written += 1

    print(f"\n{written}/{len(targets)} files created.")
    print("Next: open each in your editor and fill in the sections.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
