Fix SPARTA Explorer ChatWell to send speech_final to PersonaPlex WS. ChatTab.tsx has ChatWell + PersonaPlexVoiceTracePanel but handleSend uses piChat.send() instead of PersonaPlex protocol. Add WebSocket send alongside existing handler. golden_state_server at ws://127.0.0.1:8788/ws accepts {"type":"speech_final","session_id":"...","text":"...","persona_id":"embry","turn_id":1}. Zip: personaplex-p11-wire-chatwell-solution.zip

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260623T205513Z:7167f62b>>>

Do not print anything after that marker.
