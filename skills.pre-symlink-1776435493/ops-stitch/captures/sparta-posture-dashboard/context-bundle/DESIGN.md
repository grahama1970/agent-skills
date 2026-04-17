# SPARTA Security Posture Dashboard — Design Brief for Stitch

## Device
Desktop (1920x1080 minimum, fluid up to 2560x1440)

## Who
**Brandon Bailey** — SPARTA cybersecurity analyst at a manufacturing plant. Former USAF, now consulting on F-36 program security posture. Checks this dashboard every morning before standup. Needs to know in 10 seconds: "did anything get worse overnight?"

## What
A new view inside SPARTA Explorer (tab or full-page) that shows the **security posture at a glance** — not the raw matrix (that's the existing Grid view), but the operational health of the threat landscape as it changes over time.

## Design System
- **Theme**: NVIS MIL-STD-3009 dark (military night vision compatible)
- **Background**: `#141414` (bg), `#1a1a1a` (cards), `#0b1220` (deep)
- **Border**: `rgba(255, 255, 255, 0.13)`
- **Accent**: `#7c3aed` (purple)
- **Semantic colors**: Green `#00ff88` (satisfied/good), Amber `#ffaa00` (inconclusive/warning), Red `#ff4444` (not satisfied/critical)
- **Text**: `#e2e8f0` (primary), `#64748b` (secondary), `#334155` (muted)
- **Font**: System monospace for IDs/metrics, system sans for prose
- **Glow dots**: Small colored circles with box-shadow glow (used throughout existing UI)
- See `current-state.png` for existing SPARTA Explorer reference

## Layout
Three-column layout, top-to-bottom priority:

```
+-------------------------------------------------------------+
|  HEADER: Posture score + last updated + pipeline heartbeat  |
+------------------+------------------+-----------------------+
|                  |                  |                       |
|  DRIFT ALERTS    |  COVERAGE RING   |  DISCREPANCIES        |
|  (threat deltas) |  (by tactic)     |  (req vs table)       |
|                  |                  |                       |
+------------------+------------------+-----------------------+
|                                                             |
|  CRITICAL PATH: Top 3 weakest attack chains (mini graph)    |
|                                                             |
+-------------------------------------------------------------+
|                                                             |
|  TIMELINE: Verdict changes over time (sparkline per tactic) |
|                                                             |
+-------------------------------------------------------------+
```

## Panes

### 1. Header Bar (48px height, sticky top)
- **Posture Score**: Single number 0-100 derived from evidence coverage. Formula: (satisfied / total_techniques) * 100. Current: (38/216) * 100 = 18%. Show as large number with color (green >70, amber 40-70, red <40).
- **Last Updated**: Relative timestamp ("12m ago") from most recent evidence case timestamp
- **Pipeline Heartbeat**: 3 dots — learn-datalake (green if ran in last 24h), evidence pipeline (green if evidence_cases updated in last 24h), embedding service (green/red)
- **Datalake selector**: Dropdown (same as existing ThreatMatrix header) — "F-36 Lightning II", "CMMC Assessment"

### 2. Drift Alerts (left column, ~400px)
- **Title**: "Security Drift" with count badge
- List of threat-delta records from evidence_cases where type=threat-delta
- Each card: Red/amber left border (red if satisfied->not_satisfied, amber if satisfied->inconclusive). Control ID (monospace, bold, linked). old_verdict -> new_verdict with colored arrows. Reason text (1 line, truncated). Relative timestamp.
- If no deltas: muted "No drift detected" with green checkmark
- **Current data**: DE-0007: satisfied -> inconclusive

### 3. Coverage Ring (center column, ~400px)
- Donut/ring chart showing verdict distribution across all SPARTA techniques
- Segments: Satisfied (green), Inconclusive (amber), Not Satisfied (red), No Evidence (muted)
- Center text: total technique count (216) and coverage % (18%)
- Below ring: 9 tactic mini-bars (same as existing TacticStrip but vertical list with labels)
- Each tactic bar shows: name, satisfied/total, thin progress bar
- **Current data**: 38 satisfied, 13 inconclusive, 4 not_satisfied, 161 no evidence

### 4. Discrepancies (right column, ~400px)
- **Title**: "Discrepancies" with severity count badges (4 high, 1 medium)
- List of discrepancy records from evidence_cases where type=discrepancy
- Each card: Severity badge (HIGH red, MEDIUM amber, LOW dim). Control ID (monospace). Summary text (1 line). Expand to show: requirement_claim, table_reality, recommendation.
- Sorted by severity desc
- **Current data**: DE-0002 (medium), DE-0003.08 (high), EX-0012.07 (high), + 2 more

### 5. Critical Path (full width, ~200px height)
- Mini version of LemmaGraph showing the top 3 weakest attack chains
- Red/amber nodes only, no green
- Node labels are control IDs
- Edge labels are relationship methods
- Click a node -> navigates to matrix cell detail flyout
- **Current data**: /api/critical-path returns 45 nodes, 30 edges, 200 failing

### 6. Timeline (full width, ~150px height)
- Sparkline per tactic (9 lines) showing verdict count over time
- X-axis: last 30 days. Y-axis: count of satisfied controls per tactic
- When a line drops, something got worse — immediately visible
- If insufficient history, show "Collecting data..." placeholder

## Interactions
- **Click drift alert** -> navigates to SPARTA Explorer matrix tab, selects that control, opens detail flyout
- **Click discrepancy** -> expands to show requirement vs table text + recommendation
- **Click coverage ring segment** -> filters matrix to that verdict category
- **Click critical path node** -> navigates to matrix cell
- **Hover any metric** -> tooltip with exact numbers

## What NOT to Design
- No login/auth screens
- No settings page
- No mobile layout
- No Grafana-style drag-and-drop panel editor
- No real-time streaming — this is poll-on-mount + refresh button

## Existing Components to Reuse
- **GlowDot**: Small colored circle with glow (box-shadow: 0 0 6px color)
- **Framework badge**: Tiny colored pill with framework name (SPARTA, NIST, CWE, etc.)
- **Grade badge**: A+/A/B/C/F with color coding
- **TacticStrip**: Horizontal bar of 9 tactics with progress bars

## Inspirations
- Grafana single-stat panels (big number + sparkline)
- GitHub Security Overview (coverage donut + alert list)
- Datadog Security Posture Management (drift timeline)
- Keep it information-dense but scannable — Brandon has 30 seconds before standup
