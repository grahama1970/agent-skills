---
name: ops-linkedin
description: >
  Prepare evidence-bounded LinkedIn profile updates, posts, image-post captions,
  comments, connection notes, messages, manual search plans, lead-research plans,
  and content reviews as local drafts with typed human-execution handoff packets.
  Use when a user says "update my LinkedIn", "draft a LinkedIn post", "write a
  connection note", "plan LinkedIn outreach", "review my LinkedIn content", or
  otherwise asks for LinkedIn operations. This skill does not automate LinkedIn.
triggers:
  - linkedin
  - update my linkedin
  - linkedin profile
  - draft a linkedin post
  - linkedin content
  - linkedin comment
  - linkedin connection note
  - linkedin message
  - linkedin search plan
  - linkedin lead generation
  - linkedin outreach plan
  - review linkedin content
license: MIT
runtime_self_improvement: none
metadata:
  short-description: Draft-only LinkedIn operations with manual handoff receipts
  version: "0.1.0"
  policy-snapshot: "2026-08-02"
provides:
  - linkedin-content-drafting
  - linkedin-manual-handoff
  - linkedin-profile-governance
composes:
  - memory
  - brave-search
  - dogpile
  - task-monitor
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
taxonomy:
  - compliance
  - privacy
  - validation
  - human-in-the-loop
  - professional-networking
---

# LinkedIn Operations

> Staging note: this copy lives under `incoming/ops-linkedin`. Treat it as reviewable candidate code, not an activated repository capability, until a promotion PR moves it under `skills/` and registers its `provides` entries.

Prepare LinkedIn work locally, validate factual claims, and hand the final action to a
human. The skill deliberately stops before LinkedIn access or submission.

## Immutable boundary

The skill MUST NOT:

- open, drive, inspect, or modify LinkedIn through a browser, extension, DOM bridge,
  WebSocket bridge, browser-control skill, or headless browser;
- inspect cookies, passwords, session tokens, local storage, or login state;
- scrape profiles, posts, contacts, search results, comments, or company pages;
- automatically post, like, comment, connect, follow, message, apply, or upload;
- perform bulk engagement, outreach sequences, rate-limit evasion, or anti-bot evasion;
- report `PREPARED` work as executed, delivered, published, or platform-verified.

An official LinkedIn API adapter is outside this MVP. Add one only after documented
LinkedIn authorization, a separate security/policy review, and new live receipts.

Read `references/linkedin-policy.md` before proposing any expansion of this boundary.

## Capability lanes

| Lane | Supported preparation | Human-only finish |
|---|---|---|
| `profile` | Evidence-bounded headline, About, Experience, Skills, Featured, or profile-field draft | Open the profile, edit, review visibility, save |
| `explore` | Manual search query and review plan | Run the search and inspect results |
| `publish` | Text post or image-post caption and attachment checklist | Create, preview, and publish the post |
| `interact` | Comment, connection note, or one-to-one message draft | Confirm context and submit one action |
| `lead-gen` | Public-web research plan and individually reviewed prospect criteria | Inspect selected profiles and decide on outreach |
| `content-ops` | Analysis of user-provided/exported posts and metrics | Make any edits or follow-up actions |

The upstream `linkedin-skills` project inspired these lanes, but its browser bridge and
social-action automation are intentionally not copied. See `references/linkedin-policy.md`.

## Mandatory workflow

1. **Classify the lane and action.** Use only the action vocabulary in
   `references/contracts.md`.
2. **Gather evidence outside LinkedIn.**
   - Use `/memory` for the user's canonical resume, profile state, prior approved copy,
     and earlier handoff receipts.
   - Use `/brave-search` or `/dogpile` for current public facts. Do not ask those skills
     to scrape LinkedIn or bypass access controls.
   - Treat user-provided LinkedIn exports, pasted text, screenshots, and metrics as input
     artifacts; label their capture date.
3. **Build a request manifest.** Every factual claim that is labeled `verified` needs at
   least one source reference. Use `assets/examples/` as shape examples.
