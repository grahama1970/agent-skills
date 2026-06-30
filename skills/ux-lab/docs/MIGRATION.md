# MIGRATION — Self-Contained ux-lab Skill

Slice id: `ux-lab-skill-self-containment`
Target repo path: `${HOME}/workspace/experiments/agent-skills/skills/ux-lab`
Host app path: `${HOME}/workspace/experiments/pi-mono/packages/ux-lab`

## Migration rule

This migration is an extraction + import relocation from committed pi-mono source state `b98746993`. Do not rewrite the shared chat components while moving them. The first safe migration should preserve behavior and only change import ownership.

## P0 — Land skill-owned UI package

Copy the delivered files into the agent-skills repo:

```bash
cd ${HOME}/workspace/experiments/agent-skills
mkdir -p skills/ux-lab
cp -R /path/to/solution/skills/ux-lab/* skills/ux-lab/
```

Expected files:

```text
skills/ux-lab/SKILL.md
skills/ux-lab/ui/index.ts
skills/ux-lab/ui/package.json
skills/ux-lab/ui/tsconfig.json
skills/ux-lab/ui/*.tsx
skills/ux-lab/ui/memory-turn/*.ts
```

Gate:

```bash
cd ${HOME}/workspace/experiments/agent-skills/skills/ux-lab/ui
npm install
npm run typecheck
```

Rollback: delete `skills/ux-lab/` if the package was not previously present, or revert the commit that adds it.

## P1 — Add pi-mono alias without removing local files

In `pi-mono/packages/ux-lab/vite.config.ts`, add a stable alias:

```ts
import path from 'node:path'

resolve: {
  alias: {
    '@agent-skills/ux-lab-ui': path.resolve(__dirname, '../../../agent-skills/skills/ux-lab/ui'),
  },
},
```

In `pi-mono/packages/ux-lab/tsconfig.json`, mirror the alias:

```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@agent-skills/ux-lab-ui": ["../../../agent-skills/skills/ux-lab/ui/index.ts"],
      "@agent-skills/ux-lab-ui/*": ["../../../agent-skills/skills/ux-lab/ui/*"]
    }
  }
}
```

Gate:

```bash
cd ${HOME}/workspace/experiments/pi-mono/packages/ux-lab
npm run typecheck
```

Rollback: remove the alias entries only.

## P2 — Relocate imports surface by surface

Replace imports that point to local shared-chat files with the skill package import.

Primary replacement:

```diff
- import SharedChatShell from '../shared-chat/SharedChatShell'
+ import { SharedChatShell } from '@agent-skills/ux-lab-ui'
```

For adapter imports:

```diff
- import { SpartaComplianceAdapter } from '../shared-chat/memory-turn'
+ import { SpartaComplianceAdapter } from '@agent-skills/ux-lab-ui/memory-turn'
```

Recommended order:

1. SPARTA Explorer slide-over imports.
2. Watch report pane imports.
3. final-site/chat imports.
4. PersonaPlex gallery/reference imports.

Gate after each surface:

```bash
npm run typecheck
npm run build
```

Rollback: restore the single surface import that failed. Do not revert the whole skill package.

## P3 — Remove local pi-mono shared-chat copies

Only after P2 proves every production import resolves from the skill package, remove local duplicates:

```bash
cd ${HOME}/workspace/experiments/pi-mono/packages/ux-lab
rm -rf src/components/shared-chat
```

Gate:

```bash
grep -R "components/shared-chat" -n src || true
grep -R "from ['\"].*shared-chat" -n src || true
npm run typecheck
npm run build
```

Expected grep result: no production imports from local `src/components/shared-chat`.

Rollback: restore `src/components/shared-chat` from pi-mono commit `b98746993` and keep the alias in place for the next attempt.

## P4 — Live surface checks

Run live checks only after type/build pass:

1. Vite dev server serves ux-lab at port `3002` without resolver errors.
2. SPARTA Explorer slide-over sends a compliance turn.
3. SPARTA evidence-case turn uses evidence disclosure.
4. Watch pane has one composer and posts to `/api/projects/watch/question`.
5. PersonaPlex mode routes through `SharedChatShell → ComplianceChatWell`.

Closure gate:

```text
G1 skills/ux-lab/ui/index.ts barrel exports all shared-chat components: PASS
G2 pi-mono imports SharedChatShell from skill package: PASS
G3 Vite :3002 chat surfaces load without errors: PASS
G4 skills/ux-lab/SKILL.md documents UI package and mount contract: PASS
```

Do not claim closure from mocked import checks alone.
