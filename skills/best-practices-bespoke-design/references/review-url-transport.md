# Review URL Transport Contract

This reference defines the provider-neutral evidence contract for subjective
bespoke-design review. Project adapters such as `monitor-website`, Ask, or Surf
own browser automation. This skill owns the schema, states, thresholds, and proof
rules.

## Vocabulary

- `candidate_fingerprint`: deterministic SHA-256 over the review bundle inputs
  and canonical renders. It proves identity and integrity; it is never a secret,
  password, bearer token, or access credential.
- `access_nonce`: high-entropy capability token used only to address a temporary
  review URL. It reduces accidental discovery but is not authentication.
- `canonical_render`: frozen screenshot or equivalent pixel artifact whose path
  and digest are recorded in the bundle.
- `live_review_surface`: optional interactive rendering of the exact candidate.
  It helps reviewers inspect motion, focus, disclosures, and responsive behavior;
  it does not replace canonical renders.

## Delivery Order

```text
verified immutable review URL
→ direct canonical artifact or attachment fallback
→ BLOCKED with evidence, never improvised retry loops
```

Local deterministic checks and a current review bundle must exist before any
external reviewer call. Transport preflight proves only reachability and canary
visibility. It never consumes a rater seat.

## Bundle Rules

Use `schemas/bespoke-review-bundle.schema.json`.

- Include source state, candidate inputs, review units, viewport/state,
  canonical-render path and digest, blind-mode state, public-safety
  classification, delivery mode, and `does_not_prove` boundaries.
- Store only redacted review URLs, URL hashes, and nonce hashes in durable
  artifacts. Plain nonces belong only in ephemeral runtime state.
- Rotating only `access_nonce` must not change `candidate_fingerprint`.
- Changing source, canonical render, visible unit, prompt protocol, or candidate
  input invalidates the affected evidence.
- Public capability URLs require `public_safe`, `noindex`, expiry, cleanup, and
  no sensitive material. Private-client, credentialed, regulated, confidential,
  or ITAR material must use approved authentication or remain unpublished.

## Transport Rules

Use `schemas/bespoke-review-transport.schema.json`.

State families remain separate:

```text
transport: PASS | BLOCKED
inspection: PROVEN | NOT_PROVEN
rater: USABLE | UNUSABLE | NOT_RUN
```

A rater is countable only when the receipt proves all of these:

- expected candidate fingerprint was observed;
- expected unit IDs were observed;
- canonical render loaded or was directly provided;
- prompt, raw output, parsed output, and ordering are preserved;
- parsed answer echoes the expected fingerprint and unit set;
- no stale tab, provider page text, rate limit, login page, or unrelated context
  contaminated the answer.

A URL, attachment, rate-limit, stale-tab, or provider-context failure is
`reviewer_transport: BLOCKED`; it never changes the design gate. Existing
attachment receipts remain valid only when they satisfy the same fingerprint,
unit, canonical-render, raw-output, and redaction contract.

## Formal Threshold Stopping

For fixed thresholds such as four usable yes votes out of five seats:

- stop `PASS` once four qualifying yes votes exist;
- stop `FAIL` once two disqualifying votes make four yes votes impossible;
- otherwise continue to the registered cap.

The stopping rule must be proven equivalent to evaluating all registered seats;
see `scripts/prove_sequential_threshold.py`.
