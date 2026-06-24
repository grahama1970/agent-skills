# prompt_improvements — ux-lab Skill Self-Containment

## Better creation prompt for the project agent

```text
You are performing an extraction/import-relocation, not a rewrite.

Source authority:
- pi-mono commit: b98746993
- source directory: /home/graham/workspace/experiments/pi-mono/packages/ux-lab/src/components/shared-chat/

Target:
- /home/graham/workspace/experiments/agent-skills/skills/ux-lab/ui/

Required behavior:
1. Copy the committed shared-chat source into skills/ux-lab/ui without changing component behavior.
2. Add skills/ux-lab/SKILL.md documenting the mount contract.
3. Add ui/index.ts barrel exports for all shared-chat components and memory-turn adapters.
4. Add ui/package.json and ui/tsconfig.json.
5. Add a pi-mono alias @agent-skills/ux-lab-ui pointing to ../../../agent-skills/skills/ux-lab/ui.
6. Relocate pi-mono imports to @agent-skills/ux-lab-ui.
7. Only after type/build pass, remove the local pi-mono src/components/shared-chat copy.

Do not:
- Redesign the components.
- Add new chat CSS/layouts.
- Add Google Material Symbols.
- Change Watch endpoint contracts.
- Change SPARTA scope/depth controls.
- Route production PersonaPlex traffic to PersonaPlexChatWell.

Evidence required:
- git diff for extraction and import relocation
- npm run typecheck from skills/ux-lab/ui
- npm run typecheck from pi-mono/packages/ux-lab
- npm run build from pi-mono/packages/ux-lab
- grep proving pi-mono no longer imports local shared-chat copies
- live :3002 surf check
```

## Why this prompt is safer

The weak prompt pattern is: “move the chat components into a skill.” That invites a project agent to rewrite the UI package, reimplement adapters, or silently create a new duplicate chat path.

The safer wording pins the operation to:

- a source commit
- a source directory
- a target directory
- exact alias/import relocation
- a delete-local-copy gate
- raw evidence required for closure

## Reviewer checklist prompt

```text
Review only the extraction/import relocation. PASS requires evidence that:
1. skills/ux-lab/ui contains the shared-chat source and barrel exports.
2. pi-mono imports from @agent-skills/ux-lab-ui, not local src/components/shared-chat.
3. typecheck/build pass in the real repo.
4. Vite :3002 surfaces load.
5. no behavior rewrite or new chat renderer was introduced.

Return INSUFFICIENT_EVIDENCE if any raw command output or grep proof is missing.
```
