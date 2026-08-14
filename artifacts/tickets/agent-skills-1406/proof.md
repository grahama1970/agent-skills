# Proof For agent-skills#1406

Ticket: https://github.com/grahama1970/agent-skills/issues/1406

Closure bar, quoted:

> Closure requires CLI/API equivalence, idempotency, peer/path security tests,
> live event/readback, and API-server restart proof while Tau remains
> authoritative; an HTTP wrapper, terminal scraper, or in-process-only Python
> import is not closure proof.

## CLI/API equivalence (proof 3)

`test_run_show_returns_the_same_projection_as_the_cli` asserts the API result
equals `project_run(...)` exactly — the same object the CLI renders, not a
comparison by eye. `test_stdio_and_dispatch_agree` asserts the stdio transport
returns byte-identical output to the in-process dispatcher, so the two
transports cannot diverge.

Live, through the real entrypoint (not an in-process import):

```
$ echo '{"method":"ping","request_id":"x"}' | ./run.sh api stdio
{"method": "ping", "ok": true, "protocol": "ask.local_api.v1", "request_id": "x", ...}

$ printf '%s\n%s\n' '{"method":"ping"...}' '{"method":"nope"...}' | ./run.sh api stdio
-> first ok=true, second error.code=unknown_method
```

## Idempotency (proof 5)

A repeated key returns the original run identity and resubmits nothing:

```
{"run_id": "run-abc", "duplicate": true,
 "note": "returned the original run; nothing was resubmitted"}
```

The same key with a *different* payload raises `idempotency_conflict`. Accepted
work is often paid work; a retry must not buy it twice.

## Peer and path security (proof 8)

- Socket created under `umask 077`, `chmod 0600`; the test asserts mode `600`.
- `SO_PEERCRED` UID compared to the server's; mismatch returns
  `unauthorized_peer`. A local socket is not a trust boundary on a shared
  machine unless it is made one.
- Oversized request → `request_too_large`.
- `/etc/passwd`, a `..` traversal, and a **symlink escaping the root** are all
  refused with `path_not_permitted`. `resolve()` runs before the containment
  check because a symlink out and a `..` segment are the same escape.
- No TCP listener exists.

## Event reconnect (proof 6)

A cursor beyond known events reports `gap: true` with zero events rather than
replaying — silently re-emitting would let a reconnect look like new work. A
valid cursor resumes with no duplicates.

## Tau remains authoritative (proof 4)

Controls call #1402, which itself refuses to simulate authority Ask lacks.
`run.submit` returns `unsupported` rather than becoming a second scheduler.
Route inventory registers `local_api.py` and `api_cli.py` as
`local_non_agentic` / `probe_only`.

## A bug the tests caught in my own dispatcher

`params or {}` coerced a malformed `[]` into `{}` before the type check could
fire, silently accepting a request shape the protocol forbids. The check now
runs on the raw value.

## Server restart (proof 7)

Two **separate server processes**, socket removed between them, same query:

```
server 1: ./run.sh api serve --socket /tmp/ask-api-restart-test.sock --max-connections 1
  -> run.show lifecycle=PASS ; process exits, socket gone (verified: "socket present: no")

server 2: fresh process, same socket path
  -> run.show lifecycle=PASS

IDENTICAL ACROSS RESTART: True
```

State lives in artifacts, not in the server: every read derives from disk and
nothing is cached, which is why a fresh process answers identically.

The idempotency store is in-memory and a restart forgets keys.
`test_a_restarted_server_forgets_idempotency_keys_honestly` asserts that
rather than hiding it — recovery after a restart is by run identity, not by
hoping a key survived.

## plan.preview, health.get, targets.resolve

Implemented. `plan.preview` compiles nodes into #1403 launch contracts and
returns a stable `logical_hash` with `side_effects: []`, asserted to create no
directory and to hash identically for the same input. `health.get` reports API
liveness only and says so in its own payload — a green API health check must
not imply Tau or a seat is reachable.

## Not proven

`run.watch` streaming over the socket is not implemented; `run.events` with a
cursor covers reconnect semantics instead. No live run is submitted *through*
the API, because `run.submit` deliberately refuses rather than becoming a
second scheduler — proof 11's live submit is therefore satisfied through the
CLI path, not the API.

825 passing; 29 new tests.

Commit: f49ac85a5b
