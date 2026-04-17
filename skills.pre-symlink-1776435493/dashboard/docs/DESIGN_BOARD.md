# Embry OS Development Dashboard — Design Board

## NVIS MIL-STD-3009 Style Guide (Non-Negotiable)

| Token         | Hex       | RGB            | Semantic                          |
|---------------|-----------|----------------|-----------------------------------|
| `NVIS_GREEN`  | `#00ff88` | (0, 255, 136)  | Healthy, nominal, ownship         |
| `NVIS_RED`    | `#ff4444` | (255, 68, 68)  | Hostile, failed, critical         |
| `NVIS_AMBER`  | `#ffaa00` | (255, 170, 0)  | Warning, degraded                 |
| `NVIS_BLUE`   | `#44aaff` | (68, 170, 255) | Friendly, info, labels            |
| `NVIS_WHITE`  | `#c8c8c8` | (200, 200, 200)| Text labels                       |
| `NVIS_DIM`    | `#505050` | (80, 80, 80)   | Muted, secondary, disabled        |
| `NVIS_YELLOW` | `#ffe600` | (255, 230, 0)  | Unknown contact                   |

**Canonical source**: `streamdeck/src/streamdeck/widgets/nvis_base.py`
**Background**: Dark terminal (`#080a0c` equivalent)
**Border rule**: Panel border color = worst status within panel (green if all OK, amber if degraded, red if any critical)

## Round 1: Current State Assessment (2026-03-09)

### Layout (6 panels, 2x2+2)
```
┌────────────────────────────────────────────────┐
│          Embry OS Dev Dashboard  UTC           │ 3h
├───────────────────────┬────────────────────────┤
│    Daemons (3/3)      │    Cascade             │ 10h
│  embry-agent  OK      │  Models: 4 val 2 cls   │
│  embry-memory OK      │  Shadow: 72%           │
│                       │  LLM calls: 142        │
├───────────────────────┼────────────────────────┤
│  Chutes Quota         │  Project Progress      │ 10h
│  ████████░░ 4200/5000 │  Tests: 847 passing    │
│  Balance: $2.15       │  Skills: 227 (94%)     │
│  Slots: 3/5           │  Gaps: 0 crit, 2 high  │
├───────────────────────┴────────────────────────┤
│  Active Tasks (2)                              │ 6h
│  dogpile-search   ████████████░░░ 12/16 (75%) │
│  learn-datalake   ██░░░░░░░░░░░░░  4/50  (8%) │
├────────────────────────────────────────────────┤
│  Skill Health  HEALTHY  227 skills  0 critical │ 3h
└────────────────────────────────────────────────┘
```

### Issues
1. **No subagent visibility** — create-subagent runs Claude/Codex/Gemini tasks with zero dashboard presence
2. **No cost tracking** — ops-costs aggregates Chutes/OpenAI/Google but isn't shown
3. **Monitor reports invisible** — 9 collectors include monitor_reports but no panel renders them
4. **Wasted space** — Daemons panel uses 10h for 2-3 items. Cascade is sparse.
5. **No backend health** — which CLI backends are up? Last response time?
6. **Fixed height** — panels don't adapt to content

## Round 1: Proposed Redesign (8 panels, 3-tier)

### Design Decisions
- **Merge Daemons + Skill Health into a single "System Health" row** — both are status indicators, save vertical space
- **Add Subagents panel** — shows per-backend (Claude/Codex/Gemini) active tasks, success rate, tokens
- **Add Cost Tracker panel** — aggregate spend from ops-costs (Chutes + API keys)
- **Keep Chutes + Cascade** — both are dense enough to justify their space
- **Widen Active Tasks** — show current_item, elapsed time, backend info
- **Add Monitor Alerts row** — surface worst monitor-* findings (currently collected but hidden)

