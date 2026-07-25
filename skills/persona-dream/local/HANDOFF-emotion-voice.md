# Handoff — persona-dream weighted-emotion voice (2026-07-25)

## Status: COMPLETE, verified live, merged to main on all three repos.

Chain delivered end-to-end:
`verdict/affect → memory.intent (tone + intensity weight) → chatterbox base render (exaggeration/cfg_weight) → audible tone`.

## Merged (heads verified 2026-07-25)
| Repo | main HEAD | Change |
|---|---|---|
| graph-memory-operator | 68cbe76 | `/intent` emits `intensity`+`valence` in voice_delivery (`src/graph_memory/service/app/_intent.py`, `_voice_delivery_for_intent` + `_VOICE_TONE_AFFECT_WEIGHT`) |
| chatterbox | 29952e9 | `/synthesize-emotion` base endpoint; `synthesize_to_file` emotion gating (used by `/tau/voice-render`, `/synthesize-batch`); optional `seed` for reproducible renders (`src/chatterbox/agent/server.py`) |
| agent-skills | 14ee49f9 | `voiceAudition.ts` weighted-emotion mapping (`emotionKnobs`); contract `intensity`/`valence`; proof receipts under `skills/persona-dream/reports/goal_v5/emotion_proof/` |

## Key facts (verified this session)
- Turbo (`ChatterboxTurboTTS`) IGNORES exaggeration/cfg_weight and tags (its `/presets` self-declares this; measured identical audio for exaggeration 0.0/0.5/1.2). The BASE `chatterbox.tts.ChatterboxTTS` HONORS them.
- Emotion map (shared across all 3 layers): `exaggeration = clamp(0.3 + 0.9*intensity, 0.3, 1.4)`, `cfg_weight = clamp(0.5 - 0.2*max(0,-valence), 0.3, 0.5)`. `intensity` is the WEIGHT.
- The 2026-07-08 PROJECT_KNOWLEDGE note "intent returns flat memory_confident" is STALE. Live `/intent` already classifies affect tone (hostile→deflect_calm, discouraged→careful_concerned); the real gap was missing `intensity`, now emitted.
- Regression-safe: requests without emotion still render on Turbo.

## Re-verify quickly
```
curl -s -XPOST 127.0.0.1:8601/intent -H 'content-type: application/json' \
  -d '{"q":"you are hostile","voice_delivery":{}}'          # -> tone=deflect_calm intensity=0.55
curl -s -XPOST 127.0.0.1:8018/synthesize-emotion -H 'content-type: application/json' \
  -d '{"text":"x","exaggeration":1.1,"cfg_weight":0.4,"seed":1234}'  # same seed -> identical sha 41a5e2691e9c
```
Proof receipts + WAVs: `skills/persona-dream/reports/goal_v5/emotion_proof/{,weight_proof,live_endpoint,wired_e2e,tau_voice_render,http_host_e2e,closed_loop}/`.

## Optional future work (nothing blocking)
- Decide default-on emotion (base render currently triggers whenever `intensity` is present in voice_delivery).
- ASR-verified batch path (`asr_verify=true`) still renders Turbo; extend emotion to it if needed.
- Human subjective tone acceptance not scored.

## Live services (verified 200)
chatterbox `:8018`, memory `:8601` — both running the merged code.
