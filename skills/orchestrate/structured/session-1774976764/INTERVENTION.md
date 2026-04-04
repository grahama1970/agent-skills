# Intervention Controls

Session: session-1774976764

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `S1-wire-security-scan`: Add security-scan as Step 4.5 in monitor-codebase (code-runner/security)
- `S2-update-skill-md-security`: Update SKILL.md pipeline table with Step 4.5 security scan (code-runner/security)
- `D1-duplication-detector`: Create duplication_detector.py for cross-file code duplication (code-runner/duplication)
- `D2-wire-duplication`: Wire duplication detection into monitor-codebase Step 4.6 (code-runner/duplication)
- `G1-dep-graph`: Create dep_graph.py for import dependency analysis and circular dep detection (code-runner/deps)
- `G2-wire-dep-graph`: Wire dependency graph analysis into monitor-codebase Step 4.7 (code-runner/deps)
- `T1-coverage-tracker`: Create coverage_tracker.py for test coverage analysis (code-runner/coverage)
- `T2-wire-coverage`: Wire coverage tracking into monitor-codebase Step 4.8 (code-runner/coverage)
