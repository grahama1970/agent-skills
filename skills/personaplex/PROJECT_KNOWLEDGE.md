# Project Knowledge: personaplex

**Last updated:** 2026-06-23 13:18 by Codex
**Status:** Bridge skill scaffold with WebGPT-reviewed replay-cache gate,
strict provenance repairs, `.zshrc` HF-token loading, bounded live E2E smoke
support, a custom golden-state research-gated PersonaPlex wrapper, and
create-architecture P0 through P3-P5 deterministic fallback/control-plane
proofs. Live Deepgram/GPU PersonaPlex, real `$memory /upsert`, and real
`create-evidence-case` remain unproven unless future receipts set the
corresponding `real_*` flags to `true`.

## Current Handoff

Use the PersonaPlex-local handoff first:

```text
skills/personaplex/HANDOFF.md
```

The generic `local/HANDOFF.md` was also produced by the `$handoff` skill, but
for this project the PersonaPlex-local copy is the relevant bridge for the next
agent.

Current visible progress report:

```text
reviews/personaplex-deepgram/compliance-memory-decision-tree.html
```

Fresh UI verification marker:

```text
.codex/ui-verification/latest.json
```

Latest P3-P5 final receipt:

```text
/tmp/personaplex-p3-p5-combined-sanity/p3-p5-final-receipt.json
```

## Current Contract

- PersonaPlex `.pt` files are not generic speaker embeddings.
- The PersonaPlex runtime in `experiments/personaplex` loads `.pt` files with
  `state["embeddings"]` and `state["cache"]`.
- The bridge from Orpheus-TTS to PersonaPlex is audio:
  1. Orpheus-TTS produces clean conversational reference WAVs.
  2. PersonaPlex loads those WAVs as voice prompts.
  3. PersonaPlex saves native prompt-cache `.pt` files.
  4. PersonaPlex replays the generated `.pt` in a fresh subprocess.
  5. PersonaPlex offline conversation produces output WAV/text receipts.
- `orpheus-tts-voice-trainer` is upstream only. It provides Orpheus inference
  receipts and clean conversational reference WAVs. `personaplex` owns the
  `orpheus.personaplex_reference_pack.v1` bridge, native `.pt` cache creation,
  fresh-process `.pt` replay, live server/wrapper proof, and review receipts.

## Research-Gated Conversation Architecture

The intended useful PersonaPlex stack is:

1. Independent ASR/VAD produces the final user transcript.
2. `$memory /intent` classifies the turn and extracts entities.
3. `$memory /recall` with `collections: ["persona_memory"]` and tags such as
   `persona:embry` recalls character continuity, conflict, relationships,
   Theory-of-Mind state, and emotional salience.
4. `$brave-search` runs only when current external facts are needed, for example
   Hawaii weather, surf conditions, or other live researched facts.
5. `$scillm` one-shot formulates compact grounding and persona direction. It is
   the System 2 planner, not the final speaker for normal conversation.
6. PersonaPlex 7B receives the compact grounding/context while gated and then
   generates the actual spoken response.

Production rule: PersonaPlex may say a short controlled filler such as
"One moment" while research starts, but it must not make substantive factual
claims until memory/search/scillm grounding is ready. High-stakes exact wording
may use controlled speech mode; ordinary Embry/Horus conversation should let
PersonaPlex 7B be the final actor after context injection.

## Controlled Text / Inner-Monologue Notes

Do not copy generic Moshi snippets that use `model.stream(batch_size=1)` or a
`text_tokens=` argument. This local PersonaPlex checkout uses `LMGen.step(...)`
from `moshi/moshi/models/lm.py`:

```python
LMGen.step(input_tokens=None, moshi_tokens=None, text_token=None)
```

The existing startup prompt path is the correct repo-native pattern:

```python
self.step(
    moshi_tokens=self._encode_zero_frame(),
    text_token=text_prompt_token,
    input_tokens=self._encode_sine_frame(),
)
```

Prior memory recall for this repo also says to use `mimi.streaming_forever(1)`
and `lm_gen.streaming_forever(1)`, not `stream(batch_size=1)`, after reset.

Treat the 12.5Hz / 80ms framing as a model-step rhythm, not a reason to add a
blind `sleep(0.08)` to prompt injection. Existing prompt pre-roll feeds one
token per model step as fast as inference permits. Wall-clock pacing belongs to
the live audio transport.

