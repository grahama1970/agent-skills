---
name: ux-lab
description: React component workbench for building and previewing SPARTA Explorer UI with Vite HMR
triggers:
  - ux lab
  - component gallery
  - sparta explorer ui
  - preview component
  - build interface
  - design component
  - threat map ui
  - control table ui
provides:
  - ux-lab
composes:
  - create-styleguide
  - test-interactions
  - best-practices-react
  - memory
  - scillm
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
metadata:
  short-description: React component workbench with Vite HMR for SPARTA Explorer
  project-path: /home/graham/workspace/experiments/pi-mono/packages/ux-lab
taxonomy:
  - design
  - frontend
  - precision
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# ux-lab

React + Vite component workbench for building the SPARTA Explorer UI.
The agent edits `.tsx` files and sees changes instantly via Vite HMR at `localhost:3002`.

## What This Is

A **component gallery** where the project agent builds, previews, and iterates on
SPARTA Explorer components. Not a design tool — a development workbench.

**The agent's workflow:**
1. Edit a `.tsx` component file
2. Vite HMR updates the browser instantly
3. Human sees the change, gives course correction
4. Agent adjusts, repeat

## Architecture

```
localhost:3002  ← Vite dev server (React + HMR)
localhost:3001  ← Express API (proxies /memory to ArangoDB via Unix socket)
```

- **Frontend**: React 18 + TypeScript, inline styles using EmbryStyle tokens
- **Backend**: Express proxying `/api/memory/*` → embry-memory daemon at `/run/user/1000/embry/memory.sock`
- **Theme**: NVIS MIL-STD-3009 dark palette via `EmbryStyle.ts` tokens
- **No Tailwind** — inline style objects for zero-config component isolation

## File Structure

```
packages/ux-lab/
├── src/
│   ├── main.tsx                              # React entry
│   ├── App.tsx                               # Shell (top bar + gallery)
│   └── components/
│       ├── gallery/
│       │   ├── ComponentGallery.tsx           # Gallery with folder tree, search, variation tabs
│       │   └── sampleData.ts                 # Mock data for all components
│       └── sparta/
│           ├── common/EmbryStyle.ts           # NVIS token system
│           ├── threat-map/ThreatMap.tsx        # Tactic × technique heatmap
│           ├── tables/ControlTable.tsx         # Sortable/filterable control table
│           ├── query/ChatWell.tsx              # NL + AQL query interface
│           └── lemma-graph/LemmaGraph.tsx      # Relationship graph (SVG)
├── server/
│   └── index.ts                              # Express memory proxy
├── index.html
├── vite.config.ts
├── tsconfig.json
└── package.json
```

## EmbryStyle Tokens

All components use tokens from `src/components/sparta/common/EmbryStyle.ts`:

| Token | Value | Use |
|-------|-------|-----|
| `EMBRY.bg` | `#141414` | App background |
| `EMBRY.bgCard` | `#1a1a1a` | Card surfaces |
| `EMBRY.bgPanel` | `#151515` | Sidebar/toolbar |
| `EMBRY.bgDeep` | `#0e0e0e` | Inputs, deep wells |
| `EMBRY.border` | `rgba(255,255,255,0.13)` | All borders |
| `EMBRY.white` | `#e2e8f0` | Primary text |
| `EMBRY.dim` | `#64748b` | Secondary text |
| `EMBRY.green` | `#00ff88` | Nominal/healthy |
| `EMBRY.red` | `#ff4444` | Failed/critical |
| `EMBRY.amber` | `#ffaa00` | Warning |
| `EMBRY.blue` | `#3b82f6` | Info/selected |

**Framework colors** (`EMBRY.fw`):

| Framework | Color |
|-----------|-------|
| SPARTA | `#7c3aed` |
| ATT&CK | `#ff4444` |
| D3FEND | `#00ff88` |
| NIST | `#4a9eff` |
| CWE | `#ffaa00` |

## Adding a Component to the Gallery

1. Create component in `src/components/sparta/<folder>/<Name>.tsx`
2. Add mock data to `src/components/gallery/sampleData.ts`
3. Register in `ComponentGallery.tsx` registry:

```tsx
{
  id: 'my-component',
  name: 'MyComponent',
  folder: ['SPARTA Explorer', 'Category'],
  variations: ['default', 'filtered'],
  render: (v) => <MyComponent data={v === 'filtered' ? filtered : all} />,
}
```

## 3-Pane Waterfall Pattern

The composed Explorer Layout follows the evidence-case-viewer pattern:

| Pane | Width | Background | Content |
|------|-------|------------|---------|
| 1: Threat Overview | 30% | `#141414` | ThreatMap |
| 2: Evidence Hub | 35% | `#111111` | ControlTable + LemmaGraph |
| 3: Query & Synthesis | 35% | `#0c0c0c` | Integrity card + ChatWell |

Each pane scrolls independently. Section headers use colored pills + uppercase tracking text.
Top bar has a ThoughtTrace pipeline (Ingest → Resolve → Map → Verify → Score) with glow dots.

## Shared Component Pattern: Slide-Over Panels

When a component is accessed from multiple views, implement it as a **slide-over panel**
rather than a modal or page navigation. Slide-overs preserve context — the user sees the
triggering view behind the panel.

### Standard Slide-Over Spec
- **Width**: 480px
- **Background**: `EMBRY.bgDeep` (`#0e0e0e`)
- **Border**: 1px `EMBRY.border` left border
- **Animation**: slide in from right, 200ms ease-out
- **Close**: X button top-right, also Escape key
- **Scroll**: Panel body scrolls independently, header/footer pinned

