# Intervention Controls

Session: session-1774976924

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Add /api/memory/traceability endpoint (code-runner/0)
- `1b`: Add /api/evidence-case/trace endpoint (code-runner/0)
- `1c`: Add /api/critical-path endpoint (code-runner/0)
- `2`: Render traceability links in ThreatMatrix Detail flyout (code-runner/1)
- `3`: Add Why button with GateChain + source chunks in flyout (code-runner/1)
- `4`: Hide developer metrics from RecallCard default view (code-runner/2)
- `5`: Critical path filter mode in LemmaGraph (code-runner/2)
- `6`: Discrepancy analysis script + prompt (code-runner/3)
- `7`: Threat delta computation script + learn-datalake post-hook (code-runner/3)
