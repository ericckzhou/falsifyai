# FalsifyAI

> Falsification-first reliability testing for AI systems.
> *"Can this behavior survive falsification?"*

**Status:** pre-MVP scaffold. See [plan.md](plan.md) for the full design.

## Install (planned)

```bash
pip install falsifyai
```

Once published. Not yet available on PyPI.

## Quick start (planned)

```bash
falsifyai run eval.yaml
```

See [plan.md §22.1](plan.md) for the 2-week MVP scope.

## Local development

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
uv venv
uv sync --extra dev
uv run pytest
```

## License

Apache 2.0. See [LICENSE](LICENSE).
