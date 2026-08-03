# Morning report contract

## Purpose

The morning report is the product boundary for `monitor-opportunities`. A completed run
has one versioned JSON manifest and one human entry point rendered from that manifest.
HTML, a TUI, or a local service is a view; none is an independent ledger.

Schema: `monitor_opportunities.report.v1`.

## Required top-level evidence

Every report binds:

- `run_id`, UTC generation time, contract version, immutable-goal text/hash, and stage;
- operational readiness and capability-specific authority;
- coverage and result state for lanes A, B, and C;
- source receipts and their limitations;
- eligibility rejections that matter to the user, including relocation rejection;
- at most eight shortlisted opportunities;
- claim-bound resume variants and presentation-only diffs;
- verbatim Gmail/LinkedIn text and effect readiness;
- ATS application state and all `human_required` fields;
- claim/source-bound interview preparation;
- available human decisions;
- artifact visibility accounting;
- explicit non-claims.

## Visibility invariant

An item is action-worthy when a human can keep, reject, defer, accept, amend, authorize,
withhold, transmit, reconcile, or otherwise decide something about it. Every action-worthy
artifact must include:

```json
{
  "action_worthy": true,
  "visible_in_report": true
}
```

The manifest also records:

```json
{
  "artifact_accounting": {
    "action_worthy_total": 9,
    "visible_total": 9,
    "hidden_total": 0,
    "hidden_ids": []
  }
}
```

Runtime validation must calculate, not trust, these totals. A mismatch or nonzero hidden
count fails report admission. A mailbox draft, resume variant, application plan, source
failure, or pending decision that exists only in an internal directory or queue is a
defect.

## Lane coverage

Each enabled run reports A, B, and C independently. Co-equal means honest coverage, not
equal result counts. A lane record states whether it was searched, the closed result
status, observed/admitted counts, source receipt IDs, and limitations.

Required distinctions:

- `MATCHES`: the lane was searched and source-backed candidates were observed;
- `NO_MATCHES`: the lane was successfully searched and no candidates matched;
- `FEED_DOWN`: the intended authoritative feed could not produce a valid response;
- `AUTH_REQUIRED` / `AUTH_FAILED`: credentials were absent or rejected;
- `RATE_LIMITED`, `POLICY_BLOCKED`, `STALE_DATA`, `INVALID_REQUEST`,
  `INVALID_RESPONSE`: specific degraded results;
- `NOT_SEARCHED`: no attempt was made.

A failed or unsearched lane must never be rendered as zero opportunities.

## Opportunity card

A shortlisted card includes:

- stable opportunity ID and lane-specific type;
- title/need and organization;
- normalized location/workplace/relocation result;
- source receipt links;
- eligibility result;
- deterministic fit score and components when available;
- why the candidate fits, bound to claim keys;
- screening-interface profile with observed, inferred, unknown, and confidence fields;
- freshness, duplicate/application state, blockers, and non-claims;
- the decisions valid for that item.

Rejected items do not appear in the shortlist. User-relevant hard rejections, especially
relocation, appear in a separate rejection section with source evidence and reason code.

## Resume section

Each variant includes the exact claim snapshot digest, claim keys, output artifact
references, and a semantic diff. The diff separates allowed presentation changes from
prohibited factual changes. A variant with a prohibited factual delta cannot enter the
report as accepted or usable.

A proposed claim amendment is a separate human-review object. It never edits the approved
claim snapshot in place.

## Outreach section

Stage 0 outreach is local text only and is labeled `WOULD_PRESENT_STAGE0`. Gmail and
LinkedIn packets show verbatim body text, subject when applicable, character count, claim
keys, source/opportunity references, roundtable state, candidate send steps, and:

```json
{
  "sendable": false,
  "candidate_transmits": true
}
```

A later Gmail mailbox draft is still not a send. LinkedIn never has a platform-effect
state in this project.

## ATS application section

The report separates form inspection, prefill, authorization, and submit state. In Stage
0 every application is `BLOCKED_STAGE_0` and `authorized: false`.

Each field records label/name, type, required state, disposition, and answer provenance.
Every free-text, self-identification, clearance, work-authorization, salary, legal,
background/criminal, or ambiguous field is `human_required`. The report must not hide
unresolved required fields behind a generic “ready” state.

Future authorization binds one exact application-plan digest. It is not a reusable global
approval.

## Decision actions

The Stage 0 manifest may expose:

- `KEEP`, `REJECT`, `DEFER`;
- `ACCEPT_RESUME_VARIANT`, `PROPOSE_CLAIM_AMENDMENT`;
- `WITHHOLD_APPLICATION`, `AUTHORIZE_APPLICATION_PAYLOAD`.

At Stage 0 these actions record intent or review only; `effects_external` is false. Human
send attestations and effect commits are separate append-only events introduced by later
capability tickets.

## Rendering rules

- The JSON manifest is preserved byte-for-byte or as a documented canonical
  normalization alongside the view.
- All text is escaped. No source content is interpreted as executable HTML.
- Default HTML uses no remote scripts, fonts, analytics, trackers, images, or network
  assets.
- `FEED_DOWN`, `NO_MATCHES`, `NOT_SEARCHED`, `human_required`, hard rejection, and
  `BLOCKED_STAGE_0` are visually distinct.
- Empty-night reports remain complete and interactive for source/coverage review.
- Views state exact non-claims; they do not infer readiness from missing evidence.

## Expected fixture

`fixtures/reports/stage0_mixed_lanes.json` is the first product fixture. It contains an
eligible WNY employment opportunity, a sourced commercial need, a relocation rejection,
a degraded federal feed, claim-bound variants, local non-sendable outreach, a blocked ATS
application with a free-text field, interview preparation, decisions, and zero hidden
artifacts.
