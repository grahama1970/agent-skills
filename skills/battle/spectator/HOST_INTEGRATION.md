# Battle Spectator Host Integration

The spectator package is self-contained under `skills/battle/spectator/`. Host apps (e.g. `ux-lab`) mount it and serve static assets.

## Required static routes

| URL | Source |
|-----|--------|
| `/battle-fixtures/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json` | `skills/battle/local/battle-004-parent-spawn-pixi-replay/` |
| `/battle-sprites/pixijs/*` | `skills/battle/assets/sprites/pixijs/` |

Includes runner atlases (`blue_lizard.json`, …) and marker atlas `battle-race-atlas.png.json`.

Sync into a host `public/` tree:

```bash
cd skills/battle
./scripts/sync-host-battle-static.sh /path/to/host/public
```

## Vite host alias (ux-lab example)

```ts
"@agent-skills/battle-spectator": resolve(__dirname, "../../../agent-skills/skills/battle/spectator/src"),
```

Resolve spectator dependencies from the host `node_modules` when loading via `@fs`:

```ts
"sonner": resolveWorkspaceModule("sonner"),
"pixi.js": resolveWorkspaceModule("pixi.js"),
"pixi-viewport": resolveWorkspaceModule("pixi-viewport"),
"motion": resolveWorkspaceModule("motion"),
"@radix-ui/react-slot": resolveWorkspaceModule("@radix-ui/react-slot"),
// ... other @radix-ui/* used by spectator/ui/*
```

## App id

Default action registrations use `battle-spectator`. Hosts may override:

```tsx
<BattleSpectatorRoot appId="ux-lab">...</BattleSpectatorRoot>
```

## Proof commands (from spectator/)

```bash
npm run typecheck
npm test
BATTLE_HOST=http://127.0.0.1:3012 npm run prove:pixi
BATTLE_HOST=http://127.0.0.1:3012 npm run prove:receipt-replay
```

Or run the Battle skill orchestrator: `./run.sh prove-spectator`


## Battle audio (UX9 Genesis intro)

Serve the original round-intro MIDI from the spectator public tree:

```bash
ln -sfn /path/to/agent-skills/skills/battle/spectator/public/battle-audio \
  /path/to/ux-lab/public/battle-audio
```

URL:

```text
/battle-audio/battle-004-round-intro.mid
```

This is an original CC0-style Battle composition for Genesis-like round intros. It is not a Sega VGM dump.
