---
name: ux-lab
description: >
  Shared chat UX package for agent-facing surfaces. Use when mounting,
  migrating, auditing, or preserving the unified chat shell, memory-turn
  adapters, evidence disclosure, and production chat renderer used by SPARTA,
  Watch, final-site, and PersonaPlex.
metadata:
  short-description: Shared agent chat UX package and migration contract
provides:
  - shared-chat-ui
  - chat-surface-contracts
  - memory-turn-adapters
composes:
  - best-practices-react
  - review-design
  - watch
  - pdf-lab
  - personaplex
complies:
  - best-practices-skills
  - best-practices-react
  - best-practices-design
taxonomy:
  - frontend
  - chat-ux
  - migration
---

# ux-lab Skill

## Purpose

This skill owns the shared ux-lab chat UI package so the chat surfaces are versioned with the agent-skills ecosystem instead of living only inside `pi-mono/ux-lab`.

Use this skill when a project agent needs to mount, modify, audit, or migrate the unified chat UX used by:

- SPARTA Explorer slide-over chat
- Watch report agent pane
- PDF Lab standalone skill UI reference
- final-site/chat
- PersonaPlex voice/persona chat

## Source authority

The shared chat source was extracted from:

```text
${HOME}/workspace/experiments/pi-mono/packages/ux-lab/src/components/shared-chat/
```

The creation bundle identifies commit `b98746993` as the committed pi-mono source state. Treat this as an extraction + import relocation. Do not redesign or rewrite the components during the relocation.

## Package layout

```text
skills/ux-lab/
  SKILL.md
  ui/
    package.json
    tsconfig.json
    index.ts
    SharedChatShell.tsx
    ComplianceChatWell.tsx
    ThinkingTrace.tsx
    MessageFooter.tsx
    PersonaPlexChatWell.tsx
    thinkingTraceHelpers.ts
    memory-turn/
      MemoryTurnAdapter.ts
      SpartaComplianceAdapter.ts
      WatchChatAdapter.ts
      PersonaPlexAdapter.ts
      adapterRegistry.ts
      index.ts
```

## Mount contract

Production chat surfaces should import from the skill package rather than keeping local copies:

```ts
import { SharedChatShell } from '@agent-skills/ux-lab-ui'
```

`pi-mono/packages/ux-lab` should remain a thin Vite shell that aliases `@agent-skills/ux-lab-ui` to:

```text
../../../agent-skills/skills/ux-lab/ui
```

Project-specific product UX belongs with the owning skill. PDF Lab's product
interface is self-contained at:

```text
../../../agent-skills/skills/pdf-lab/ui
```

`ux-lab` may link to or shell that route, but it must not become the source
authority for PDF Lab product components or API bridges.

## UX invariants

- `SharedChatShell` is the canonical wrapper.
- `MemoryTurnAdapter` is the adapter seam.
- `ComplianceChatWell` is the single production renderer.
- `ThinkingTrace` renders reasoning/evidence disclosure.
- `MessageFooter` renders on every assistant turn.
- PersonaPlex production traffic must not route to a separate PersonaPlex grid/CSS renderer.
- Watch must keep its existing backend endpoint.
- PDF Lab must keep its standalone skill UI under `skills/pdf-lab/ui`.
- SPARTA must keep scope/depth controls in the host shell.
- Preserve existing `data-qid` values when migrating imports.
- Use lucide icons only. Do not add Google Material Symbols or bespoke icon fonts.

## Validation

Minimum validation after import relocation:

```bash
cd ${HOME}/workspace/experiments/agent-skills/skills/ux-lab/ui
npm run typecheck

cd ${HOME}/workspace/experiments/pi-mono/packages/ux-lab
npm run typecheck
npm run build
```

Then perform live surface checks:

1. SPARTA Explorer slide-over chat loads and can send a compliance turn.
2. Evidence-case turns show shield disclosure, not generic thinking copy.
3. Watch report pane has one composer and still posts to `/api/projects/watch/question`.
4. PersonaPlex mode renders through `ComplianceChatWell`, not `PersonaPlexChatWell`.

## Rollback

If a production surface fails after the relocation, revert only the pi-mono import/alias changes first. Keep the skill package in place unless the extracted source itself is proven invalid.
