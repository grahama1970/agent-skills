# OpenClaw /hack Closure Notes

## Accepted Closure Pattern

The Round 4 OpenClaw package is the accepted `/hack` proof-candidate / patch-pending closure pattern. It is not a verified-fixed claim.

- Run root: `/mnt/storage12tb/artifacts/agent-skills/hack/openclaw-weakspot-closure-20260510T173627Z`
- Review package: `/mnt/storage12tb/artifacts/agent-skills/hack/openclaw-weakspot-closure-20260510T173627Z/HACK_OPENCLAW_CLOSURE_REVIEW_PACKAGE_ROUND4.zip`
- WebGPT review: `/mnt/storage12tb/artifacts/agent-skills/hack/openclaw-weakspot-closure-20260510T173627Z/webgpt-review-round4/response.md`
- WebGPT verdict: `MERGE/SHIP VERDICT: pass`
- Visual proof: `/tmp/codex-ui-verification/agent-skills/hack-openclaw-final-report-failclosed-http4/20260512T141326Z.png`

## Required Status Semantics

The closure pattern must fail closed and keep these states separate:

- `status`: `proof_candidate_reproduced_patch_pending`
- `proof_candidate_reproduced`: `true`
- `patch_pending`: `true`
- `verified_fixed`: `false` until a post-patch Docker proof rerun passes
- `verification_status`: `blocked_patch_not_applied` when no patch verification exists
- `provenance_complete`: `false` when commit/origin/branch or Docker image digest capture is incomplete

`green_allowed` is not a valid machine-readable field for `/hack` closure reports.

## Regression Gates

The closure/report generator must reject or normalize the blockers found before Round 4:

- Do not accept git `ERROR:` strings as commit, branch, or origin provenance.
- Use explicit provenance fallback sources when direct git capture fails.
- Do not emit final report status `unknown` when `CLOSURE_VERDICT.json` exists.
- Map session-audit fields from `has_hack_report`, `has_semgrep`, and `has_launch_plan`.
- Treat battle zero findings as non-success unless supported by real findings or explicit limitations.
- Capture battle memory/Dogpile unavailability in mode evidence and human reports.
- Package raw source ledgers and compute hashes for included artifacts.
- Include an explicit missing marker for absent post-patch verification.

## Separation From Product Patch

This closure pattern only proves that `/hack` can produce a credible proof-candidate report and review package. The OpenClaw product fix is separate work:

- Patch target: unauthenticated or disallowed-origin WebSocket handshakes to `/hooks/wake` must not return `101`.
- Legitimate authorized local-control handshakes must continue to work.
- `verified_fixed=true` requires a post-patch Docker rerun and `post-patch-verification.json`.

## Follow-Up Backlog

These are useful hardening items but do not block the Round 4 proof-candidate closure pattern:

- Capture Docker scanner image digests reliably.
- Replace the legacy battle weak gate entirely.
- Extract exact Dogpile citation spans for successful exploit origins.
- Enrich non-winning exploit strains with per-strain terminal signals.
- Add broader structural consistency checks across HTML, Markdown, and JSON.
- Distinguish manifest `source_exists=false` from generated package marker artifacts.
