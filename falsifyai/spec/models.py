"""Pydantic v2 models for the falsify YAML spec format.

Mirrors the schema in plan.md section 6. All models use extra='forbid' so typos
in user YAML are rejected loudly rather than silently ignored.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_STRICT = ConfigDict(extra="forbid")

Severity = Literal["critical", "high", "medium", "low"]
CasingVariant = Literal["upper", "lower", "title"]
UnicodeMethod = Literal["invisible_space", "zero_width", "homoglyph"]


class FalsifyMeta(BaseModel):
    model_config = _STRICT
    version: Literal["1.0"]
    name: str = Field(min_length=1)


class ModelConfig(BaseModel):
    model_config = _STRICT
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=512, ge=1)
    seed: int | None = None


class RunConfig(BaseModel):
    model_config = _STRICT
    replications: int = Field(default=5, ge=1)
    parallel: int = Field(default=1, ge=1)
    timeout_seconds: int = Field(default=30, ge=1)
    seed: int
    cache: bool = True


class InputSection(BaseModel):
    model_config = _STRICT
    text: str = Field(min_length=1)


class ExpectedSection(BaseModel):
    model_config = _STRICT
    contains: list[str] = Field(default_factory=list)
    not_contains: list[str] = Field(default_factory=list)
    reference: str | None = None


class VerdictConfig(BaseModel):
    model_config = _STRICT
    stable_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    fragile_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    use_worst_case_stability: bool = True


class TypoNoiseSpec(BaseModel):
    model_config = _STRICT
    type: Literal["typo_noise"]
    count: int = Field(default=5, ge=1)
    rate: float = Field(default=0.05, ge=0.0, le=1.0)


class CasingVariantSpec(BaseModel):
    model_config = _STRICT
    type: Literal["casing"]
    variants: list[CasingVariant] = Field(default_factory=lambda: ["upper", "lower", "title"])


class ParaphrasePerturbationSpec(BaseModel):
    """Semantic-preserving rewrite via LLM. Phase B per validation campaign.

    Generates `count` paraphrases of the case input by calling an LLM. Each
    paraphrase is validated against the original via embedding cosine
    similarity; only paraphrases at or above `similarity_threshold` are kept.
    If a generation attempt fails validation, the perturbation retries up to
    `max_attempts` times per missing paraphrase before giving up.

    `model` is optional — when None, paraphrase generation reuses the spec's
    primary model. Override when the system-under-test is the spec.model
    (e.g. model-migration testing) to avoid the self-paraphrase paradox.
    """

    model_config = _STRICT
    type: Literal["paraphrase"]
    count: int = Field(default=3, ge=1)
    model: ModelConfig | None = None
    similarity_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    max_attempts: int = Field(default=3, ge=1)


class UnicodePerturbationSpec(BaseModel):
    """Visually-identical, byte-different inputs (invisible/confusable chars).

    Exposes a model's sensitivity to text that a human reads as identical to
    the original. Each method in `methods` emits `count` samples; `rate` is the
    fraction of eligible positions mutated per sample.

    - `invisible_space`: ASCII space -> Unicode space variant (NBSP, U+202F, ...)
    - `zero_width`: insert zero-width characters between characters
    - `homoglyph`: Latin letter -> Cyrillic/Greek confusable

    Intent-preserving by construction (high validity), so a failure under this
    family is a reliability defect, not a response to a malformed prompt.
    """

    model_config = _STRICT
    type: Literal["unicode"]
    methods: list[UnicodeMethod] = Field(
        default_factory=lambda: ["invisible_space", "zero_width", "homoglyph"],
        min_length=1,
    )
    count: int = Field(default=3, ge=1)
    rate: float = Field(default=0.5, ge=0.0, le=1.0)


class PluginPerturbationSpec(BaseModel):
    """Reference a third-party perturbation registered via entry points.

    Decision 1A: built-ins keep their typed, validated specs; plugins use this
    generic escape hatch. `name` is the entry-point name under the
    `falsifyai.perturbations` group; `params` are passed to the plugin class
    constructor. Plugin perturbations must be constructible from `params` alone
    (pure/local, no injected resources).
    """

    model_config = _STRICT
    type: Literal["plugin"]
    name: str = Field(min_length=1)
    params: dict = Field(default_factory=dict)


PerturbationSpec = Annotated[
    TypoNoiseSpec
    | CasingVariantSpec
    | ParaphrasePerturbationSpec
    | UnicodePerturbationSpec
    | PluginPerturbationSpec,
    Field(discriminator="type"),
]


class ContainsInvariantSpec(BaseModel):
    model_config = _STRICT
    type: Literal["contains"]
    values: list[str] = Field(min_length=1)
    severity: Severity = "high"
    case_sensitive: bool = False


class SemanticEquivalenceInvariantSpec(BaseModel):
    model_config = _STRICT
    type: Literal["semantic_equivalence"]
    threshold: float = Field(ge=0.0, le=1.0)
    embedding_model: str = "local:all-MiniLM-L6-v2"
    severity: Severity = "high"


class SchemaMatchInvariantSpec(BaseModel):
    """Strict structural assertion on JSON output (subset of JSON Schema).

    `schema` is a JSON-Schema-subset dict; recognized keys are `type`,
    `required`, and `properties[*].type`. The YAML key is `schema`; it is
    exposed on the model as `json_schema` to avoid shadowing pydantic's
    `BaseModel.schema`.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    type: Literal["schema_match"]
    json_schema: dict = Field(alias="schema")
    severity: Severity = "high"


class PluginInvariantSpec(BaseModel):
    """Reference a third-party invariant registered via entry points.

    Decision 1A escape hatch (mirrors `PluginPerturbationSpec`). `name` is the
    entry-point name under the `falsifyai.invariants` group; `params` are passed
    to the plugin class constructor.
    """

    model_config = _STRICT
    type: Literal["plugin"]
    name: str = Field(min_length=1)
    params: dict = Field(default_factory=dict)


InvariantSpec = Annotated[
    ContainsInvariantSpec
    | SemanticEquivalenceInvariantSpec
    | SchemaMatchInvariantSpec
    | PluginInvariantSpec,
    Field(discriminator="type"),
]


class CaseSpec(BaseModel):
    model_config = _STRICT
    id: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    input: InputSection
    expected: ExpectedSection = Field(default_factory=ExpectedSection)
    perturbations: list[PerturbationSpec] = Field(min_length=1)
    invariants: list[InvariantSpec] = Field(min_length=1)
    verdict_config: VerdictConfig = Field(default_factory=VerdictConfig)


class Spec(BaseModel):
    model_config = _STRICT
    falsify: FalsifyMeta
    model: ModelConfig
    run: RunConfig
    cases: list[CaseSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _no_duplicate_case_ids(self) -> "Spec":
        """Reject specs with duplicate case ids.

        Materialization derives per-case seeds from ``(session_seed, case_id)``,
        so duplicate ids would produce identical perturbations for distinct
        cases -- a silent footgun. Catch it at parse time.
        """
        seen: set[str] = set()
        duplicates: set[str] = set()
        for case in self.cases:
            if case.id in seen:
                duplicates.add(case.id)
            seen.add(case.id)
        if duplicates:
            raise ValueError(f"Duplicate case ids: {sorted(duplicates)}")
        return self
