---
name: Bug report
about: Something FalsifyAI did unexpectedly. Include a replay session id if possible.
title: '[bug] '
labels: bug
---

## What happened

<!-- Brief description of the unexpected behavior. -->

## Expected behavior

<!-- What you thought should happen instead. -->

## Reproduction

<!-- Minimal spec / command sequence that triggers the issue.
     If possible, paste the YAML spec inline. -->

```yaml
# your spec here
```

```bash
$ falsifyai run ...
# observed output
```

## Replay session id (high-signal!)

<!-- The unique value-add: if the bug shows up in a real run, the saved
     replay session contains EVERYTHING needed to reproduce. -->

- **Session id:** `<paste the session_id printed at the end of `falsifyai run`>`
- **Store path:** `<usually .falsifyai/replays.db>`
- Confirm you're OK sharing the artifact contents (model outputs may
  contain sensitive prompts/responses).

If you can attach the `.falsifyai/replays.db` file (or a sanitized copy),
add it to the issue. That's the deepest reproduction we can ask for.

## Environment

- **FalsifyAI version:** <`falsifyai --version` or `python -c "import falsifyai; print(falsifyai.__version__)"`>
- **Python version:** <`python --version`>
- **OS:** <macOS / Linux / Windows + version>
- **Model provider + model:** <e.g., openai/gpt-4o-mini>

## Additional context

<!-- Anything else: workarounds you tried, related issues, etc. -->
