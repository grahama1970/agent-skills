# Persona Dream Phase 08-11 Provider Boundary

Status: source-derived dry-run architecture artifact

This document separates media evidence, provider routing, provider contract compilation, live submission, provider return, and Watch handoff. It is intentionally narrower than the full Persona Dream cognitive loop.

## Phase Model

1. Phase 08 Media Lock
   - State: `PASS_MEDIA_LOCK`
   - Owns all accepted storyboard frame evidence, hashes, dimensions, identity status, and local media-lock lineage.
   - Does not choose a video provider and does not imply provider readiness.

2. Phase 09 Video Provider
   - State: `PASS_VIDEO_PROVIDER_PACKET_DRY_RUN`
   - Owns video scene classification, provider registry refresh evidence, provider scorecard, recommended provider, and provider-specific dry-run packet.
   - May rank a provider while keeping live submission blocked.

3. Phase 10 Provider Contract
   - State: `PASS_PHASE10_PROVIDER_CONTRACT_DRY_RUN`
   - Owns provider request-body compilation, payload hash, field mapping, media publication plan, cost contract, entitlement contract, async return contract, manual-acceptance status, and live-readiness blockers.
   - Must keep `provider_live=false`, `paid_call_authorized=false`, `submitted=false`, and `actual_provider_call_attempts=0`.

4. Phase 10 Provider Contract Gate
   - State: `PASS_PHASE10_PROVIDER_CONTRACT_DRY_RUN_GATE`
   - Owns deterministic validation of required contract sections, field mappings, payload hash, async polling plan, non-claims, and no-network side effects.

5. Phase 11 Provider Return
   - Intended state after future live authorization only.
   - Owns submitted task id, poll or callback evidence, returned media, media hash, FFprobe output, contact sheet, and handoff to Watch.

## Boundary Diagram

```text
Phase 08 Media Lock
  PASS_MEDIA_LOCK
  all accepted storyboard frames locked by hash
        |
        v
Phase 09 Video Provider
  PASS_VIDEO_PROVIDER_PACKET_DRY_RUN
  provider registry + scorecard + selected provider packet
        |
        v
Phase 10 Provider Contract
  PASS_PHASE10_PROVIDER_CONTRACT_DRY_RUN
  request body + payload hash + mapping + live blockers
        |
        v
Phase 10 Contract Gate
  PASS_PHASE10_PROVIDER_CONTRACT_DRY_RUN_GATE
  no provider call, no paid call, no live-ready claim
        |
        v
Future Phase 11 Live Submit Gate
  BLOCKED until URLs, probes, cost, entitlement, manual acceptance,
  paid authorization, callback/polling, and live policy all pass
        |
        v
Future Provider Return
  returned video + ffprobe + contact sheet
        |
        v
Future Watch Handoff
  observed visible/audible facts only
```

## Invalidation Rules

Any change to these inputs makes the Phase 10 contract stale:

- accepted storyboard frame hash
- media lock manifest hash
- selected provider
- provider scorecard
- provider registry refresh receipt
- fal endpoint or provider payload shape
- scene prompt, duration, aspect ratio, audio state, or reference inputs
- provider-accessible media URL route
- cost mode or cost ceiling
- manual-acceptance receipt
- paid-call authorization receipt

Stale contracts must not be promoted to live submission. They must be regenerated from the current Phase 09 packet and registry refresh evidence.

## Phase 10 Required Contract Sections

- `provider_id`
- `fal_model_endpoint`
- `registry_refresh_status`
- `normalized_request_schema`
- `provider_request`
- `field_mapping`
- `provider_media_publication_plan`
- `cost_contract`
- `entitlement_contract`
- `async_return_contract`
- `manual_acceptance`
- `phase10_contract_blockers`
- `phase11_live_readiness_blockers`
- `non_claims`

## Live Blockers Retained By Phase 10

- `BLOCKED_PROVIDER_ACCESSIBLE_URLS_MISSING`
- `BLOCKED_PROVIDER_URL_PROBES_MISSING`
- `BLOCKED_COST_ESTIMATE_UNVERIFIED`
- `BLOCKED_PROVIDER_ENTITLEMENT_UNVERIFIED`
- `BLOCKED_MANUAL_ACCEPTANCE_MISSING`
- `BLOCKED_PAID_CALL_AUTHORIZATION_MISSING`
- `BLOCKED_LIVE_SUBMIT_DISABLED_IN_PHASE10_DRY_RUN`

## Non-Claims

Phase 10 dry-run contract evidence does not prove:

- current live fal schema compatibility
- provider-accessible media URLs
- URL probe success
- cost approval
- provider entitlement
- callback readiness
- manual acceptance
- paid-call authorization
- live provider readiness
- live video generation
- provider return
- Watch observation
- dream interpretation
- memory persistence

The strongest valid claim at this boundary is:

```text
The Phase 09 provider packet was compiled into a local, payload-hashed,
field-mapped, fail-closed Phase 10 provider contract with explicit future
live-readiness blockers and zero provider calls.
```
