# PersonaPlex 8771 Static ChatWell Parity Fix

## Goal

Replace the static review page at:

`reviews/personaplex-deepgram/personaplex-interactive-chat.html`

with a standalone HTML/JS page that visually follows the shared-chat ChatWell / PersonaPlexChatWell design without requiring the broken React production build.

## Files

| File | Purpose |
| --- | --- |
| `reviews/personaplex-deepgram/personaplex-interactive-chat.html` | Standalone ChatWell-style UI, mic button, Deepgram streaming, golden_state_server WebSocket, Embry response rendering, real_* tool trace rows. |
| `reviews/personaplex-deepgram/serve_personaplex_interactive_chat.py` | Threaded static server for port 8771 that serves repo root and injects runtime env into the HTML. |
| `tests/personaplex-deepgram/test_static_chat_solution.py` | Deterministic static checks for no pasted-key UI, env injection, required UX classes, and required real_* flags. |
| `fixtures/personaplex-deepgram/sample_tool_trace_event.json` | Representative golden_state_server event used as a protocol fixture. |

## Runtime flow

1. Browser loads `/reviews/personaplex-deepgram/personaplex-interactive-chat.html`.
2. `serve_personaplex_interactive_chat.py` injects `window.__ENV__` from process env / local shell env files.
3. The page opens `ws://127.0.0.1:8788/ws` by default and sends a best-effort subscription for `personaplex_tool_trace`.
4. The user can type, or press the mic button.
5. Mic flow:
   - `navigator.mediaDevices.getUserMedia({ audio: true })`
   - `MediaRecorder` chunks audio as `audio/webm;codecs=opus` where available
   - chunks stream to Deepgram WebSocket using the injected key
   - Deepgram `speech_final` triggers a golden_state_server payload:

```json
{
  "type": "speech_final",
  "topic": "personaplex_tool_trace",
  "session_id": "static-chat-...",
  "text": "...",
  "transcript": "...",
  "persona_id": "embry",
  "turn_id": 1,
  "source": "voice"
}
```

6. The golden_state_server response stream updates ChatWell-style messages and `real_*` tool trace rows.

## Env injection contract

The HTML file contains no committed Deepgram secret and no key input field. The server injects:

- `DEEPGRAM_API_KEY`
- `VITE_DEEPGRAM_API_KEY` as the same effective value for compatibility
- `PERSONAPLEX_WS_URL` / `GOLDEN_STATE_WS_URL`, default `ws://127.0.0.1:8788/ws`
- `PERSONAPLEX_PERSONA_ID` / `PERSONA_ID`, default `embry`
- `PERSONAPLEX_SESSION_ID`, optional
- `DEEPGRAM_WS_URL`, optional override

Process env wins. As a convenience for the documented local setup, the server also reads `.env`, `.env.local`, `~/.zshrc`, `~/.bashrc`, and `~/.profile` for simple `export KEY=value` assignments. It prints only whether the key is present, never the secret.

## Commands

Run from the agent-skills repository root after applying the files:

```bash
export DEEPGRAM_API_KEY="$DEEPGRAM_API_KEY"
python3 reviews/personaplex-deepgram/serve_personaplex_interactive_chat.py --host 127.0.0.1 --port 8771
```

Open:

```text
http://127.0.0.1:8771/reviews/personaplex-deepgram/personaplex-interactive-chat.html
```

Run static checks:

```bash
python3 -m pytest tests/personaplex-deepgram/test_static_chat_solution.py
```

## Rollback

Restore the previous static page and remove the server script:

```bash
git checkout -- reviews/personaplex-deepgram/personaplex-interactive-chat.html
rm -f reviews/personaplex-deepgram/serve_personaplex_interactive_chat.py
rm -f tests/personaplex-deepgram/test_static_chat_solution.py
rm -rf fixtures/personaplex-deepgram
```

## Known limitations

- The HTML/JS page is a standalone parity implementation, not a React bundle. This is intentional because the production React build is pre-broken by missing `public/pdf-lab-pages/*` files.
- The browser must receive a Deepgram key to open Deepgram's WebSocket. The key is injected at request time and not committed, but it is necessarily visible to the browser session that uses it.
- WebSocket event parsing is deliberately tolerant of several likely golden_state_server event shapes. It does not require server protocol changes.
- Real live proof still requires the local services to be running: golden_state_server at 8788, memory daemon, PersonaPlex GPU container, and a valid Deepgram key.
