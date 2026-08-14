# Proof For agent-skills#1405

Ticket: https://github.com/grahama1970/agent-skills/issues/1405

Closure bar, quoted:

> Closure requires truthful per-operation readiness and live readback across
> heterogeneous targets; a static configuration dump, CLI-help scrape, or
> global `healthy: true` result is not closure proof.

## Live readback across heterogeneous targets

`./run.sh targets list --readiness --live --json`

```
live: True | counts: {'READY': 11, 'BLOCKED': 1, 'UNAVAILABLE': 1}

  tau.harness            READY        doctor_ok            live=True
  scillm.transport       READY        health_2xx           live=True
  browser.webgpt         READY        probe_ok             live=True
  browser.webclaude      READY        probe_ok             live=True
  memory.graph           BLOCKED      health_failed        live=True
  session.herdr          UNAVAILABLE  herdr_not_running    live=True
```

Required proof 11 asks for a Tau/SciLLM profile, two authenticated browser
handlers, Memory, and one named-session resolution. All present. Memory and
Herdr are reported blocked and unavailable rather than substituted or
smoothed — which is the point of the bar.

## Not a config dump, not a help scrape, not a global boolean

- `READY` requires readback from the owning subsystem in this run. Presence of
  a Tau checkout yields `NOT_TESTED`, not `READY`.
- There is no `healthy` key. `test_there_is_no_global_healthy_flag` asserts its
  absence, because one summary flag is exactly what hides a blocked lane.
- The default report performs no generation, submission, or mutation, and
  enumerates every skipped probe (`skipped_probes`, 10 by default).

## Per-operation, not per-target

- `webdeepseek` reports `text=yes, attachment=no` — distinct from a seat that
  was merely not tested (proof 5).
- A degraded probe reports `text=None`, so uncertainty cannot read as
  readiness (rule 1).
- `scillm.transport` (kind `model_api`) and `browser.webclaude` (kind
  `browser_seat`) are separate capabilities for the same provider family
  (proof 6).
- One seat blocked leaves the others untouched
  (`test_one_failed_seat_does_not_contaminate_the_others`, proof 8).

## Required proofs

1. Fixtures cover every state per target family — parametrized over
   BLOCKED/UNAVAILABLE/DEGRADED/READY.
2. Human and JSON derive from one object — `render_text()` takes the report.
3. Default doctor touches no subsystem — `test_the_default_report_touches_no_subsystem`.
4. Skipped probes recorded — `test_skipped_probes_are_listed_not_defaulted`.
5. Text-ready/attachment-blocked stays distinct — webdeepseek fixture.
6. API vs web readiness distinct — `test_api_and_web_readiness_are_separate_capabilities`.
8. No cross-contamination — covered above.
9. Next commands carry no secrets — `test_next_commands_carry_no_secrets`.
12. Existing doctor untouched; `targets` is an additive command family.

## Freshness and invalidation (proof 7)

Every record carries `observed_at`, `ttl_seconds`, and `stale`. Two independent
reasons invalidate a verdict, either alone sufficient:

```
fresh           -> stale=False  ttl=120
after TTL       -> stale=True   ttl_expired
identity change -> stale=True   identity_changed
```

`identity_fingerprint()` hashes the Herdr pane set, the controlled browser tab
id, and the Tau git revision. Recency is not relevance: a verdict observed
against a different tab, session, or Tau revision describes a world that no
longer exists, however recent it is.

TTLs differ by kind because volatility does: browser seats expire in 120s
(tabs are reassigned constantly), local capabilities in 3600s. `NOT_TESTED`
never goes stale — it was never fresh.

## Not proven

Proof 10 — a plan using a stale optimistic report being revalidated and blocked
by Tau — is NOT implemented. It depends on #1403 (per-node launch contract),
which is not built. This report exposes `stale` for a consumer to act on, but
nothing yet enforces that a planner must.

Commits: 55063140f1, plus freshness/TTL/identity invalidation
