# Source integrity contract

## Research-first admission

The monitor starts from a committed, reviewed target-account registry. It does not probe
arbitrary ATS slugs or enumerate broad boards as its primary strategy. Search engines and
aggregators may locate a candidate primary source, but a result is admitted only after
primary-source readback and a retained source receipt.

## Lane source rules

### Lane A — employment

Prefer the employer career site or employer-configured ATS posting interface. Preserve the
full posting content, employer identity, provider/source identity, stable posting ID when
available, location/workplace/relocation fields, dates, apply URL, content hash, and
limitations.

A public posting interface establishes discovery evidence. It does not establish
candidate-side submission authority.

### Lane B — federal/defense

Use the declared authoritative feed and record exact health/query evidence. A failed feed
must not be replaced with unsourced aggregator results. Federal notices remain
`federal_notice` records with their own fields and are not coerced into job postings.

### Lane C — commercial contract

A commercial candidate is an observed need signal, not a speculative company list. It
requires a primary company, customer, procurement, technical, project, or other approved
source showing a current need. Preserve the observed need, source excerpt/hash, freshness,
proposed service fit, contact-known/unknown state, and unresolved assumptions. Outreach is
a later step.

## Closed result states

```text
MATCHES
NO_MATCHES
FEED_DOWN
AUTH_REQUIRED
AUTH_FAILED
RATE_LIMITED
POLICY_BLOCKED
STALE_DATA
INVALID_REQUEST
INVALID_RESPONSE
NOT_SEARCHED
```

- `NO_MATCHES` requires a successful valid search with zero matching records.
- `FEED_DOWN` requires evidence that the intended feed did not return a usable response.
- `NOT_SEARCHED` means no attempt occurred.
- Authentication, policy, rate-limit, stale-data, request, and response failures remain
  distinct.

## Source receipt

Every attempt records:

- receipt ID, run ID, lane, provider, target account, and source class;
- UTC observation time;
- request method/path and parameter summary with secrets removed;
- response status, content type, response length, gateway/provider headers when useful;
- result state, parser result, retry count, and bounded timeout;
- content hash and retained artifact reference where content exists;
- credential profile/reference, never the secret;
- limitations and non-claims.

A tool success response is not proof. The normalized source artifact and receipt must be
read back before the run advances.

## Normalized opportunity identity

Use provider/employer stable IDs when available. A fallback fingerprint binds normalized
organization, title/need, location, source URL/identity, and source content hash. The same
source record in an unchanged run produces a stable ID. Duplicate detection does not rely
on title similarity alone.

## Network and parser safety

- bounded connect/read/overall timeouts;
- bounded response size and pagination;
- explicit status/content-type validation;
- no unbounded retry or arbitrary URL following;
- no credentials, tokens, personal data, or full sensitive responses in logs;
- HTML/JSON parsed as data, never executed;
- unsupported/drifting forms produce explicit invalid/degraded receipts.
