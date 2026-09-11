---
name: ops-recruiter
description: >
  Turn a recruiter message plus Graham's approved resume/claim context into a
  drafted, humanized reply — webgpt writes, webkimi humanizes — with optional
  brave-search company research as a seed. Claim-bound (never mints facts) and
  human-transmitted only (never sends). Stores correspondence in Memory. Use when
  a recruiter emails or messages about a role and Graham wants a tailored reply
  drafted with comprehensive context. Composed by monitor-opportunities.
triggers:
  - draft recruiter reply
  - respond to recruiter
  - recruiter response
  - reply to this recruiter message
  - ops-recruiter
provides:
  - recruiter-reply-draft
  - recruiter-correspondence-memory
---

# ops-recruiter

## Immutable goal

> Given a recruiter message, the target role, and Graham's approved resume/claim
> context, produce a clear, humanized, claim-bound reply DRAFT — never fabricating
> facts, never sending anything. The human always transmits.

This skill composes existing skills; it does not reimplement browser transport,
LLM routing, or mailbox access.

## Pipeline

```
recruiter message + role text + approved resume/claims
  recall      recruiter_correspondence memory -> prior thread + relationship flag
  (optional)  $brave-search  -> company/role research seed (cited, degradable)
  build       context packet (incl. prior thread) + claim ledger + browser-prompt preflight
  gate        claim-bind check: every factual assertion maps to an approved claim
  draft       $ask webgpt    -> comprehensive first draft
  humanize    $ask webkimi   -> clarity + humanized-prose edit of that draft
  store        $memory /store -> recruiter_correspondence collection
  return       DRAFT to the human. No send. Ever.
```

`run.sh` owns steps `build`, `gate`, and `store`. The `draft`/`humanize` steps
are `$ask` (webgpt then webkimi); `run.sh build` emits the exact preflighted
`$ask` commands so the composition boundary stays in `$ask`.

## Load-bearing contract (this is the skill, not the two model calls)

- **Claim-bound, never fact-minting.** The fact ledger is the approved
  `career_profile` claim snapshot or `RESUME.md`. webgpt/webkimi may reword,
  order, tighten, and choose emphasis; they may not invent employers, titles,
  dates, metrics, clearances, or a capability claim the ledger does not back.
  `gate` fails closed if the draft asserts a fact absent from the ledger.
- **Relationship-aware, never re-introduces.** `build` recalls prior
  `recruiter_correspondence` for the recruiter/thread and sets a relationship
  flag (`existing`/`new`/`unknown`). An existing thread must not be written as
  first contact; if recall is unavailable the opening stays relationship-neutral
  rather than falsely claiming first contact.
- **Human-transmitted only.** Draft-and-return. No email send, no LinkedIn
  action. Mirrors monitor-opportunities `who transmits = the human`.
- **`$brave-search` is a seed, not authority.** Company/role context only, cited,
  and honestly degradable to "no research" without failing the draft.

## Correspondence memory

Recruiter threads persist in the `recruiter_correspondence` Memory collection via
`$memory` `/store` (never raw AQL, never inline vector arrays). One document per
message with deterministic `_key` (`<source>:<thread-id>:<message-id>`), fields:
`direction` (`inbound`/`draft`/`sent`), `source` (`gmail`/`linkedin`/`manual`),
`recruiter`, `company`, `role`, `body`, `role_ref`, `claim_keys[]`, `draft_ref`,
`received_at`, `tags`. Recall with `$memory recall --collections recruiter_correspondence`.

## Ingestion boundaries (read before wiring any source)

- **Email → `/gmail`, NOT `$ops-google`.** `$ops-google` is the Gemini API
  budget skill and has nothing to do with mailbox access. Graham's
  `graham@grahama.co` inbox is reached only through the `/gmail` capability (the
  same one `mailbox-mining` delegates to). ops-recruiter consumes gmail messages
  that `/gmail` has already fetched; it does not talk to Gmail directly.
- **LinkedIn is read-only and human-driven.** `linkedin_automation` is
  `PERMANENTLY_FORBIDDEN` across monitor-opportunities and ops-linkedin. Do NOT
  use `$surf` to scrape LinkedIn messages. The only compliant path is a
  read-only capture of Graham's own session, human-initiated, after explicit
  account-risk acknowledgement, via `$ops-linkedin` — pasted/exported/screenshot
  correspondence is ingested as local evidence, then the workflow leaves the
  platform. No connecting, messaging, posting, or bulk capture.

## Commands

```bash
./run.sh status --json
./run.sh build --recruiter-message MSG.md --role ROLE.md --resume RESUME.md \
  [--recruiter R --thread-id T] [--research] [--out DIR]  # recalls prior thread; packet + $ask commands
./run.sh gate --draft DRAFT.md --claims CLAIMS.json # fail-closed claim-bind check
./run.sh store --message MSG.json                   # write one correspondence doc to Memory
./sanity.sh
```

## Compliance

- `$best-practices-skills`: this frontmatter, progressive disclosure (pipeline
  detail in `references/pipeline.md`), `sanity.sh`, retained `$agentic-evals`
  fixture asserting the claim-bind gate rejects an unbacked assertion.
- `$best-practices-readme`: README voice, with an explicit non-claims section:
  ops-recruiter does not send email, does not touch LinkedIn, and does not mint facts.

## Related skills

- `$ask` (webgpt draft, webkimi humanize) — composition transport.
- `$memory` — recruiter_correspondence collection.
- `$brave-search` — optional research seed.
- `/gmail` — email ingestion. `$ops-linkedin` — read-only LinkedIn evidence.
- `$monitor-opportunities` — composes this skill into the morning report.

## References

- `references/pipeline.md` — packet format, claim ledger, and the exact ask chain.
