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

There are intentionally no `login`, `browse`, `search`, `send`, `publish`, `like`,
`connect`, or `apply` execution actions.

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

## Exit codes

- `0`: command succeeded and, for `prepare`, packet is ready or `--allow-blocked` was used.
- `2`: JSON, schema, or boundary validation error.
- `3`: blocked readiness or refused lifecycle transition.
- `127`: `uv` unavailable and system-Python override not selected.
