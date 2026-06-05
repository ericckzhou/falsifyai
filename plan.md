# FalsifyAI — Implementation Plan (v2 — Deep Revision)

> Falsification-first reliability testing for AI systems.
> *"Can this behavior survive falsification?"*

---

## Preface: What v2 Adds Over v1

This revision is not a polish pass. It addresses ten substantive architectural flaws in v1:

| # | v1 Flaw | v2 Fix |
|---|---------|--------|
| 1 | Popperian framing was invoked, not formalized | Formal epistemic-state mapping (§1) |
| 2 | Missing `CONSISTENTLY_WRONG` verdict (the production-dangerous case) | 8-verdict 2D taxonomy (§2) |
| 3 | Aggregate stability hid per-perturbation-type failures | Stratified statistical analysis with worst-case stability (§12) |
| 4 | Replay was broken for non-deterministic perturbations | Spec materialization: intention vs. instance (§8) |
| 5 | No perturbation validity check → false `FRAGILE` verdicts | Validity protocol with bidirectional NLI (§9.3) |
| 6 | `INVALID_EVAL` was ad-hoc | Meta-oracle architecture derives it rigorously (§11) |
| 7 | No differential testing — the actual OSS killer feature | `falsifyai diff` as Phase 0 MVP deliverable (§14, §22.1) |
| 8 | Users could game the framework with trivial assertions | Falsifiability scoring (§15) |
| 9 | Single replay mode | Three modes: exact / behavioral / resample (§8.3) |
| 10 | SQLite was hard-coded, blocking future service-ification | `ReplayStore` protocol with pluggable backends (§19) |

v1 also under-scoped MVP at 6–8 weeks. v2 ships a **3-week Phase 0 MVP** that includes the wedge features (`falsifyai diff` + `CONSISTENTLY_WRONG` + falsifiability scoring), not just an engine. Compression around the differentiator, not expansion of the timeline. See §22.

---

## Table of Contents

