"""NLI backend primitive: ``NLIBackend`` Protocol + lazy real impl + mock.

Natural-language inference (NLI) answers a question embedding cosine cannot:
given a *premise* and a *hypothesis*, does the premise **entail**, stay
**neutral** toward, or **contradict** the hypothesis? The 0.6.0 semantic oracles
(Contradiction / Hallucination / Grounding -- PR-J) reason about entailment, so
this module is the foundation they build on. It ships no oracle and changes no
verdict; it is a pure interpretation-layer primitive.

Design mirrors ``EmbeddingBackend`` (``invariants/semantic.py``):

- ``NLIBackend`` is a runtime-checkable Protocol so oracles depend on the
  interface, never the concrete model.
- ``TransformersNLIBackend`` is **lazy** -- construction is cheap; the ~500MB
  deberta model loads on the first ``classify()`` call. The dependency is an
  opt-in extra (``pip install "falsifyai[nli]"``); reaching ``classify()``
  without it raises a friendly ``ImportError``.
- ``MockNLIBackend`` is deterministic and is the ONLY backend tests use, so CI
  never downloads weights.

Every ``NLIResult`` carries ``model_version`` so oracle confidence is traceable
and model drift is detectable across runs -- the same model:version convention
the embedding layer uses (decision 2A: soft determinism, logged version).
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from transformers import PreTrainedModel, PreTrainedTokenizerBase


class NLILabel(Enum):
    """The three NLI relations a premise can hold toward a hypothesis."""

    ENTAILMENT = "entailment"
    NEUTRAL = "neutral"
    CONTRADICTION = "contradiction"


@dataclass(frozen=True)
class NLIResult:
    """One NLI judgment.

    ``label`` is the arg-max over ``scores``. ``scores`` is the full per-label
    distribution so oracles can threshold on confidence (e.g. the meta-oracle's
    high-confidence conflict gate) rather than trust a bare label.
    ``model_version`` identifies the backend that produced this so drift is
    visible in replay artifacts.
    """

    label: NLILabel
    scores: dict[NLILabel, float]
    model_version: str


@runtime_checkable
class NLIBackend(Protocol):
    """Classifies (premise, hypothesis) pairs into an :class:`NLIResult`."""

    model_version: str

    def classify(self, premise: str, hypothesis: str) -> NLIResult:
        """Return the NLI relation of ``premise`` toward ``hypothesis``."""
        ...


def _distribution_for(label: NLILabel) -> dict[NLILabel, float]:
    """A plausible softmax-shaped distribution that arg-maxes to ``label``.

    The winning label gets 0.9; the remaining 0.1 splits evenly. Kept simple and
    summing to 1.0 so oracle confidence math behaves like the real backend's.
    """
    other = (1.0 - 0.9) / 2
    return {member: (0.9 if member is label else other) for member in NLILabel}


class MockNLIBackend:
    """Deterministic NLI for tests. Never loads a model.

    Label resolution precedence (documented contract relied on by PR-J/PR-K
    oracle tests):

    1. ``rules`` -- an explicit ``{(premise, hypothesis): NLILabel}`` override,
       for tests that need different labels per pair (e.g. one output entails a
       reference while another contradicts it).
    2. ``default_label`` -- forces every pair to one label (e.g. "every output
       contradicts the reference").
    3. Substring heuristic -- ``ENTAILMENT`` when the hypothesis (stripped,
       case-folded) is a literal substring of the premise; otherwise
       ``NEUTRAL``. The heuristic never *invents* ``CONTRADICTION`` -- a mock
       must not fake real NLI contradiction detection; drive that via ``rules``
       or ``default_label``.
    """

    model_version = "mock-nli-v1"

    def __init__(
        self,
        *,
        rules: dict[tuple[str, str], NLILabel] | None = None,
        default_label: NLILabel | None = None,
    ) -> None:
        self._rules = rules or {}
        self._default_label = default_label

    def classify(self, premise: str, hypothesis: str) -> NLIResult:
        label = self._resolve(premise, hypothesis)
        return NLIResult(
            label=label,
            scores=_distribution_for(label),
            model_version=self.model_version,
        )

    def _resolve(self, premise: str, hypothesis: str) -> NLILabel:
        if (premise, hypothesis) in self._rules:
            return self._rules[(premise, hypothesis)]
        if self._default_label is not None:
            return self._default_label
        h = hypothesis.strip().casefold()
        p = premise.strip().casefold()
        if h and h in p:
            return NLILabel.ENTAILMENT
        return NLILabel.NEUTRAL


# Maps a model's raw label string to our enum. deberta NLI heads label with
# exactly these three words (any casing); we normalize and look up.
_LABEL_MAP = {label.value: label for label in NLILabel}


class TransformersNLIBackend:
    """NLI via a local HuggingFace model (default ``nli-deberta-v3-small``).

    Lazy: the tokenizer + model are constructed on the first ``classify()`` call,
    so importing this module and instantiating the backend stay cheap. Tests use
    ``MockNLIBackend`` and never trigger a load.
    """

    def __init__(self, model_name: str = "cross-encoder/nli-deberta-v3-small") -> None:
        self.model_name = model_name
        self.model_version = model_name
        self._model: PreTrainedModel | None = None
        self._tokenizer: PreTrainedTokenizerBase | None = None
        self._torch = None

    def classify(self, premise: str, hypothesis: str) -> NLIResult:
        if self._model is None:
            self._load()
        assert self._tokenizer is not None and self._model is not None
        torch = self._torch
        inputs = self._tokenizer(premise, hypothesis, return_tensors="pt", truncation=True)
        with torch.no_grad():
            logits = self._model(**inputs).logits[0]
        probs = torch.softmax(logits, dim=-1).tolist()
        id2label = self._model.config.id2label
        scores: dict[NLILabel, float] = {}
        for idx, prob in enumerate(probs):
            raw = str(id2label[idx]).strip().casefold()
            label = _LABEL_MAP.get(raw)
            if label is not None:
                scores[label] = float(prob)
        # Defensive: ensure all three labels present (some heads omit none, but
        # downstream code assumes a full distribution).
        for label in NLILabel:
            scores.setdefault(label, 0.0)
        best = max(scores, key=scores.get)
        return NLIResult(label=best, scores=scores, model_version=self.model_version)

    def _load(self) -> None:
        try:
            import torch
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )
        except ImportError as exc:
            raise ImportError(
                "The NLI oracles require the `nli` extra (transformers + torch). "
                'Install it with: pip install "falsifyai[nli]"'
            ) from exc
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
