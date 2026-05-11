# /ask CAE Gap Review Contract

This contract defines a prompt-only CAE gap review path for `/ask`. It compares retrieved policy evidence, retrieved technical enforcement evidence, and retrieved control-catalog entries. It is an analyst workbench pattern, not an attestation process and not a new runtime engine.

## Boundary

Use existing `/ask` reviewer specs and review protocol primitives. Do not add a scheduler, state machine, endpoint, runner, database, or orchestration layer for this route.

The route is composed of four prompt-role specs, executed in this order:

1. `cae-policy-evidence`: extract cited policy requirements from retrieved policy artifacts.
2. `cae-technical-enforcement`: extract cited enforcement signals from retrieved technical artifacts.
3. `cae-control-mapping`: map cited findings to controls present in the supplied catalog.
4. `cae-gap-judge`: produce the final cautious analyst decision and routing recommendation.

## Required inputs

A review must provide or retrieve these fields before role execution:

- `review_id`: stable review identifier.
- `question`: original user question, preserved exactly.
- `scope`: named system, asset, organization unit, policy area, or control family.
- `retrieved_policy_evidence`: array of policy artifacts with `source_id`, `title`, `retrieved_from`, `retrieved_at`, `excerpt`, and optional `citation`.
- `retrieved_technical_evidence`: array of technical artifacts with `source_id`, `system`, `evidence_type`, `retrieved_from`, `retrieved_at`, `excerpt`, and optional `citation`.
- `control_catalog`: array of candidate controls with `control_id`, `framework`, `title`, `text`, and optional `source_id`.
- `constraints`: array of user or system constraints.

If required inputs are absent and cannot be retrieved, return `INSUFFICIENT_EVIDENCE` or `NEEDS_CLARIFICATION`. Do not fabricate inputs.

## Closed vocabularies

`final_status`: `NEEDS_VERIFICATION`, `INSUFFICIENT_EVIDENCE`, `NEEDS_CLARIFICATION`

`decision`: `GAP_INDICATED`, `NO_GAP_FOUND_IN_RETRIEVED_EVIDENCE`, `PARTIAL_GAP_INDICATED`, `INSUFFICIENT_EVIDENCE`, `NEEDS_CLARIFICATION`

`route_to`: `human_reviewer`, `policy_evidence`, `technical_enforcement`, `control_mapping`, `additional_retrieval`, `stop`

`stop_reason`: `required_input_missing`, `no_retrieved_evidence`, `evidence_conflict`, `mapping_unresolved`, `analysis_complete_with_caveats`

## Evidence rules

- Use only retrieved artifacts, cited extraction outputs, and supplied controls as evidence.
- Treat memory, summaries, and model assertions as context only.
- Use retrieval language: `retrieved`, `found`, `extracted`, and `cited`.
- Do not issue approval, certification, audit opinion, or assurance outcome.
- Do not invent source IDs, control IDs, citations, systems, dates, or enforcement mechanisms.

## Integration result

The `/ask` integration result must expose a separate advisory contract object
alongside the raw reviewer and judge turns. Required fields:

- `advisory_only`: always `true`.
- `final_status`: one of the closed-vocabulary final statuses.
- `missing_evidence`: the judge-provided missing evidence list, or an empty list.
- `qra_correction_recommendation`: advisory correction guidance only. A proposed
  QRA correction is not grounded until it is rerun through `/create-evidence-case`.
- `route_to_persona`: the next reviewer persona or terminal human/retrieval route.
- `source_artifact_requirements`: machine-readable reminders that memory and
  dogpile are context/retrieval aids only, retrieved artifacts need source IDs,
  source artifacts must be present in the evidence-case payload, and QRA
  corrections require a new `/create-evidence-case` run.

Do not persist this object as evidence. Persist it as advisory review lineage
linked to the evidence case version that was reviewed.

## Required judge result

The final `cae-gap-judge` JSON object must include `review_id`, `decision`, `decision_summary`, `cited_basis`, `missing_evidence`, `route_to`, `stop_reason`, and `final_status`.

Human-facing markdown may summarize the judge result, but the machine-readable JSON objects from the prompt-role specs are the source of record.

## Prompt-lab gate

Prompt changes to CAE reviewer or judge roles must run through `/prompt-lab`
before production use. Use a 50-200 item sample of failed, inconclusive, and
synthetic evidence-case examples. The sample must include memory-only context,
missing source IDs, repeated missing evidence, a valid terminal human route, and
a proposed QRA correction that still requires a new `/create-evidence-case` run.

## Rejection gates

Reject or reroute the review if a required input is missing, an output uses a value outside the closed vocabularies, a claim lacks a cited retrieved basis, context is treated as evidence, identifiers are invented, or the judge omits required routing and status fields.

## Non-goals

CAE gap review does not replace human judgment, issue attestations, certify systems, or infer unavailable evidence from plausible system behavior.
