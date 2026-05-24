# FalsifyAI — Compliance Mapping

> **Scope:** how FalsifyAI replay artifacts map to the testing-evidence
> requirements that high-risk AI systems will face under
> [EU AI Act Article 11 + Annex IV](https://ai-act-service-desk.ec.europa.eu/en/ai-act/annex-4).
> This is **a mapping document, not a certification claim.** FalsifyAI is
> open-source tooling that produces evidence of a specific shape; whether
> that evidence satisfies any particular conformity assessment is a
> determination only the provider, their notified body, and (ultimately)
> the national competent authority can make.
>
> As of v0.3.0 the artifact has strong **deterministic identity** (sha256
> hashes on every layer — artifact-internal hashes plus bundle-level
> content addressing via `falsifyai export --bundle`) but is **not
> cryptographically signed**. Signing is deferred until artifacts cross
> trust boundaries (e.g., regulatory submission) — see
> [`EVIDENCE.md` §6](EVIDENCE.md#6-portability-infrastructure-not-core-guarantees-intended-phase-1).
> Until signing lands, the mapping below identifies which Annex IV
> obligations the current artifact substantively addresses, and which
> require either (a) provider-supplied wrapping or (b) future FalsifyAI work.

---

## 1. Why this document exists

EU AI Act Article 11 requires providers of high-risk AI systems to draw up
technical documentation **before** the system is placed on the market, and
to keep it up to date. The minimum content is defined in Annex IV across
nine sections.

Section 2(g) of Annex IV — the validation-and-testing subsection — requires:

> *"the validation and testing procedures used, including information about
> the validation and testing data used and their main characteristics;
> metrics used to measure accuracy, robustness and compliance with other
> relevant requirements set out in Chapter III, Section 2, as well as
> potentially discriminatory impacts; **test logs and all test reports dated
> and signed by the responsible persons**, including with regard to
> pre-determined changes as referred to under point (f)..."*

A replay artifact is structurally the test-log shape this clause asks for:
dated, identity-anchored, fully evidenced, immutable after save, with a
preserved verdict that can be re-derived from the preserved inputs and
judgments. That is the substantive fit. The two gaps —
**cryptographic signature** and **pre-declared performance thresholds** —
are addressable; this document names them honestly rather than papering
over them.

---

## 2. Field-level mapping (Annex IV(2)(g))

| Annex IV(2)(g) requirement | FalsifyAI artifact field | Notes |
|---|---|---|
| **Validation and testing procedure** | `materialized.cases[].perturbations[]` + the spec YAML referenced via `spec_hash` | The materialized spec preserves *every realized perturbation string* with its family, parameters, and seed lineage. A reader can reconstruct what was tested without the source YAML. |
| **Command that produced this evidence** | `cli_invocation.argv` + `cli_invocation.falsifyai_version` (since v0.3.0+PR-35) | Captures the normalized CLI invocation at `cmd_run` entry. Records *what command produced the artifact*, not a guarantee that re-running it will produce identical outputs (replay determinism still lives in `materialized_hash` and `bundle_id`). Pre-PR-35 artifacts carry `cli_invocation = null` and require external bookkeeping for this requirement. |
| **Information about validation/testing data** | `materialized.cases[].original_input` + `case_results[].perturbed[].perturbed_input` | Original inputs and the full perturbation set are preserved verbatim, as data, not as a reference. |
| **Metrics used to measure accuracy/robustness** | `case_results[].stability`, `stability_ci_low`, `stability_ci_high`, `per_family_stability`, `worst_case_family` | Worst-case stratified bootstrap CI per perturbation family. The metric definition is documented in [`EVIDENCE.md` §4.5](EVIDENCE.md#45-the-verdict). |
| **Test logs** | The artifact itself (one `ReplayArtifact` per `falsifyai run`) | Immutable after save (see [`EVIDENCE.md` §5.1](EVIDENCE.md#51-immutability-after-save)). |
| **Test reports** | `falsifyai inspect <session_id>` rendered output | Per-case deep-dive over preserved evidence; consumer surface, not stored separately — see [`EVIDENCE.md` §9.2](EVIDENCE.md#92-inspection). |
| **Dated** | `created_at` (UTC, ISO 8601) | Naive datetimes are rejected by the serializer; the timestamp is authoritative for "when this test ran." |
| **Signed by the responsible persons** | **Not yet supported.** | Cryptographic signing is on the post-Phase-D track. Until then, providers should wrap the artifact in their existing attestation workflow (e.g., git-signed commit of the exported artifact, internal sign-off in a change-management system). |
| **Pre-determined changes (Annex IV(2)(f))** | `falsifyai diff <baseline> <candidate>` exit code 5 | A verdict-class downgrade is a *pre-determined* regression criterion — the threshold is the verdict shape, not a tunable number. Diff produces a reviewable, reproducible report against a committed baseline `session_id`. |

---

## 3. Identity, traceability, and reproducibility

Annex IV(2)(c) requires the documentation to describe how the system can
be tested and validated reproducibly. The artifact's three-hash identity
model directly supports this:

| Annex IV concern | Artifact field | How it addresses the concern |
|---|---|---|
| *"Which spec file produced this evidence?"* | `spec_hash` (sha256 of source YAML bytes) | Two runs of the same YAML produce identical `spec_hash`; any edit changes it. |
| *"Were the same inputs actually executed?"* | `materialized_hash` (sha256 of realized perturbations + lineage) | Identical seed + identical spec → identical `materialized_hash`. Distinguishes "same intent" from "same execution." |
| *"Which specific invocation am I looking at?"* | `session_id` (UUID4 at save) | Two runs of identical spec at different times share hashes but have different `session_id`s — distinguishes "same evaluation, different invocation" from "different evaluation" in one glance. |
| *"What software produced this?"* | `falsifyai_version` | Required for forward-compat reading; refusing to open newer artifacts is enforced via `schema_meta.version` in the store. |

These four together give a notified-body reader the ability to answer
"is this the same test you ran in March?" without relying on file paths,
naming conventions, or operator memory.

---

## 4. The "pre-declared performance threshold" requirement

Multiple Annex IV guides
([aiacto.eu](https://www.aiacto.eu/en/blog/documentation-technique-ai-act-article-11-annexe-iv),
[unorma.com](https://unorma.com/build-a-compliant-ai-technical-file/))
emphasize that regulators look for evidence the performance bar was set
**before** the test ran — not retro-fitted to whatever the system
happened to achieve.

FalsifyAI's spec satisfies this *structurally*:

- The **invariants** in `cases[].invariants` declare what counts as "the
  same answer" *before* the model is called. They are the pre-declared
  pass condition.
- The **verdict semantics** are fixed in the framework, not the spec.
  `STABLE` means "every perturbation passed every invariant" — that
  definition cannot be tuned per-run without changing the FalsifyAI
  version, which is preserved as `falsifyai_version` on the artifact.
- The **regression criterion** in `diff` is a verdict-class downgrade —
  again, framework-level, not run-level. There is no per-run threshold
  to retro-fit.

For an auditor, the chain is:

1. The spec YAML (hashed in `spec_hash`) declares the invariants.
2. The framework version (`falsifyai_version`) pins the verdict semantics.
3. The artifact's `verdict` is the deterministic output of (1) + (2)
   applied to the observed evidence.

A reader cannot move the goalposts after the fact without leaving a
visible hash change.

---

## 5. Retention and discoverability (Article 12 + Annex IV(7))

Article 12 requires automatic logs of high-risk AI systems be retained
for **at least six months**; Article 18 requires the technical
documentation itself be retained for **10 years** after the system is
placed on the market.

FalsifyAI's default store is `.falsifyai/replays.db` (SQLite). Operational
guidance for providers in scope:

- **Commit replay databases as repository artifacts** alongside the code
  that generated them. Git provides tamper-evident history.
- **For CI evidence**, archive the `.falsifyai/replays.db` as a workflow
  artifact with the retention policy you would apply to a SARIF report
  or test-log JSON.
- **For multi-year retention**, store exported artifacts in a
  WORM-suitable system (object storage with retention locks).
  `falsifyai export <session_id> --bundle <output>.fai.zip` (shipped in
  vNEXT) productizes this packaging — a deterministic zip containing
  `manifest.json` (with content-addressed `bundle_id`, per-file SHA256s,
  and provenance metadata), `artifact.json`, optional `spec.yaml`, and an
  auto-generated `README.md`. Two exports of the same artifact with the
  same `--exported-at` produce byte-identical bundles and identical
  `bundle_id`s. The SQLite file itself plus the source spec YAML remains
  a valid durable unit; the bundle is the recommended portable form.

---

## 6. Known gaps relative to a full Annex IV submission

A replay artifact is **one input** to a technical file, not the entire
file. Annex IV requires nine sections; FalsifyAI's artifact materially
addresses parts of Section 2 (validation/testing/metrics) and Section 9
(post-market monitoring, when artifacts are produced on a schedule).
Everything else — general system description, data governance, risk
management, human oversight, cybersecurity, declaration of conformity —
is the provider's responsibility, not the artifact's.

Explicit gaps in the *artifact itself*:

| Gap | Status |
|---|---|
| **Cryptographic signature of the artifact** | Deferred until post-Phase-D artifact track. Today's identity is deterministic (sha256) but not signed. Aligns with broader [AIBOM signing efforts](https://arxiv.org/html/2601.05703) using in-toto attestations. |
| **Operator identity ("signed by responsible persons")** | Not preserved in the artifact by design (see [`EVIDENCE.md` §10.3](EVIDENCE.md#103-no-external-state)). Providers should bind operator identity at the **commit / export** layer (signed git commit, change-management ticket). |
| **PII / data-minimization annotation on inputs** | The artifact preserves whatever the spec puts into `original_input`. Providers using production data as test inputs must apply their own data-governance discipline upstream of the spec. |
| **Standardized export format** | `falsifyai export <session_id> --bundle <output>.fai.zip` shipped in vNEXT. Produces a deterministic zip with content-addressed `bundle_id` (sha256 over canonical manifest); per-file SHA256s; provenance metadata (`exported_at`, `falsifyai_version`, `platform`, `python_version`); `pre_export_integrity` block; reserved `attestations: []` and `signature_slots: []` for future signing. Refuses to export corrupted artifacts by default. |

These gaps are *named here* rather than buried in code, so a compliance
team reviewing FalsifyAI for adoption can plan around them rather than
discover them mid-audit.

---

## 7. Practical adoption checklist

For teams considering FalsifyAI as part of an Annex IV technical-file
workflow:

- [ ] Author the spec YAML to declare invariants explicitly — these are
  the pre-declared pass conditions. Avoid retro-fitting them after seeing
  outputs.
- [ ] Commit baseline `session_id`s to a versioned location (repo
  variable, change-management record) so `diff` runs have a stable
  comparator.
- [ ] Treat the `.falsifyai/replays.db` (or exported bundle, when
  available) as a first-class artifact in your release workflow.
- [ ] Wrap operator identity at the commit / CI layer. Until artifacts
  are signed, the surrounding workflow (signed commits, audit trail of
  who triggered the CI run) carries the "signed by responsible persons"
  requirement.
- [ ] Document the FalsifyAI version, spec hash, and session id of the
  evidence cited in your technical file's testing section. These three
  fields are the chain of custody.
- [ ] Re-run the suite on any "pre-determined change" (model upgrade,
  spec evolution, prompt rewrite) and preserve the new artifact alongside
  the old one. `falsifyai diff` produces the comparative report.

---

## 8. See also

- [`EVIDENCE.md`](EVIDENCE.md) — what the artifact *is* as a protocol,
  including the four load-bearing guarantees (immutability, self-containment,
  deterministic identity, resolver predictability).
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — how the code is organized to
  produce the artifact.
- [EU AI Act Article 11](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-11)
  and [Annex IV](https://ai-act-service-desk.ec.europa.eu/en/ai-act/annex-4)
  — the source obligations this mapping addresses.
- [G7 SBOM-for-AI guidance](https://www.acn.gov.it/portale/documents/d/guest/g7-sbom-for-ai-miminum-elements_12-may-2026)
  and [SPDX 3.0 AIBOM](https://www.linuxfoundation.org/hubfs/LF%20Research/lfr_spdx_aibom_102524a.pdf)
  — the adjacent standardization context for AI evidence formats.
