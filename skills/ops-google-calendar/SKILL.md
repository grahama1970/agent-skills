---
name: ops-google-calendar
description: >
  Read and propose Google Calendar changes over OAuth for meeting-assistant
  scheduling. Use for "schedule a follow-up", "reschedule", "move the meeting",
  "push this to Friday", "what's on my calendar", "calendar oauth", or when
  live-evidence proposes a calendar action. Writes are PROPOSE-ONLY and require
  an explicit --confirm; nothing mutates a real calendar without it.
triggers:
  - google calendar
  - calendar oauth
  - reschedule meeting
  - move the meeting
  - push meeting to friday
  - whats on my calendar
  - schedule a follow-up
  - ops-google-calendar
metadata:
  short-description: Google Calendar read + propose-only scheduling over OAuth
provides:
  - calendar-read
  - calendar-propose
  - google-calendar-oauth
composes:
  - task-monitor
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
taxonomy:
  - scheduling
  - integration
  - loyalty
  - resilience
runtime_self_improvement: basic
disciplines:
  - integration-operations
  - developer-tooling
---

# Ops Google Calendar

Read the calendar, and **propose** (never silently apply) scheduling changes an
agent hears in a meeting. This is the destination for the live-evidence
`schedule` action: "can we push this to Friday?" becomes a proposal a human
approves, not an automatic calendar write.

The Google Calendar API and OAuth are **free** (quota-limited, no per-call
billing). This is unrelated to `ops-google`, which is a Gemini-API budget
manager.

## One-time auth setup

OAuth needs a Google Cloud OAuth client (Desktop type). You create it once:

1. In Google Cloud Console, enable the Calendar API and create an OAuth 2.0
   **Desktop** client. Download the JSON.
2. Save it (path is configurable):

   ```bash
   mkdir -p ~/.config/ops-google-calendar
   cp ~/Downloads/client_secret_*.json ~/.config/ops-google-calendar/client_secret.json
   ```

3. Run the consent flow in your own terminal (it opens a browser). Because this
   is interactive, run it yourself with the `!` prefix:

   ```bash
   ! ./run.sh auth
   ```

   The refresh token is stored at `~/.config/ops-google-calendar/token.json`
   (mode 0600). The scope is `calendar.events` — event read/write only, no
   account or contact access.

## Commands

```bash
./run.sh status --json                       # authed? reachable? (read-only)
./run.sh events --days 7 --json              # upcoming events (read-only)
./run.sh propose-reschedule --event-id <id> --to '2026-08-28T15:00:00-04:00'
./run.sh propose-create --summary 'Sparta sync' \
    --start '2026-08-28T15:00:00-04:00' --end '2026-08-28T15:30:00-04:00'
./run.sh sanity                              # non-mocked local checks
```

`status` and `events` are read-only. `propose-*` emit a
`ops_google_calendar.proposal.v1` receipt and **do not touch the calendar**
unless you add `--confirm`. Without `--confirm` the proposal is printed for a
human to approve; with `--confirm` and a valid token the change is applied and
the applied event is read back into the receipt.

## Boundaries

- **Propose-only by default.** A calendar write is outward-facing and affects
  other people; it fails closed without `--confirm` and without a valid token.
  Nothing here auto-executes.
- **No secrets in output.** Tokens live in a 0600 file and are never printed;
  receipts carry event ids and times, not credentials.
- **Ambiguity is surfaced, not guessed.** A proposal states exactly which event
  and time it would set; underspecified requests ("push to Friday") must be
  resolved to a concrete datetime by the caller before `--confirm`.
- **Not `ops-google`.** That skill manages the paid Gemini API; this one is a
  free Calendar OAuth integration with a separate credential.
