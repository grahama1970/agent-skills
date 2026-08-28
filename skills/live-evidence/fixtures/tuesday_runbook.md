# Tuesday morning: an agent starts producing bad output. Runbook.

Spoken answer shape: how I KNOW, how I DIAGNOSE, what I DO. Every step names
an artifact that already exists in my systems — nothing is reconstructed
after the fact, because it was written during execution.

## How I know (before a user tells me)

- A gate trips, not a complaint: reconciliation disagreement, groundedness
  floor breach, unsupported-answer rate over threshold on a segment, or a
  join receipt going DEGRADED. Absence trips too — a node that produced
  nothing is surfaced, never dropped (stage ladder: an unadmitted answer
  cannot read as success).
- Alert dimensions are versioned: model id, prompt version, tool version,
  policy digest, index/corpus version, tenant segment. Bad output with flat
  latency and flat HTTP errors is a QUALITY regression — exactly the case
  metrics-only monitoring misses.

## How I diagnose (dispatch table, not war room)

1. events.jsonl — which runs, when did the shape change, what deployed near
   that timestamp.
2. Node receipts — status + failure_code per node; find the lane where wrong
   begins. Receipts carry requested vs resolved model and requested vs
   dispatched reasoning effort with any downgrade reason: silent provider
   substitution and throttling fallbacks are visible here (a real bug we
   caught: the receipt said one model PASSed while another had answered —
   now it is a recorded substitution).
3. Retrieval evidence — did retrieval return anything, and did the answer
   cite it? A complete trace showing zero evidence and a confident answer is
   a broken admission gate, not a model mood.
4. Recovery packets — the failing lane names its own next command.
5. Version skew matrix — model/prompt/tool/policy/index versions against the
   incident window. Tuesday 9:30 specials: market-open load, cache
   staleness, provider throttling with fallback, queue lag.
6. Breakpoint LAST — only for in-process state no artifact explains. The
   ladder is enforced: dispatch to the owning artifact, then breakpoint,
   then research; a third retry from stale context is a guess and is refused.

## What I do

- Lane-local first: quarantine the failing lane or segment; healthy peers
  keep serving (DEGRADED, not outage). Kill switches are granular — stop
  unsafe writes immediately, keep read-only diagnostics, record who flipped
  what, support controlled restart.
- Roll back the version the skew matrix indicts; the frozen contract makes
  old runs reproducible across policy versions.
- The regulator-ready timeline already exists: goal hash, receipts, and the
  publication journal were written during execution. Books-and-records is a
  traversal, not an investigation.
- Postmortem lands as an eval case: the incident's signature becomes a
  permanent regression gate before the fix counts as done.

## The line

"I know because a gate trips, not because a customer calls. Diagnosis is a
dispatch table — the symptom names the one artifact that owns it. And the
audit trail costs nothing on Tuesday because it was written on Monday."