Required wrapper helpers still missing:

- `LMGen.step_listen_only(...)` or equivalent to ingest user audio while forcing
  assistant audio/text to silence/PAD.
- `LMGen.inject_text_tokens_async(...)` to inject compact grounding without
  emitting answer audio.
- a server-level output gate before Opus audio is appended/sent.
- one model-owner loop so audio, research, and context injection never call
  `LMGen.step()` concurrently.

Implemented wrapper spike:

- Script:
  `skills/personaplex/scripts/personaplex_golden_state_server.py`
- Golden-state probe:
  `skills/personaplex/scripts/personaplex_golden_state_probe.py`
- It imports Moshi/PersonaPlex modules directly from
  `${HOME}/workspace/experiments/personaplex`, not from the skill venv.
- It performs the Embry voice/persona pre-roll once at boot and clones
  `lm_gen.get_streaming_state()` for fast per-session restore.
- It uses the real local API boundary:
  `lm_gen.set_streaming_state(...)` and
  `lm_gen.step(codes, text_token=forced_text)`.
- It does **not** use generic snippets such as `model.stream(batch_size=1)`,
  `template_stream.kv_cache`, or `stream.step(..., text_tokens=...)`.
- It calls `$memory /intent` first.
- It then runs `$memory /recall`, `$brave-search`, and the selected route
  product as an `asyncio.as_completed` batch.
- Route products are first-class staged products:
  `/answer`, `/clarify`, `/deflect`, or a fail-closed
  `create-evidence-case` gate.
- Compliance/evidence-case turns must not release a factual answer until the
  CAE branch produces a verdict and evidence packet.
- `/api/grounded-speech` is a deterministic non-mocked proof endpoint:
  research route -> concise script -> forced PersonaPlex WAV.

Proof from 2026-06-22:

- Health boot timings from the wrapper:
  `load_ms=13048.25`, `warmup_ms=6962.43`,
  `golden_pre_roll_ms=29627.2`, `golden_clone_ms=1.45`,
  `boot_total_ms=49639.43`.
- Normal research turn:
  intent `2.75ms`, persona memory `144.17ms`, Brave `1153.57ms`,
  route product `1925.98ms`.
- Grounded PersonaPlex WAV receipt:
  `/mnt/storage12tb/skills/personaplex/outputs/golden-state-wrapper/embry-grounded-20260622T194535Z.json`
- Grounded PersonaPlex WAV:
  `/mnt/storage12tb/skills/personaplex/outputs/golden-state-wrapper/embry-grounded-20260622T194535Z.wav`
  (`760364` bytes, `24kHz`, `15.84s`).
- WebSocket scripted sanity:
  handshake `~10.5ms`, intent queued `~13.7ms`, memory queued `~153ms`,
  Brave queued `~1221ms`, route queued `~2261ms`.
- Compliance/evidence-case gate sanity for the Ivanti/CVE question:
  `evidence_gated=true`, route endpoint `create-evidence-case`, and script:
  "I need to check the evidence case before I answer that..."

## Current Embry Technical Artifacts

- Orpheus provisional reference receipt:
  `/mnt/storage12tb/skills/voice-segment-selector/checkpoints/embry_orpheus_lora/personaplex_reference_20260622T152415Z/inference_receipt.json`
- Orpheus reference WAV:
  `/mnt/storage12tb/skills/voice-segment-selector/checkpoints/embry_orpheus_lora/generated/dd628b1be9e4.wav`
- PersonaPlex reference pack:
  `/mnt/storage12tb/skills/personaplex/outputs/reference-packs/embry-personaplex-conversational-20260622T152527Z.json`
- Native cache/replay E2E receipt:
  `/mnt/storage12tb/skills/personaplex/outputs/e2e/embry-conversational-20260622T152647Z/personaplex-publish-receipt.json`
- Generated PersonaPlex voice prompt:
  `/mnt/storage12tb/skills/personaplex/outputs/e2e/embry-conversational-20260622T152647Z/neutral/voice-prompt.pt`
- `.pt` sha256:
  `4bbeb9b0d5245f0c30e5d2fc5ad9eaeb2cde58a2a72c4cca4ba6cbcea694feb6`
- Built-in UI URL used for smoke review:
  `https://127.0.0.1:8998/?voice_prompt=voice-prompt.pt`
