# Safety, promotion, and effect contract

## Separate capability readiness from item authorization

A maturity stage is not an external-effect authorization. Capability promotion says one
bounded adapter/action class has passed its gates. Per-item authorization says a human
approved one exact effect payload. Both are required where specified.

Stage 0 is `STAGE_0_RESEARCH_ONLY`. It permits approved public-source reads, local
artifacts, deterministic ranking, local claim-bound resume compilation, and report
rendering. It permits no connected-system write.

## Capability matrix

| Capability | Stage 0 | Permanent boundary |
|---|---|---|
| approved public-source read | allowed when implemented | source/policy scoped |
| local dossier/report/resume artifacts | allowed | no hidden queue |
| local outreach text | allowed, not sendable | human transmits |
| Gmail mailbox draft creation | blocked pending promotion | draft only |
| Gmail send/schedule-send/forward | forbidden | never implemented here |
| LinkedIn human handoff readiness | blocked pending promotion | local packet only |
| LinkedIn discovery/contact evidence | read-only only when explicitly authorized and bounded | no connect/message/post/apply |
| LinkedIn Easy Apply submit | blocked pending post-report exact human authorization | never automatic; no standing class authorization |
| ATS form inspect | blocked pending site/provider promotion | read-only |
| ATS form prefill | blocked pending separate promotion | no submit |
| ATS form submit | blocked pending separate promotion and item authorization | exact payload only |

## Promotion receipt

A promotion is explicit, human-issued, capability-specific, scoped, versioned,
receipt-bearing, expiring or revocable, and bound to evidence. Minimum fields:

```json
{
  "schema": "monitor_opportunities.capability_promotion.v1",
  "capability": "ats_form_inspect:greenhouse:example.com",
  "actor": "human",
  "decision": "PROMOTE",
  "contract_version": "0.2.0",
  "evidence_receipt_ids": ["..."],
  "scope": {"providers": ["greenhouse"], "sites": ["example.com"]},
  "effective_at": "...",
  "expires_at": "...",
  "revocation_ref": null,
  "does_not_authorize": ["future_application_payloads", "gmail_send", "linkedin"]
}
```

Promotion cannot be inferred from elapsed time, a successful fixture, CI, model/panel
agreement, prior successful effects, or exit code zero.

## Per-application authorization

ATS and LinkedIn Easy Apply submission additionally require a human authorization,
given after report review/collaboration, bound to:

- posting and employer identity;
- current form schema/content digest;
- resume and attachment digests;
- exact answers and answer-bank version;
- unresolved-field set (which must be empty for required fields);
- provider/site policy digest;
- application-plan/payload digest;
- actor, timestamp, and idempotency key.

Any change invalidates authorization. A global stage change never authorizes future
unknown applications. Top Applicant, Easy Apply, quick-apply, or similar low-friction
signals improve priority only; they do not authorize submission.

## Two-phase external effect

```text
PREPARED
  -> HUMAN_AUTHORIZED
  -> COMMITTING
  -> COMMITTED | BLOCKED | INDETERMINATE
```

Before `COMMITTING`, reserve the stable application/effect key. After an attempted write,
read back provider evidence. Timeout or connection loss after the possible commit point is
`INDETERMINATE`, never presumed failed. Automatic retry is blocked until reconciliation
proves committed or not committed.

## Human-only fields

The following are always `human_required` and cannot be generated or inferred:

- EEO, veteran, disability, gender/race/ethnicity self-identification;
- clearance and citizenship/work authorization;
- salary/compensation expectations;
- legal, background, or criminal disclosures;
- ambiguous choice fields;
- every free-text application field;
- any field without an exact approved answer-bank hit.

## Outreach

Every proposed Gmail or LinkedIn message is claim-bound and requires a permitting `/ask`
roundtable receipt. Gmail may create a mailbox draft only after its own promotion; send is
forbidden. LinkedIn outreach output remains a local handoff packet and performs no
platform action. The candidate is the transmitter.

## Runtime self-improvement boundary

Runtime observations may propose parser, source, ranking, or report improvements. They may
not silently modify the immutable goal, geography, authority, source allowlists, target
registry, claim facts, human attestations, ranking thresholds, caps, or effect policy.
