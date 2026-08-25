# ops-linkedin contracts

## Request schema

Schema: `ops-linkedin.request.v1`

Required fields:

- `schema_version`: exactly `ops-linkedin.request.v1`.
- `lane`: `profile`, `explore`, `publish`, `interact`, `lead-gen`, or `content-ops`.
- `action`: one action valid for that lane.
- `content.text`: the local draft, query, or analysis input.

Optional fields:

- `content.title`
- `content.attachment_paths`
- `target.name`, `target.company`, `target.url`
- `claims[]`
- `research_inputs[]`
- `notes[]`

Unknown fields fail validation.

## Lane/action matrix

| Lane | Actions |
|---|---|
| `profile` | `profile-update` |
| `explore` | `search-plan` |
| `publish` | `post`, `image-post` |
| `interact` | `comment`, `connection-note`, `message` |
| `lead-gen` | `lead-research-plan` |
| `content-ops` | `content-review` |

There are intentionally no `login`, unscoped `browse`, `search`, `send`, `publish`,
`like`, `connect`, `follow`, or `apply` execution actions.

## Claim schema

```json
{
  "claim_id": "stable-local-id",
  "text": "The exact factual claim.",
  "status": "verified",
  "source_refs": ["receipt-or-public-source"],
  "notes": "Optional scope or caveat."
}
```

Statuses:

- `verified`: requires at least one source reference.
- `needs-source`: blocks the packet.
- `excluded`: retained for audit but not approved for use.

`profile-update` and `lead-research-plan` require at least one verified claim. Other actions
may omit a claim ledger, but the packet warns the human to verify all factual statements.

## Handoff schema

Schema: `ops-linkedin.handoff.v1`

Important fields:

- `packet_id`: unique local packet identifier.
- `request_digest_sha256`: canonical request digest.
- `status`: lifecycle state.
- `readiness`: evidence gate.
- `guardrails`: fixed negative-capability record.
- `manual_steps`: human-only execution instructions.
- `proof`: explicit execution and verification limits.

Every newly prepared packet has:

```json
{
  "status": "PREPARED",
  "requires_human": true,
  "proof": {
    "execution_claim": "NOT_EXECUTED",
    "platform_verified": false
  }
}
```

## Attestation contract

`attest` requires all of the following:

1. The packet validates.
2. Its status is `PREPARED`.
3. Its readiness is `READY_FOR_HUMAN_REVIEW`.
4. The caller supplies `--actor`.
5. The caller supplies `--confirm-human-completed` after an explicit human statement.

The resulting packet uses:

```json
{
  "status": "HUMAN_ATTESTED_COMPLETE",
  "proof": {
    "execution_claim": "USER_ATTESTED_MANUAL_ACTION",
    "platform_verified": false,
    "human_attestation": {
      "actor": "...",
      "attested_at": "...Z",
      "statement": "I performed this LinkedIn action manually."
    }
  }
}
```

The statement is not a LinkedIn API receipt, browser receipt, delivery receipt, impression
receipt, or independent verification.

## Editable own-profile entry schema

Schema: `ops-linkedin.profile_entry.v1`

This is the project-agent editable source for Graham's LinkedIn profile. Generate it
from `RESUME.md`, review or edit the JSON, then feed it to `profile-sync-plan`.

Important fields:

- `source.path`, `source.sha256`, `source.generated_at`: the resume source identity.
- `profile_url`: must be Graham's own `https://www.linkedin.com/in/...` profile URL.
- `name`, `location`, `headline`, `about`: primary profile text.
- `featured_links[]`: links such as `https://grahama.co/resume`.
- `experience[]`: editable role entries with `title`, `organization`, `dates`, `body`,
  and `source_ref`.
- `skills[]`: flat editable skill list.
- `editor_notes[]`: instructions for project agents editing the JSON.

The profile-entry file is easy to diff and edit. Project agents should change this JSON
first, not LinkedIn fields directly.

## Own-profile Surf sync plan schema

Schema: `ops-linkedin.profile_sync.v1`

