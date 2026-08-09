# /ask roundtable live reliability — six browser lanes

Date: 2026-08-09 (UTC 20260809T195010Z)
Method: live non-deterministic roundtable trials, judged on DELIVERED output
(each seat's node receipt `ok` + non-empty response, read back from the join
receipt). Gate: Wilson 95% score-interval lower bound ≥ 85%.
Harness: `skills/ask/scripts/live_roundtable_reliability.sh`.
Diagnosis: `skills/ask/scripts/diagnose_roundtable_run.py` (deterministic
failure-code decision tree).

## Scorecard

| Lane        | Sample  | Wilson 95% LB | Gate | Notes |
|-------------|---------|---------------|------|-------|
| webgpt      | 30/30   | 88.6%         | MET  | |
| webkimi     | 30/30   | 88.6%         | MET  | |
| webgemini   | 30/30   | 88.6%         | MET  | |
| webclaude   | 41/42   | 87.7%         | MET  | one transient `browser_clean_output_contaminated` |
| webdeepseek | 43/45   | 85.2%         | MET  | two `prompt_too_large_or_stalled` timeouts |
| webgrok     | see below | not established | NOT MET (external quota) | `browser_provider_rate_limited` |

5 of 6 lanes MET with Wilson ≥ 85%.

## webgrok — functional but rate-limited (deterministically diagnosed)

grok the LANE is proven functional: a fresh single trial delivers real,
on-topic content (probe PASS 1/1 on 2026-08-09 after the lane sat idle).

grok CANNOT currently produce a clean rapid Wilson sample. Under sustained
submission — even spaced 120 s apart — it throttles after the first hit:
a 30-trial spaced run scored 4/15 before it was stopped (trial 1 PASS, then a
long run of 0-seat failures, occasional recovery at trials 13/15).

Root cause is NOT a lane defect. A single trial run to a preserved output dir
and passed through the deterministic diagnostic returns:

```
join status: NEEDS_ATTENTION | removed_seats: ['webgrok']
  XX webgrok: delivered=False chars=0 | failure_code=browser_provider_rate_limited
     -> wait for the provider cooldown, then retry
```

`browser_provider_rate_limited` is grok's external provider quota. It resets on
grok's clock (the 4-day gap between measurement sessions was enough for a fresh
trial to pass again). A legitimate ≥85% Wilson sample for grok therefore needs
trials trickled wide enough to stay under grok's quota (long-horizon), not a
rapid burst — bursting only re-confirms and re-arms the throttle.

## What is durably proven here

- The deterministic provider-debugging path works end-to-end: run one trial →
  `diagnose_roundtable_run.py` → typed `failure_code` + recommended action,
  read back from the seat's node receipt (not inferred from a log string).
- 5/6 lanes clear the Wilson ≥85% gate on delivered content.
- grok's shortfall is attributed to a receipt-backed external cause
  (`browser_provider_rate_limited`), not to an `/ask` or lane bug.

## Regression protection landed this session

- `agentic_eval_regressions.json`:
  `browser-probe-hard-kills-process-group-on-timeout-1307` and
  `live-roundtable-trial-is-hard-bounded-no-indefinite-hang` — lock in that a
  wedged browser submit can never hang indefinitely and monopolize a lane
  (observed failure: a wedged grok trial ran ~4 days holding the only grok tab).
