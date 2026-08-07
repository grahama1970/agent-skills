---
name: monitor-drift-sensors
description: CUSUM and Page-Hinkley statistical drift detection on sensor data streams
triggers:
  - "drift detection"
  - "sensor drift"
  - "monitor sensors"
allowed-tools:
  - Bash
provides:
  - monitor-drift-sensors
composes:
  - create-figure
  - task-monitor
disciplines:
  - observability-operations
  - data-engineering
---

# monitor-drift-sensors

Statistical drift detection on sensor data streams using CUSUM (Cumulative Sum) and Page-Hinkley algorithms.

## Usage

```bash
# Analyze a JSONL file of sensor readings for drift
./run.sh analyze <data.jsonl>

# Analyze with built-in test fixtures (no file needed)
./run.sh analyze --dry-run

# Watch a live sensor stream (requires running daemons)
./run.sh watch --sensor vibration --threshold 3.0

# Show algorithm parameters and last detection results
./run.sh status
```

## Input Format

Each JSONL line:
```json
{"timestamp": "2026-02-19T10:00:00", "sensor": "vibration", "value": 50.3}
```

## Output

Table of detected drift points:

```
SAMPLE_IDX | TIMESTAMP            | CUSUM_VALUE | METHOD       | SEVERITY
17         | 2026-02-19T10:00:16  | 12.45       | CUSUM        | HIGH
18         | 2026-02-19T10:00:17  | 8.32        | PAGE_HINKLEY | MEDIUM
```

## Algorithms

- **CUSUM**: Tracks cumulative sum of deviations from running mean. Detects sustained shifts.
- **Page-Hinkley**: Monitors difference between observed values and their running mean. Sensitive to gradual drift.

Both run simultaneously; drift is flagged when either detector triggers.
