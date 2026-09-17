# Threat model and privacy

## Protected boundaries

The app treats submitted source, event labels, timings, headers and bearer tokens
as untrusted. It validates JSON and typed payloads, requires explicit consent,
applies resource and deadline constraints, and uses parameterized SQLite queries.
Submitted source is parsed only. Safe JSON weights avoid pickle-based model loading.
Model selection is an operator setting, not a candidate endpoint parameter.

No AI provider receives candidate code. No webcam/microphone, unrelated tabs,
operating-system processes, global keys or clipboard contents are monitored.
Paste events inside the assessment editor are disclosed and never prove AI use.
Security errors omit source, credentials and raw Pydantic input/context values.

## Important limitations

The browser is not a trusted hardware witness. A candidate can use another device
or report incomplete events. Hash chains cannot prove a true human history or resist
an administrator who can rewrite all stored evidence. Browser `isTrusted` is not
an intellectual-authorship credential. The service does not claim otherwise.

SQLite serialization and finite budgets are not a full Internet abuse program.
The service is loopback research software, not a hostile multi-tenant deployment.
Deploying behind a proxy would require explicit trusted-origin/host configuration,
TLS, operator authentication, access controls, rate limiting, logging policy and
an independent security review. Default proxy header trust is disabled.

Source and deleted edits remain confidential data. File permissions are not disk
encryption. Retention cleanup requires the service to run; deleted exports/backups
are not revoked, and row deletion is not a secure-media erasure guarantee.

The optional Transformers adapter uses trusted local configuration and pinned
safetensors, disables remote code, and refuses unbounded/truncated inference. That
reduces some risks; it is not a proof that every permitted model format/parser is
safe. Keep optional model runs in a separately managed research environment.

## Reporting a problem

Do not attach real candidate content, bearer tokens or client source to a public
issue. Reproduce against synthetic inputs, retain the redacted failure and source
hash, add a capable regression, and preserve the failed qualification report.
The bundle was not published to GitHub and does not configure an issue endpoint.
