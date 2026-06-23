# Prompt Improvements for Future P11 Requests

A stronger future creation bundle would include:

1. The full current `ChatTab.tsx` body, not only line references.
2. The expected ChatWell `onSend` signature and TypeScript type names.
3. Whether the Pi backend response should remain visible, be hidden, or be replaced by PersonaPlex replies.
4. A captured WebSocket trace from `golden_state_server.py` for one successful `speech_final` turn.
5. The ux-lab test command actually used in the monorepo, such as `pnpm test`, `npm test`, or `vitest`.

The current bundle was still sufficient because it identified the exact source seam: `piChat.send(query, type)` in `ChatTab.tsx`.
