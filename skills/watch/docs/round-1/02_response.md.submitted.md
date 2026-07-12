# Clarify, Then Create Self-Contained Watch Skill UI

I've attached a creation bundle zip containing:
1. **GOAL.md** — full convergence goal with acceptance gates
2. **HANDOFF.md** (SKILL.md) — current skill documentation

Watch is a video analysis skill with scene detection, transcript extraction, and emotion analysis. Its UI currently lives in ux-lab (separate repo). The goal is to make it self-contained so the UI is versioned alongside the skill's Python backend.

## What exists already

The UI components were already copied into `skills/watch/ui/`:
- `components/WatchReportView.tsx` — scene search table + Orpheus annotation sidebar + SharedChatShell chat
- `SharedChatShell.tsx`, `ComplianceChatWell.tsx`, `ThinkingTrace.tsx`, `MessageFooter.tsx`
- `memory-turn/` — adapter seam (MemoryTurnAdapter, WatchChatAdapter, SpartaComplianceAdapter, PersonaPlexAdapter)

## What needs to be done

1. **Barrel export** — create `skills/watch/ui/index.tsx` that exports all components
2. **Self-contained imports** — fix imports that reference `../sparta/` (RecallCard, GateChain, ThreatMatrixCard) which only exist in ux-lab. Either copy them in, replace with inline rendering, or stub them.
3. **`package.json`** — dependencies for standalone build (react, lucide-react)
4. **`tsconfig.json`** — TypeScript config for the UI package
5. **Update WatchReportView.tsx** so it compiles without ux-lab's sparta dependencies
6. **MIGRATION.md** — steps to switch ux-lab from `src/components/watch/` to `skills/watch/ui/`
7. **prompt_improvements.md**

## Key files for context

The watch skill's UI is at `/home/graham/workspace/experiments/agent-skills/skills/watch/ui/`. The Express API serves watch data at endpoints like:
- `GET /api/projects/watch/report` — watch report JSON
- `GET /api/projects/watch/static/watch-frames/` — frame images
- `POST /api/projects/watch/question` — chat Q&A
- `GET/POST /api/projects/watch/orpheus-segments` — emotion annotation segments

## Constraints

- No changes to Express API routes (keep in ux-lab for now)
- Keep the visual design matching the Watch mockup (split pane: search table left, chat/annotation right)
- Preserve lucide icons (no Material Symbols)
- Do NOT return a review verdict. Return either questions or the solution zip.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260624T182137Z:752be201>>>

Do not print anything after that marker.
