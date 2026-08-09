---
name: mailbox-mining
description: >
  Mine a mailbox into the typed contact graph under an enforced export-control and
  PII redaction contract, and gate outbound career mail behind a mandatory /ask
  roundtable. Mailbox access is delegated entirely to /gmail; this skill adds only
  what /gmail does not own — what may enter a searchable knowledge graph, and what
  must happen before a message is sent. Use when an agent needs warm contacts from
  email, referral paths, reply outcomes for tracked outreach, or validation of an
  outbound draft before it is prepared.
allowed-tools:
  - Bash
  - Read
  - Write
triggers:
  - mine my inbox
  - mine contacts from email
  - warm contacts from gmail
  - who have I emailed
  - did they reply
  - check my mail for replies
  - build the contact graph from email
  - redact mail before storing
  - validate an outbound draft
  - mailbox mining
metadata:
  short-description: Mailbox to contact-graph mining with redaction and an outbound roundtable gate
  author: Graham
  version: "0.2.0"
runtime_self_improvement: basic

provides:
  - warm-contact-extraction
  - mailbox-mining
  - outbound-draft-gate
composes:
  - gmail
  - memory
  - task-monitor
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-arangodb
  - best-practices-roundtable
taxonomy:
  - operations
  - privacy
  - corruption
  - precision
  - composition
disciplines:
  - data-engineering
  - compliance-security
  - research-retrieval
domains:
  - marketing
---

# mailbox-mining

**This skill does not talk to Gmail.** `/gmail` owns mailbox access: OAuth profiles,
the REST API, two-phase plan/commit writes, approval codes, exactly-once receipts,
and reconciliation of indeterminate states. Verified 2026-08-02 at commit
`53add58fd` — 23 tests pass, `sanity.sh` PASS.

This skill owns the two concerns `/gmail` deliberately does not:

| Concern | Owner |
|---|---|
| Reading, searching, drafting, sending, labelling mail | **`/gmail`** |
| OAuth, scopes, tokens, plan/commit, receipts | **`/gmail`** |
| What mail-derived content may enter a searchable knowledge graph | **this skill** |
| Turning correspondence into typed contact records | **this skill** |
| The mandatory roundtable gate before outbound career mail | **this skill** |

## Why the split matters

`/gmail`'s receipts correctly exclude MIME bodies, attachment bytes, and tokens. But
nothing in `/gmail` stops an agent running `search --hydrate full` and then writing a
message body straight into ArangoDB, where it becomes permanently searchable. `/gmail`
governs *mail operations*; this skill governs *what crosses into memory*. Those are
different failure modes and they need different gates.

## The redaction contract (NON-NEGOTIABLE)

This mailbox contains **ITAR / export-controlled client material**.

**Extract relationship metadata, never correspondence.**

| Never enters memory | May be recorded |
|---|---|
| Message bodies, in bulk or excerpted | Counterparty name, email domain, employer |
| Attachments of any kind | Thread count, last contact date, who replied first |
| Credentials, API keys, 2FA codes, reset or recovery links | Reply latency, warmth tier |
| Financial, medical, legal, family correspondence | Solicitation deadline dates |
| Anything from a thread where `export_controlled=true` | For flagged threads: identity + org **only** |

A thread is flagged when it matches configured markers (ITAR, EAR, CUI,
distribution-statement language) or a configured client domain. Enforced at the
producer in `scripts/redaction.py` — pass, self-heal-with-record, or raise. Never
warn-and-continue.

## Commands

```bash
./run.sh redact --input threads.json    # agent-extracted threads -> safe documents
./run.sh mine --dry-run                 # MANDATORY first run; writes nothing
./run.sh mine --commit                  # write typed records via /memory
./run.sh draft-validate spec.json       # schema + roundtable gate before /gmail plan
./run.sh assess <file>                  # audit code that bypasses /gmail
./sanity.sh                             # 25 behavioral gates
```

## The flow

```
/gmail search --hydrate full        (agent; /gmail owns the API call)
        |
        v
mailbox-mining redact               (this skill; producer-side redaction)
        |
        v
mailbox-mining mine --commit        (typed records through /memory, never raw Arango)
```

For outbound:

```
draft spec -> mailbox-mining draft-validate  (schema + roundtable gate)
           -> /gmail plan outbound            (/gmail owns the write)
           -> human reviews plan, supplies approval code
           -> /gmail commit
```

Note the division: this skill decides whether a message is *fit to prepare*; `/gmail`
decides how it is *safely executed*. Neither replaces the human, who supplies the
approval code.

## Every outbound message requires an /ask roundtable

Operator decision 2026-08-02. `draft-validate` enforces it directly rather than
trusting the schema alone, because it is the last gate before `/gmail plan`.

Required in `roundtable_review`: `ran: true`, `topology: concurrent` (a sequential
chain is a pipeline, not a roundtable), `follows_best_practices_roundtable: true`, a
`run_dir` so receipts can be inspected, **at least two PASSing seats** (one voice is
not a panel), and a verdict of `SEND_AS_IS` or `SEND_WITH_REVISIONS`.

Why the expensive review is the cheap option: outbound volume is deliberately low
(5 InMails/month plus sparse email) and each message is dossier-backed and aimed at a
named person, so response likelihood is high. One badly-worded message costs a contact
and their organization permanently. Low volume plus high hit-rate inverts the usual QA
calculus.

## Mining output

Typed records written **through `/memory` only** — never direct ArangoDB
(`best-practices-skills` ArangoDB Access Policy):

| Collection | Record |
|---|---|
| `contacts` | one per counterparty; `role_basis: existing_correspondence` |
| `contact_orgs` | one per employer domain |
| `outreach_attempts` | one per outbound thread, with `outcome` |
| `contact_edges` | `works_at`, `introduced_by`, `referral_path` |

Warmth tiers: `two_way_recent`, `two_way_dormant`, `one_way_only`, `inbound_only`.

**Warm beats cold.** A mined `two_way_recent` contact outranks any cold prospect from
web research. Check mined contacts before cold outreach.

## First run is read-only

`mine --dry-run` is mandatory before `--commit`. The dry run proves the extraction is
correct and, more importantly, that the export-control filter fired where it should —
before anything is persisted.

## Related skills, easily confused

| Skill | Actually does |
|---|---|
| `/gmail` | Gmail REST API control: read, search, plan/commit writes, receipts |
| `/ops-google` | Gemini **API billing and rate limits** — nothing to do with mail |
| `mailbox-mining` | this skill: redaction, contact-graph mining, outbound gate |

## History

Originally authored as `ops-gmail` with the claude.ai Gmail MCP connector as its
transport. Superseded 2026-08-02 when `skills/gmail` landed on branch
`agent/add-gmail-control-skill` (PR #1154, draft): that skill is API-first with a
stronger write model than the drafts-only approach used here, so the transport half was
deleted rather than maintained twice. Renamed because two skills named for Gmail invite
exactly the confusion `/ops-google` already causes.

## References

- `scripts/redaction.py` — the enforced contract
- `references/misuse_patterns.json` — patterns for `assess`
- `docs/PROJECT_KNOWLEDGE.md` — current state, gaps, defect history
- `fixtures/agentic_eval.json` — positive, negative, adversarial cases
