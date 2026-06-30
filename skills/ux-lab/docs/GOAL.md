# GOAL — Self-Contained ux-lab Skill

**Slice id:** `ux-lab-skill-self-containment`
**Skill repo:** `${HOME}/workspace/experiments/agent-skills/skills/ux-lab`
**Current source:** `${HOME}/workspace/experiments/pi-mono/packages/ux-lab/src/components/shared-chat/`

## Product question

Can ux-lab's shared chat components (SharedChatShell, ComplianceChatWell, ThinkingTrace, MessageFooter, MemoryTurnAdapter) live in `agent-skills/skills/ux-lab/` so they are versioned alongside the skills ecosystem, while pi-mono/ux-lab becomes a thin Vite shell that imports from the skill?

## What exists

| Component | Current location | Target |
|-----------|-----------------|--------|
| SharedChatShell | pi-mono/ux-lab/src/components/shared-chat/ | agent-skills/skills/ux-lab/ui/ |
| ComplianceChatWell | pi-mono/ux-lab/src/components/shared-chat/ | agent-skills/skills/ux-lab/ui/ |
| ThinkingTrace | pi-mono/ux-lab/src/components/shared-chat/ | agent-skills/skills/ux-lab/ui/ |
| MessageFooter | pi-mono/ux-lab/src/components/shared-chat/ | agent-skills/skills/ux-lab/ui/ |
| thinkingTraceHelpers | pi-mono/ux-lab/src/components/shared-chat/ | agent-skills/skills/ux-lab/ui/ |
| MemoryTurnAdapter seam | pi-mono/ux-lab/src/components/shared-chat/memory-turn/ | agent-skills/skills/ux-lab/ui/memory-turn/ |
| Watch UI | pi-mono/ux-lab/src/components/watch/ | agent-skills/skills/watch/ui/ (already done) |
| SpartaExplorer chat | pi-mono/ux-lab/src/components/sparta/ | agent-skills/skills/sparta/ui/ (future) |

## Why

The Watch project was lost because it only existed on disk in pi-mono with no git history. Moving skill-owned UIs into the skill repos means they're versioned alongside the backends, deployable independently, and protected by the skill's own git history.

## Acceptance gates

| # | Gate | Proof |
|---|------|-------|
| G1 | `agent-skills/skills/ux-lab/ui/index.ts` barrel exports all shared-chat components | tsc compiles |
| G2 | pi-mono/ux-lab imports SharedChatShell from `../../agent-skills/skills/ux-lab/ui/` | grep shows no local copies in pi-mono/src |
| G3 | Vite dev server at :3002 still serves chat surfaces without errors | surf check |
| G4 | SKILL.md documents the UI package and mount contract | file exists |

## What WebGPT should deliver

1. **`skills/ux-lab/SKILL.md`** — documents the skill
2. **`skills/ux-lab/ui/index.ts`** — barrel exports
3. **`skills/ux-lab/ui/package.json`** — dependencies
4. **`skills/ux-lab/ui/tsconfig.json`** — TypeScript config
5. **`MIGRATION.md`** — steps to switch pi-mono imports
6. **`PATCH_PLAN.md`** — file-level edits for pi-mono
7. **`prompt_improvements.md`**

Do NOT return a review verdict. Return either numbered clarifying questions or the solution zip.
