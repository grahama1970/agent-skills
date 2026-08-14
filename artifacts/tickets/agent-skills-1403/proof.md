# Proof For agent-skills#1403

Ticket: https://github.com/grahama1970/agent-skills/issues/1403

Closure bar, quoted:

> Closure requires deterministic no-widening tests plus live requested-versus-
> resolved contract receipts from Tau; a pretty preview, prompt-only
> restriction, or direct provider preflight is not closure proof.

## The asymmetry

Tau may TIGHTEN a ceiling and may never widen one. Tightening is a safety
decision and is accepted and reported; widening is an escalation and is
rejected.

## No-widening tests (deterministic)

Every ceiling dimension, each rejected when widened:

| widened | result |
| --- | --- |
| `tools` (reviewer given `write`, `shell`) | rejected — proof 8 |
| `allowed_paths` (`/etc` added) | rejected — proof 9 |
| `effects` (`network` added) | rejected |
| `timeout_seconds` 600 → 3600 | rejected |
| `required_evidence` weakened | rejected |
| `goal_hash` changed | rejected |
| model substituted without permission | rejected |
| `tools` narrowed to `read` | **accepted**, reported as tightened — proof 6 |

## Canonical digest (proofs 2 and 3)

- Reordering `tools` does not change the digest; changing membership does.
- Changing target, path scope, evidence requirement, or output schema changes it.
- `tab_id`, `run_dir`, `created_at` and the rest of the ephemeral set are
  excluded — a contract whose hash moved when a tab was reassigned could never
  be compared, and comparison is what makes widening detectable.
- Ephemeral identities appear only in `runtime_binding` on the receipt.

## Fails closed before execution (proof 5)

Compilation is dict-in/dict-out and side-effect-free, so refusing costs
nothing:

- unknown effect class
- contradictory intent — `filesystem_write` without `write_intent`, or the reverse
- `write_intent` with no allowed path
- unsupported target/adapter pair — a browser seat cannot claim
  `tau_native_agent` guarantees when it runs behind a compat transport

## Blocks before submission (proof 7)

`preflight_blocks()` consumes #1405's report: a seat that is BLOCKED, whose
readiness is stale, or that cannot take attachments blocks BEFORE the task is
submitted rather than failing after the prompt is in. This also supplies
#1405's own proof 10 — a stale optimistic capability report now has something
that refuses on it.

## Route inventory (proof 10)

`launch_contract.py` is registered `local_non_agentic` / `probe_only`; the
route-inventory tests prove the preflight creates no direct provider, browser,
or session dispatch path.

## A bug the tests caught in my own verifier

`verify_runtime` treated a field *absent* from a partial runtime resolution as
a weakening claim, so every narrow receipt flagged itself as violating its own
contract. Absence is not an assertion; the check now requires the runtime to
actually declare the field.

## Not proven

The closure bar's "live requested-versus-resolved contract receipts **from
Tau**" is NOT satisfied. Tau does not currently emit a resolved-ceiling receipt
per node, so there is no runtime resolution to compare against a real dispatch.
`verify_runtime` is exercised against constructed resolutions covering every
ceiling dimension, and `preflight_blocks` is exercised against a real #1405
report — but the Tau side of that handshake does not exist yet.

This ticket therefore delivers the contract, the canonicalization, the
no-widening verifier, and the preflight gate. Wiring Tau to emit resolved
ceilings is upstream work in the Tau repo, not something Ask can complete
alone.

805 passing; 26 new tests.

Commit: bf75a3ddf6
