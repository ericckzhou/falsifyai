"""Reusable MockEmbedder for tests.

Implements the ``EmbeddingBackend`` Protocol with deterministic, in-memory
vector generation. Tests use this to exercise ``SemanticEquivalenceInvariant``
and (later) ``ConsistencyOracle`` without downloading a real
sentence-transformer model.

Two modes:

- ``MockEmbedder()`` (default): identical strings -> identical vectors;
  different strings -> different vectors. Vectors are pseudo-random but
  deterministic per string (sha256 -> seeded numpy RNG -> unit vector).

- ``MockEmbedder(response_map={"hello": [1, 0, 0], "world": [0, 1, 0]})``:
  explicit string -> vector mapping for fine-grained test control (e.g.
  testing orthogonal pairs, identical pairs, near-pairs).

Vectors are NOT L2-normalized by default. Tests that care about cosine
similarity should pass explicit pre-normalized vectors via response_map.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

_DEFAULT_DIM = 8


@dataclass
class MockEmbedder:
    """Programmable EmbeddingBackend substitute for tests."""

    response_map: dict[str, Sequence[float]] = field(default_factory=dict)
    dim: int = _DEFAULT_DIM
    calls: list[list[str]] = field(default_factory=list)

    def embed(self, texts: list[str]) -> np.ndarray:
        self.calls.append(list(texts))
        rows = [self._embed_one(t) for t in texts]
        return np.array(rows, dtype=np.float64)

    def _embed_one(self, text: str) -> np.ndarray:
        explicit = self.response_map.get(text)
        if explicit is not None:
            arr = np.array(list(explicit), dtype=np.float64)
            if arr.shape != (self.dim,):
                # Allow response_map vectors to set the dim implicitly.
                return arr
            return arr
        # Deterministic pseudo-random vector seeded by the text's hash.
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        seed = int.from_bytes(digest[:8], "big")
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(self.dim)
        norm = float(np.linalg.norm(vec))
        if norm == 0.0:
            return vec
        return vec / norm

    @property
    def call_count(self) -> int:
        return len(self.calls)