4. **Prepare the packet.**

   ```bash
   bash ./incoming/ops-linkedin/run.sh prepare request.json --output handoff.json
   ```

5. **Inspect readiness.**
   - `READY_FOR_HUMAN_REVIEW` means the packet may be reviewed and manually executed.
   - `BLOCKED_UNVERIFIED_CLAIMS` means stop. Add evidence, soften the copy, or mark the
     unsupported claim `excluded`; do not bypass the gate.
6. **Give the human the draft and manual steps.** Do not call `/surf`, browser control,
   or any hidden LinkedIn transport.
7. **Record completion only after an explicit user statement.** When the user says they
   personally completed the action, the agent may run:

   ```bash
   bash ./incoming/ops-linkedin/run.sh attest handoff.json \
     --actor "<human name>" \
     --confirm-human-completed \
     --output completion.json
   ```

   The resulting proof is `USER_ATTESTED_MANUAL_ACTION` and remains
   `platform_verified: false`.

For multi-item work, use `/task-monitor` to track each packet separately. Never collapse
several recipients or posts into one ambiguous receipt.

## CLI

```bash
# Dated policy snapshot and current implementation state
bash ./incoming/ops-linkedin/run.sh policy
bash ./incoming/ops-linkedin/run.sh status

# Prepare and validate a local packet
bash ./incoming/ops-linkedin/run.sh prepare request.json -o handoff.json
bash ./incoming/ops-linkedin/run.sh validate handoff.json

# Record explicit human completion; this is not platform verification
bash ./incoming/ops-linkedin/run.sh attest handoff.json \
  --actor "Graham" \
  --confirm-human-completed \
  -o completion.json

# Deterministic local checks
bash ./incoming/ops-linkedin/sanity.sh
```

`prepare` exits `3` when it writes a blocked packet. `--allow-blocked` may be used only by
a review pipeline that needs the blocked artifact; it does not make the packet executable.

## Claim discipline

- Do not infer evidence from confident wording.
- Do not label a claim `verified` without a source reference.
- `profile-update` and `lead-research-plan` require at least one verified claim.
- Any `needs-source` claim blocks the packet.
- Quantitative, credential, employer, clearance, customer, funding, scale, performance,
  and deployment claims should point to concrete local or public evidence.
- If evidence is unavailable, soften or remove the claim rather than inventing support.

The CLI intentionally does not extract claims from free-form text. The agent or human must
supply the explicit claim ledger so the review boundary remains inspectable.

## Receipt semantics

| Field | Meaning |
|---|---|
| `status: PREPARED` | Local draft and manual steps exist; nothing was done on LinkedIn |
| `readiness: READY_FOR_HUMAN_REVIEW` | Evidence gate passed for human review |
| `readiness: BLOCKED_UNVERIFIED_CLAIMS` | Do not execute the draft |
| `execution_claim: NOT_EXECUTED` | No action was claimed |
| `execution_claim: USER_ATTESTED_MANUAL_ACTION` | A named human said they performed it |
| `platform_verified: false` | The skill has no independent LinkedIn proof |

Never rewrite these semantics in prose as stronger proof.

## Data handling

- Keep request and handoff JSON at a caller-selected local path.
- Do not store passwords, cookies, session artifacts, or copied contact databases.
- Do not commit real private messages, recipient lists, or private exports.
- Use `/memory` only when the user requests durable recall and apply the appropriate
  purpose/sensitivity scope.
- For public prospect research, store source URLs and capture dates; avoid sensitive
  personal data that is not necessary for the stated purpose.

## Progressive disclosure

Read only what the task needs:

- `references/contracts.md` — request, packet, status, and failure contracts.
- `references/linkedin-policy.md` — policy rationale, official sources, and upstream
  adaptation notes.
- `PROJECT_KNOWLEDGE.md` — implemented, excluded, aspirational, and verification state.
- `README.md` — human-oriented setup and examples.

## Evaluation posture

`fixtures/agentic_eval.json` exercises the real local CLI for positive, negative, and
adversarial cases. It proves request validation, fail-closed evidence gating, and bounded
attestation. It does not prove any live LinkedIn action.
