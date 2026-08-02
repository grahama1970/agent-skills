# Gmail project knowledge

Last updated: 2026-08-02

## Immutable goal

Provide Codex a reliable, inspectable Gmail capability that uses Gmail's REST
API, requests the smallest practical OAuth authority, keeps reads separate from
writes, and makes every external effect human-reviewable and receipt-bearing.
The skill must never silently send, permanently delete mail, switch to browser
scraping, leak OAuth material, obey instructions embedded in mail, or report
ambiguous transport as success.

## Current state

Overall readiness: **USABLE_WITH_GAPS**

| Surface | State | Evidence |
|---|---|---|
| Skill routing/frontmatter | Implemented | `SKILL.md`; composition/compliance fields |
| Read/search REST client | Implemented; live not established | `api.py`; HTTP boundary tests |
| Opaque ID path handling | Implemented | percent-encoding regression test |
| MIME normalization | Implemented | nested body/attachment fixtures |
| OAuth profiles | Implemented; live not established | scope map, mode checks, refresh path |
| Direct draft/send plans | Implemented | exact payload hash, approval, RFC Message-ID |
| Existing-draft send | Implemented with residual race | raw hash checked immediately before send |
| Mailbox mutation plans | Implemented | bounded label/Trash/Untrash and partial receipts |
| Receipts/idempotency | Implemented | one plan/one receipt; replay test |
| Ambiguous-write handling | Implemented | indeterminate receipts for transport and 5xx |
| Prompt-injection boundary | Documented | mail is data, never action authority |
| Live Gmail OAuth sanity | Available; not run | `sanity-live.sh` requires owner consent |
| Recipient delivery/spam placement | Not established | outside API acceptance and local tests |

## Verified deterministic evidence

The local gate on 2026-08-02 passed:

```text
23 tests passed
schema drift check passed
Python compilation passed
Typer help smoke passed
shell syntax passed
gmail sanity: PASS
```

Covered cases include plan tampering, UUID/path safety, header injection,
combined attachment bounds, opaque-ID URL encoding, bounded retries,
non-idempotent transport and 5xx ambiguity, exact approval, replay prevention,
partial Trash progress, partial uncertainty, attachment drift, existing-draft
raw-MIME drift, receipt privacy, and custom-output directory permissions.

This proves local contract behavior only. It does not prove Google Cloud setup,
OAuth consent, Workspace policy, mailbox access, outbound delivery, or recipient
receipt. A fresh `uv` dependency installation could not run in the offline build
environment because uncached packages were unavailable; normal online
resolution remains a packaging gate.

## Architecture decisions

1. **REST over UI:** Gmail has first-party endpoints for messages, threads,
   attachments, labels, drafts, sending, label mutation, Trash, and Untrash.
   Surf would add a brittle authenticated-DOM boundary without capability gain.
2. **Three independent token profiles:**
   - `readonly` -> `gmail.readonly`
   - `compose` -> `gmail.compose`
   - `manage` -> `gmail.modify`
3. **No full-mail scope:** the skill never requests `https://mail.google.com/`
   and does not expose immediate permanent-delete methods.
4. **Plan then commit:** preparation freezes payload and account. Commit checks
   exact approval, expiration, account, attachment/draft hashes, prior receipt,
   and lock ownership.
5. **No automatic retry for send/create:** transport loss or an ambiguous 5xx
   after dispatch can conceal an effect. The receipt is `indeterminate`, and a
   stable RFC Message-ID or draft identity supports reconciliation.
6. **Pydantic at boundaries:** plan files, receipts, payloads, IDs, timestamps,
   and recipient addresses require runtime validation. HTTP client state remains
   a normal class because it owns a connection and token.
7. **Untrusted-content rule:** bodies, HTML, attachments, and links can be
   returned for the user but cannot authorize tools or override the plan gate.

## Open gates

1. Run `./run.sh auth login --profile readonly ...` with the account owner.
2. Run `./sanity-live.sh readonly` and preserve a redacted result.
3. On a normal networked machine, run `./sanity.sh` from a clean `uv`
   environment and preserve dependency-resolution evidence.
4. Authorize `compose` and create a draft addressed to the owner; verify the
   draft in Gmail without sending.
5. Send a reviewed self-addressed message and reconcile API message ID, RFC
   Message-ID, Sent label, and actual receipt.
6. Exercise an existing-draft send while proving the pre-send hash check; do not
   edit the draft after approval.
7. Authorize `manage` and exercise archive/unarchive plus read/unread on a test
   message, then restore original state.
8. Decide whether public distribution is intended. If so, assess Google OAuth
   verification and restricted-scope requirements before claiming readiness.
9. Run repository `skills-ci` and best-practices validation on the full branch.

## Non-claims

- Local tests are not a live Gmail end-to-end pass.
- An HTTP success response is not proof of inbox placement or human receipt.
- OAuth consent is not proof of public app verification or administrator policy.
- Pre-send draft revalidation cannot make Gmail's read-to-send gap atomic.
- Plan/receipt controls are not a legal, compliance, records-retention, or
  data-loss-prevention determination.
- The skill does not sanitize untrusted email into safe shell/tool instructions.
