# OAuth scope profiles

The skill persists each profile in a separate token file so a read-only Codex
session never inherits write authority by convenience.

| Profile | Scope | Intended operations |
|---|---|---|
| `readonly` | `gmail.readonly` | profile, search, messages, threads, attachments, labels, drafts |
| `compose` | `gmail.compose` | profile, read/list drafts, create drafts, send mail |
| `manage` | `gmail.modify` | read/send plus labels, archive, state, star, Trash/Untrash |

The exact scope URIs are:

```text
https://www.googleapis.com/auth/gmail.readonly
https://www.googleapis.com/auth/gmail.compose
https://www.googleapis.com/auth/gmail.modify
```

The skill never requests:

- `https://mail.google.com/` — broad access including permanent deletion;
- `gmail.settings.basic` or `gmail.settings.sharing`;
- `gmail.insert`;
- Workspace domain-wide delegation.

Google currently classifies `gmail.send` as sensitive and `gmail.readonly`,
`gmail.compose`, and `gmail.modify` as restricted. Public app verification and
security-assessment obligations depend on distribution and how restricted data
is stored or transmitted. Keep those deployment questions separate from local
CLI correctness.

Canonical source:
`https://developers.google.com/workspace/gmail/api/auth/scopes`
