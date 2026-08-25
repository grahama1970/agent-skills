# ops-linkedin project knowledge

Last reviewed: 2026-08-24

## Immutable goal

Provide useful LinkedIn profile/content/outreach preparation while preventing the agent
from acting on LinkedIn broadly. Outbound operations end in a local draft and a
human-execution handoff with honest proof limits. Graham's own profile is handled by a
source-derived editable JSON entry and a bounded Surf sync plan. Named opportunity
contacts may use a bounded read-only contact graph capture plan for relationship degree
and visible mutual-contact evidence after explicit authorization.

## Current readiness

Overall: **READY_FOR_DRAFT_PROFILE_SYNC_AND_CONTACT_GRAPH_PLANNING**

| Feature | State | Evidence |
|---|---|---|
| Typed request validation | READY | Pydantic v2 models and tests |
| Evidence-aware packet generation | READY | `prepare` emits `ops-linkedin.handoff.v1` |
| Block unsupported profile/lead claims | READY | deterministic readiness gate and exit code `3` |
| Packet schema validation | READY | `validate` command |
| Human completion attestation | READY | explicit confirmation flag; `platform_verified=false` |
| Editable own-profile JSON | READY | `profile-entry-export` emits `ops-linkedin.profile_entry.v1` from `RESUME.md` |
| Own-profile Surf sync plan | READY | `profile-sync-plan` emits `ops-linkedin.profile_sync.v1` with `external_effects=false` |
| Named contact graph capture plan | READY | `contact-graph-capture-plan` emits `ops-linkedin.contact_graph_capture_plan.v1` with `NOT_EXECUTED` |
| Browser/session automation outside bounded plans | PROHIBITED | immutable boundary and static sanity gate |
| Live LinkedIn execution receipt | NOT_ESTABLISHED | plan exists; Surf mutation execution is not yet implemented |
| Official LinkedIn API adapter | NOT_IMPLEMENTED | authorization and separate review required |

## Implemented artifacts

- Agent-facing `SKILL.md` with progressive disclosure and routing.
- Human-facing `README.md`.
- Typer CLI with `policy`, `status`, `prepare`, `validate`, and `attest`.
- Pydantic request, claim, handoff, status, and policy contracts.
- Pydantic editable profile-entry and profile-sync plan contracts.
- Pydantic contact-graph capture plan contract for named opportunity contacts.
- Pure service functions with no network/browser dependencies.
- Unit tests, non-mocked sanity checks, and an agentic-evals fixture.
- Dated LinkedIn policy and upstream adaptation reference.

## Deliberately excluded

- Chrome extensions or browser plug-ins.
- WebSocket/DOM bridges.
- Selenium, Playwright, browser-use, Surf, or equivalent LinkedIn control except the
  explicit Graham-owned profile sync plan and the explicit named-contact graph capture
  plan.
- Login/session/cookie inspection.
- Bulk scraping or systematic unrelated profile/post viewing.
- Automated posting, comments, likes, connections, follows, message/InMail sending,
  applications, or uploads.
- Behavior simulation, randomized delays, rate-limit evasion, selector maintenance, or
  anti-detection logic.
- Bulk prospect collection or outreach sequencing.

These are exclusions, not missing MVP features.

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

Status: **PARTIALLY_ESTABLISHED**

The current integration consumes the public `RESUME.md` presentation and emits an editable
`ops-linkedin.profile_entry.v1` JSON file for project-agent editing. A future integration
should consume the deeper canonical `career_profile` claim ledger and emit synchronized
resume, LinkedIn, memory, and application variants while preserving claim IDs, source
references, sensitivity, active-version precedence, and purpose-specific field rules.

## Known risks

- LinkedIn terms can change after the dated policy snapshot.
- A user may manually execute stale copy after the evidence changes.
- Human attestation can be mistaken for independent platform proof unless downstream
  consumers preserve the receipt semantics.
- Public-web research can still collect unnecessary personal data if purpose limits are
  ignored.
- An agent could try to convert read-only contact graph capture into connection or send
  automation; SKILL.md explicitly forbids that route.

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

`fixtures/agentic_eval.json` covers positive, negative, and adversarial lifecycle cases,
including editable profile-entry export, own-profile sync planning, and named-contact
graph capture planning.
It does not and must not claim live LinkedIn mutation, send, connection, or mutual-contact
proof.

Latest local receipts on 2026-08-24:

- `bash skills/ops-linkedin/sanity.sh`: `Result: PASS`.
- `bash skills/agentic-evals/run.sh run skills/ops-linkedin/fixtures/agentic_eval.json`:
  `readiness=READY`, 9 cases, 27 trials, mocked=false, live=true for local CLI paths.


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