`profile-sync-plan` consumes either `RESUME.md` directly or an
`ops-linkedin.profile_entry.v1` JSON file. It emits:

- `profile_entry`: the exact editable profile entry being proposed.
- `fields[]`: flattened field-level sync targets for browser work.
- `guardrails`: `own_profile_only=true`, `account_risk_accepted=true`,
  `no_third_party_profile_access=true`, `no_scraping=true`,
  `no_outbound_social_actions=true`, `external_effects=false`, and
  `platform_verified=false`.
- `surf_commands[]`: the bounded Surf command plan.
- `execution_claim`: always `NOT_EXECUTED` at plan time.

The plan is not proof that LinkedIn changed. A future executor must produce a separate
Surf receipt and before/after evidence before claiming any platform mutation.

## Contact graph capture plan schema

Schema: `ops-linkedin.contact_graph_capture_plan.v1`

`contact-graph-capture-plan` emits a bounded plan for named opportunity contacts only.
It requires both `--user-authorized-read-only` and `--accept-account-risk`.

Important fields:

- `opportunity`: the job/client opportunity this capture supports.
- `targets[]`: named `NAME|COMPANY|https://www.linkedin.com/in/...` profile targets.
- `authorization`: always `USER_AUTHORIZED_READ_ONLY_ACCOUNT_RISK_ACCEPTED` when emitted.
- `allowed_observations`: visible relationship degree, visible mutual names when shown,
  visible title/company/location headline, and relevance signals for the named target.
- `prohibited_actions`: includes connect/follow/react/post/apply/save and sending any
  message/InMail.
- `output_schema`: `monitor_opportunities.linkedin_contact_graph_evidence.v1`.
- `execution_claim`: always `NOT_EXECUTED` at plan time.
- `platform_verified`: always `false` at plan time.

The plan is not proof that a mutual contact exists and it is not outreach authority. A
later browser receipt may record the allowed observations; any InMail/message copy remains
a local handoff packet and sending is a separate human action.

## Exit codes

- `0`: command succeeded and, for `prepare`, packet is ready or `--allow-blocked` was used.
- `2`: JSON, schema, or boundary validation error.
- `3`: blocked readiness or refused lifecycle transition.
- `127`: `uv` unavailable and system-Python override not selected.


## Outbound roundtable contract (added 2026-08-02)

`HandoffRequest.roundtable_review` is required for every action in `OUTBOUND_ACTIONS`
(`post`, `image-post`, `comment`, `connection-note`, `message`).

| Field | Rule |
|---|---|
| `ran` | must be `true` |
| `run_dir` | Ask tau-dag run directory; receipts must be inspectable |
| `topology` | must be `concurrent`; sequential is a pipeline, not a roundtable |
| `immutable_goal` | >= 20 chars; `$ask` fails preflight without one |
| `shared_packet_identical_for_every_seat` | must be `true`; no seat gets hidden context |
| `seats` | >= 3 requested, **>= 2 with status `PASS`** |
| `synthesis` | `seat_status`, `common_ground`, `attributed_dissent` required |
| `rounds_run` | 1..3 (best-practices-roundtable cap) |
| `verdict` | only `SEND_AS_IS` or `SEND_WITH_REVISIONS` permit execution |
| `follows_best_practices_roundtable` | must be `true` |

A missing or non-permitting review yields `readiness: BLOCKED_MISSING_ROUNDTABLE`. The
readiness gate is evaluated in the service rather than raised in the model so the caller
receives an inspectable blocked packet with a warning, not an opaque validation error.
Structural violations (sequential topology, one PASS seat) are model-level and raise.

## Claim vocabulary binding (added 2026-08-02)

`Claim.claim_key` references the approved claim in the canonical `career_profile`
collection in `/memory`, shared with `grahamaco.inmail_draft.v1`
`claims_referenced[].claim_key`. A `verified` claim without `claim_key` is rejected:
two independent ledgers over the same facts is how the 70-vs-90 worker-role drift
happened, and on this surface the drift would be a false claim to an employer.
