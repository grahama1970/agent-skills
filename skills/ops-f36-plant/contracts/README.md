# F-36 Watch Evidence Contracts

This directory holds the contract-first gate for the first recorded F-36 visual
evidence canary. It is intentionally separate from Watch UI/runtime code.

## Current Slice

- `schemas/f36_watch_contracts.v1.schema.json` defines the shared contract
  bundle requested by architecture review:
  - `common.event_envelope.v1`
  - `common.evidence_artifact_ref.v1`
  - `common.persistence_outbox_event.v1`
  - `f36.semantic_package_manifest.v1`
  - `f36.test_procedure_snapshot.v1`
  - `f36.work_context.v1`
  - `f36.asset_registry.v1`
  - `f36.test_run.v1`
  - `f36.test_adapter_event.v1`
  - `f36.telemetry_event.v1`
  - `watch.source_session.v1`
  - `watch.detector_profile.v1`
  - `watch.detector_observation.v1`
  - `watch.sequence_event.v1`
  - `watch.coverage_event.v1`
  - `watch.crop_artifact.v1`
  - `watch.label_decision.v1`
  - `watch.memory_ingest_receipt.v1`
  - `watch.suggestion_request.v1`
  - `watch.suggestion_result.v1`
  - `f36.visual_evidence_bundle.v1`
  - `f36.visual_evidence_review.v1`
  - `f36.disposition.v1`
  - `sparta.evidence_case_link.v1`

- `fixtures/f36_recorded_visual_canary.positive.json` is the smallest positive
  recorded visual-inspection fixture.
- `fixtures/negative/*.json` are mutation fixtures for the failure modes that
  would create false confidence.
- `scripts/validate_f36_watch_contracts.py` validates schema and semantic
  contract rules.

## Validation

```bash
python3 skills/ops-f36-plant/contracts/scripts/validate_f36_watch_contracts.py
```

This proves contract and fixture behavior only.

It does not prove:

- Watch browser UI behavior
- live Memory/Qdrant recall
- SPARTA resolver correctness against a real semantic package
- Embry OS runtime integration
- manufacturing disposition behavior
