# @agent-skills/ux-lab-ui

Self-contained shared chat UI package for ux-lab surfaces.

This directory is the canonical agent-skills home for shared chat UI components
used by skill-owned surfaces.

## Public imports

```ts
import {
  SharedChatShell,
  ComplianceChatWell,
  ThinkingTrace,
  MessageFooter,
  SpartaComplianceAdapter,
  WatchChatAdapter,
  PersonaPlexAdapter,
} from '@agent-skills/ux-lab-ui'
```

Memory turn internals are also exported when a host surface needs direct adapter control:

```ts
import { createAdapterRegistry, type MemoryTurnAdapter } from '@agent-skills/ux-lab-ui/memory-turn'
```

## Contract

- `SharedChatShell` is the canonical wrapper.
- `ComplianceChatWell` is the only production message renderer.
- `ThinkingTrace` owns trace disclosure visuals.
- `MessageFooter` renders for every assistant turn.
- `MemoryTurnAdapter` provides the adapter seam for SPARTA, Watch, and PersonaPlex.
- No Google Material Symbols are used; lucide icons are the only icon dependency.

## Typecheck

```bash
cd agent-skills/skills/ux-lab/ui
npm ci
npm run typecheck
```
