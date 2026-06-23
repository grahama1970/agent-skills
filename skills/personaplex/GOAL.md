# PersonaPlex Goal (Immutable)

PersonaPlex is working as expected when:

## 1. Live Voice Session — End to End, No Fixtures

A human speaks into a microphone. Embry responds. Every step uses real services:

1. **Deepgram ASR** captures `speech_final=true` from live microphone audio
2. **Turn gate** increments `turn_id`, closes output, fences stale work
3. **Memory intent** classifies the transcript, returns route + tools + recall_profile
4. **Recall / evidence case** runs real queries against the memory daemon (`http://127.0.0.1:8601`)
5. **PersonaPlex GPU inference** (`LMGen.step(...)`) generates grounded speech
6. **Persistence upsert** writes the canonical turn record to `conversation_history`
7. **Session compaction** updates rolling summaries and CAS session head

Receipts for all 7 steps exist with `real_*` flags all `true`.

## 2. Visual Verification Surface

A running UI (SPARTA Chat in `$ux-lab` or SPARTA Explorer React) shows:

| Signal | Where | What the human sees |
|--------|-------|---------------------|
| Transcript received | Chat panel | User text appears after Deepgram final |
| Intent route | Tool trace | "intent → COMPLIANCE (0.94)" |
| Recall | Tool trace | "recall → 3 items (BM25 0.82, dense 0.91)" |
| Evidence case | Tool trace | "evidence-case → can_answer=true, route=/answer" |
| PersonaPlex response | Chat panel | Embry's text/audio appears |
| Upsert | Tool trace | "upsert → conversation:session:000003 → 201" |
| Gate state | Status bar | "gate: OPEN | queue: 0" |

No tool trace row shows `real_*=false`, `fallback_used=true`, or `deterministic_fixture`.

## 3. Deterministic Safety Net

All deterministic tests still pass:
```
PYTHONPATH="$PWD/skills/personaplex/scripts:${PYTHONPATH:-}"
python3 -m unittest discover -s skills/personaplex/tests -v
# Ran N tests, OK
```

## Scope

This goal covers `skills/personaplex/` and `reviews/personaplex-deepgram/`.
It does not cover Orpheus TTS training, persona profile authoring, or production deployment.