### Pattern: One Component, Multiple Entry Points

```tsx
// Shared component — lives in src/components/<project>/common/
<DetailPanel itemId={id} onClose={() => setOpen(false)} />

// TableView — triggered by "Details" button on a row
<DetailPanel itemId={selectedRowId} onClose={closePanel} />

// GraphView — triggered by "Inspect" on a graph node
<DetailPanel itemId={nodeId} onClose={closePanel} />

// ListView — triggered by "Check" on a list item
<DetailPanel itemId={listItemId} onClose={closePanel} />
```

Each view's entry point passes different context, but the panel component is identical.
Document all entry points in the `component-manifest.json` under the shared component's
`used_by` field.

### When to Use Slide-Over vs Modal vs Page

| Pattern | Use When | Example |
|---------|----------|---------|
| **Slide-over** | User needs to see triggering view behind panel | Evidence case from threat matrix |
| **Modal** | Confirmation/destructive action, brief interaction | "Delete this evidence case?" |
| **Page navigation** | Full-screen workflow, no need for prior context | Settings, configuration |

## Commands

```bash
# Start dev server (Vite on :3002, Express on :3001)
cd packages/ux-lab && npm run dev

# Type check
npx tsc --noEmit

# Health check the API
curl http://localhost:3001/api/health

# Query memory through the proxy
curl http://localhost:3001/api/memory/search -X POST \
  -H 'Content-Type: application/json' \
  -d '{"query": "SPARTA techniques"}'
```

## Component Manifest (agent-readable)

**`component-manifest.json`** is the agent's structured context for the entire design system.
Read this file FIRST before editing any component. It contains:

- All component names, files, line counts, props, and data sources
- Token rules (what's allowed, what's forbidden)
- Composition relationships (which components go in which panes)
- Planned components not yet built
- Test status per component
- Gallery structure and sample data location

**After every component change**, update `component-manifest.json` to keep it current.
This is how the agent (and subagents) stay oriented across sessions.

### Token Enforcement Rules (from manifest)

1. NEVER use raw hex colors — always reference `EMBRY.*` tokens
2. NEVER use raw font sizes — use `label` (10px), `heading` (14px), `body` (13px) presets
3. All borders use `EMBRY.border`, never custom rgba values
4. Card surfaces use `card` preset, darker wells use `panel` preset
5. Framework-specific colors MUST come from `EMBRY.fw[framework]`
6. Status colors follow NVIS: green=nominal, red=critical, amber=warning, blue=info

## Agent Collaboration Protocol

### Direct editing (main agent)

1. **Read `component-manifest.json`** — understand what exists before touching anything
2. **Whole interface**: Edit `ComponentGallery.tsx` composed layouts
3. **Individual component**: Edit the specific component `.tsx` file
4. **Style tokens**: Edit `EmbryStyle.ts` for global changes
5. **Mock data**: Edit `sampleData.ts` for preview data
6. **Update manifest** — after any change, update `component-manifest.json`

### Subagent workflow (context protection)

For targeted changes that shouldn't pollute the main agent's context, use `/subagent-service`:

```
Main agent reads manifest → identifies needed change → spawns subagent with:
  - The specific component file path
  - The relevant section of component-manifest.json
  - Token rules from the manifest
  - The specific edit instruction

Subagent makes the change → main agent verifies via:
  - npx tsc --noEmit (type check)
  - manifest still accurate
  - human confirms via HMR preview
```

This keeps the main agent's context clean for orchestration while subagents handle
individual component edits, new component scaffolding, or data integration work.

### Course correction loop

The human watches `localhost:3002` and provides course corrections.
The agent (or subagent) adjusts files, Vite HMR applies changes in <100ms.

## What This Tracks

| Concern | Source of Truth | Skill |
|---------|----------------|-------|
| Component manifest | `component-manifest.json` | — |
| Design plan | `/plan` task file | `/plan` |
| Style guide | `EmbryStyle.ts` tokens | `/create-styleguide` |
| Best practices | Consulted before changes | `/best-practices-react` |
| Interaction testing | Run on components | `/test-interactions` |
| Data integration | `/api/memory/*` proxy | `/memory` |
| Targeted edits | Subagent dispatch | `/subagent-service` |

## Architecture Decisions (from /dogpile research 2026-03-13)

| Decision | Rationale |
|----------|-----------|
| Custom Vite workbench, not Storybook/Ladle | Full control over manifest format, no CSF overhead. Ladle validates this approach (335 Uber projects). |
| `component-manifest.json` over CSF stories | Agent-readable JSON is cheaper than parsing TSX. Mirrors Storybook MCP's Component Manifest pattern. |
| "Agent proposes, catalog constrains" (A2UI) | Agent only composes from registered manifest components. No arbitrary JSX generation. |
| Inline styles over Tailwind/CSS modules | Zero-config component isolation. Tokens enforced via `EMBRY.*` imports, not class names. |
| Vitest Browser Mode for future visual regression | `toMatchScreenshot()` with Playwright headless. No external service needed. |

## Remaining Work

- [ ] Connect components to real ArangoDB data via `/api/memory/*` proxy
- [ ] Replace static SVG LemmaGraph with D3 force-directed layout
- [ ] Build ControlDetail drill-down panel
- [ ] Build QRADetail view for individual Q/R/A triples
- [ ] Add DimensionCard for taxonomy bridge visualization
- [ ] Add IntegrityCard as standalone component (currently inline in gallery)
- [ ] Add Vitest browser mode for visual regression screenshots
