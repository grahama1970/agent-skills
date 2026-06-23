# Fix: Wire SPARTA Explorer ChatWell to send speech_final to PersonaPlex golden_state_server

## Problem

The SPARTA Explorer at `http://localhost:3002/#sparta-explorer` has a `ChatWell`
chat component and a `PersonaPlexVoiceTracePanel` below it. The tool trace panel
IS connected to the PersonaPlex golden_state_server at `ws://127.0.0.1:8788/ws`
but receives NO events because `ChatWell` sends queries through `piChat.send()`
(Pi backend), not through the PersonaPlex pipeline.

## Files

- `pi-mono/packages/ux-lab/src/components/sparta/explorer/ChatTab.tsx`
  - Line 12: `import { usePiChat } from '@pi-chat-adapter/hook'`
  - Line 25: `import { PersonaPlexVoiceTracePanel } from './PersonaPlexVoiceTracePanel'`
  - Line 244: `piChat.send(query, type)` — current send handler
  - Line 566: `<ChatWell onSend={handleSend} .../>`
  - Line 594: `<PersonaPlexVoiceTracePanel className="mt-4" />` — already below ChatWell

- `pi-mono/packages/ux-lab/src/components/sparta/explorer/PersonaPlexVoiceTracePanel.tsx`
  - Thin wrapper around `ToolCallTracePanel`
  - Default wsUrl: `ws://127.0.0.1:8788/ws` (matches running golden_state_server)
  - Subscribes to channel `personaplex_tool_trace` with events: `grounding_stage_*`,
    `memory_tool_call_*`, `intent_tool_calls`

## Required Fix

Modify `ChatTab.tsx` `handleSend` so that in addition to (or instead of)
`piChat.send(query, type)`, it also sends a `speech_final` message to the
PersonaPlex golden_state_server WebSocket at `ws://127.0.0.1:8788/ws`:

```json
{"type":"speech_final","session_id":"...","text":"<query>","persona_id":"embry","turn_id":<n>}
```

This will cause the golden_state_server to process through:
1. Memory intent -> emits tool_trace events
2. Recall/evidence -> emits tool_trace events
3. Returns response -> ChatWell shows reply
4. PersonaPlexVoiceTracePanel shows all tool traces in real-time

The golden_state_server is already running at `ws://127.0.0.1:8788/ws`.

## Constraints

- Keep existing ChatWell styling and SPARTA Explorer layout
- Keep PersonaPlexVoiceTracePanel where it is (below ChatWell)
- Use OpenCode as the backend (not Pi)
- The WebSocket connection should persist for the session lifetime
- Tool trace panel already auto-connects — just need to send speech_final messages

## Deliverable

One solution zip with the updated `ChatTab.tsx` file (and any other files needed
for the wiring). If additional files (hooks, context, types) are needed, include
them.

Zip: `personaplex-p11-wire-chatwell-solution.zip`
