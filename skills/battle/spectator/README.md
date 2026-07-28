# Battle Spectator (BATTLE-004)

Self-contained receipt-backed spectator UI + Pixi race engine for Battle.

**Canonical location:** `skills/battle/spectator/` (not `ux-lab`).

## Scripts

```bash
npm install
npm run build       # Vite standalone source build
npm run preview     # Serve the built Battle spectator locally
npm run typecheck   # TypeScript
npm test            # Vitest unit tests
npm run prove:source-build  # Build, serve, and run test-interactions
npm run prove:pixi  # Live Pixi route sanity (requires host on BATTLE_HOST)
npm run prove:receipt-replay  # 6 receipt requirements (requires host)
```

Full local gate from battle skill root: `./run.sh prove-spectator`
Focused source-build gate from battle skill root: `./run.sh prove-spectator-source-build`

See `HOST_INTEGRATION.md` for ux-lab wiring.
