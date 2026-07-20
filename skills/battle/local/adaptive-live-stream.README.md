# Battle-004 adaptive-lineage live stream — how to run

The spectator "Live" view (`#battle/live`) streams the **real** adaptive-lineage
Docker-replay console (`RED_EXPLOIT_CONFIRMED` on the vulnerable target, the
blue-patch `UnsafeArchivePath` traceback on the defended target) into the Agent
Detail pane via SSE.

## Reproduce the served fixture

The live fixture is derived (not hand-authored) from two real artifacts:

- base shell:  `spectator/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json`
- real capture: `local/adaptive-lineage-capture-verify/capture/capture-events.jsonl` (18 events: 6 stdout / 6 stderr / 6 packet)

```bash
cd skills/battle
python3 local/derive_adaptive_live_fixture.py
# -> spectator/public/battle-fixtures/battle-004-adaptive-live/battle.normalized_ux_fixture.json
#    (validated in-process via build_live_transport_source; container /workspace paths normalized)
```

## Start the SSE server (ephemeral — must be restarted per machine/session)

```bash
cd skills/battle
uv run --project "$PWD" python -m battle_skill.cli serve-live-transport \
  --fixture spectator/public/battle-fixtures/battle-004-adaptive-live/battle.normalized_ux_fixture.json \
  --battle-id battle-004 --host 127.0.0.1 --port 18765
```

Verify:

```bash
curl -s http://127.0.0.1:18765/healthz            # -> status PASS, event_count 54
# frames seq 25-41 carry payload.source_event.output.stdout_excerpt = "RED_EXPLOIT_CONFIRMED"
```

Then open `http://localhost:3002/#battle/live?engine=pixi&battle=battle-004`,
select a lane (e.g. `Archive Escape red-1`), open the Agent Detail **Live** tab.

## Known-not-done (for the successor)

- Streaming + fun codenames live only on `#battle/live`. The `#battle/receipt`
  mockup race view still shows static Docker-replay/lifecycle evidence and
  generic lane names — it does not subscribe to the live bus.
- Pre-existing failures in `spectator/src/engine/battle-lane-variant-map.test.ts`
  (from the constant-sprite-lock change) are unaddressed.
- `skills/battle/skills/` is a mis-rooted run-artifact tree (untracked scratch);
  safe to `git clean -fd skills/battle/skills`.