- CDP screenshots:
  `/tmp/codex-ui-verification/agent-skills/personaplex-embry-built-in-ui/20260622T153220Z.png`,
  `/tmp/codex-ui-verification/agent-skills/personaplex-embry-research-eval-refresh/20260622T155343Z.png`

These are technical cache/replay and UI reachability artifacts. They are not
publication proof and not live full-duplex research-gated proof.

## WebGPT Review Outcome

Initial review artifact root:
`/mnt/storage12tb/skills/personaplex/outputs/webgpt-review-20260622T124436Z`

The usable review run is:
`personaplex-orpheus-bridge-review-inline-nopaths-20260622T124436Z`

Verdict: `INSUFFICIENT_EVIDENCE`.

Key accepted design decision:

- Keep `personaplex` as a separate downstream skill. Orpheus owns training and
  approved reference production; PersonaPlex owns model-specific cache
  compilation, validation, replay, and conversation evidence.

Blocking findings translated into implementation requirements:

- generated `.pt` must be replay-tested in a fresh PersonaPlex process;
- PersonaPlex should be invoked as a subprocess from its pinned runtime, not
  imported through the skill virtual environment;
- `.pt` validation must inspect safe-loaded tensor structure, hashes, finite
  values, and nonempty payloads;
- persona/register values must be slug-only to prevent path traversal;
- generated review HTML must escape model-controlled text;
- output checks must parse text JSON and validate nonempty, nonsilent WAVs;
- live full-duplex readiness is a separate WebSocket/server-client proof and is
  not established by the offline E2E gate.

Follow-up WebGPT review artifact root:
`/mnt/storage12tb/skills/personaplex/outputs/webgpt-review-20260622T0916Z`

The usable raw review run is:
`personaplex-orpheus-bridge-review-sanitized2-20260622T0925Z`

Wrapper status: completed with degraded focus transport; wrapper parsed verdict
as `BLOCKED` with empty `verdict_data`, but
`round-1/02_response.raw.md` contains a structured `NEEDS_CHANGES` review.

Accepted follow-up findings and local repairs:

- strict provenance is now required for release-relevant E2E;
- `pack-from-receipt` no longer converts `verified: false` into PASS-like
  review status;
- unverified receipts require `--allow-unverified-smoke` and are marked
  `review_status: "unverified_smoke"`;
- `from-orpheus`/`verify-e2e` reject unverified references unless
  `--allow-provisional-reference` is explicitly supplied;
- `from-orpheus` refuses nonempty output directories and stale `.pt` files;
- each register stages the prompt as fixed `voice-prompt.wav` to avoid reserved
  filename collisions;
- generated `.pt` mtime must be newer than the build start time;
- PersonaPlex Python is required from the PersonaPlex venv or explicit
  `--personaplex-python`; there is no fallback to the skill interpreter;
- receipts now record PersonaPlex git head/status, offline patch hash, Python
  version, and a pip-freeze artifact;
- output text JSON must be a nonempty list of strings with lexical content;
- final receipts are written atomically after review HTML exists;
- technical success status is `CACHE_REPLAY_PASS` with
  `publication_status: "NOT_PUBLISHED"` and
  `human_review_status: "NOT_REVIEWED"`.

## Known Gaps

- `experiments/personaplex/moshi/moshi/offline.py` now exposes
  `--save-voice-embeddings` locally. That patch belongs with the PersonaPlex
  checkout and must be preserved or upstreamed.
- Local PersonaPlex venv import smoke currently passes after installing
  `moshi-personaplex`, `torch`, `sphn`, `soundfile`, `pyloudnorm`, and
  `hf_transfer`.
- `skills/personaplex/run.sh` loads `HF_TOKEN` and
  `HUGGINGFACE_HUB_TOKEN` from interactive zsh evaluation of `~/.zshrc` when
  the shell environment lacks them. HF auth was checked with the PersonaPlex
  venv and returned user `grahamaco`.
- The local shell exports `LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64...` while
  PersonaPlex Torch is `2.4.1+cu121` with bundled CUDA/cuDNN 12.1 libraries.
  That mismatch caused cuDNN failures such as
  `Unable to load ... libcudnn_graph.so.9` and `Invalid handle. Cannot load
  symbol cudnnCreate`. `run_personaplex_offline_cli` now prepends the
  PersonaPlex venv's bundled `nvidia/*/lib` paths and removes NoMachine
  `LD_PRELOAD=/usr/NX/lib/libnxegl.so` for PersonaPlex subprocesses.
