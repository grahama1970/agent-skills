---
name: monitor-workstation
description: >
  Nightly workstation health monitor. Enforces "no artifacts on NVMe" rule,
  detects cache bloat, checks drive health, and alerts on threshold breaches.
  Composes existing ops-* skills — never reimplements their logic.
  Uses /analytics + /create-figure for visual reports.
triggers:
  - monitor workstation
  - check workstation health
  - nightly workstation check
  - nvme storage check
  - artifact violation check
  - is the home drive full
  - workstation health
provides:
  - workstation-health-monitoring
  - nvme-artifact-enforcement
  - cache-bloat-detection
composes:
  - ops-workstation
  - ops-arango
  - ops-docker
  - ops-claude
  - monitor-claude
  - analytics
  - create-figure
  - memory
  - scheduler
  - agentic-evals
taxonomy:
  - monitoring
  - operations
  - infrastructure
disciplines:
  - observability-operations
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# monitor-workstation

Nightly workstation health monitor. Runs 13 probes to enforce storage rules, detect cache bloat, and verify drive health.

## Usage

```bash
# Run all probes (markdown table output)
./run.sh check

# JSON output with figure_data for /dashboard
./run.sh check --json

# Auto-fix safe issues (cache pruning)
./run.sh check --autofix

# Visual report via /analytics → /create-figure
./run.sh check --report

# Register nightly 4am job
./run.sh register-nightly
```

## Probes

| ID  | Name              | Checks                                          | Thresholds              |
|-----|-------------------|--------------------------------------------------|-------------------------|
| W01 | nvme-usage        | `/` disk usage                                   | >85% warn, >95% critical |
| W02 | nvme-artifacts    | Models/backups/media on NVMe that belong on 12TB | Any match = WARN        |
| W03 | cache-bloat       | uv, huggingface, pip, npm cache sizes            | uv>20GB, hf>30GB, pip/npm>2GB |
| W04 | experiment-growth | Experiment dirs on NVMe >50GB                    | Any >50GB = WARN        |
| W05 | arango-backup     | Backup freshness + path on 12TB                  | >48h = WARN             |
| W06 | docker-reclaimable| Docker system reclaimable space                  | >50GB = WARN            |
| W07 | zombie-processes  | Zombie Claude/Chromium/Python processes           | Any = WARN              |
| W08 | drive-health      | SMART status of NVMe + HDD                       | Any non-PASSED = FAIL   |
| W09 | tmp-bloat         | Orphaned skill temporary directories             | Orphans = FAIL         |
| W10 | inotify-watches   | Kernel watch budget                              | See probe thresholds   |
| W11 | agent-cli-freshness | Installed agent CLI versions                    | Stale = WARN           |
| W12 | skill-symlinks    | Copied skills, wrong/broken links, pre-symlink leftovers | Any match = WARN; scan errors = FAIL |
| W13 | gpu-container-capability | GPU-attached containers actually have working CUDA inside | Any dead-CUDA container = FAIL; unprobeable (no python3/torch) = WARN |

## One Canonical Skills Directory

`~/workspace/experiments/agent-skills/skills` is the only canonical skills tree.
Existing agent skill locations must be symlinks to it, not copied directories.
W12 checks home and immediate project roots under `~/workspace` and
`~/workspace/experiments`, without traversing project symlinks or copied trees.
Missing agent skill locations are not created automatically.

`./run.sh fix skill-symlinks` removes owned `skills.pre-symlink-*` directories
only beside a valid canonical `skills` symlink. It does not archive copies on
either drive. Wrong links and live copied `skills` directories remain warnings
for explicit reconciliation; a missing canonical tree prevents any deletion.
Removal is read back before it is reported as applied.

## Autofix (--autofix)

Cache pruning is auto-executed:
- `uv cache prune`
- `pip cache purge`
- `npm cache clean --force`

Docker prune is logged as a recommendation, never auto-executed.
W09 also removes orphaned temporary workspaces, W11 updates stale agent CLIs,
and W12 removes pre-symlink leftovers under the safeguards above.

## State

- Latest report: `~/.pi/monitor-workstation/report.json`
- History: `~/.pi/monitor-workstation/history.jsonl`
