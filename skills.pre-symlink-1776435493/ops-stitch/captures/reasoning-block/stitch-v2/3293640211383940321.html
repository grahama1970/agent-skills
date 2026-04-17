# Reasoning Block — Shared Chat Component Design Brief

## Device
Desktop (1920x1080 minimum)

## Who
**Brandon Bailey** — SPARTA cybersecurity analyst. Asks questions in chat across all Embry OS projects (SPARTA Explorer, Binary Explorer, Embry Terminal). Needs to see the evidence trail behind every answer without leaving the conversation.

## What
A **reasoning block** that renders inline in the shared EmbryChat between the user's question and the agent's answer. It shows the evidence case pipeline results — gates, recall, drift, source traceability — as a progressive disclosure component with 3 levels of detail.

## Visual Identity — Three Distinct Blocks
The chat has three visually separate message types. They must look DIFFERENT from each other:

### 1. User Message (existing)
- Right-aligned bubble
- Dark background (#1a1a1a card)
- User's question text

### 2. Reasoning Block (NEW — this is what we're designing)
- Centered, full-width within chat column
- Distinct from both user and agent messages
- Left border in accent purple (#7c3aed) — this is the machine's evidence trail
- Background: slightly different tone (#0f1218 — between bg and bgCard)
- Collapsible — shows Level 0 by default, expands on click
- NOT a chat bubble. It's a structured data card.

### 3. Agent Response (existing)
- Left-aligned, flush with chat edge
- No container/border
- Natural language synthesis of the reasoning

## Progressive Disclosure (3 Levels)

### Level 0 — Verdict Line (always visible, 32px height)
One line showing the outcome. Click anywhere to expand to Level 1.
```
[●] SATISFIED (A+) · 7/7 gates · DE-0007, CWE-300 · 12 sources     ▾
```
Components:
- Verdict glow dot (green/amber/red)
- Verdict text + grade badge
- Gate fraction (e.g. 7/7)
- Control IDs (monospace, truncated if >3)
- Source count
- Expand chevron (▾)

If drift detected, add a drift indicator:
```
[●] SATISFIED→INCONCLUSIVE · 5/7 gates · DE-0007 · DRIFT ⚠     ▾
```

### Level 1 — Reasoning Summary (click to expand, ~120px)
Shows the pipeline steps as a horizontal or compact vertical chain. Click any step to drill to Level 2.
```
┌─────────────────────────────────────────────────────────────┐
│ [●] SATISFIED (A+) · 7/7 gates · DE-0007                   │
│                                                             │
│  ✓ topic  ✓ recall  ✓ ground  ✓ bridge  ✓ semantic  ✓ decompose  ✓ lean4  │
│                                                             │
│  Recall: 12 results (3 controls, 5 QRAs, 4 chunks)         │
│  Drift: no change (last checked 2h ago)                     │
│  Sources: 3 Requirements · 2 Tables · 1 Figure              │
└─────────────────────────────────────────────────────────────┘
```
Components:
- Gate chain as horizontal dots (✓/✗) with gate names — like existing GateChain but HORIZONTAL and compact
- Recall summary line (count + breakdown by collection)
- Drift status line (no change / verdict changed with old→new)
- Source traceability summary (count by asset_type with colored badges)
- Each section clickable to drill to Level 2

### Level 2 — Full Detail (drill into any section)
Expanding a section from Level 1 shows the full data inline:

**Gates expanded**: Vertical GateChain (existing component) with pass/fail detail text per gate
**Recall expanded**: RecallCard (existing component) with source badges and debug scores
**Drift expanded**: Side-by-side before/after — previous verdict + gate chain vs current, with diff highlighting (green=still pass, red=flipped to fail)
**Sources expanded**: Traceability chunks grouped by asset_type (Requirement, Table, Figure, Text) with doc_id:page references and text excerpts

Only ONE section expands at a time (accordion pattern) to keep the chat scrollable.

## Design System
Same NVIS MIL-STD-3009 dark theme:
- Background (reasoning block): #0f1218 (slightly blue-shifted from #141414)
- Left border: #7c3aed (accent purple) — 3px solid
- Border: rgba(255, 255, 255, 0.08) — subtler than card borders
- Green: #00ff88 (pass/satisfied), Amber: #ffaa00 (inconclusive), Red: #ff4444 (fail/not_satisfied)
- Gate dots: 14px circles with glow
- Text: #e2e8f0 (primary), #64748b (secondary)
- Font: System monospace for IDs/gates/metrics, system sans for prose
- Lucide icons: ChevronDown, ChevronRight, Shield, CheckCircle, XCircle, AlertTriangle, TrendingDown, FileText, Table2, Image

## Interaction Details
- Level 0 → Level 1: click anywhere on the verdict line
- Level 1 → Level 2: click on a specific section (Gates, Recall, Drift, Sources)
- Level 2 → Level 1: click the section header again (toggle)
- Level 1 → Level 0: click the verdict line again (collapse all)
- Click a control ID anywhere: fires onNavigateToControl callback (navigates to matrix cell in SPARTA Explorer)
- Click a source chunk: fires onNavigateToSource callback (navigates to datalake viewer)

## Context: How It Appears in Chat Flow
```
┌─────────────────────────────────────────────┐
│                                    [User]   │
│          Why did DE-0007 fail?     ████████  │
│                                             │
│  ┌─ REASONING ──────────────────────────┐   │
│  │ [●] INCONCLUSIVE (C) · 5/7 gates    │   │
│  │     DE-0007, CWE-300 · 8 sources    │   │
│  │                                      │   │
│  │  ✓ topic ✓ recall ✓ ground          │   │
│  │  ✓ bridge ✗ semantic ✗ decompose    │   │
│  │  ✓ lean4                            │   │
│  │                                      │   │
│  │  Drift: satisfied → inconclusive ⚠  │   │
│  │  Sources: 2 Req · 1 Table · 1 Fig   │   │
│  └──────────────────────────────────────┘   │
│                                             │
│  [Agent]                                    │
│  DE-0007 (Defense Evasion: Rootkit          │
│  Detection) is currently INCONCLUSIVE       │
│  because the semantic relation and          │
│  decomposition gates failed. The F-36       │
│  firmware spec references CWE-300 but       │
│  the requirement text doesn't explicitly    │
│  address rootkit detection mechanisms...    │
│                                             │
└─────────────────────────────────────────────┘
```

## What NOT to Design
- No standalone Evidence Case Lab view (that's a separate ops tool)
- No separate workspace panel — this is INLINE in chat messages
- No settings or configuration UI
- No mobile layout
- No animation beyond expand/collapse transitions (150ms ease)

## Existing Components to Reuse (render inside Level 2)
- GateChain.tsx (84 lines) — vertical gate timeline with status dots
- RecallCard.tsx (103 lines) — collapsible recall results with debug scores
- ThreatMatrixCard.tsx — compact coverage summary

## Data Shape (what the backend returns per message)
```json
{
  "verdict": "inconclusive",
  "grade": "C",
  "gates_passed": 5,
  "gates_total": 7,
  "gate_summary": "PASS: topic; PASS: recall; PASS: ground; PASS: bridge; FAIL: semantic; FAIL: decompose; PASS: lean4",
  "control_ids": ["DE-0007", "CWE-300"],
  "tier": "T0",
  "drift": { "old_verdict": "satisfied", "new_verdict": "inconclusive", "timestamp": "2026-04-01T16:12:44Z" },
  "recall_count": 12,
  "recall_breakdown": { "sparta_controls": 3, "sparta_qra": 5, "datalake_chunks": 4 },
  "source_traceability": { "Requirement": 2, "Table": 1, "Figure": 1 }
}
```

## Inspirations
- Claude.ai thinking block (collapsible, visually distinct from user/assistant)
- GitHub Copilot Chat reasoning steps
- Datadog trace waterfall (progressive detail)
- Keep it compact — this lives in a chat column, not a full-screen dashboard
