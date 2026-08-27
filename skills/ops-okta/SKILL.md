---
name: ops-okta
description: >
  Read-only Okta posture detector: env/config presence (domain, client id,
  token presence redacted), OIDC discovery endpoint reachability, and JWKS
  fetch when a domain is configured. Detection only - no writes, no token
  minting, no user/group mutation. Use for "okta health", "is okta
  configured", "check oidc discovery", "ops-okta".
triggers:
  - ops-okta
  - okta health
  - okta configured
  - oidc discovery check
provides:
  - okta-posture-detection
composes:
  - triage-error
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-security
runtime_self_improvement: none
taxonomy:
  - validation
  - observability
disciplines:
  - developer-tooling
---

# ops-okta

Detection only, fail-closed, secrets never printed (presence booleans only).

```bash
./run.sh doctor            # env posture: OKTA_DOMAIN, OKTA_CLIENT_ID, token presence
./run.sh discovery         # GET /.well-known/openid-configuration on OKTA_DOMAIN
./run.sh jwks              # fetch signing keys metadata (kids only)
```

Typed outcomes with failure_code on every non-PASS. Authorization decisions,
app assignments, and token issuance stay with Okta and the gateway; an
agent-facing mutation lane would be a separately-contracted Tau tool.
