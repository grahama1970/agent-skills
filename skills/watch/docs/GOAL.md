# GOAL — Self-Contained Watch Skill UI

**Slice id:** `watch-ui-self-containment`
**Skill repo:** `/home/graham/workspace/experiments/agent-skills/skills/watch`
**UI source:** `skills/watch/ui/` (React TypeScript components)
**ux-lab:** `/home/graham/workspace/experiments/pi-mono/packages/ux-lab`
**Express API:** `http://127.0.0.1:3001` (Watch routes live here)

## Primary product question

Can the Watch skill own its own React UI components — scene search, Orpheus annotation, chat sidebar — so they are versioned alongside the skill's Python backend, while ux-lab becomes a thin shell that discovers and mounts skill UIs?

## Current state

| Component | Location | Status |
|-----------|----------|--------|
| `WatchReportView.tsx` (scene search + chat sidebar + annotation) | `skills/watch/ui/components/` | **COPIED** (not yet wired) |
| `SharedChatShell.tsx` + deps | `skills/watch/ui/` | **COPIED** (duplicated from ux-lab) |
| MemoryTurnAdapter seam | `skills/watch/ui/memory-turn/` | **COPIED** |
| Express API Watch routes | ux-lab server `:3001` | **LIVE** (unchanged) |
| Watch report data | `/mnt/storage12tb/media/watch-frames/` | **LIVE** |
| ux-lab mounts Watch from | `src/components/watch/WatchReportView.tsx` | **LIVE** (but should mount from skill) |
| Watch skill Python scripts | `skills/watch/scripts/` | **LIVE** |

## Target architecture

```text
agent-skills/skills/watch/
├── SKILL.md                    # documents skill + UI entrypoint
├── ui/
│   ├── index.tsx               # barrel export for all UI components
│   ├── components/
│   │   └── WatchReportView.tsx  # scene search + Orpheus annotation + chat
│   ├── SharedChatShell.tsx      # shared chat component (skill-owned copy)
│   ├── ComplianceChatWell.tsx
│   ├── MemoryTurnAdapter.ts     # adapter seam
│   └── ...
├── scripts/                    # Python backend (unchanged)
│   ├── cli.py
│   ├── scenes.py
│   ├── report.py
│   └── ...
└── docs/
    └── GOAL.md                 # this file

ux-lab (thin shell):
├── mounts Watch UI from `skills/watch/ui/`
└── provides Vite dev server + Express API host
```

## Acceptance gates

| # | Gate | Status (2026-07-18) |
|---|------|---------------------|
| G1 | Watch skill has `ui/index.tsx` barrel that exports all components | **DONE** — `ui/index.tsx` exists; `tsc --noEmit` covers `index.tsx`, `components/`, `memory-turn/`, `scripts/` and passes |
| G2 | ux-lab imports Watch UI from the skill instead of local copy | **SUPERSEDED / OPEN IN UX-LAB** — the skill now self-hosts its UI (`npm run dev:all`, `:3002/#watch`) so it no longer depends on ux-lab; ux-lab still lazy-imports its legacy `src/components/watch/` copy, which should be deleted or re-pointed at `skills/watch/ui/index.tsx` in a pi-mono change |
| G3 | Dev server serves Watch page without errors | **DONE (self-hosted)** — the skill's own Vite+Express (`dev:all`) serves `:3002/#watch`; earlier browser proofs recorded under `docs/architecture/generated/` |
| G4 | Scene search, annotation, chat sidebar render | **DONE (self-hosted)** — exercised by annotation/browser proofs; smoke tests cover session reducer, receipt replay, and broad handoff-stop projection |
| G5 | SKILL.md documents UI entry point and mount instructions | **DONE** — "UI Entry Point (Skill-Owned)" section in SKILL.md |

Import-path cleanup from the original delivery list is complete:
`WatchAgentPaneConverged.tsx` no longer imports from ux-lab's `../shared-chat/`
paths (fixed 2026-07-18).

## Non-goals

- Moving Express API routes out of ux-lab (future slice)
- Extracting shared-chat as an npm package (future slice)
- Rewriting Python scripts
- Changing the watch report data format

## Current file inventory (what WebGPT should work with)

### Watch UI components (already in `skills/watch/ui/`)

**Mountable components:**
- `components/WatchReportView.tsx` — scene search table + Watch sidebar with tab toggle (agent/annotation)
- `WatchAgentPaneConverged.tsx` — alternative slim wrapper

**Shared chat dependencies (copied from ux-lab):**
- `SharedChatShell.tsx` — mode toggle, adapter dispatch, internal state management
- `ComplianceChatWell.tsx` — message list + composer + ThinkingTrace + MessageFooter
- `ThinkingTrace.tsx` — per-branch thinking disclosure (shield/mic/sparkle)
- `MessageFooter.tsx` — per-branch footer with metadata
- `thinkingTraceHelpers.ts` — branch detection, icon mapping, disclosure parts
- `MarkdownRenderer.tsx` — markdown rendering for rich content
- `InlineEvidenceCase.tsx` — inline evidence case display
- `ToolAction.tsx` — tool action display
- `SpartaShieldIcon.tsx` — shield icon component
- `memory-turn/MemoryTurnAdapter.ts` — adapter interface, StreamingStep, collectMemoryTurn
- `memory-turn/WatchChatAdapter.ts` — Watch adapter, POSTs to `/api/projects/watch/question`
- `memory-turn/SpartaComplianceAdapter.ts` — SPARTA adapter
- `memory-turn/PersonaPlexAdapter.ts` — PersonaPlex adapter
- `memory-turn/adapterRegistry.ts` — registry for surface/mode routing
- `memory-turn/index.ts` — barrel exports

### Dependencies these components import (need resolution)

The components import from:
- `lucide-react` — icons (Mic, Shield, Sparkles, Search, Star, etc.)
- `react` — standard
- `../shared-chat/memory-turn/` — adapter types (already in ui/)
- `../sparta/query/RecallCard` — IN ux-lab only (needs resolution)
- `../sparta/query/GateChain` — IN ux-lab only
- `../sparta/query/ThreatMatrixCard` — IN ux-lab only
- `../sparta/shared/BuildingEvidenceCase` — IN ux-lab only

## What WebGPT should deliver in solution zip

1. **`skills/watch/ui/index.tsx`** — barrel export for all UI components
2. **`skills/watch/ui/package.json`** — dependencies (react, lucide-react) for standalone build
3. **`skills/watch/ui/tsconfig.json`** — TypeScript config for the UI package
4. **Updated `WatchReportView.tsx`** — fix import paths to resolve within the skill (not from ux-lab's `../sparta/`)
5. **Replace divergent imports** — `RecallCard`/`GateChain`/`ThreatMatrixCard` either:
   a. Copied into the skill's `ui/` directory, or
   b. Replaced with simpler inline rendering
   c. Stubbed as optional imports
6. **`MIGRATION.md`** — steps to switch ux-lab from local `src/components/watch/` to `skills/watch/ui/`
7. **`PATCH_PLAN.md`** — file-level edits
8. **`prompt_improvements.md`** — what to improve next round

## Required output format

One solution zip `watch-ui-self-containment-solution.zip` with:
- `MANIFEST.json` — file list with sha256
- All finished TypeScript/TSX source files
- `MIGRATION.md`
- `PATCH_PLAN.md`
- `prompt_improvements.md`

Do NOT return a review verdict. Return either numbered clarifying questions or the zip.
