# ops-recruiter pipeline

## Packet format (`build`)

`context-packet.md` = recruiter message + role text + approved resume/claim
ledger (the fact authority). `build` prints the exact `$ask` chain; it does not
run browser transport itself.

## The ask chain (writing lives in $ask, not in an agent)

1. optional `$brave-search web` — company/role/rate research seed. Cited,
   degradable to "no research" without failing the draft.
2. `$ask webgpt` (fresh-keep) — comprehensive first draft, ledger attached.
3. `$ask webkimi` (fresh-keep) — clarity + humanized-prose edit of that draft.
4. `ops-recruiter gate` — fail-closed claim-bind check before the human uses it.

Web* chat models are chosen deliberately for writing/reviewing prose from
comprehensive context; coding subagents are not in the writing path.

## Claim-bind gate

Heuristic v1: numeric metrics/dates/counts in the draft must appear in the
ledger, else `ops_recruiter_claim_unbacked` (fail-closed). Not LLM claim-binding
proof. Upgrade to an LLM claim-binder only if the heuristic mis-fires.

## Correspondence memory

Collection `recruiter_correspondence`, `_key = <source>:<thread_id>:<message_id>`.
Fields: `direction` (inbound|draft|sent), `source` (gmail|linkedin|manual),
`recruiter`, `company`, `role`, `rate`, `body`, `role_ref`, `claim_keys[]`,
`draft_ref`, `received_at`, `tags`, plus outcome label once known. Write via
`$memory /store`; recall via `$memory recall --collections recruiter_correspondence`.

## Failure vocabulary ($triage-error, no ambiguity)

Pipeline failures resolve to a `$triage-error` catalog code or a minted
`ops_recruiter_unclassified_<8hex>`, each with `{code, cause, next_command}`.
Known local codes: `ops_recruiter_claim_unbacked`, `ops_recruiter_bad_message_json`,
`ops_recruiter_message_missing_field`, `ops_recruiter_bad_direction`.

## Deferred: `analyze` slice (build after threads are stored)

Mines `recruiter_correspondence` into labeled signal — the monitor-opportunities
flywheel pattern, not the `$mine-transcripts` tool (that is tuned for CLI
transcripts). Closed enums, fail-closed to the unknown value:

- disposition: `PURSUE | DEFER | DECLINE_LOW_RATE | DECLINE_PUSHY | DECLINE_OFF_MANDATE | NEEDS_HUMAN`
- rate: `ABOVE_FLOOR | AT_FLOOR | BELOW_FLOOR | RATE_UNKNOWN`
- tone: `NORMAL | PERSISTENT | PUSHY | UNKNOWN`

Never guess a rate or infer a decline the thread does not support. Graduate to a
trained classifier only at sufficient labeled volume, mirroring
`opportunity_labels` -> `classifier-lab`.
