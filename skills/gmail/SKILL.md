---
name: gmail
description: >
  Read-only Gmail access through the authenticated Chrome tab via surf.
  Find the Gmail tab, snapshot inbox rows, open and read a thread by
  keyword. Use when the user says "check my email", "read the inbox",
  "did a verification code arrive", "find the bounce message", or when a
  workflow needs email as an inbound channel (codes, bounces, replies).
  Outbound mail is out of scope — drafts belong to mailbox-mining.
triggers:
  - check my email
  - read the inbox
  - did the code email arrive
  - find the bounce message
  - gmail verification code
provides:
  - mailbox-read
composes:
  - surf
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - precision
---
# gmail

Read-only Gmail through the already-authenticated Chrome tab. Closes the
`composes: [gmail]` edge mailbox-mining has declared.

## Commands

```bash
./run.sh tabs                          # Gmail tab id
./run.sh inbox --limit 10              # row snapshot (from/subject/time)
./run.sh read --keyword godaddy        # open newest matching thread, extract body
```

## Boundaries

- READ-ONLY. No compose, no send, no label changes.
- Requires a Gmail tab open in Chrome (surf transport).
- Bodies are truncated to 3000 chars — enough for codes/bounces, not for archives.

## Failure posture

Typed JSON exits: `gmail_tab_not_found` (2, fix: open Gmail), `thread_not_found`
(3), transport error (1). Never a bare failure.
