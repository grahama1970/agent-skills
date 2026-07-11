---
name: provider-packet
description: >
  Build or validate provider dry-run packets before any paid media provider
  call. Use when a storyboard, reference sheets, story contract, or visual
  packet needs to become a locked provider request with hashes, readiness
  checks, and explicit paid-call blocking.
triggers:
  - provider packet
  - provider-packet
  - kling prompt packet
  - dry-run provider request
  - final provider prompt
provides:
  - provider-request-dry-run
  - referenced-artifacts-lock
  - readiness-receipt
composes:
  - persona-dream
  - create-storyboard
  - contact-sheet
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - video
  - provider
  - receipt
  - fail-closed
---

# Provider Packet

Validate or build the boundary between accepted storyboard/reference artifacts
and a live media provider runner.

This skill is deliberately dry-run first. It must not upload files, create paid
jobs, poll provider queues, download videos, or claim render acceptance.

## Boundary

Own:

- `final_kling_prompt.md`
- `provider_request_dry_run.json`
- `referenced_artifacts.lock.json`
- `readiness_receipt.json`
- Fail-closed validation that all referenced paths exist and paid/live flags are
  false until explicit approval exists.

Do not own:

- Story writing.
- Casting/reference research.
- Contact-sheet generation.
- Storyboard board generation.
- Live Kling execution.
- Manual visual acceptance.

## Runtime

Validate an existing packet:

```bash
cd skills/provider-packet

./run.sh validate \
  --packet-dir /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/provider_packet \
  --root /mnt/storage12tb/skills/persona-dream/outputs/<run-id>
```

The command writes:

```text
provider_packet_validation_receipt.json
```

## Acceptance

Automated acceptance requires:

- `provider_request_dry_run.json` exists and uses schema
  `persona_dream.provider_request_dry_run.v1`.
- `referenced_artifacts.lock.json` exists and every locked path exists.
- `readiness_receipt.json` exists.
- `paid_call_performed` is false.
- `live_call_authorized` is false.
- final prompt path, storyboard board path, and reference image paths exist.
- readiness remains `BLOCKED` unless manual review receipts and paid approval
  have been supplied by a separate workflow.

Validating a dry-run packet is not live provider readiness. It is proof that the
packet is inspectable and cannot accidentally perform a paid call.
