# Battle Spectator (BATTLE-004)

Self-contained receipt-backed spectator UI + Pixi race engine for Battle.

**Canonical location:** `skills/battle/spectator/` (not `ux-lab`).

## Scripts

```bash
npm install
npm run typecheck   # TypeScript
npm test            # Vitest unit tests
npm run prove:pixi  # Live Pixi route sanity (requires host on BATTLE_HOST)
npm run prove:receipt-replay  # 6 receipt requirements (requires host)
```

Full local gate from battle skill root: `./run.sh prove-spectator`

See `HOST_INTEGRATION.md` for ux-lab wiring.
