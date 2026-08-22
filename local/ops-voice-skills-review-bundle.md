# Ops Voice Skills Review Bundle

Objective: create two new reusable ops skills in `agent-skills`:

- `ops-chatterbox`
- `ops-realtimestt`

Acceptance bar:

- Each skill has concise frontmatter with triggers, provides, composes, and complies metadata.
- Each skill has a `run.sh`, script-backed diagnostics, `sanity.sh`, and `fixtures/agentic_eval.json`.
- Deterministic diagnostics must produce JSON receipts with `schema`, `status`, `ok`, `live`, `mocked`, `checks`, `failures`, and `next_actions`.
- Live service claims must remain opt-in and must read back real HTTP, Docker, or file artifacts. Fixture proof must be labeled as deterministic and not as live service readiness.
- Persona Dream should be able to call these skills later instead of embedding Chatterbox and STT service diagnosis.

Project context:

- Persona Dream already has the corrected-goal receipt for one live paired dream plus journal carryover proof.
- The next maintainability improvement is reusable service diagnosis for the live dependencies that support audible Horus and Embry conversations.
- Chatterbox is the renderer. Persona Dream owns the dream, journal, answer invariance, and emotional-lineage invariants.
- RealtimeSTT or Whisper-style ASR is listener or transcript infrastructure. It should not be treated as Chatterbox behavior.

Brave grounding:

- Search for `Chatterbox TTS GitHub API Docker health endpoint` surfaced public Chatterbox TTS servers with `/tts`, `/docs`, `/config`, and `/health`-style status checks.
- Search for `Resemble AI Chatterbox TTS Python usage emotion exaggeration cfg_weight` surfaced Chatterbox defaults such as `exaggeration=0.5` and `cfg_weight=0.5`, and upstream guidance that `cfg_weight=0` can mitigate language-transfer accent inheritance.
- Search for `RealtimeSTT GitHub docker server websocket API` surfaced RealtimeSTT loopback-first server operation, health/readiness/capabilities style endpoints, raw PCM final transcription, ordered streaming WebSocket endpoints, and WebSocket port movement around `9001`.
- Search for `KoljaB RealtimeSTT CUDA cuDNN faster-whisper Docker` surfaced current CUDA/cuDNN packaging as a real diagnosis area.

Local observed context:

- Chatterbox service URL used by Persona Dream defaults to `http://127.0.0.1:8018`.
- Live Chatterbox `/health` readback returned `ok:true`, `engine:"chatterbox_turbo"`, `model_loaded:true`, `device:"cuda"`, and capability maps for `tag_handling` and `voice_delivery_effect`.
- Persona Dream requires per-render receipts and transcript readback. Echo-back of request fields is not evidence that the audio changed.
- For Persona Dream, Chatterbox emotion can travel through intensity and tempo; valence is currently not a perceptual promise.
- Current ASR container named `whisper` listens on port `9000`; `/health` returns `{"status":"ok","model":"base"}`.
- Current Whisper OpenAPI paths include `/v1/audio/transcriptions`, `/v1/audio/translations`, and `/v1/models`.
- Current Whisper `/v1/models` returns HTTP 401 without the configured API key.
- Local RealtimeSTT repo has an Embry runtime with `/health` and `/readiness` returning schemas `embry.realtimestt_container_health.v2` and `embry.realtimestt_container_readiness.v2`.
- Legacy RealtimeSTT server uses separate control and data WebSocket ports, defaulting to `8011` and `8012`; examples also use `9001` and `9002`.

Proposed `ops-chatterbox` commands:

- `doctor`: aggregate HTTP health, Docker container status, optional render-smoke, and optional ASR-backed transcript readback.
- `health`: read one or more service health endpoints and classify capability fields.
- `container`: inspect a named Docker container without printing secrets.
- `render-smoke --live`: POST a short text to a configured synth endpoint and verify a non-empty WAV or returned audio path.
- `assess <file>`: scan caller code for common misuse such as treating request echo as acoustic proof, passing raw user bracket tags, not separating answer text from render text, or missing per-render receipt checks.

Proposed `ops-realtimestt` commands:

- `doctor`: aggregate HTTP health/readiness, Docker status, optional OpenAI-style ASR smoke, optional WebSocket port probe, and CUDA/cuDNN environment signals.
- `health`: read `/health`, `/readiness`, `/openapi.json`, or Whisper-compatible health endpoints.
- `container`: inspect container status and non-secret env categories.
- `transcribe-smoke --live`: POST a known WAV to `/v1/audio/transcriptions` with an explicit API key source and verify non-empty transcript.
- `websocket-probe --live`: connect to configured control/data WebSocket URLs and record handshake or timeout.
- `assess <file>`: scan caller code for common misuse such as assuming `/v1/models` is unauthenticated, using ASR output as identity authority, missing `/readiness`, or confusing Whisper with RealtimeSTT.

Review questions for WebGPT:

1. Are these the right skill boundaries, or should Chatterbox and RealtimeSTT share one ops skill?
2. Which commands should be in v1 so Persona Dream can stop bespoke service diagnosis?
3. What should be deferred so the skills do not become a new pipeline or product layer?
4. What deterministic and live eval cases should gate the first implementation?
5. What output fields should be mandatory in the receipts?

Requested response:

- Return concise implementation guidance and blockers.
- Name the v1 command set for each skill.
- Name mandatory receipt fields and eval cases.
- Identify any boundary mistakes relative to Persona Dream.
- Do not claim local completion; this is reviewer guidance only.
