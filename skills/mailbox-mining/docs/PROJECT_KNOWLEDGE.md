# mailbox-mining — project knowledge

**As of 2026-08-02.** Current state, not proof.

## Purpose
Redaction + contact-graph mining + the outbound roundtable gate. **Mailbox access is
`/gmail`'s job**, not this skill's.

## Supersession (2026-08-02)
Originally `ops-gmail`, built on the claude.ai Gmail MCP connector. `skills/gmail`
landed on branch `agent/add-gmail-control-skill` (commit `53add58fd`, draft PR #1154)
with an API-first design: OAuth profile separation, two-phase plan/commit with approval
codes, exactly-once receipts, indeterminate-state reconciliation, no
`mail.google.com` scope, and content-drift detection. Verified locally: 23 tests pass,
`sanity.sh` PASS. That is a stronger write model than the drafts-only approach here, so
the transport half of this skill was deleted rather than maintained twice.

## Current state
| Item | State |
|---|---|
| Mailbox access | delegated to `/gmail`; its OAuth is **not yet authorized** (PR #1154 is draft pending live OAuth + mailbox tests) |
| Redaction contract | Implemented and gated; 25 behavioral assertions pass |
| `redact` / `mine --dry-run` | Working through the real CLI path |
| `mine --commit` | Implemented, **never executed** — no live run yet |
| `draft-validate` | Implemented; enforces `grahamaco.inmail_draft.v1` **and** the mandatory roundtable gate |
| Send capability | none here; `/gmail plan outbound` + human approval code owns it |
| Live connector trial | `NOT_ESTABLISHED` |

## Architecture boundary (easy to get wrong)
A shell process cannot call MCP tools. The **agent** makes
`mcp__claude_ai_Gmail__*` calls; this **CLI** owns the deterministic half —
redaction, schema validation, and writes through `/memory`. `auth-status`
therefore reports `UNKNOWN_FROM_SHELL` rather than pretending to know.

## Known gaps
- Export-control marker list is heuristic; review against real mail before trusting `--commit`.
- Referral-path edge extraction is specified but not implemented.
- No live corpus has been read, so classification accuracy is unmeasured.

## Defect history
- **2026-08-02:** `mine` and `redact` disagreed — `mine` dropped the extra fields, so a
  record carrying an API key counted toward `would_write` while `redact` refused it.
  Fixed by a single shared `_extract()`; a regression trial now guards it.

## Invariants that must not regress
1. No send, delete, bulk-label, or filter/forwarding mutation.
2. No direct ArangoDB access — writes go through `/memory`.
3. Export-controlled threads contribute identity and organization only.
4. `mine --commit` requires a prior dry-run confirmed by the human.
5. An upsert response is not proof; read back before claiming success.
6. No draft without a completed /ask roundtable: concurrent topology, >=2 PASSing seats,
   verdict SEND_AS_IS or SEND_WITH_REVISIONS. Operator decision 2026-08-02.
