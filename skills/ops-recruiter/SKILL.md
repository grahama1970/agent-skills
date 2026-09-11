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
  research    $brave-search  -> company/role AND recruiter (LinkedIn page + history) seed (cited, degradable)
  build       context packet (incl. prior thread) + claim ledger + browser-prompt preflight
  gate        claim-bind check: every factual assertion maps to an approved claim
  draft       $ask webgpt    -> comprehensive first draft
  humanize    $ask webkimi   -> clarity + humanized-prose edit of that draft
  T0 gate     run.sh gate    -> deterministic token floor (fail-closed)
  T1 review   PROJECT AGENT  -> semantic claim-bind verdict vs ledger
                on FAIL: structured findings -> webgpt redraft -> webkimi -> T0 -> T1
                (<=3 rounds, each carrying a specific correction; else fail closed to human)
  store        $memory /store -> recruiter_correspondence collection
  return       DRAFT to the human. No send. Ever.
```

`run.sh` owns steps `build`, `gate`, and `store`. The `draft`/`humanize` steps
are `$ask` (webgpt then webkimi); `run.sh build` emits the exact preflighted
`$ask` commands so the composition boundary stays in `$ask`.

## Load-bearing contract (this is the skill, not the two model calls)

- **Claim-bound, never fact-minting — two-tier, independently reviewed.** The
  fact ledger is the approved `career_profile` claim snapshot or `RESUME.md`.
  webgpt/webkimi may reword, order, tighten, and choose emphasis; they may not
  invent employers, titles, dates, metrics, clearances, or a capability claim the
  ledger does not back. Two gates, in order:
  - **T0 deterministic (`run.sh gate`)** — numeric/fact-token floor; fails closed
    on any metric/date absent from the ledger. Cheap, automated, in the e2e.
  - **T1 semantic claim-bind — the PROJECT AGENT is the reviewer of record.** The
    creator (webgpt) and humanizer (webkimi) never certify their own draft. The
    project agent reads the produced draft against the ledger and issues a
    per-claim verdict (each factual sentence traces to a claim, or the draft is
    rejected), fail-closed, before the draft is handed to the human to send. This
    is the same boundary as everywhere else: a model seat's PASS is only
    evidence; the project agent verifies against local evidence before acceptance.
  A self-certifying model seat is not a substitute for the project-agent review.
- **Bounded course-correction loop on T1 FAIL.** If the project-agent review
  rejects a claim as unsupported, it does not stop and it does not blindly
  retry. It emits a structured finding (offending sentence, the unsupported
  claim, and what the ledger actually supports) and feeds that exact correction
  back to webgpt (redraft) -> webkimi (rehumanize) -> T0 -> T1 again. A retry
  that does not carry a specific correction is spray-and-pray and is forbidden.
  Cap at 3 rounds; on exhaustion, fail closed and hand the draft plus surviving
  findings to the human. Never send, never loop unbounded.
- **Relationship-aware, never re-introduces.** `build` recalls prior
  `recruiter_correspondence` for the recruiter/thread and sets a relationship
  flag (`existing`/`new`/`unknown`). An existing thread must not be written as
  first contact; if recall is unavailable the opening stays relationship-neutral
  rather than falsely claiming first contact.
- **Human-transmitted only.** Draft-and-return. No email send, no LinkedIn
  action. Mirrors monitor-opportunities `who transmits = the human`.
- **`$brave-search` is a seed, not authority.** Covers both company/role context
  and recruiter deep-research (their LinkedIn page and background/history) so the
  reply is informed by who is actually reaching out. Cited, and honestly
  degradable to "no research" without failing the draft.

## Correspondence memory

ALL correspondence with a recruiter or hiring contact — every channel, no
exceptions — persists in the single `recruiter_correspondence` Memory collection
via `$memory` `/store` (never raw AQL, never inline vector arrays). `source` is an
OPEN vocabulary: known values below, but the store never rejects a new channel,
so email, LinkedIn, call/interview transcripts, SMS, referral intros, ATS
messages, and manual notes all land on the same thread. One document per
message with deterministic `_key` (`<source>:<thread-id>:<message-id>`), fields:
`direction` (`inbound`/`draft`/`sent`/`meeting`), `source`
(`gmail`/`linkedin`/`manual`/`google-meet`/`live-evidence`), `recruiter`,
`company`, `role`, `body`, `role_ref`, `claim_keys[]`, `draft_ref`,
`received_at`, `tags`. A call/interview transcript is stored as
`direction=meeting` on the same thread. Thread continuity fetches this thread
exactly via Memory `/list` filters; cross-thread semantic `$memory recall`
lights up once the memory repo registers `recruiter_correspondence` in
`builtin_sources()` (memory-repo change; ops-recruiter must not wire views or AQL).

## Ingestion boundaries (read before wiring any source)

- **Email → `/gmail`, NOT `$ops-google`.** `$ops-google` is the Gemini API
  budget skill and has nothing to do with mailbox access. Graham's
  `graham@grahama.co` inbox is reached only through the `/gmail` capability (the
  same one `mailbox-mining` delegates to). ops-recruiter consumes gmail messages
  that `/gmail` has already fetched; it does not talk to Gmail directly.
- **Meeting/call transcripts → `$ops-google-meet` / `$live-evidence`.**
  ops-recruiter does not record or transcribe. It consumes transcripts those
  skills already produced (Google Meet prep/companion and the live interview
  copilot) and stores them on the recruiter thread as `direction=meeting`,
  `source=google-meet` or `live-evidence`, so a call becomes part of the same
  thread history and future context.
- **LinkedIn research is delegated to `$ops-linkedin`.** ops-recruiter does not
  drive LinkedIn itself. `$ops-linkedin` (lead-gen lane) owns the authorized
  read-only recruiter/company-page research — a `$surf` headed tab in Graham's
  own session, human-supervised, after `--accept-account-risk`. Engagement
  (connecting, messaging/InMail, posting, commenting, background automation,
  bulk scraping) stays forbidden there. Login-free recruiter/company research
  still prefers `$brave-search`. ops-recruiter consumes the captured evidence
  into `recruiter_correspondence`.

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
