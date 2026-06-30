# PATCH_PLAN — ux-lab Skill Self-Containment

This patch plan assumes the delivered zip is unpacked at repo root for `agent-skills`.

## 1. Add skill files

Add the full delivered tree:

```text
skills/ux-lab/SKILL.md
skills/ux-lab/ui/README.md
skills/ux-lab/ui/package.json
skills/ux-lab/ui/tsconfig.json
skills/ux-lab/ui/index.ts
skills/ux-lab/ui/ChatWell.tsx
skills/ux-lab/ui/SharedChatShell.tsx
skills/ux-lab/ui/ComplianceChatWell.tsx
skills/ux-lab/ui/ThinkingTrace.tsx
skills/ux-lab/ui/MessageFooter.tsx
skills/ux-lab/ui/PersonaPlexChatWell.tsx
skills/ux-lab/ui/thinkingTraceHelpers.ts
skills/ux-lab/ui/PERSONAPLEX_CHATWELL_DEPRECATION.md
skills/ux-lab/ui/memory-turn/MemoryTurnAdapter.ts
skills/ux-lab/ui/memory-turn/SpartaComplianceAdapter.ts
skills/ux-lab/ui/memory-turn/WatchChatAdapter.ts
skills/ux-lab/ui/memory-turn/PersonaPlexAdapter.ts
skills/ux-lab/ui/memory-turn/adapterRegistry.ts
skills/ux-lab/ui/memory-turn/index.ts
```

No behavior patch is required inside these files for the extraction. They are the skill-owned copy of the committed shared chat source.

## 2. Add Vite alias in pi-mono/ux-lab

File:

```text
${HOME}/workspace/experiments/pi-mono/packages/ux-lab/vite.config.ts
```

Patch shape:

```diff
+ import path from 'node:path'

  export default defineConfig({
+   resolve: {
+     alias: {
+       '@agent-skills/ux-lab-ui': path.resolve(__dirname, '../../../agent-skills/skills/ux-lab/ui'),
+     },
+   },
    plugins: [react()],
  })
```

If `resolve.alias` already exists, merge this key rather than replacing existing aliases.

## 3. Add TypeScript path alias in pi-mono/ux-lab

File:

```text
${HOME}/workspace/experiments/pi-mono/packages/ux-lab/tsconfig.json
```

Patch shape:

```diff
  {
    "compilerOptions": {
+     "baseUrl": ".",
+     "paths": {
+       "@agent-skills/ux-lab-ui": ["../../../agent-skills/skills/ux-lab/ui/index.ts"],
+       "@agent-skills/ux-lab-ui/*": ["../../../agent-skills/skills/ux-lab/ui/*"]
+     }
    }
  }
```

If `baseUrl` or `paths` already exist, merge entries without deleting existing project aliases.

## 4. Relocate imports from local shared-chat to skill package

Search:

```bash
cd ${HOME}/workspace/experiments/pi-mono/packages/ux-lab
grep -R "components/shared-chat\|../shared-chat\|./shared-chat" -n src
```

Patch common imports:

```diff
- import SharedChatShell from '../shared-chat/SharedChatShell'
+ import { SharedChatShell } from '@agent-skills/ux-lab-ui'

- import ComplianceChatWell from '../shared-chat/ComplianceChatWell'
+ import { ComplianceChatWell } from '@agent-skills/ux-lab-ui'

- import ThinkingTrace from '../shared-chat/ThinkingTrace'
+ import { ThinkingTrace } from '@agent-skills/ux-lab-ui'

- import MessageFooter from '../shared-chat/MessageFooter'
+ import { MessageFooter } from '@agent-skills/ux-lab-ui'

- import { createAdapterRegistry } from '../shared-chat/memory-turn'
+ import { createAdapterRegistry } from '@agent-skills/ux-lab-ui/memory-turn'
```

Do not change component props or adapter behavior during this pass.

## 5. Surface-specific notes

### SPARTA Explorer

Keep scope/depth controls in `SpartaExplorer.tsx`. Only relocate imports for `SharedChatShell` and memory-turn adapter types.

### WatchReportView

Keep Watch chrome, greeting, chips, selected-scene context, annotation tab callback, and endpoint contract. Only relocate imports for shared chat UI and Watch adapter types.

### final-site/chat

Route production chat to `SharedChatShell` from `@agent-skills/ux-lab-ui`. Keep any `PersonaPlexChatWell` import gallery-only.

## 6. Remove local source copy after all imports pass

After all imports resolve from the skill package:

```bash
rm -rf ${HOME}/workspace/experiments/pi-mono/packages/ux-lab/src/components/shared-chat
```

Then confirm:

```bash
cd ${HOME}/workspace/experiments/pi-mono/packages/ux-lab
grep -R "src/components/shared-chat\|from ['\"].*shared-chat" -n src || true
npm run typecheck
npm run build
```

## 7. Required evidence

Attach raw command output:

```text
agent-skills/skills/ux-lab/ui npm run typecheck
pi-mono/packages/ux-lab npm run typecheck
pi-mono/packages/ux-lab npm run build
surf check for :3002 chat surfaces
```

Do not mark the slice complete if only the skill package exists but pi-mono still imports local copies.
