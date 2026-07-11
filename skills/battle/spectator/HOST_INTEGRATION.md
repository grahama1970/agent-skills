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

## Music M1 fixture

Public normalized music fixture:

```text
/battle-fixtures/battle-004-music-runtime/battle.normalized_music_fixture.json
```

Route: `#battle/music?fixture=battle-004-music-runtime`

Promoted assets:

```text
/battle-audio/promoted/v1/<promotion-id>/
```

If the host serves `public/battle-fixtures` via per-fixture symlinks (ux-lab), add:

```bash
ln -sfn <agent-skills>/skills/battle/spectator/public/battle-fixtures/battle-004-music-runtime \
  <ux-lab>/public/battle-fixtures/battle-004-music-runtime
```

`public/battle-audio` should already cover promoted OGGs when it points at the spectator `battle-audio` tree.


## Music M2 readiness (deferred — backend)

UX will consume live music only via public contracts, never composer/create-midi working dirs:

```text
battle.live_event.v1 carrying normalized schedule entries
  OR refreshed battle.normalized_music_fixture.v1
+ /battle-audio/promoted/v1/<promotion-id>/
```

Required for M2 UX turn-on:
- `composer_live` may be true only when promotion/schedule receipts say so
- death/victory/next-arena remain NOT_EMITTED without authorizing receipts
- schedule entries keep `playback_class: promoted`
- actor-focus stays `local_preview` / `semantic_authority: false`

UX will not implement Music Director execution.

## Audio production pass (deferred — content)

Replace provisional GM/TimGM6mb OGGs in-place under the same promoted URLs:

```text
/battle-audio/promoted/v1/<promotion-id>/*.ogg
```

Bindings, schedule entry IDs, and receipt authorization must not change. MIDI remains source material. Until that pass lands, assets remain provisional renders; UX must not claim final mix or speaker-mastered production.


## Critical layout rule (do not regress)

Critical spectator geometry (**header**, **facts row**, **main rails**, **score block**) must live in **real CSS classes** in `battle-race.css` / `battle-proof-card.css`.

Do **not** trust Tailwind arbitrary utilities (`grid-cols-[…]`, `max-w-[…]`) for those paths until proven live with `getComputedStyle` — the `@agent-skills/battle-spectator` alias can leave arbitrary classes unscanned, collapsing grids to one column (score/title collision).

Gate regressions with:

```bash
npm run prove:layout-geometry
```

That prove asserts column counts, no score/title overlap, no nav collisions, race card fills center height, and Difficulty is unclipped. `mocked: no`, `live: yes`.
