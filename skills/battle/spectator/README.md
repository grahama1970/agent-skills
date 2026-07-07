# Battle Spectator (BATTLE-004)

Self-contained receipt-backed spectator UI + Pixi race engine for Battle.

## Host responsibilities

The embedding app (e.g. `ux-lab`) must serve:

- `/battle-fixtures/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json`
- `/battle-sprites/pixijs/*` (symlink to `skills/battle/assets/sprites/pixijs`)

## Usage

```tsx
import { BattleSpectatorRoot, BattleSpectatorArena } from "@agent-skills/battle-spectator";

export function BattleHost() {
  return (
    <BattleSpectatorRoot>
      <BattleSpectatorArena />
    </BattleSpectatorRoot>
  );
}
```

## Proof

```bash
UX_LAB_UI_PORT=3012 node scripts/prove-battle-receipt-replay-6.mjs
```