- The skill venv does not include Torch. PersonaPlex `.pt` validation must use
  the PersonaPlex venv Python, not the skill runtime. The validator now supports
  a subprocess-backed PersonaPlex Python path.
- Live E2E with the default
  `${HOME}/workspace/experiments/personaplex/assets/test/input_assistant.wav`
  fixture was stopped after roughly 9 minutes because the fixture is 40.0s and
  `moshi.offline` writes output only after processing the full input. Use
  `--max-human-input-seconds 2.0` for bounded non-mocked smoke runs; the receipt
  records original and cropped input metrics.
- A bounded Embry provisional smoke run reached `CACHE_REPLAY_PASS` after
  closing large GPU consumers and fixing the CUDA/cuDNN subprocess environment:
  `/mnt/storage12tb/skills/personaplex/outputs/e2e/embry-provisional-short-validatorfix-20260622T144727Z/personaplex-publish-receipt.json`.
  This is not a publication gate because the source reference is still
  provisional/unverified.
- Current Horus and Embry reference packs are usable as provisional technical
  smoke inputs only. Horus is a `[sigh] Not again.` smoke WAV; Embry is a short
  hub smoke WAV. Neither is a final clean human-approved identity anchor.
- Native cache E2E is not live full-duplex readiness. Full-duplex readiness
  requires a real PersonaPlex server/WebSocket client proof.
- Live memory-backed operation has now been verified for wrapper calls to
  `/intent`, `/recall`, and `/answer` through `http://127.0.0.1:8601`.
  `/clarify` and `/deflect` remain route paths in code but still need explicit
  smoke receipts.
- 2026-06-22 `/memory` persona-current-fact intent flow is the active contract
  for Embry/Kai/Hawaii blended answers. `/intent` with `scope=persona_memory`
  returns `question_kind=persona_current_fact_blend`, Brave tool call
  `Hawaii weather today`, `/recall` over `collections=["persona_memory"]` with
  `tags=["persona:embry"]`, and dependent `/answer` with
  `source_packets=["current_facts","persona_memory"]`. The wrapper now consumes
  that intent plan directly, runs Brave and recall first, and passes
  `external_sources` plus `recall_snapshot` into `/answer`. Proof:
  `/tmp/personaplex-memory-intent-flow-proof.json` (`/answer` returned
  `memory.answer.v1`, `can_answer=true`, `answer_type=persona_current_fact_blend`,
  `external_sources_count=1`, `recall_item_count=8`,
  `source_packet_included=true`).
- `$scillm` is not yet in the wrapper. The current forced speech endpoint uses a
  deterministic script assembled from memory/Brave/route products.
- Direct async Deepgram live ASR/VAD is wired into the custom golden-state
  WebSocket wrapper, not a separate microservice. Incoming client Opus is
  decoded once, PCM is fed to both Moshi/PersonaPlex and Deepgram, Deepgram
  `speech_final=true` transcript events trigger grounding, and an output gate masks generated
  audio/text with silence until required memory/Brave/answer stages finish.
  New code: `scripts/personaplex_deepgram_live.py` and
  `scripts/personaplex_memory_flow.py`; live proof harness:
  `scripts/personaplex_deepgram_live_probe.py`; wrapper entry:
  `scripts/personaplex_golden_state_server.py`. Deterministic proof under the
  PersonaPlex venv parsed a representative Deepgram final transcript and
  closed/opened the gate. Live Deepgram proof receipt:
  `/mnt/storage12tb/skills/personaplex/outputs/deepgram-live-probe/embry/20260622T203618Z/personaplex-deepgram-live-probe-receipt.json`.
  It streamed a synthesized 24 kHz speech fixture through browser-style Opus
  frames, received full transcript
  `Embry, what is the weather like in Hawaii today, and how would that make you feel about surfing with Kai?`
  with `speech_final=true`, then emitted `grounding_started`, four
  `grounding_stage_queued` stages (`intent`, `memory`, `brave`, `route`), and
  `grounding_complete` with the gate open and `queue_depth=268`.

## Artifact Roots

- Code: `skills/personaplex`
- Heavy outputs: `/mnt/storage12tb/skills/personaplex/outputs`
- Work/log/data/model roots are symlinked to `/mnt/storage12tb/skills/personaplex`.
