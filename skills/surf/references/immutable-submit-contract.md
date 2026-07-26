# Surf Immutable Submit Contract

Schema: `surf.immutable_submit.v1`

Every provider submit wrapper is expected to preserve enough local state for an
agent to recover or audit the request without relying on browser memory.

Required artifacts per submit:

- `input`: exact source request file supplied by the caller.
- `submitted_output`: exact prompt text rendered and sent to the provider after
  wrapper expansion, sentinel insertion, and attachment routing.
- `output`: clean assistant response consumed by the caller.
- `raw_output`: raw provider/browser capture before parser cleanup.
- `meta`: provider metadata JSON.
- `stderr_log`: bounded transport/provider stderr when available.

Required metadata per submit:

- provider command and route decision.
- requested tab/view id and requested URL when supplied.
- controlled tab/view id and actual URL when observed.
- model and reasoning settings requested or selected.
- completion proof status and sentinel fields.
- retryability and bounded error code/message.
- stale-binding detection, repair attempt, and new binding when repair occurs.

`surf meta.normalize --meta response.meta.json --json --strict` is the offline
checker for this contract. Strict mode fails when the immutable request snapshot
or core proof artifacts are missing.