### New Layout
```
┌─────────────────────────────────────────────────────────────────┐
│  EMBRY OS  ▪  2026-03-09 14:23 UTC  ▪  3 daemons  ▪  227 skills │ 3h header
├──────────────────┬──────────────────┬───────────────────────────┤
│ Daemons (3/3)    │ Subagents        │ Cost Tracker              │ 8h
│ embry-agent  ●OK │ Claude   2 run   │ Today:  $1.42             │
│ embry-memory ●OK │ Codex    0 idle  │ Chutes: $0.85 (4200/5000) │
│ embry-scillm ●OK │ Gemini   1 run   │ OpenAI: $0.57             │
│                  │ 14 done  1 err   │ MTD:    $38.20            │
├──────────────────┴──────────────────┼───────────────────────────┤
│ Cascade + LLM                       │ Chutes Quota              │ 8h
│ 4 val  2 cls  1 reg  Shadow: 72%    │ ████████░░ 4200/5000      │
│ LLM 24h: 142 calls  Avg: 1.2s      │ $2.15 bal  Reset: 6h 12m  │
│ Cache: 68%  T1=40% T2=35% T3=25%   │ Slots: 3/5  ●●●○○        │
├─────────────────────────────────────┴───────────────────────────┤
│ Active Tasks (3)                                                │ 8h
│ dogpile-search    ████████████░░░ 12/16 (75%)  23.4s  synthesis │
│ learn-datalake    ██░░░░░░░░░░░░░  4/50  (8%)  5m12s  pdf #42  │
│ create-subagent   ████████████████  1/1 (100%) 3.2s   claude/s  │
├─────────────────────────────────────────────────────────────────┤
│ Monitors: ●workstation OK  ●memory OK  ●skills OK  ●codebase ▲ │ 3h
└─────────────────────────────────────────────────────────────────┘
```

### Color Rules (NVIS)
- **Panel borders**: Reflect worst-status within (●OK=green, ▲warn=amber, ✕fail=red)
- **Progress bars**: NVIS_BLUE for fill, NVIS_DIM for empty
- **Daemon dots**: ● colored per status
- **Subagent backends**: row colored by status (green=active, dim=idle, red=errors)
- **Cost numbers**: green if under budget, amber if >80%, red if over
- **Monitor strip**: inline status dots, only show non-OK in detail

### Typography
- Headers: `bold NVIS_WHITE`
- Labels: `NVIS_BLUE`
- Values: `NVIS_WHITE`
- Status indicators: colored by semantic meaning
- Muted/secondary: `NVIS_DIM`

---

## Round 2: Implementation Complete (2026-03-09)

### What Was Built

**Files changed**: `tui.py` (309 → 429 lines), `collectors.py` (349 → 481 lines)

#### New Collectors (`collectors.py`)
| Collector | Source | Data |
|-----------|--------|------|
| `collect_subagent_state()` | `~/.pi/task-monitor/create-subagent_task_state.json` | Per-backend (Claude/Codex/Gemini) running/completed/errored counts |
| `collect_cost_data()` | `ops-costs report --json` | Today/MTD spend by provider |

Total collectors: 11 (was 9). `monitor_reports` was already collected but never rendered — now surfaced.

#### New Panels (`tui.py`)
| Panel | Row | Content |
|-------|-----|---------|
| `create_subagents_panel()` | Row 1 | Per-backend status with run/idle/err, NVIS border = worst status |
| `create_cost_panel()` | Row 1 | Today + per-provider + MTD, green/amber/red thresholds ($5/$10) |
| `create_monitors_panel()` | Footer | Compact status dots for all `monitor-*` reports |

#### Layout Change
```
OLD (6 panels, 2x2+2):                 NEW (7 panels, 3-tier):
┌──────────┬──────────┐               ┌────────┬──────────┬──────────┐
│ Daemons  │ Cascade  │ 10h           │Daemons │Subagents │  Cost    │ 8h
├──────────┼──────────┤               ├────────┴──────────┼──────────┤
│ Chutes   │ Project  │ 10h           │ Cascade + LLM (2x)│  Chutes  │ 8h
├──────────┴──────────┤               ├───────────────────┴──────────┤
│ Active Tasks        │ 6h            │ Active Tasks                 │ 8h
├─────────────────────┤               ├──────────────────────────────┤
│ Skill Health        │ 3h            │ Monitors (●dots strip)       │ 3h
└─────────────────────┘               └──────────────────────────────┘
```

#### What Was Eliminated (and why)
- **Project Progress panel** — skill count moved to header; test/gap data was rarely glanced at (low signal density). Can be restored if needed.
- **Skill Health panel** — replaced by monitors strip which covers skill health AND 8 other monitors in the same 3h row. More info, less space.

#### Header Upgrade
Old: `Embry OS Dev Dashboard  2026-03-09 14:23 UTC`
New: `EMBRY OS ▪ 2026-03-09 14:23 UTC ▪ 2/2 daemons ▪ 228 skills`

