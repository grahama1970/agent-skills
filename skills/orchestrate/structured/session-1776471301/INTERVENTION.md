# Intervention Controls

Session: session-1776471301

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Extract NIST SP 800-53r5 with current extractor (local/0)
- `2`: Scan all 492 pages for defects (local/0)
- `3`: Fix top defect category in extract_for_pdflab.py (code-runner/1)
- `4`: Append round outcome to tally (local/2)
