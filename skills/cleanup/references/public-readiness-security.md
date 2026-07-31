# Public-Readiness Security Contract

This reference defines the cleanup lane for repositories being prepared for
public review or public visibility. It is a release-readiness lane, not a
deletion lane.

## Required Findings

`$cleanup --public-readiness` reports these blockers:

- gitleaks history scan missing, corrupt, stale, or containing findings;
- synthetic-looking `generic-api-key` findings such as `_key`, `expected_key`,
  fixture, mock, test, or sample identifiers that still need explicit triage or
  allowlisting;
- working-directory gitleaks findings dominated by ignored local runtime folders
  such as `.venv`, `.codex`, `local/`, `artifacts/`, `node_modules/`, caches, or
  build outputs;
- missing maintainer inventory for GitHub visibility, security, secret scanning,
  branch protection, issue/reporting, and disclosure settings.

## Closure Criteria

Public-readiness blockers close only when deterministic receipts exist:

1. A fresh gitleaks history report exists under
   `artifacts/cleanup/public_readiness/`.
2. Every history finding is triaged as `real_secret`,
   `synthetic_allowlisted`, or `false_positive_with_receipt`.
3. Synthetic-looking findings have an explicit rationale or allowlist entry and
   a fresh scan receipt.
4. Working-directory scan noise is narrowed by scope/config or each ignored
   runtime hit is justified.
5. GitHub settings are inventoried by a maintainer; cleanup does not change
   remote visibility or security settings without explicit authority.
6. The cleanup report states whether the public flip remains blocked.

## Non-Claims

- Synthetic-looking secrets are not safe until triaged.
- A noisy working-directory scan is not public-readiness proof.
- WebGPT or reviewer output is not closure proof without local scan/settings
  receipts.
- Cleanup does not rewrite history, edit allowlists, or flip repository
  visibility by default.
