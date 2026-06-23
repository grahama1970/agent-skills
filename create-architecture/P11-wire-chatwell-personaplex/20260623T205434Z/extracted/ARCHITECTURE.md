# PersonaPlex P11 — Wire SPARTA Explorer ChatWell to PersonaPlex speech_final

## Goal

The SPARTA Explorer ChatWell currently sends text through the normal Pi chat backend with `piChat.send(query, type)`. The PersonaPlex voice trace panel below it is already connected to `ws://127.0.0.1:8788/ws`, but it receives no turn-level events unless the golden_state_server receives a PersonaPlex turn message.

This overlay adds the missing bridge: each ChatWell final text turn is mirrored to the golden_state_server as:

```json
{"type":"speech_final","session_id":"...","text":"<query>","persona_id":"embry","turn_id":1}
```

The existing `piChat.send(query, type)` call remains in place so current ChatWell UI behavior is not removed.

## Files

- `pi-mono/packages/ux-lab/src/components/sparta/explorer/personaplexSpeechFinalClient.ts`
  - Browser WebSocket client for the golden_state_server JSON control channel.
  - Keeps a session-lifetime WebSocket singleton.
  - Persists `session_id` and monotonic `turn_id` in `sessionStorage`.
  - Sends only JSON `speech_final`; it does not use the PersonaPlex container binary audio stream.

- `pi-mono/packages/ux-lab/src/components/sparta/explorer/ChatTab.tsx.p11.patch`
  - Human-readable minimal diff for `ChatTab.tsx`.

- `skills/personaplex/scripts/apply_p11_wire_chatwell.py`
  - Deterministic source patcher for the real checkout.
  - Adds the import and inserts the PersonaPlex send immediately after `piChat.send(query, type)`.
  - Idempotent: a second run leaves the file unchanged.

- `skills/personaplex/tests/test_p11_wire_chatwell_patch.py`
  - Local deterministic tests for patching and protocol contract.

- `pi-mono/packages/ux-lab/src/components/sparta/explorer/__tests__/personaplexSpeechFinalClient.test.ts`
  - Vitest-style browser client test for projects using the ux-lab test runner.

## Commands and expected exit codes

From repo root after unpacking this overlay:

```bash
python3 skills/personaplex/tests/test_p11_wire_chatwell_patch.py
# expected: exit 0

python3 skills/personaplex/scripts/apply_p11_wire_chatwell.py --repo-root .
# expected: exit 0 when ChatTab.tsx contains piChat.send(query, type)
# expected: exit 2 if the known seam has drifted and a human needs to rebase the patch

bash skills/personaplex/sanity_p11_wire_chatwell.sh .
# expected: exit 0 after deterministic test + patch apply
```

Optional ux-lab test command, depending on the monorepo package manager configuration:

```bash
cd pi-mono/packages/ux-lab
npm test -- personaplexSpeechFinalClient
# expected: exit 0 in a configured ux-lab test environment
```

Manual live check:

1. Start `golden_state_server.py` so it listens at `ws://127.0.0.1:8788/ws`.
2. Start SPARTA Explorer at `http://localhost:3002/#sparta-explorer`.
3. Send a ChatWell message.
4. Confirm the PersonaPlexVoiceTracePanel receives `grounding_stage_*`, `intent_tool_calls`, and `memory_tool_call_*` events for the turn.

## Honesty boundary

This overlay does not claim a live PersonaPlex run in the artifact itself. The deterministic tests prove the client and source-patching behavior. Live proof requires the running local golden_state_server and browser UI.