1. [Philosophical Foundations](#1-philosophical-foundations)
2. [Verdict Taxonomy](#2-verdict-taxonomy)
3. [Architecture](#3-architecture)
4. [File Structure](#4-file-structure)
5. [Core Abstractions](#5-core-abstractions)
6. [YAML Spec Format](#6-yaml-spec-format)
7. [Cost Model — First-Class](#7-cost-model)
8. [Replay & Spec Materialization](#8-replay--spec-materialization)
9. [Perturbation System](#9-perturbation-system)
10. [Invariant API](#10-invariant-api)
11. [Oracle API + Meta-Oracle](#11-oracle-api--meta-oracle)
12. [Stratified Statistical Engine](#12-stratified-statistical-engine)
13. [Verdict Resolver](#13-verdict-resolver)
14. [Differential Testing](#14-differential-testing)
15. [Falsifiability Scoring](#15-falsifiability-scoring)
16. [CI Integration (Deep)](#16-ci-integration-deep)
17. [Plugin Entry-Point System](#17-plugin-entry-point-system)
18. [Storage Abstraction](#18-storage-abstraction)
19. [Competitor Comparison](#19-competitor-comparison)
20. [Research Risks](#20-research-risks)
21. [Scalability Bottlenecks](#21-scalability-bottlenecks)
22. [Roadmap (Aggressive + Extended)](#22-roadmap)
23. [Testing FalsifyAI Itself](#23-testing-falsifyai-itself)
24. [OSS Wedge](#24-oss-wedge)
25. [Weak Assumptions Challenged](#25-weak-assumptions-challenged)

---

## 1. Philosophical Foundations

### 1.1 Formal Popperian Mapping

Popper: a scientific theory is meaningful only if it forbids something. Strength = restrictiveness.

Translation to AI evaluation:

| Popperian Concept | FalsifyAI Concept |
|-------------------|-----------------|
| Theory | Test case (input → expected behavior) |
| Auxiliary hypotheses | Invariants + oracles |
| Falsification attempt | Perturbation |
| Corroboration | Survival of perturbation set |
| Ad-hoc rescue | Invariant relaxation to make tests pass |
| Duhem-Quine problem | When a test fails, the model, the invariant, or the perturbation may be at fault — the `INVALID_EVAL` verdict |

### 1.2 Three Epistemic States (Underlie the 8 Verdicts)

For a test `T = (input, assertion A, perturbation set P, model M)`:

1. **Falsified** — at least one perturbation in P produced an output violating A. The behavior is not robust.
2. **Corroborated** — no perturbation in P produced violation despite effort. The behavior is robust *with respect to P*. (Never "proven robust" — Popper.)
3. **Untestable** — cannot determine whether T discriminates. The eval itself is the problem.

The 8 verdicts in §2 are sub-classifications of these three.

### 1.3 Why "Untestable" is the Killer Concept

Most eval frameworks collapse `untestable` into either `pass` or `fail`. This is the deepest validity problem in AI evaluation:

- If your eval can't distinguish "model is wrong" from "test is wrong," your CI is theater.
- If your eval gives 100% on a trivial assertion, you have validated nothing.
- If your oracles disagree, your verdict is noise.

FalsifyAI treats `INVALID_EVAL` as the **highest-priority verdict**. If the eval is broken, no other signal can be trusted.

### 1.4 The Information-Theoretic View

A test extracts information about the model. The amount of information depends on:

```
I(T) = H(prior over behavior) − H(posterior | T outcome)
```

A trivially-passing test extracts ≈0 bits. A demanding test extracts many bits. The **falsifiability score** (§15) is an operational proxy for this.

---

## 2. Verdict Taxonomy

### 2.1 The 2D Verdict Space

Verdicts live in a 2D space defined by two orthogonal axes:

- **Stability axis**: how much behavior varies under perturbation (low / mid / high)
- **Grounding axis**: whether outputs are factually/safely correct (ungrounded / unknown / grounded)

Two cross-cutting meta-verdicts (`INVALID_EVAL`, `AMBIGUOUS`) overlay the space.

```
                          STABILITY →
                  Low              Mid              High
  G  Grounded   FRAGILE_GROUNDED  ADV_VULN_GRND   INFORMATION_PRESENT
  R  Unknown    FRAGILE           AMBIGUOUS       STABLE
  N  Ungrounded INFORMATION_NULL  FRAGILE         CONSISTENTLY_WRONG
  D                                                ⬆ MOST DANGEROUS
  
  Cross-cutting: INVALID_EVAL (eval itself broken), AMBIGUOUS (insufficient evidence)
```

### 2.2 The Eight Verdicts

```python
class Verdict(Enum):
    # High stability + confirmed grounding — the gold standard
    INFORMATION_PRESENT = "information_present"
    
    # High stability, no grounding claim — most common positive result
    STABLE = "stable"
    
    # High stability + KNOWN-WRONG outputs (consistent hallucination/false claim).
    # Most dangerous production case: model is confidently and consistently wrong.
    # Requires: ground truth (`expected`) provided AND outputs consistently contradict.
    CONSISTENTLY_WRONG = "consistently_wrong"   # ← NEW in v2
    
    # Mid-low stability + targeted failure pattern
    ADVERSARIALLY_VULNERABLE = "adversarially_vulnerable"
    
    # Mid-low stability + random failure pattern
    FRAGILE = "fragile"
    
    # Outputs consistent in structure but semantically empty (noise, refusals, hedging)
    INFORMATION_NULL = "information_null"
    
    # Insufficient evidence to discriminate between states above
    AMBIGUOUS = "ambiguous"
    
    # The evaluation itself is broken (oracles disagree, invariants malformed, etc.)
    INVALID_EVAL = "invalid_eval"
```

### 2.3 Why `CONSISTENTLY_WRONG` Is Critical

This was missing from v1. It's the most dangerous production case: the model gives the same wrong answer to every variant of the question.

- Distinct from `INFORMATION_NULL`: outputs are coherent and confident, not noise.
- Distinct from `STABLE`: outputs are *known wrong*, not just consistent.
- Requires: `expected` block provides ground truth that all outputs contradict.

Without this verdict, a confidently hallucinating model gets `STABLE` — the worst false-positive in the framework.

### 2.4 Verdict Confidence

Every verdict carries a confidence in `[0, 1]`. Confidence is derived from:
- Bootstrap CI width of stability score
- Oracle confidence
- Sample count (small N → low confidence regardless)
- Presence of `INFORMATION_NULL` symptoms in any subset

Two cases with the same verdict but different confidences have different downstream behavior in CI.

---

## 3. Architecture

### 3.1 Revised Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                       Spec Loader + Validator                         │
│                     (YAML → Pydantic Spec model)                      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────┐
│                      Spec Materializer                                │
│   (perturbation generation + validity filtering = MaterializedSpec)   │
│                                                                       │
│   spec_hash:         hash(yaml bytes)                                 │
│   materialized_hash: hash(realized perturbations)                     │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────┐
│                      Session Context                                  │
│       (rng, model config, cost ledger, cache, replay store)           │
└──────┬────────────────────────┬───────────────────────────────────┬──┘
       │                        │                                   │
┌──────▼──────┐         ┌───────▼────────┐                  ┌──────▼──────┐
│ Execution   │────────▶│  ExecutionSet  │                  │ Replay      │
│ Engine      │         │   (per case)   │                  │ Store       │
│ (LiteLLM,   │         └────────┬───────┘                  │ (pluggable) │
│  async)     │                  │                          └─────────────┘
└─────────────┘                  │
                                 ▼
        ┌────────────────┬───────┴────────┬────────────────┐
        ▼                ▼                ▼                ▼
  ┌──────────┐    ┌──────────┐    ┌─────────────┐    ┌─────────────┐
  │Invariant │    │ Oracle   │    │ Stratified  │    │Falsifiabil. │
  │ Checker  │    │Evaluator │    │ Statistical │    │  Scorer     │
  │ (per-out)│    │ (cross-  │    │  Engine     │    │ (per-case)  │
  │          │    │   set)   │    │ (per-type)  │    │             │
  └────┬─────┘    └────┬─────┘    └──────┬──────┘    └──────┬──────┘
       │               │                  │                  │
       │               ▼                  │                  │
       │        ┌──────────────┐          │                  │
       │        │ Meta-Oracle  │          │                  │
       │        │ (oracle      │          │                  │
       │        │  consistency │          │                  │
       │        │  + INVALID_  │          │                  │
       │        │   EVAL)      │          │                  │
       │        └──────┬───────┘          │                  │
       │               │                  │                  │
       └───────────────┼──────────────────┴──────────────────┘
                       │
              ┌────────▼────────┐
              │ Verdict         │
              │ Resolver        │
              │ (2D state       │
              │  machine)       │
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │ Report +        │
              │ CI Exit Code    │
              └─────────────────┘
```

### 3.2 Key Architectural Decisions

1. **Spec Materializer is its own stage.** Perturbations are generated *before* execution, validated, and frozen. The materialized perturbation set has its own hash. This makes replay sound for non-deterministic perturbations.

2. **Meta-Oracle sits between oracles and resolver.** It detects oracle inconsistency and is the sole source of `INVALID_EVAL`.

3. **Statistical engine receives invariant results stratified by perturbation type**, not flat-aggregated.

4. **All storage is behind a `ReplayStore` protocol.** SQLite is the default impl; future Postgres/S3/in-memory are drop-in.

5. **Cost ledger runs alongside execution.** Every API call is tracked. `falsifyai plan` shows estimate before execution.

---

## 4. File Structure

```
falsifyai/
├── pyproject.toml
├── falsifyai/
│   ├── __init__.py
│   ├── cli/
│   │   ├── main.py
│   │   ├── run.py           # `falsifyai run`
│   │   ├── plan.py          # `falsifyai plan` — cost estimate, no execution
│   │   ├── replay.py        # `falsifyai replay [--exact|--resample]`
│   │   ├── diff.py          # `falsifyai diff` — differential testing
│   │   ├── inspect.py       # `falsifyai inspect <session>`
│   │   ├── history.py       # `falsifyai history --case <id>`
│   │   └── report.py        # `falsify report`
│   ├── spec/
│   │   ├── models.py        # Pydantic Spec + MaterializedSpec
│   │   ├── loader.py
│   │   ├── validator.py
│   │   └── materializer.py  # Spec → MaterializedSpec
│   ├── session/
│   │   ├── context.py       # SessionContext (rng, cache, cost ledger)
│   │   ├── seeding.py       # Deterministic seed derivation tree
│   │   └── cost_ledger.py   # Tracks API calls, latency, $ estimates
│   ├── perturbation/
│   │   ├── base.py          # Perturbation Protocol + ValidityResult
│   │   ├── registry.py      # Plugin registry via entry points
│   │   ├── modes.py         # IndependentMode / Compositional / Adversarial
│   │   ├── validity.py      # Bidirectional NLI validity check
│   │   ├── pipeline.py
│   │   ├── linguistic.py
│   │   ├── structural.py
│   │   └── retrieval.py
│   ├── execution/
│   │   ├── engine.py        # AsyncExecutionEngine
│   │   ├── adapter.py       # ModelAdapter Protocol
│   │   ├── litellm_adapter.py
│   │   ├── models.py        # Execution, ExecutionSet
│   │   └── cache.py         # Content-addressed (model, input, temp) cache
│   ├── invariants/
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── contains.py
│   │   ├── schema.py
│   │   ├── semantic.py
│   │   ├── safety.py
│   │   └── determinism.py
│   ├── oracles/
│   │   ├── base.py          # Oracle Protocol
│   │   ├── meta_oracle.py   # Detects oracle inconsistency → INVALID_EVAL
│   │   ├── registry.py
│   │   ├── contradiction.py
│   │   ├── hallucination.py
│   │   ├── grounding.py
│   │   ├── consistency.py   # Detects CONSISTENTLY_WRONG
│   │   ├── jailbreak.py
│   │   └── drift.py
│   ├── statistical/
│   │   ├── stratified.py    # Per-perturbation-type analysis
│   │   ├── stability.py
│   │   ├── bootstrap.py
│   │   ├── sensitivity.py
│   │   ├── power.py
│   │   └── calibration.py   # Oracle calibration tracking
│   ├── falsifiability/
│   │   └── scorer.py        # Per-case falsifiability scoring
│   ├── verdict/
│   │   ├── types.py         # 8 verdicts + VerdictResult
│   │   ├── resolver.py      # 2D state machine
│   │   ├── reasoning.py     # VerdictReason tree
│   │   └── confidence.py    # Verdict confidence calculation
│   ├── replay/
│   │   ├── store_protocol.py # ReplayStore interface
│   │   ├── sqlite_store.py
│   │   ├── memory_store.py
│   │   ├── models.py
│   │   ├── modes.py         # exact / behavioral / resample
│   │   └── diff.py          # Session diff for differential testing
│   ├── differential/
│   │   └── runner.py        # `falsifyai diff` orchestration
│   └── reporting/
│       ├── terminal.py
│       ├── json_report.py
│       ├── ci.py            # Exit codes + GH/GitLab annotations
│       └── pr_comment.py    # Optional PR comment rendering
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   │   ├── mock_adapter.py
│   │   └── known_verdict_cases.yaml  # All 8 verdicts represented
│   └── meta/                # Tests that test the testing framework
└── examples/
    ├── basic.yaml
    ├── rag_grounding.yaml
    ├── agent_reliability.yaml
    └── model_migration_diff.yaml  # Differential testing example
```

---

## 5. Core Abstractions

### 5.1 Perturbation Protocol (with Validity)

```python
# falsifyai/perturbation/base.py
from typing import Protocol, runtime_checkable
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

class PerturbationCategory(Enum):
    LEXICAL = "lexical"          # typos, casing, whitespace
    SYNTACTIC = "syntactic"       # rephrasing, instruction reorder
    SEMANTIC = "semantic"         # paraphrase, tone shift
    CONTEXTUAL = "contextual"     # distractor injection, retrieval noise
    ADVERSARIAL = "adversarial"   # targeted attacks

@dataclass(frozen=True)
class PerturbationLineage:
    perturbation_type: str
    category: PerturbationCategory
    method: str
    seed: int
    params: dict[str, object]
    parent_input_hash: str

@dataclass
class PerturbedInput:
    text: str
    lineage: PerturbationLineage
    validity_score: float          # filled by validator
    metadata: dict[str, object] = field(default_factory=dict)

@dataclass
class ValidityResult:
    is_valid: bool
    validity_score: float          # 0-1
    reason: str
    method: str                    # "nli_bidirectional", "embedding_threshold", etc.

@dataclass
class CostEstimate:
    api_calls: int
    estimated_usd: float | None    # None if pricing unknown
    is_local: bool                 # True if entirely local

@runtime_checkable
class Perturbation(Protocol):
    name: str
    category: PerturbationCategory
    is_deterministic: bool
    is_local: bool                 # No API calls in apply() or validate()
    
    def apply(
        self,
        input_text: str,
        rng: np.random.Generator,
        count: int = 1,
    ) -> list[PerturbedInput]:
        """Generate `count` candidate perturbations. May produce invalid ones."""
        ...
    
    def validate(
        self,
        original: str,
        perturbed: str,
    ) -> ValidityResult:
        """Check if perturbed remains semantically equivalent to original.
        Invalid perturbations are discarded before execution."""
        ...
    
    def cost_estimate(self, count: int) -> CostEstimate: ...
```

> **Design note:** `validate` is a required method, not optional. v1 had no validity protocol — invalid perturbations would falsely trigger `FRAGILE` verdicts. v2 makes validity a first-class concern: perturbations that fail validation are discarded and replacements generated.

### 5.2 Invariant Protocol

```python
# falsifyai/invariants/base.py
from enum import Enum
from dataclasses import dataclass, field
from typing import Protocol

class Severity(Enum):
    CRITICAL = "critical"   # Any failure → FRAGILE immediately, regardless of stability_score
    HIGH = "high"           # Weighted into stability_score with high weight
    MEDIUM = "medium"
    LOW = "low"             # Logged but doesn't affect verdict

@dataclass
class InvariantResult:
    invariant_name: str
    passed: bool
    score: float | None
    details: str
    severity: Severity
    evidence: dict[str, object] = field(default_factory=dict)

@runtime_checkable
class Invariant(Protocol):
    name: str
    severity: Severity
    
    def check(
        self,
        original_output: str,
        perturbed_output: str,
        context: dict[str, object],
    ) -> InvariantResult:
        ...
    
    def falsifiability_contribution(self) -> float:
        """How restrictive is this invariant? Used in falsifiability scoring.
        contains: ["Paris"] → ~0.95
        length > 0 → ~0.05
        semantic_equivalence threshold=0.9 → ~0.7"""
        ...
```

### 5.3 Oracle Protocol

```python
# falsifyai/oracles/base.py
from dataclasses import dataclass, field
from typing import Protocol

@dataclass
class OracleVerdict:
    oracle_name: str
    triggered: bool
    verdict_contribution: "Verdict | None"
    confidence: float
    reasoning: str
    evidence: dict[str, object] = field(default_factory=dict)

@runtime_checkable
class Oracle(Protocol):
    name: str
    
    def evaluate(
        self,
        execution_set: "ExecutionSet",
        context: dict[str, object],
        # NEW in v2: oracles can see other oracles' verdicts (for meta-oracles)
        peer_verdicts: list[OracleVerdict] | None = None,
    ) -> OracleVerdict:
        ...
    
    def cost_estimate(self, execution_set_size: int) -> CostEstimate: ...
    
    def calibration_target(self) -> "CalibrationTarget | None":
        """Optional: provide known-good test cases for periodic calibration."""
        ...
```

### 5.4 Verdict Result with Reasoning Tree

```python
# falsifyai/verdict/types.py
from dataclasses import dataclass, field

@dataclass
class VerdictReason:
    """Tree node — verdict derivations are hierarchical, not linear."""
    claim: str
    weight: float                  # how much this contributed to verdict
    sub_reasons: list["VerdictReason"] = field(default_factory=list)
    evidence: dict[str, object] = field(default_factory=dict)

@dataclass
class VerdictResult:
    verdict: Verdict
    confidence: float              # 0-1
    
    # Stratified statistics
    stability_aggregate: float
    stability_per_type: dict[str, float]    # perturbation_category → stability
    stability_worst_case: float             # min across types (this drives verdict)
    stability_ci_aggregate: tuple[float, float]
    stability_ci_per_type: dict[str, tuple[float, float]]
    
    # Falsifiability
    falsifiability_score: float    # how restrictive this test was
    
    # Oracle aggregate
    oracle_verdicts: list[OracleVerdict]
    meta_oracle_verdict: OracleVerdict      # for INVALID_EVAL detection
    
    # Reasoning
    reasoning_tree: VerdictReason
    
    # Provenance
    materialized_spec_hash: str
    overrideable: bool             # False if oracle/meta-oracle forced verdict
```

---

## 6. YAML Spec Format

```yaml
# eval.yaml — FalsifyAI Spec v1.0
falsify:
  version: "1.0"
  name: "RAG grounding robustness"

# Model — provider-agnostic via LiteLLM
model:
  provider: openai
  model: gpt-4o-mini
  temperature: 0.7
  max_tokens: 512
  seed: 42                    # best-effort; flagged non-deterministic if ignored

# Run config
run:
  replications: 5
  parallel: 4
  timeout_seconds: 30
  seed: 12345                 # session seed → deterministic per-case derivation
  cache: true
  
  # NEW v2: explicit perturbation mode
  perturbation_mode: independent  # "independent" | "compositional" | "adversarial"

# Validity gates (NEW v2)
validity:
  enabled: true
  min_validity_score: 0.85       # discard perturbations below this
  max_retry: 3                   # if too many invalid, give up and warn
  method: nli_bidirectional      # or "embedding", "reference_match"
  
# Test cases
cases:
  - id: capital_france
    tags: [geography, factual]
    
    input:
      text: "What is the capital of France?"
    
    expected:                    # ground truth for CONSISTENTLY_WRONG detection
      contains: ["Paris"]
      not_contains: ["Lyon", "Marseille"]
      reference: "Paris"         # used by hallucination oracle + meta-oracle
    
    perturbations:
      - type: typo_noise
        count: 5
        params: { rate: 0.05 }
        
      - type: paraphrase
        count: 5
        params: { method: template }   # "template" (local) or "llm" (opt-in)
        
      - type: casing
        variants: [upper, lower, title]
        
      - type: instruction_prefix
        prefixes: ["Please:", "Briefly,", "Be concise."]
    
    invariants:
      - type: contains
        values: ["Paris"]
        severity: critical
        
      - type: semantic_equivalence
        threshold: 0.85          # NO default in framework — must be explicit
        model: local:all-MiniLM-L6-v2
        severity: high
    
    oracles:
      - type: contradiction
      - type: hallucination
        reference: "Paris is the capital of France."
      - type: consistency        # NEW v2: detects CONSISTENTLY_WRONG
        expected: "Paris"
    
    verdict_config:
      stable_threshold: 0.95
      fragile_threshold: 0.5
      use_worst_case_stability: true   # v2 default: stratified

# Differential testing config (NEW v2)
differential:
  enabled: false                 # `falsifyai diff` overrides
  baseline_model:
    provider: openai
    model: gpt-4o-2024-05-13
  candidate_model:
    provider: openai
    model: gpt-4o-2024-08-06
  regression_threshold: 0.1      # stability_score drop > this = regression

# Global config
global_invariants:
  - type: schema_match
  - type: safety_boundary
    forbidden_patterns: [hate_speech, pii_exposure]
    severity: critical

# Output
output:
  format: [json, terminal]
  replay: true
  replay_store: sqlite           # "sqlite" | "postgres" | "memory" | custom
  replay_path: .falsifyai/replays/
  ci_mode: true
  fail_on:
    - fragile
    - adversarially_vulnerable
    - invalid_eval
    - consistently_wrong         # NEW v2
  warn_on:
    - ambiguous
    - low_falsifiability         # NEW v2: warn if test is toothless
```

---

## 7. Cost Model

Cost is first-class. The CLI offers `falsifyai plan` (Terraform-style):

```bash
$ falsifyai plan eval.yaml

  FalsifyAI Plan: eval.yaml
  
  Cases:                3
  Total executions:     90  (3 cases × 6 perturbations × 5 replications)
  
  Cost estimate:
    Model API calls:    90    → $0.12  (gpt-4o-mini)
    Perturbation gen:   0     → $0.00  (all local)
    Oracle calls:       3     → $0.01  (NLI local + 1 hallucination ref check)
    Embedding calls:    0     → $0.00  (local: all-MiniLM-L6-v2)
    
  Total estimated:      $0.13
  Total time estimate:  ~45 seconds (parallel=4)
  
  Replay storage:       ~150 KB
  
  Run with:  falsifyai run eval.yaml
```

Cost ledger tracked per-session and persisted in replay artifact. Enables:
- Budget caps: `--max-cost 1.00` aborts session when exceeded
- Cost regression detection in differential runs
- Honest cost-per-verdict reporting

---

## 8. Replay & Spec Materialization

### 8.1 The Materialization Problem (v1 missed this)

v1 stored the YAML spec and assumed perturbations could be regenerated from seed. This is **wrong for non-deterministic perturbations** (LLM paraphrasers, even some local methods with library-version drift).

v2 separates **intention** from **instance**:

```python
@dataclass
class Spec:
    """Intention. The YAML loaded into Pydantic."""
    spec_hash: str               # sha256(yaml bytes)
    ...

@dataclass
class MaterializedSpec:
    """Instance. After perturbation generation and validity filtering."""
    spec_hash: str
    materialized_hash: str       # sha256 of realized perturbations
    cases: list[MaterializedCase]

@dataclass
class MaterializedCase:
    case_id: str
    case_seed: int
    original_input: str
    realized_perturbations: list[PerturbedInput]  # frozen at materialization time
    invariants: list[Invariant]
    oracles: list[Oracle]
```

Replay loads `MaterializedSpec`. The current YAML is only consulted to detect drift.

### 8.2 SQLite Schema (Pluggable via §18)

```sql
CREATE TABLE sessions (
    id                  TEXT PRIMARY KEY,
    spec_hash           TEXT NOT NULL,
    materialized_hash   TEXT NOT NULL,
    spec_yaml           TEXT NOT NULL,        -- original YAML
    materialized_spec   JSON NOT NULL,        -- materialized perturbations
    timestamp           TEXT NOT NULL,
    global_seed         INTEGER NOT NULL,
    falsify_version     TEXT NOT NULL,
    model_config        JSON NOT NULL,
    session_verdict     TEXT,
    total_cost_usd      REAL,
    artifact            JSON NOT NULL
);

CREATE TABLE case_verdicts (
    session_id          TEXT REFERENCES sessions(id),
    case_id             TEXT NOT NULL,
    verdict             TEXT NOT NULL,
    confidence          REAL NOT NULL,
    stability_aggregate REAL,
    stability_worst     REAL,                 -- ← used for verdict (v2)
    falsifiability     REAL,                  -- ← NEW v2
    timestamp           TEXT NOT NULL,
    PRIMARY KEY (session_id, case_id)
);

CREATE INDEX idx_case_verdicts_verdict        ON case_verdicts(verdict);
CREATE INDEX idx_case_verdicts_case           ON case_verdicts(case_id);
CREATE INDEX idx_sessions_spec_hash           ON sessions(spec_hash);
CREATE INDEX idx_sessions_materialized_hash   ON sessions(materialized_hash);

-- Trend detection (history queries)
CREATE INDEX idx_case_verdicts_timestamp      ON case_verdicts(timestamp);
```

### 8.3 Three Replay Modes

```bash
falsifyai replay <id>                # behavioral (default)
falsifyai replay <id> --exact        # bit-exact; fails on any non-determinism
falsifyai replay <id> --resample     # regenerate perturbations from spec
falsifyai replay <id> --diff         # vs. current run of same spec
```

| Mode | Same outputs? | Same materialized spec? | Same verdict expected? |
|------|---------------|------------------------|------------------------|
| **exact** | Required | Required | Required |
| **behavioral** | No | Required | Yes (else flag drift) |
| **resample** | No | No | Yes (else spec is unstable) |

`exact` is useful for forensic debugging. `behavioral` for regression detection. `resample` for testing spec robustness itself.

---

## 9. Perturbation System

### 9.1 Three Perturbation Modes

v1 implicitly assumed independent perturbations. v2 makes the mode explicit:

**Independent Mode** (default):
- Each perturbation type generates N samples independently from original
- Total = sum(N_i) executions
- Best for: sensitivity analysis ("which perturbation type breaks things?")

**Compositional Mode**:
- Perturbations stacked: layer1(layer2(original))
- Total = N executions, each with full stack
- Best for: realistic robustness ("does it survive real-world noise?")
- Risk: confounding — failure cause is ambiguous

**Adversarial Mode**:
- Optimization loop: search perturbation space for breaking input
- Budget: K API calls
- Returns: best adversarial input found + invariants it broke
- Best for: vulnerability detection ("can ANY perturbation break this?")

```yaml
# Independent
perturbation_mode: independent
perturbations:
  - type: typo_noise
    count: 5

# Compositional
perturbation_mode: compositional
perturbations:
  composition:
    layers:
      - { type: typo_noise, rate: 0.05 }
      - { type: paraphrase, count: 1 }
    count: 10

# Adversarial
perturbation_mode: adversarial
perturbations:
  target_invariant: contains_paris
  attacker_budget: 50
  attack_methods: [typo_noise, paraphrase, instruction_prefix]
```

### 9.2 MVP Local Perturbations (Zero API Cost)

```python
class TypoNoise:
    """Character-level: swap, drop, insert, transpose.
    Validity check: edit distance ≤ ceil(input_len × 2 × rate)"""
    name = "typo_noise"
    category = PerturbationCategory.LEXICAL
    is_deterministic = True
    is_local = True

class CasingVariant:
    """Whole-text casing transformations."""
    name = "casing"
    category = PerturbationCategory.LEXICAL
    is_deterministic = True
    is_local = True

class WhitespaceNoise:
    """Extra spaces, tabs, newlines."""
    name = "whitespace"
    category = PerturbationCategory.LEXICAL
    is_deterministic = True
    is_local = True

class InstructionPrefix:
    """Curated instruction-style prefix templates."""
    name = "instruction_prefix"
    category = PerturbationCategory.SYNTACTIC
    is_deterministic = True
    is_local = True

class TemplateParaphrase:
    """Rule-based syntactic transformation from curated templates."""
    name = "paraphrase_template"
    category = PerturbationCategory.SYNTACTIC
    is_deterministic = True
    is_local = True
```

### 9.3 Validity Check (NEW v2)

```python
# falsifyai/perturbation/validity.py

class BidirectionalNLIValidator:
    """The default validity check.
    
    A perturbation is valid iff:
      original entails perturbed  AND  perturbed entails original
      
    Uses local NLI model (cross-encoder/nli-deberta-v3-small). No API cost.
    """
    
    def validate(self, original: str, perturbed: str) -> ValidityResult:
        forward = self._nli(original, perturbed)
        reverse = self._nli(perturbed, original)
        
        forward_entail = forward.label == "entailment" and forward.score > 0.7
        reverse_entail = reverse.label == "entailment" and reverse.score > 0.7
        
        is_valid = forward_entail and reverse_entail
        validity_score = min(forward.score, reverse.score) if is_valid else 0.0
        
        return ValidityResult(
            is_valid=is_valid,
            validity_score=validity_score,
            reason=f"forward={forward.label}/{forward.score:.2f}, reverse={reverse.label}/{reverse.score:.2f}",
            method="nli_bidirectional",
        )
```

**Invalid perturbation budget**: If >20% of generated perturbations are invalid, emit warning. If >50%, abort case with `INVALID_EVAL` reason "perturbation method is unreliable for this input."

### 9.4 LLM-Based Perturbations (Phase 2, Opt-In Only)

```python
class LLMParaphrase:
    name = "paraphrase_llm"
    category = PerturbationCategory.SEMANTIC
    is_deterministic = False    # CRITICAL: marked non-deterministic
    is_local = False             # API cost incurred
    
    # WARNING in docs: model-in-the-loop bias. Same model family
    # paraphrasing its own prompts creates systematic blind spots.
    # MITIGATION: use a different provider for paraphrase vs. evaluation.
```

---

## 10. Invariant API

### 10.1 Built-In Invariants

```python
# Contains (highest falsifiability for factual questions)
class ContainsInvariant:
    def __init__(self, values: list[str], severity: Severity, case_sensitive: bool = False): ...
    def falsifiability_contribution(self) -> float:
        # Higher for longer/more specific required substrings
        return min(1.0, sum(len(v) for v in self.values) / 50)

# Semantic equivalence (no default threshold — must be explicit per domain)
class SemanticEquivalenceInvariant:
    def __init__(
        self,
        threshold: float,            # required, no default
        embedding_model: str = "local:all-MiniLM-L6-v2",
        severity: Severity = Severity.HIGH,
    ): ...
    def falsifiability_contribution(self) -> float:
        # 0.5 threshold = weak, 0.95 = strong
        return max(0.0, (self.threshold - 0.5) * 2)

# Schema match (strict structural assertion)
class SchemaMatchInvariant:
    def __init__(self, schema: dict, severity: Severity): ...
    def falsifiability_contribution(self) -> float:
        # Roughly: number of required fields × type strictness
        return min(1.0, len(self.schema.get("required", [])) * 0.2)
```

### 10.2 Embedding Backend

**Default: local `sentence-transformers`** (all-MiniLM-L6-v2). Reproducible, no API cost, no embedding drift.

API embedding models supported but flagged: every embedding call logged with `model:version` so drift is detectable.

---

## 11. Oracle API + Meta-Oracle

### 11.1 Primary Oracles

```python
# Contradiction: cross-execution NLI
class ContradictionOracle:
    """Pairwise NLI check. Uses local nli-deberta-v3-small."""
    name = "contradiction"
    
    def evaluate(self, execution_set, context, peer_verdicts=None) -> OracleVerdict:
        ...

# Consistency: detects CONSISTENTLY_WRONG (NEW v2)
class ConsistencyOracle:
    """Detects high agreement across perturbations on a known-wrong answer.
    
    Requires `expected.reference` in context. Triggers CONSISTENTLY_WRONG when:
    - >90% of outputs are semantically equivalent (low variance)
    - outputs contradict the reference (NLI: contradiction)
    """
    name = "consistency"
    
    def evaluate(self, execution_set, context, peer_verdicts=None) -> OracleVerdict:
        if "reference" not in context.get("expected", {}):
            return OracleVerdict(
                oracle_name=self.name,
                triggered=False,
                verdict_contribution=None,
                confidence=0.0,
                reasoning="No reference provided; cannot evaluate consistency oracle",
            )
        # ... check intra-set agreement AND contradiction with reference

# Hallucination: NLI entailment against reference (prefers local over LLM-judge)
class HallucinationOracle:
    name = "hallucination"
    # ...

# Grounding: for RAG cases — output must entail from context
class GroundingOracle:
    name = "grounding"
    # ...
```

### 11.2 Meta-Oracle (NEW v2)

```python
# falsifyai/oracles/meta_oracle.py

class MetaOracle:
    """Sole source of INVALID_EVAL verdicts.
    
    Detects four classes of evaluation failure:
    
    1. ORACLE CONFLICT: oracles return contradictory verdicts with high confidence.
       Example: contradiction_oracle says AMBIGUOUS (outputs contradict each other),
       consistency_oracle says CONSISTENTLY_WRONG (outputs agree). Impossible to
       both be true → INVALID_EVAL.
    
    2. INVARIANT DEGENERATION: an invariant fails on >95% of cases including original.
       The invariant is malformed (too strict, wrong type, etc.).
    
    3. PERTURBATION DEGENERATION: >50% of generated perturbations failed validity.
       The perturbation method is unreliable for this input domain.
    
    4. CALIBRATION FAILURE: oracle calibration tests fail.
       (Phase 2; requires calibration ground-truth fixtures.)
    """
    
    def evaluate(
        self,
        execution_set: ExecutionSet,
        primary_verdicts: list[OracleVerdict],
        invariant_results: list[list[InvariantResult]],
        materialization_stats: MaterializationStats,
    ) -> OracleVerdict:
        # Returns OracleVerdict with verdict_contribution=Verdict.INVALID_EVAL
        # if any of the four classes is detected.
        ...
```

The meta-oracle is what makes `INVALID_EVAL` rigorous rather than ad-hoc.

---

## 12. Stratified Statistical Engine

### 12.1 Why Stratification Matters

v1 computed:
```
stability_score = pass_count / total_count
```

This hides per-type failures. Example:
- 100% pass on typo_noise (5/5)
- 0% pass on paraphrase (0/5)
- Aggregate: 50%

The aggregate reports "fragile but recoverable." The truth is "completely broken on paraphrase." The verdict should be `FRAGILE`, not "AMBIGUOUS."

### 12.2 Stratified Analysis

```python
# falsifyai/statistical/stratified.py

@dataclass
class StratifiedStability:
    aggregate: float                              # weighted by sample size
    aggregate_ci: tuple[float, float]
    per_category: dict[PerturbationCategory, float]
    per_category_ci: dict[PerturbationCategory, tuple[float, float]]
    per_type: dict[str, float]                    # finer than category
    per_type_ci: dict[str, tuple[float, float]]
    
    worst_case: float                             # min across types
    worst_case_type: str                          # which type was worst
    worst_case_ci: tuple[float, float]
    
    warning: str | None                           # power warnings, drift, etc.

class StratifiedAnalyzer:
    def __init__(self, bootstrap_iterations: int = 1000, ci_level: float = 0.95): ...
    
    def analyze(
        self,
        execution_set: ExecutionSet,
        invariant_results: list[list[InvariantResult]],
    ) -> StratifiedStability:
        # Bootstrap WITHIN each perturbation type, then aggregate
        # Worst-case is computed from the lower CI bound of each type
        ...
```

### 12.3 Verdict Uses Worst-Case Stability

The verdict resolver uses `worst_case` stability, not aggregate. This is a substantive v2 design change.

Rationale: aggregating across perturbation types makes safety-critical failures invisible. A 99% stable model that catastrophically fails on a 1% perturbation type is **not stable** — it has a known attack vector.

The aggregate is still reported in the artifact but the verdict is derived from worst-case.

---

## 13. Verdict Resolver

### 13.1 2D State Machine

```python
# falsifyai/verdict/resolver.py

class VerdictResolver:
    """Resolves the 8 verdicts from stratified stats + oracles + meta-oracle.
    
    Resolution order (HIGHEST PRIORITY FIRST):
    
    1. meta_oracle.triggered=True → INVALID_EVAL
       Stop. Nothing else matters.
    
    2. consistency_oracle says CONSISTENTLY_WRONG with confidence > 0.8
       AND `expected.reference` was provided → CONSISTENTLY_WRONG
    
    3. adversarial mode found a working attack → ADVERSARIALLY_VULNERABLE
    
    4. CRITICAL invariant failed on ANY perturbation → FRAGILE
       (severity overrides stability)
    
    5. worst_case_stability CI upper bound < fragile_threshold (0.5)
       → FRAGILE
       (worst type is broken even optimistically)
    
    6. All outputs semantically near-identical AND no oracle confirms signal
       AND no reference provided → INFORMATION_NULL
    
    7. worst_case_stability CI lower bound > stable_threshold (0.95)
       - If hallucination_oracle and grounding_oracle confirm → INFORMATION_PRESENT
       - Otherwise → STABLE
    
    8. contradiction_oracle triggered OR
       worst_case_stability CI is too wide (n insufficient) → AMBIGUOUS
    
    9. Otherwise → FRAGILE
    
    Each transition is logged into reasoning_tree."""
    
    def resolve(
        self,
        execution_set: ExecutionSet,
        invariant_results: list[list[InvariantResult]],
        oracle_verdicts: list[OracleVerdict],
        meta_oracle_verdict: OracleVerdict,
        statistical: StratifiedStability,
        falsifiability: float,
    ) -> VerdictResult:
        ...
```

### 13.2 Confidence Derivation

Verdict confidence ∈ [0, 1] derived from:
- Stability CI width (narrower = more confident)
- Oracle confidence (max across triggered oracles)
- Sample size penalty (`max(0, 1 - 5/n)`)
- Validity rate (low validity → low confidence)

Two `FRAGILE` verdicts with confidence 0.95 vs. 0.4 have different CI behavior.

---

## 14. Differential Testing

### 14.1 Why This Is the Killer Feature

Every AI team's most common question:
> "OpenAI just released gpt-4o-2024-08-06. Will my prompts still work?"

No existing OSS tool answers this systematically. Promptfoo can run both, but doesn't diff verdicts. LangSmith traces don't compare. OpenAI Evals are benchmark-aggregated.

`falsifyai diff` answers this in one command:

```bash
falsifyai diff eval.yaml \
  --baseline openai:gpt-4o-2024-05-13 \
  --candidate openai:gpt-4o-2024-08-06
```

### 14.2 Output

```
DIFFERENTIAL TEST: gpt-4o-2024-05-13 → gpt-4o-2024-08-06
Spec: eval.yaml
Replications: 5
Total cost: $0.42

╔═══════════════════════════╦═══════════════════════════════╦══════════════╗
║ Case                       ║ Verdict Change                ║ Δ Stability  ║
╠═══════════════════════════╬═══════════════════════════════╬══════════════╣
║ capital_france             ║ STABLE → STABLE               ║   +0.02      ║
║ rag_grounding              ║ STABLE → FRAGILE              ║   −0.34  ⚠   ║
║ customer_service           ║ FRAGILE → STABLE              ║   +0.41  ✓   ║
║ pii_detection              ║ STABLE → CONSISTENTLY_WRONG   ║   N/A    🚨   ║
║ math_word_problem          ║ AMBIGUOUS → STABLE            ║   +0.18  ✓   ║
╚═══════════════════════════╩═══════════════════════════════╩══════════════╝

Summary:
  Unchanged:         1
  Improvements:      2
  Regressions:       1
  CRITICAL changes:  1
  
Verdict: REGRESSION DETECTED
Exit: 2 (FAILURE)
```

### 14.3 Differential Mode Considerations

- **Materialized spec is shared** between baseline and candidate runs. Same perturbations, different models. Removes perturbation noise as a confound.
- **Per-case verdict diff** is the primary signal, not aggregate.
- **Stability delta** highlights regression magnitude.
- **Stratified stability diff** available in verbose mode: see *which perturbation types* broke under the new model.

This is a Phase 0 MVP deliverable, not deferred. The launch story requires it.

---

## 15. Falsifiability Scoring

### 15.1 The Problem

A user can game any eval framework by writing toothless assertions:

```yaml
invariants:
  - type: length_greater_than
    value: 0
```

This passes for any non-empty output. The test is meaningless. v1 had no defense.

### 15.2 The Solution

Each invariant reports `falsifiability_contribution() -> float`. The per-case score is the maximum (most restrictive invariant). Suite-level falsifiability is the mean.

```python
# falsifyai/falsifiability/scorer.py

class FalsifiabilityScorer:
    def score_case(self, case: MaterializedCase) -> float:
        if not case.invariants:
            return 0.0
        return max(inv.falsifiability_contribution() for inv in case.invariants)
    
    def score_suite(self, cases: list[MaterializedCase]) -> SuiteFalsifiability:
        per_case = {c.case_id: self.score_case(c) for c in cases}
        suite_mean = sum(per_case.values()) / len(per_case)
        
        warnings = []
        if suite_mean < 0.3:
            warnings.append(
                "LOW SUITE FALSIFIABILITY: Average test restrictiveness is "
                f"{suite_mean:.2f}. Your test suite may not be discriminating. "
                "Consider adding more specific assertions."
            )
        
        low_cases = [cid for cid, s in per_case.items() if s < 0.2]
        if low_cases:
            warnings.append(f"Trivially-passing cases: {low_cases}")
        
        return SuiteFalsifiability(per_case=per_case, suite_mean=suite_mean, warnings=warnings)
```

Surfaced in CLI:
```
  Suite Falsifiability:  0.62  (good)
  Per-case range:        0.10 — 0.93
  ⚠ Trivially-passing cases: ['length_check_only']
```

Suite falsifiability is logged in every replay artifact and can be tracked over time. **Low falsifiability + 100% pass rate ≠ stability.** It means your tests aren't testing.

---

## 16. CI Integration (Deep)

### 16.1 Exit Codes

```python
class ExitCode(IntEnum):
    SUCCESS              = 0   # all STABLE or INFORMATION_PRESENT
    DEGRADED             = 1   # any FRAGILE / AMBIGUOUS
    FAILURE              = 2   # any ADVERSARIALLY_VULNERABLE / INVALID_EVAL / CONSISTENTLY_WRONG
    ERROR                = 3   # infrastructure (network, auth, config)
    INSUFFICIENT         = 4   # insufficient samples for any meaningful verdict
    REGRESSION           = 5   # differential mode: regression detected
    LOW_FALSIFIABILITY   = 6   # suite falsifiability below threshold (warning by default)
```

### 16.2 PR Comment Rendering (Phase 2)

```bash
falsifyai run eval.yaml --pr-comment ./comment.md
```

Produces Markdown for GitHub/GitLab PR comments. Includes:
- Verdict table (STABLE/FRAGILE/etc. with emoji)
- Stratified stability summary
- Diff vs. main branch (if available in replay store)
- Cost and timing

### 16.3 Trend Detection

`falsifyai history --case <id>` queries the replay store:

```
History for case `rag_grounding` (last 20 sessions):

  Session       Date         Verdict                Stability
  abc1234       2026-05-01   STABLE                 0.96
  abc2345       2026-05-08   STABLE                 0.94
  abc3456       2026-05-15   AMBIGUOUS              0.78  ⚠
  abc4567       2026-05-20   FRAGILE                0.52  🚨

Regression detected at abc3456. Bisect: `falsify bisect rag_grounding`
```

### 16.4 Quarantine

Mark known-flaky cases so they don't block CI:

```yaml
cases:
  - id: occasionally_flaky_case
    quarantine:
      until: "2026-06-01"
      reason: "Known flaky during model deprecation transition"
      tracking_issue: "github.com/repo/issues/42"
```

Quarantined cases still run and report, but don't trigger CI failure.

---

## 17. Plugin Entry-Point System

Standard Python entry points via `pyproject.toml`:

```toml
# my_falsifyai_plugin/pyproject.toml
[project.entry-points."falsifyai.perturbations"]
custom_legal_paraphrase = "my_pkg.perturbations:LegalParaphrase"

[project.entry-points."falsifyai.invariants"]
hipaa_safety = "my_pkg.invariants:HIPAASafetyInvariant"

[project.entry-points."falsifyai.oracles"]
medical_grounding = "my_pkg.oracles:MedicalGroundingOracle"

[project.entry-points."falsifyai.adapters"]
my_internal_model = "my_pkg.adapters:InternalLLMAdapter"

[project.entry-points."falsifyai.reporters"]
slack = "my_pkg.reporters:SlackReporter"
datadog = "my_pkg.reporters:DatadogReporter"

[project.entry-points."falsifyai.stores"]
postgres = "my_pkg.stores:PostgresReplayStore"
```

Discovery:
```python
# falsifyai/perturbation/registry.py
from importlib.metadata import entry_points

def discover_perturbations() -> dict[str, type[Perturbation]]:
    eps = entry_points(group="falsifyai.perturbations")
    return {ep.name: ep.load() for ep in eps}
```

Same pattern as pytest, Black, setuptools. Battle-tested.

---

## 18. Storage Abstraction

### 18.1 Protocol

```python
# falsifyai/replay/store_protocol.py

class ReplayStore(Protocol):
    def save_session(self, artifact: ReplayArtifact) -> None: ...
    def load_session(self, session_id: str) -> ReplayArtifact: ...
    def query_sessions(
        self,
        spec_hash: str | None = None,
        case_id: str | None = None,
        verdict: Verdict | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> Iterator[ReplayArtifact]: ...
    def case_history(self, case_id: str, limit: int = 50) -> list[CaseVerdictRow]: ...
    def diff_sessions(self, baseline_id: str, candidate_id: str) -> SessionDiff: ...
```

### 18.2 Implementations

- **`SQLiteStore`** — default; file-based; perfect for local dev and small CI
- **`PostgresStore`** — Phase 2; for shared team replay history
- **`InMemoryStore`** — for testing FalsifyAI itself; instant, no I/O
- **`S3Store`** — Phase 3; durable cloud storage for long-running teams

All four conform to the same protocol. Spec config selects:

```yaml
output:
  replay_store: sqlite    # or "postgres", "s3", or plugin name
  replay_path: .falsifyai/replays/
```

Critical: **no SQLite-specific assumptions in core code**. All store access goes through the protocol.

---

## 19. Competitor Comparison

| Dimension | **FalsifyAI v2** | Promptfoo | DeepEval | LangSmith | OpenAI Evals | Hypothesis |
|-----------|----------------|-----------|----------|-----------|--------------|------------|
| Philosophy | Falsificationist | Accuracy | LLM-judge metrics | Observability | Benchmarks | Property-based |
| Perturbation testing | Core primitive (3 modes) | Basic variants | Limited | None | None | Generation+shrinking |
| Epistemic verdicts | 8 types | Pass/fail | Score | None | % | Pass/fail |
| `INVALID_EVAL` | Meta-oracle derived | No | No | No | No | No |
| `CONSISTENTLY_WRONG` | Yes (v2) | No | No | No | No | N/A |
| Statistical rigor | Stratified bootstrap | Point estimates | Scores | None | Aggregate | Statistical|
| Per-type stability | Yes (v2) | No | No | No | No | N/A |
| Differential testing | Native `falsifyai diff` (v2) | Manual | No | No | No | N/A |
| Falsifiability scoring | Yes (v2) | No | No | No | No | Implicit |
| Spec materialization | Yes (v2) | No | No | No | No | Yes (replay) |
| Three replay modes | Yes (v2) | Limited | No | Traces | Basic | DB-based |
| Provider agnostic | Yes (LiteLLM) | Yes | Yes | Partial | OpenAI only | N/A |
| Local oracles | Yes (NLI default) | No | No | No | No | N/A |
| Plugin entry points | Yes | Limited | No | No | No | Yes |
| OSS | Yes | Yes | Yes | No (hosted) | Yes | Yes |

**Strongest closest competitor**: Promptfoo. v2's `falsifyai diff` is the most pressing gap they don't fill.
**Philosophical cousin**: Hypothesis. We adopt their property-based mindset but apply it semantically rather than type-directed.
**OpenAI Evals**: useful as a benchmark library; not a testing framework.

---

## 20. Research Risks

| Risk | Severity | v2 Mitigation |
|------|----------|----------------|
| **Perturbation invalidity** → false FRAGILE verdicts | HIGH | Bidirectional NLI validity check is required (§9.3). Invalid perturbations discarded. >50% invalid → INVALID_EVAL. |
| **Oracle circularity** (LLM judging same family) | HIGH | Default to local NLI oracles. LLM-judge is explicit opt-in. Recommend different provider for oracle vs. evaluation. |
| **Seed non-reproducibility** at provider | HIGH | Track `is_deterministic=False`. Replications average variance. Replay modes distinguish exact vs. behavioral. |
| **Oracle conflict** (different oracles disagree) | HIGH | Meta-oracle (§11.2) detects conflict → INVALID_EVAL. No silent collapse. |
| **`semantic_equivalence` threshold gaming** | MEDIUM | No default threshold. Falsifiability score (§15) penalizes weak thresholds. |
| **Sample size insufficiency** | MEDIUM | Stratified bootstrap CI surfaces uncertainty. INSUFFICIENT exit code. Power estimator warns. |
| **Perturbation space coverage incompleteness** | MEDIUM | Documented honestly: never claim "robust," only "survived this perturbation set." |
| **Embedding model drift** | LOW | Embedding model:version logged. Default to local sentence-transformers. |
| **Test suite gaming** (toothless assertions) | LOW | Falsifiability scoring (§15) surfaces this. |
| **Differential test confounding** | MEDIUM | Shared materialized spec across baseline/candidate. No perturbation regeneration between runs. |

---

## 21. Scalability Bottlenecks

| Bottleneck | Trigger | Mitigation |
|-----------|---------|------------|
| **API rate limits** | Large suites × replications | Async execution, configurable concurrency, exponential backoff with jitter |
| **API cost** | Production CI | Content-addressed cache: `hash(model, input, temp=0)` → cached output. Pre-generated perturbation sets. `falsifyai plan` shows cost upfront. |
| **Oracle cost** | Many cases × many oracles | Local NLI is default. Lazy oracle evaluation (skip if invariants all pass for STABLE). |
| **Storage growth** | Long-running CI | Configurable retention (`replay_retention_days`). Deduplication by materialized_hash. |
| **Perturbation generation** | LLM paraphraser | Materialize once per spec_hash; cache materialized spec separately. |
| **Embedding compute** | Large semantic_equivalence checks | Local sentence-transformers + batch encoding. |
| **NLI compute** | Many oracle invocations | NLI batching across pairs. Quantized models for CI. |
| **Replay store query** | History/diff queries | Indexed columns on (spec_hash, case_id, verdict, timestamp). Postgres impl for team scale. |

---

## 22. Roadmap

> **Reconciliation note (post-0.4, 2026-06).** Actual delivery diverged from the
> original phase plan below. After 0.1.0 the work went deep on the
> artifact/provenance track (verify → export --bundle → embedded invocation →
> evidence-gap docs, shipped through 0.4.0) rather than Phase 1 capability
> breadth. The capability-breadth gap is now being closed as a sequence of
> milestones on `dev`:
>
> - **0.5.0** — `unicode` perturbation (closes CS-01's detect-but-can't-generate
>   loop) + `schema_match` invariant (structured-output assertion).
> - **0.6.0** — the oracle layer: `Oracle` Protocol + `OracleVerdict`,
>   `ConsistencyOracle`, and the `MetaOracle` that makes `INVALID_EVAL` rigorous.
>   Guarded by a resolver branch-count meta-test. Hallucination/Grounding +
>   the full 8-verdict expansion remain a separately-gated future milestone.
> - **0.7.0** — the entry-point **plugin system**, pulled forward from Phase 2
>   (§22.3) because it is the OSS-adoption lever. Decision 1A: built-ins keep
>   their closed, typed discriminated-union specs; plugins use a generic
>   `{type: plugin, name, params}` spec + runtime discovery. Plugin discovery is
>   classified as **assembly/wiring infrastructure** — a tier beneath the three
>   evidence layers (generation / interpretation / preservation), the same tier
>   as the spec loader and CLI parser — so it does not violate the one-layer
>   rule. The hard boundary: registries change *how* objects are constructed,
>   never *what* they do.
> - **0.8.0** — reliability analytics (consumer surface, never the resolver):
>   N-model reliability matrix, per-case robustness timeline, minimal-falsifier
>   search.

### 22.1 Phase 0 — Falsification MVP (3 Weeks, Public 0.1.0)

**Goal**: ship `pip install falsifyai==0.1.0` that demonstrates the **wedge**, not just the engine.

The MVP optimizes for **narrative clarity over feature count**. Competitors (Promptfoo, DeepEval) can match an engine that runs perturbations and reports variance. They cannot match a tool that (a) catches confident hallucinations under perturbation (`CONSISTENTLY_WRONG`) and (b) flags model-migration regressions structurally (`falsifyai diff`). The MVP must show those two things or the launch is undifferentiated.

The structuring principle: compress around the differentiator, do not expand the timeline.

**Week 1 — It works** (core perturbation engine):
- YAML loader (`model`, `cases`, `input`, `expected`, `perturbations`, `invariants`, `oracles`)
- LiteLLM sync execution + content-addressed cache
- **2 perturbation families**: `typo_noise` + `casing_variant` (≥2 makes bootstrap CI honest, not "stratified with N=1")
- **2 invariants**: `contains` + `semantic_equivalence` (explicit threshold required)
- SQLite replay store with `spec_hash` + `materialized_hash`
- `falsifyai run` + `falsifyai replay`
- Bootstrap CI per perturbation type (aggregate also reported)
- **Dogfooding from day one**: `examples/` are real cases tested in FalsifyAI's own CI

**Week 2 — It matters** (differentiation layer):
- **`falsifyai diff`**: shared materialized spec across two model configs; per-case verdict-change table; exit code 5 (REGRESSION)
- **`ConsistencyOracle`** (lightweight: embedding agreement + reference contradiction; defers heavyweight NLI implementation to Phase 1)
- **`CONSISTENTLY_WRONG`** verdict wired into resolver
- **Falsifiability scoring** per invariant + suite-mean warning (cheap to add; prevents users learning the wrong mental model — see §15, §25.6)
- MVP verdict set: `STABLE`, `FRAGILE`, `CONSISTENTLY_WRONG`, `INSUFFICIENT`, `INVALID_EVAL` (5 verdicts — the minimum that tells the story; full 8 land in Phase 1)

**Week 3 — Others can use it** (OSS hardening, no polish):
- JSON output + plain terminal output (rich/colored output deferred — not a wedge)
- CI exit codes (0 / 1 / 2 / 4 / 5 / 6) per §16.1
- README with one tutorial end-to-end + `falsifyai diff` example + `CONSISTENTLY_WRONG` example
- GitHub Actions example workflow
- PyPI release: `pip install falsifyai==0.1.0`

#### 22.1.1 Phase 0 Acceptance Gate

`0.1.0` does **not** tag until ALL of these pass. PyPI publication is deployment, not validation — the gate below is validation.

- [ ] `examples/stable.yaml` triggers `STABLE`
- [ ] `examples/fragile.yaml` triggers `FRAGILE`
- [ ] `examples/consistently_wrong.yaml` triggers `CONSISTENTLY_WRONG`
- [ ] `examples/model_migration.yaml` via `falsifyai diff` exits 5 (REGRESSION)
- [ ] FalsifyAI's own test suite passes in CI (self-testing milestone)
- [ ] Deterministic reproduction verified: same seed → same `materialized_hash`
- [ ] One worked tutorial in README, end-to-end
- [ ] Demo GIF or video recorded

### 22.2 Phase 1 — Differentiation Expansion (+4 Weeks)

- 3 more perturbations: `whitespace`, `instruction_prefix`, `paraphrase_template`
- 1 more invariant: `schema_match`
- Meta-oracle: invariant degeneration + oracle conflict detection (2 of the 4 detection classes from §11.2)
- Stratified bootstrap proper (now ≥5 perturbation families to justify the term — fixes §22.1's honest "bootstrap CI" wording)
- `falsifyai plan` (Terraform-style cost preview)
- Full 8-verdict resolver: adds `INFORMATION_PRESENT`, `INFORMATION_NULL`, `ADVERSARIALLY_VULNERABLE`, `AMBIGUOUS`
- Hallucination + Grounding oracles (NLI; pulls in heavyweight `transformers` + `torch` as opt-in `[hallucination]` extra)
- `falsifyai history` + `falsifyai inspect`

### 22.3 Phase 2 — OSS Ecosystem (+6 Weeks)

- Async parallel execution
- Compositional + Adversarial perturbation modes
- LLM-based perturbations (opt-in, with bias warnings per §9.4)
- Full meta-oracle (all 4 detection classes incl. calibration tests)
- PR comment renderer for GitHub/GitLab
- Plugin entry-point system fully wired (`falsifyai.perturbations`, `.invariants`, `.oracles`, `.adapters`, `.reporters`, `.stores`)
- GitHub Actions native action
- Jailbreak + Drift oracles

### 22.4 Phase 3 — Research-Grade Platform (+12 Weeks)

- Multi-turn conversation support
- Tool-call reliability + trajectory perturbations
- Drift oracle (longitudinal; reads replay history)
- `PostgresStore` + `S3Store` (team-scale and cloud-durable)
- REST API + async worker for hosted CI integrations
- Web UI (verdict explorer, history, diff visualizations)
- Knowledge graph of verdicts over time

### 22.5 Punted Forever (Out of Scope for v1.x)

- Web dashboard before v1.0
- Distributed execution beyond async parallel
- Cloud-hosted FalsifyAI-as-a-service (consider as separate commercial product, not OSS core)
- Auth / multi-tenancy in OSS core
- Custom embedding backends beyond `sentence-transformers` + provider APIs
- Hand-rolled NLI models (defer to HuggingFace ecosystem)

---

## 23. Testing FalsifyAI Itself

The meta-problem: **a testing framework must be tested with high rigor, but its own outputs are by design uncertain.**

### 23.1 Three Test Layers

```
tests/
├── unit/
│   ├── test_perturbations.py       # determinism, validity, lineage
│   ├── test_invariants.py          # known input → known result
│   ├── test_oracles.py             # known sets → expected oracle verdicts
│   ├── test_meta_oracle.py         # all 4 INVALID_EVAL detection classes
│   ├── test_statistical.py         # bootstrap coverage property (95% CI captures truth 95%)
│   ├── test_verdict_resolver.py    # all 8 verdict transitions exercised
│   ├── test_falsifiability.py      # known invariants → expected scores
│   └── test_materialization.py     # spec_hash stability, materialized_hash uniqueness
├── integration/
│   ├── test_full_run.py            # end-to-end against MockAdapter
│   ├── test_replay_modes.py        # exact, behavioral, resample all preserve invariants
│   └── test_differential.py        # diff produces correct regression flags
└── meta/                            # tests of tests
    ├── known_verdict_fixtures.yaml  # hand-crafted, all 8 verdicts represented
    └── test_eight_verdicts.py       # each verdict reachable + correctly identified
```

### 23.2 The MockAdapter

```python
# tests/fixtures/mock_adapter.py

class MockAdapter:
    """Deterministic LLM substitute.
    
    Programmable: returns predetermined outputs for specific inputs.
    Useful for constructing all 8 verdict scenarios deterministically."""
    
    def __init__(self, response_map: dict[str, str | Callable[[str], str]]): ...
    def generate(self, input_text: str) -> str: ...
```

### 23.3 Constructing All Eight Verdicts in Fixtures

This is the hardest part. Each verdict needs a deterministic fixture:

- `STABLE`: all outputs contain "Paris" exactly
- `INFORMATION_PRESENT`: STABLE + hallucination oracle confirms reference
- `CONSISTENTLY_WRONG`: all outputs say "London" when reference is "Paris"
- `FRAGILE`: 60% say "Paris", 40% say "France's capital is the famous city"
- `ADVERSARIALLY_VULNERABLE`: 95% say "Paris", but specific prefix attack causes "I cannot help"
- `INFORMATION_NULL`: all outputs are "I'm sorry I cannot help with that"
- `AMBIGUOUS`: 60% say "Paris", 40% contradict, oracles disagree
- `INVALID_EVAL`: invariant config malformed → meta-oracle triggers

**Build these fixtures BEFORE implementing the resolver.** They are the spec for the verdict logic.

### 23.4 Property-Based Tests for Statistical Engine

Use `hypothesis` library on the statistical engine:
- Property: 95% bootstrap CI captures the true mean in 95% of trials (within tolerance)
- Property: stratified analysis worst-case ≤ aggregate ≤ best-case
- Property: confidence is monotonic in sample size

---

## 24. OSS Wedge

Ranked:

1. **`falsifyai diff`** — model migration is universal pain. No competitor solves it. Ships in v0.1 (Phase 0 MVP).
2. **`INVALID_EVAL` via meta-oracle** — the philosophical hook. "Your eval might be broken" is the conversation that pulls research-oriented users.
3. **`CONSISTENTLY_WRONG` verdict** — production safety teams care about this specifically. Differentiates from accuracy-focused tools.
4. **Falsifiability scoring** — surfaces test suite quality. Self-reinforcing: users improve their tests over time.
5. **Zero-API-cost MVP** — only requires their own model key. No additional services.
6. **`pip install falsifyai` + `falsifyai run`** — pytest-like UX wins adoption.
7. **Plugin entry points** — community-contributed perturbations/oracles. Drives ecosystem.

---

## 25. Weak Assumptions Challenged

### 25.1 Assumption: `semantic_equivalence` threshold of 0.85 is a reasonable default.

**Wrong.** Threshold is deeply domain-dependent. A 0.85 cosine on medical outputs may represent dangerously different clinical advice. **v2 ships without a default**; threshold is a required parameter. CLI errors clearly if omitted.

### 25.2 Assumption: aggregate stability_score is sufficient.

**Wrong.** Aggregate hides per-type catastrophic failures. **v2 uses worst-case stability across stratified types** as the primary verdict input. Aggregate is reported but secondary.

### 25.3 Assumption: more perturbations = better.

**Wrong.** Five paraphrases of the same syntactic structure provide correlated samples, not independent ones. **v2 adds perturbation diversity scoring in Phase 2**: warn when perturbations are highly correlated.

### 25.4 Assumption: LLM seeds guarantee reproducibility.

**False.** Providers reserve the right to ignore seeds. **v2 treats all LLM outputs as non-deterministic unless `temperature: 0` AND empirical verification.** Replay modes (`--exact` vs `--behavioral`) make the distinction explicit.

### 25.5 Assumption: oracles are independent.

**Wrong.** Oracles can disagree for valid reasons (contradiction oracle vs. grounding oracle). **v2 meta-oracle treats conflict as a first-class signal**, producing `INVALID_EVAL` when oracles cannot be reconciled.

### 25.6 Assumption: a test that passes is informative.

**Wrong.** A trivially passing test is not informative. **v2 falsifiability scoring surfaces this** and warns on low-falsifiability suites.

### 25.7 Assumption: "the model" is the right unit of test.

**Partially wrong.** Often the *system* under test is a RAG pipeline, an agent, or a prompt template — not just the model. **v2 architecture is provider-agnostic via `ModelAdapter`** so any callable system (RAG, agent, classifier) can be tested. Phase 2 adds multi-turn and tool-call support.

### 25.8 Assumption: perturbation validity is inherent.

**Wrong.** Generated perturbations are not automatically valid. **v2 makes validity checking required** (bidirectional NLI by default). Without this, FRAGILE verdicts may be artifacts of invalid perturbations rather than model fragility.

### 25.9 Assumption: SQLite is good enough forever.

**Will be wrong.** Team-scale + cloud-deployed FalsifyAI needs Postgres or S3. **v2 abstracts storage behind `ReplayStore` protocol** so backends are pluggable without core refactor.

### 25.10 Assumption: YAML is the right spec format.

**Maybe.** YAML is human-readable but error-prone (whitespace, type coercion). For Phase 3, consider Python-DSL specs (à la Bazel/Buck) as an alternative. v2 keeps YAML as primary but architects spec loading behind a protocol so other formats can be added.

---

## Closing

This v2 plan is **substantively different from v1**, not a polish. Key shifts:

1. The verdict system is now Popper-grounded with 8 verdicts in a 2D space, including `CONSISTENTLY_WRONG` for the dangerous production case.
2. Replay is sound for non-deterministic perturbations via spec materialization.
3. Statistical analysis is stratified — worst-case stability drives verdicts.
4. `INVALID_EVAL` is rigorously derived by a meta-oracle, not ad-hoc.
5. Perturbation validity is required, not optional.
6. `falsifyai diff` ships in Phase 0 MVP — the launch story needs it from day one.
7. Falsifiability scoring stops users from gaming the framework.
8. Storage is abstracted for future service-ification.
9. A 3-week Phase 0 MVP is locked, with `falsifyai diff` + `CONSISTENTLY_WRONG` + falsifiability scoring + dogfooding inside it, not deferred. An 8-item acceptance gate replaces "PyPI release" as the ship criterion.
10. Ten weak assumptions are explicitly challenged.

**Estimated complexity**: HIGH
- Phase 0 MVP: ~2,500 lines of production Python (~3 weeks solo)
- Through Phase 1: ~6,000 lines (~7 weeks total)
- Through Phase 3: ~16,000 lines (~6 months solo)

LOC estimates are speculative without a velocity baseline. Calibration happens after Week 1 of Phase 0.

**Phase 0 MVP scope is locked.** Implementation begins with Week 1 (core perturbation engine, 2 perturbation families, 2 invariants, SQLite replay, dogfooded examples).
