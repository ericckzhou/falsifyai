# Capturing the FalsifyAI Demo

A ~30-second terminal recording that shows the migration-investigation
workflow end-to-end. The demo is the visual complement to the README
walkthrough section.

The recording itself is **user-side** — this document gives you the exact
commands to run and a tool recommendation. It does NOT live in the repo
(the binary `.cast` would; we prefer to embed it via GitHub Pages or a
hosted asciinema URL).

## Tooling

We recommend [asciinema](https://asciinema.org) — a free, lightweight
terminal recorder that produces text-based `.cast` files. Reasons:

- The output renders as an animated terminal in any browser.
- The file is plain text (small, diff-friendly).
- The asciinema-player can embed in the README via raw HTML once GitHub
  enables it (currently external link only).
- No video editing. No screen capture. No cropping.

Install:

```bash
# macOS
brew install asciinema

# Linux
pip install asciinema
# or your package manager
```

## Prerequisites

- An `OPENAI_API_KEY` (or equivalent for your provider) set in your
  shell. The demo uses real LiteLLM calls for authenticity.
- FalsifyAI installed: `uv sync --extra dev` or `pip install falsifyai`.
- A clean `.falsifyai/` directory so the demo's session ids are visible.

```bash
rm -rf .falsifyai/
```

> **MockAdapter fallback (no API key, faster recording):**
> If you'd rather record without credentials, monkey-patch
> `falsifyai.cli.run.build_adapter` in a small wrapper script:
> ```python
> # demo_with_mock.py
> import sys
> import falsifyai.cli.main as cli_main
> import falsifyai.cli.run as cli_run
> from tests.fixtures.mock_adapter import MockAdapter
>
> _MOCK_GOOD = MockAdapter(default_response="Paris is the capital of France.")
> _MOCK_BAD = MockAdapter(default_response="I don't know.")
>
> # Swap the adapter based on an env var the script sets between runs.
> import os
> cli_run.build_adapter = lambda model: (
>     _MOCK_BAD if os.environ.get("FALSIFY_DEMO_MODE") == "bad" else _MOCK_GOOD
> )
>
> sys.exit(cli_main.main(sys.argv[1:]))
> ```
> Use it as `python demo_with_mock.py run examples/model_migration.yaml`.
> Document in the recording's caption that the underlying model is
> mocked.

## The demo script (real LiteLLM)

The whole thing is ~30 seconds at a comfortable read pace.

### 1. Start the recording

```bash
asciinema rec falsifyai-demo.cast
```

Asciinema starts capturing your terminal. Speak slowly; don't rush.

### 2. Set the scene

```bash
clear
echo "FalsifyAI: catch LLM migration regressions in one command"
sleep 1
```

### 3. Show the spec briefly

```bash
cat examples/model_migration.yaml
sleep 2
```

Don't read it aloud; just show that the spec exists and is small.

### 4. Run against the baseline model

```bash
falsifyai run examples/model_migration.yaml
sleep 2
```

The output shows STABLE verdicts. Highlight (visually or with a follow-up
`echo`) the session id printed at the end.

### 5. Switch the model

For the real-LiteLLM version, change the `model:` field in
`examples/model_migration.yaml` (or have a degraded variant ready):

```bash
# Edit the spec: e.g., change gpt-4o-mini -> gpt-3.5-turbo, or use
# a deliberately-weaker setup.
sed -i.bak 's/gpt-4o-mini/gpt-3.5-turbo/' examples/model_migration.yaml
sleep 1
```

(If the audience won't see the spec change, narrate it.)

### 6. Run again

```bash
falsifyai run examples/model_migration.yaml
sleep 2
```

The output may now show FRAGILE or CONSISTENTLY_WRONG. Note the new
session id.

### 7. Diff the two runs

```bash
# Substitute the actual session ids printed in steps 4 and 6.
falsifyai diff <SESSION_A> <SESSION_B>
sleep 3
```

The REGRESSED row appears. Exit code: 5.

```bash
echo "Exit code: $?"
sleep 1
```

### 8. Stop the recording

Press `Ctrl-D` (or `exit`).

Asciinema saves the `.cast` file at the path you specified.

## Publishing

```bash
# Upload to asciinema.org for a public URL.
asciinema upload falsifyai-demo.cast
```

The upload returns a public URL. Add it to the README and pin it to the
GitHub Release. If you'd rather self-host, the `.cast` file pairs with
the asciinema-player JS for embedding.

## Optional: showcase the 0.6.0 NLI layer

The core demo above stays on the migration wedge. For the 0.6.0 release you
may want a second short clip showing the opt-in NLI oracle layer turning a
silent pass into a graded verdict:

```bash
# Without --nli: the case looks STABLE.
falsifyai run examples/information_present.yaml
sleep 2

# With --nli: the grounding oracle surfaces INFORMATION_PRESENT.
falsifyai run examples/information_present.yaml --nli
sleep 2
```

The point to narrate: `--nli` is **purely additive** — it never flips a pass
into a fail, it adds grounding/hallucination evidence that the resolver
compresses into the full 8-verdict taxonomy (`INFORMATION_PRESENT`,
`INFORMATION_NULL`, `ADVERSARIALLY_VULNERABLE`, `AMBIGUOUS` joined the prior
five in 0.6.0). Requires `pip install "falsifyai[nli]"`; the NLI model
downloads on the first run, so mention that in the caption to keep the pause
from reading as a hang.

## Tips

- **Type slowly** — the recording captures keystrokes. Real-time typing
  is part of the texture.
- **Show the regression's session ids explicitly** — for viewers who
  pause the video, the ids should be readable.
- **Don't try to fit ARCHITECTURE.md into the demo.** The demo's job is
  to communicate the wedge in 30 seconds; the README's job is to expand
  it; ARCHITECTURE.md's job is to deep-dive. Keep the demo at the wedge.

## What the demo should NOT show

- **Don't show stack traces or error states** unless a separate
  "what failure looks like" demo is intended.
- **Don't show provider-specific output** that would tie the demo to one
  vendor's quirks. The point is the FalsifyAI workflow, not OpenAI vs
  Anthropic.
- **Don't show the verbose `falsifyai --help` output.** Save that for
  a separate reference demo if needed.
