# ops-linkedin project knowledge

Last reviewed: 2026-08-02

## Immutable goal

Provide useful LinkedIn opportunity discovery plus profile/content/outreach preparation
while preventing the agent from acting on LinkedIn through unauthorized automation.
Opportunity discovery may capture one human-authorized, already-open Jobs/opportunity tab
as read-only local evidence. Every outbound/action operation must end in a local draft and
a human-execution handoff with honest proof limits.

## Current readiness

Overall: **READY_FOR_DRAFT_ONLY_USE**

| Feature | State | Evidence |
|---|---|---|
| Typed request validation | READY | Pydantic v2 models and tests |
| Authorized opportunity capture | READY | `capture-opportunity-tab` emits `ops-linkedin.opportunity_capture.v1` |
| Evidence-aware packet generation | READY | `prepare` emits `ops-linkedin.handoff.v1` |
| Block unsupported profile/lead claims | READY | deterministic readiness gate and exit code `3` |
| Packet schema validation | READY | `validate` command |
| Human completion attestation | READY | explicit confirmation flag; `platform_verified=false` |
| Browser/session action automation | PROHIBITED | immutable boundary and static sanity gate |
| Live LinkedIn execution | NOT_ESTABLISHED | deliberately outside scope |
| Official LinkedIn API adapter | NOT_IMPLEMENTED | authorization and separate review required |

## Implemented artifacts

- Agent-facing `SKILL.md` with progressive disclosure and routing.
- Human-facing `README.md`.
- Typer CLI with `policy`, `status`, `prepare`, `validate`, and `attest`.
- Read-only `capture-opportunity-tab` command for one human-authorized LinkedIn tab.
- Pydantic request, claim, handoff, status, and policy contracts.
- Pure service functions with no network/browser dependencies.
- Unit tests, non-mocked sanity checks, and an agentic-evals fixture.
- Dated LinkedIn policy and upstream adaptation reference.

## Deliberately excluded

- Chrome extensions or browser plug-ins.
- WebSocket/DOM bridges.
- Hidden or broad Selenium, Playwright, browser-use, Surf, or equivalent LinkedIn control.
- Login/session/cookie inspection.
- Scraping or systematic profile/post viewing.
- Automated posting, comments, likes, connections, follows, messages, applications, or
  uploads.
- Behavior simulation, randomized delays, rate-limit evasion, selector maintenance, or
  anti-detection logic.
- Bulk prospect collection or outreach sequencing.

These are exclusions, not missing MVP features. Authorized read-only opportunity capture is
the narrow exception because finding relevant LinkedIn opportunities is part of the
product goal; it is not permission to apply, connect, message, post, or collect profiles.

## Aspirational work with hard prerequisites

### Authorized official API adapter

Status: **NOT_IMPLEMENTED**

Prerequisites:

1. Written evidence that the intended LinkedIn product/API and operations are authorized.
2. Exact scopes, data retention, deletion, and member-consent contract.
3. Separate adapter package with httpx timeouts, typed boundary validation, credential
   isolation, and test/live receipts.
4. Security and policy review before adding the adapter to `composes` or claiming support.
5. Negative tests proving unsupported social actions remain unavailable.

### Profile-system propagation

Status: **NOT_ESTABLISHED**

A future integration may consume one canonical career-profile schema and emit synchronized
resume, LinkedIn, memory, and application variants. It must preserve claim IDs, source
references, sensitivity, active-version precedence, and purpose-specific field rules. The
current skill accepts manifests but does not define that wider canonical schema.

## Known risks

- LinkedIn terms can change after the dated policy snapshot.
- A user may manually execute stale copy after the evidence changes.
- Human attestation can be mistaken for independent platform proof unless downstream
  consumers preserve the receipt semantics.
- Public-web research can still collect unnecessary personal data if purpose limits are
  ignored.
- An agent could try to bypass the skill by delegating to a browser-control tool; SKILL.md
  explicitly forbids that route.

## Verification

```bash
bash ./skills/ops-linkedin/sanity.sh

OPS_LINKEDIN_USE_SYSTEM_PYTHON=1 \
  bash ./skills/ops-linkedin/run.sh prepare \
  ./skills/ops-linkedin/assets/examples/publish-post.json \
  -o /tmp/ops-linkedin-packet.json

OPS_LINKEDIN_USE_SYSTEM_PYTHON=1 \
  bash ./skills/ops-linkedin/run.sh validate /tmp/ops-linkedin-packet.json
```

`fixtures/agentic_eval.json` covers positive, negative, and adversarial lifecycle cases.
It does not and must not claim live LinkedIn proof.


## Outbound roundtable gate + claim binding (2026-08-02)

Two integration gaps were closed while the skill was still staged under `incoming/`.

1. **No roundtable gate.** `grep -rn roundtable` returned nothing. The `interact` lane
   prepared connection notes and one-to-one messages gated on evidence only, which would
   have allowed outbound contact without the panel the operator mandated for every
   outbound message. Added `RoundtableReview` with `OUTBOUND_ACTIONS` and the
   `BLOCKED_MISSING_ROUNDTABLE` readiness state.
2. **Two claim vocabularies.** Nothing bound the claim ledger to `career_profile` claim
   keys, while `grahamaco.inmail_draft.v1` already used `claims_referenced[].claim_key`.
   `Claim.claim_key` is now required for `verified` claims.

Verification: 23 tests pass (15 original + 8 new gate tests), `sanity.sh` PASS. The 6
pre-existing tests that failed on first run did so because their fixtures predated the
contract; they were upgraded to the production shape, which is the contract working
rather than a regression.

Still not established: any live LinkedIn action, and the exec-bit loss from ZIP staging
(now fixed with mode 100755).
