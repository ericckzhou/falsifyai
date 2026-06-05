"""Unit tests for the ``build_nli_backend`` CLI seam (PR-L).

The seam decides whether ``falsifyai run`` constructs an NLI backend. It must
return None by default (oracles inert, no download) and a *lazy* real backend
when enabled (cheap to construct; the model loads only on first ``classify()``).
"""

from falsifyai.cli.run import build_nli_backend
from falsifyai.oracles.nli import NLIBackend, TransformersNLIBackend


def test_disabled_returns_none() -> None:
    assert build_nli_backend(False) is None


def test_enabled_returns_lazy_transformers_backend() -> None:
    backend = build_nli_backend(True)
    assert isinstance(backend, TransformersNLIBackend)
    assert isinstance(backend, NLIBackend)
    # Lazy: constructing the backend must NOT have loaded the model.
    assert backend._model is None