### Key Decisions
1. **Cascade gets 2x width** — it was the densest panel (models + shadow + LLM + cache + tiers). Now has room to breathe.
2. **Cost thresholds are hardcoded** — Today: green <$5, amber <$10, red >=10. MTD: green <$50, amber <$80, red >=80. Should these be configurable?
3. **Monitors strip shows ALL monitors** — not just non-OK. Every `~/.pi/monitor-*/report.json` gets a dot. Green/amber/red/dim per health status.
4. **Subagent panel reads TaskClient state** — wired via `server.py` changes in Round 1 (creates `create-subagent_task_state.json`).

---

## Round 3: Design Decisions (2026-03-09)

Interview conducted via `/interview` → Claude Code AskUserQuestion. All 8 questions resolved.

### Information Density
- [x] **Project Progress** → **Move to `/program-state`**. Test counts and gap counts change slowly — nightly cadence fits better than 5-second dashboard refresh. Not restored as a panel.
- [x] **Task detail** → **Elapsed + current_item only**. Backend is redundant with Subagents panel. Shows: `dogpile-search ████░░ 12/16 (75%) 23.4s synthesis`
- [ ] **Chutes slot visualization** — Design board proposed `●●●○○` dots. Currently just `N/5 slots` text. (Deferred — low priority)

### New Data Sources (ALL approved)
- [x] **Backend health** — ping test for claude/codex/gemini CLI availability. New collector + surface in dashboard.
- [x] **Git status** — current branch, uncommitted changes, last commit age. Dev context panel or header enrichment.
- [x] **D-Bus worker pool** — worker count, queue depth, circuit breaker state from `org.embry.Agent`. Surface in Daemons or separate panel.
- [x] **Disk/NVMe health** — from `monitor-workstation` probes. Surface key metrics in monitors strip.

### Layout & Visibility
- [x] **Always show all panels** — consistent layout means muscle memory works. Empty panels show `(idle)` or `(none)`. No conditional hiding.

### Cost Thresholds
- [x] **Config file** — read thresholds from `~/.pi/dashboard/config.json`. Spending patterns will change as more backends come online. Simple and transparent.

### Output Modes (ALL approved)
- [x] **JSON API** — `./run.sh status --json` for programmatic consumers (Discord bot, web UI, Stream Deck)
- [x] **Snapshot mode** — `./run.sh snapshot` renders one frame to stdout (no live loop) for cron/logging
- [x] **Stream Deck page** — render dashboard summary to a Stream Deck page (NVIS palette matches)
- [x] **Discord webhook** — post dashboard snapshot to Discord channel on schedule

### `/program-state` Skill Design
- [x] **Scope**: pi-mono + active projects only — skip archived/inactive, scan only those with recent commits. Not tied to full `~/.agent_skills_targets` registry.
- [x] **Categories**: 5 buckets — **Broken** (failing tests, down daemons, critical alerts) | **Missing** (unresolved deps, skills without sanity.sh) | **In Progress** (active tasks, open PRs, recent commits) | **Aspirational** (design board TODOs, unimplemented triggers) | **Completed** (passing tests, healthy monitors, compliant skills)
- [ ] **Schedule**: Nightly via `/scheduler` + on-demand via `/program-state report`
- [ ] **Dashboard integration**: Feed into monitors strip or header summary
- [ ] **Composes**: `/project-state` + `/monitor-skill-health` + `/monitor-codebase` + design board scanning

---

## Round 4: Implementation Queue

Priority order based on Round 3 decisions:

### P1 — Dashboard Enhancements (next session)
1. **Task detail**: Add elapsed time + current_item to Active Tasks panel
2. **Cost config**: Read thresholds from `~/.pi/dashboard/config.json` (with fallback to current hardcoded values)
3. **Backend health collector**: `collect_backend_health()` — ping claude/codex/gemini CLIs
4. **Git status collector**: `collect_git_status()` — branch, dirty files, last commit

### P2 — New Collectors
5. **D-Bus pool collector**: `collect_dbus_pool()` — query `org.embry.Agent` for worker/queue state
6. **Disk health**: Surface NVMe % from `monitor-workstation` report in monitors strip

### P3 — Output Modes
7. **JSON API**: `./run.sh status --json` — serialize all collector data to JSON
8. **Snapshot mode**: `./run.sh snapshot` — one-shot Rich render to stdout

### P4 — `/program-state` Skill
9. Build new skill with 5-bucket categorization
10. Wire into `/scheduler` for nightly runs

### P5 — Integrations (later)
11. **Stream Deck page**: Compose with `/create-streamdeck-page`
12. **Discord webhook**: Compose with `/ops-discord`
