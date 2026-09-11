---
name: ops-godaddy
description: >
  GoDaddy DNS operations via the API: diagnose mail-auth (SPF/DKIM/DMARC/MX),
  put records, replace whole zones. Use when the user says "godaddy", "dns
  records", "spf", "dmarc", "dkim", "mx records", "email bouncing", "domain
  verification", or asks to fix mail authentication for a GoDaddy-managed
  domain.
triggers:
  - fix dmarc bounce
  - update godaddy dns records
  - check spf dkim dmarc
  - godaddy dns
  - email bouncing domain policy
  - set mx records google workspace
provides:
  - dns-management
composes:
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - resilience
  - precision
---
# ops-godaddy

DNS record operations for GoDaddy-managed domains, via the public API —
never the web UI (it demands per-mutation SMS step-up verification; the
API does not).

## Token (one time, ~60s, browser)

1. In the authenticated Chrome session, open `developer.godaddy.com/keys`.
2. Generate Token: name it, scope `domains.dns:update`, 30-day expiry.
   (Generate twice if the first click does not submit.)
3. Copy the `gd_pat_...` value ONCE, then `export GODADDY_PAT=...` or put
   it in the skill's `.env`.
4. Token semantics: **write-only** (reads 401) — that is normal for
   dns:update scope; verification reads use `dig`, not the API.

## Commands

```bash
./run.sh diagnose --domain grahama.co          # SPF/DKIM/DMARC/MX at the authoritative NS + verdict
./run.sh put-record --domain grahama.co --rtype TXT --name @ --data "v=spf1 include:_spf.google.com ~all"
./run.sh put-zone --domain grahama.co --zone-file zone.json   # FULL replacement; omit-to-delete
```

## The four API traps (each verified live 2026-09-11)

| Trap | Symptom | Correct move |
|---|---|---|
| Zone PUT needs NS | 422 MISSING_NAME_SERVER | body must contain >= 2 NS records (enforced by our pydantic Zone) |
| PATCH appends | 422 DUPLICATE_RECORD | never PATCH; use zone-wide PUT |
| PUT `[]` does not delete | 200, record persists | delete by zone-wide PUT omitting the record |
| DELETE verb | 409 CONFLICTING_STATUS | same: zone-wide PUT omitting the record |

## Verification

`dig @<ns1> <TYPE> <domain>` against the authoritative nameserver is
instant truth — no TTL wait. `diagnose` does this for mail-auth.

## Google Workspace mail fix recipe (proven)

1. `diagnose` → confirm `spf_does_not_authorize_gmail`.
2. put-record TXT @ `v=spf1 include:_spf.google.com ~all`
3. put-record MX @ the 5 records: aspmx(1), alt1/2(5), alt3/4(10), ttl 600.
4. Zone PUT with everything except stale-provider remnants (old SPF
   delegates, foreign DKIM selectors, verify CNAMEs) — this deletes them.
5. `diagnose` again → `google_workspace_send_ok`. DMARC stays `p=quarantine`.
6. Optional defense-in-depth: DKIM key from Workspace admin
   (Apps → Gmail → Authenticate email), publish `google._domainkey` TXT.

## Failure posture

Missing token → typed `missing_token` JSON with the fix, exit 2. API
non-200 → exit 1 with body excerpt. No bare failures.
