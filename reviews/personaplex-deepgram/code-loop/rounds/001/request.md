# Targeted Review: PersonaPlex Deepgram Live ASR/VAD Wrapper

## Reviewer Instructions

Review this as a code review request for Web GPT or another external reviewer.
Focus on correctness, regression risk, security, maintainability, test coverage, and mismatches between the stated intent and the actual diff.
Do not rewrite the entire implementation unless the diff is fundamentally unsafe.
Return findings first, grouped by severity, with concrete file/function references where possible.


## Decision Needed

Are there blocking correctness, reliability, or production-readiness issues in the direct-async Deepgram + PersonaPlex wrapper approach before browser microphone testing?

## Rationale And Context

# PersonaPlex Deepgram Live ASR/VAD Code Review Context

## Objective

Review the direct-async Deepgram integration for the PersonaPlex golden-state
wrapper. The implementation should support a production-style "Talker-Reasoner"
flow: browser Opus audio is decoded once, PCM is fed to both PersonaPlex/Moshi
and Deepgram, Deepgram `speech_final` turn events trigger grounding, and output
speech is masked until required facts arrive.

## Decision Requested

Is this approach safe enough to continue building on, or are there blocking code
or architecture problems in the current implementation that should be fixed
before adding microphone/browser UI tests?

## Review Scope

- `skills/personaplex/scripts/personaplex_golden_state_server.py`
- `skills/personaplex/scripts/personaplex_deepgram_live.py`
- `skills/personaplex/scripts/personaplex_deepgram_live_probe.py`
- `skills/personaplex/scripts/personaplex_memory_flow.py`
- `skills/personaplex/PROJECT_KNOWLEDGE.md`

## Expected Contracts

1. Deepgram turn triggering must be based on `speech_final=true`, not partial
   `is_final=true`, to avoid premature memory/Brave calls.
2. Live audio must continue driving PersonaPlex at the 12.5 Hz cadence while
   Deepgram and grounding run asynchronously.
3. Output gating must mask generated speech/text while required grounding is in
   flight and open only after required stages finish or error handling releases
   the gate.
4. Memory and Brave stages must remain evidence-bearing and source-packeted; no
   facts should be spoken before the grounding stages are complete.
5. GPU/model work must run under `torch.no_grad()` in the live loop and not leak
   gradients or CUDA memory.
6. The proof harness must be clearly marked as synthesized speech, not
   microphone capture.
7. The stock container/runtime must be restored after live wrapper testing.

## Local Evidence Already Run

Compile:

```text
/home/graham/workspace/experiments/personaplex/.venv/bin/python -m py_compile \
  skills/personaplex/scripts/personaplex_golden_state_server.py \
  skills/personaplex/scripts/personaplex_deepgram_live.py \
  skills/personaplex/scripts/personaplex_deepgram_live_probe.py \
  skills/personaplex/scripts/personaplex_memory_flow.py
```

Compile exit code was 0.

Wrapper health:

```json
{
  "schema": "personaplex.golden_state_server.health.v1",
  "ok": true,
  "device": "cuda",
  "cuda_device": "NVIDIA RTX A5000",
  "timings": {
    "load_ms": 6805.2,
    "warmup_ms": 5983.97,
    "golden_pre_roll_ms": 9072.53,
    "golden_clone_ms": 1.15,
    "boot_total_ms": 21862.94
  }
}
```

Deepgram live proof receipt:

```text
/mnt/storage12tb/skills/personaplex/outputs/deepgram-live-probe/embry/20260622T203618Z/personaplex-deepgram-live-probe-receipt.json
```

Receipt summary:

```json
{
  "status": "PASS",
  "speech_final": true,
  "transcript": "Embry, what is the weather like in Hawaii today, and how would that make you feel about surfing with Kai?",
  "stages": ["intent", "memory", "brave", "route"],
  "gate_complete_active": false,
  "queue_depth": 268
}
```

Stock container restored:

```text
personaplex-personaplex-1 Up ... 0.0.0.0:8998->8998/tcp
```

## Known Risks To Re-check

- `deepgram_loop` may hang waiting on `turn_queue.get()` if shutdown ordering is
  wrong.
- The output gate currently masks audio with silence but still allows early
  generated text before the first grounding trigger; decide whether that is
  acceptable or should be state-gated earlier.
- Grounding stage order can vary because memory and Brave may race; review
  whether required facts are truly complete before route/answer tokens are
  injected.
- Deepgram buffering joins final segments with spaces; review whether duplicate
  segment text can occur with Deepgram result semantics.
- The live probe uses synthesized speech and trailing silence; it is not a
  browser microphone proof.

## Non-goals

- Do not review unrelated `skills/personaplex` files outside the listed scope.
- Do not treat WebGPT review as deterministic closure proof.
- Do not require a separate Deepgram microservice unless the direct-async design
  creates a concrete correctness or reliability problem.

## Required Reviewer Output

Return:

```json
{
  "verdict": "satisfied | needs_changes | blocked | insufficient_evidence",
  "blocking_findings": [],
  "non_blocking_findings": [],
  "patch_suggestions": [],
  "tests_to_run": [],
  "do_not_do": [],
  "aggregation_ready": false,
  "missing_evidence": []
}
```


## Expected Safety Contract

Deepgram turn triggering must be based on speech_final=true, not partial is_final=true.

The 12.5Hz PersonaPlex loop must continue while memory and Brave grounding run asynchronously.

Output gating must mask generated speech/text while required grounding is in flight and open only after required stages finish or error handling releases the gate.

GPU/model inference in the live loop must run under torch.no_grad and avoid gradient/CUDA leaks.


## Prior Critique Being Rechecked

First live probe exposed a premature is_final trigger and was patched to require speech_final=true.

First live probe exposed a requires_grad numpy conversion in opus_loop and was patched with torch.no_grad plus detach.


## Non-goals For This Review

Do not review unrelated PersonaPlex files outside the selected scope.


## Original Review Request

(No request file supplied; review the current repository changes.)

## Repository Snapshot

- Generated at: `2026-06-22T21:54:33.170960+00:00`
- Working directory: `/home/graham/workspace/experiments/agent-skills/skills/review-code`
- Repository root: `/home/graham/workspace/experiments/agent-skills`
- Branch: `feat/webgpt-no-activate`
- Remote: `git@github.com:grahama1970/agent-skills.git`

## Git Status

```text
?? skills/personaplex/PROJECT_KNOWLEDGE.md
?? skills/personaplex/scripts/personaplex_deepgram_live.py
?? skills/personaplex/scripts/personaplex_deepgram_live_probe.py
?? skills/personaplex/scripts/personaplex_golden_state_server.py
?? skills/personaplex/scripts/personaplex_memory_flow.py
```

## Selected Review Files

These are the files intentionally selected for external review. Do not expand scope just because other files are changed in the worktree.

- `skills/personaplex/scripts/personaplex_golden_state_server.py`
- `skills/personaplex/scripts/personaplex_deepgram_live.py`
- `skills/personaplex/scripts/personaplex_deepgram_live_probe.py`
- `skills/personaplex/scripts/personaplex_memory_flow.py`
- `skills/personaplex/PROJECT_KNOWLEDGE.md`

## Changed Files In Selected Scope

- `skills/personaplex/PROJECT_KNOWLEDGE.md`
- `skills/personaplex/scripts/personaplex_deepgram_live.py`
- `skills/personaplex/scripts/personaplex_deepgram_live_probe.py`
- `skills/personaplex/scripts/personaplex_golden_state_server.py`
- `skills/personaplex/scripts/personaplex_memory_flow.py`

## Diff

```diff
diff --git a/skills/personaplex/PROJECT_KNOWLEDGE.md b/skills/personaplex/PROJECT_KNOWLEDGE.md
new file mode 100644
index 000000000..295295715
--- /dev/null
+++ b/skills/personaplex/PROJECT_KNOWLEDGE.md
@@ -0,0 +1,295 @@
+# Project Knowledge: personaplex
+
+**Last updated:** 2026-06-22 19:49 by agent
+**Status:** Bridge skill scaffold with WebGPT-reviewed replay-cache gate,
+strict provenance repairs, `.zshrc` HF-token loading, bounded live E2E smoke
+support, and a custom golden-state research-gated PersonaPlex wrapper.
+
+## Current Contract
+
+- PersonaPlex `.pt` files are not generic speaker embeddings.
+- The PersonaPlex runtime in `experiments/personaplex` loads `.pt` files with
+  `state["embeddings"]` and `state["cache"]`.
+- The bridge from Orpheus-TTS to PersonaPlex is audio:
+  1. Orpheus-TTS produces clean conversational reference WAVs.
+  2. PersonaPlex loads those WAVs as voice prompts.
+  3. PersonaPlex saves native prompt-cache `.pt` files.
+  4. PersonaPlex replays the generated `.pt` in a fresh subprocess.
+  5. PersonaPlex offline conversation produces output WAV/text receipts.
+- `orpheus-tts-voice-trainer` is upstream only. It provides Orpheus inference
+  receipts and clean conversational reference WAVs. `personaplex` owns the
+  `orpheus.personaplex_reference_pack.v1` bridge, native `.pt` cache creation,
+  fresh-process `.pt` replay, live server/wrapper proof, and review receipts.
+
+## Research-Gated Conversation Architecture
+
+The intended useful PersonaPlex stack is:
+
+1. Independent ASR/VAD produces the final user transcript.
+2. `$memory /intent` classifies the turn and extracts entities.
+3. `$memory /recall` with `collections: ["persona_memory"]` and tags such as
+   `persona:embry` recalls character continuity, conflict, relationships,
+   Theory-of-Mind state, and emotional salience.
+4. `$brave-search` runs only when current external facts are needed, for example
+   Hawaii weather, surf conditions, or other live researched facts.
+5. `$scillm` one-shot formulates compact grounding and persona direction. It is
+   the System 2 planner, not the final speaker for normal conversation.
+6. PersonaPlex 7B receives the compact grounding/context while gated and then
+   generates the actual spoken response.
+
+Production rule: PersonaPlex may say a short controlled filler such as
+"One moment" while research starts, but it must not make substantive factual
+claims until memory/search/scillm grounding is ready. High-stakes exact wording
+may use controlled speech mode; ordinary Embry/Horus conversation should let
+PersonaPlex 7B be the final actor after context injection.
+
+## Controlled Text / Inner-Monologue Notes
+
+Do not copy generic Moshi snippets that use `model.stream(batch_size=1)` or a
+`text_tokens=` argument. This local PersonaPlex checkout uses `LMGen.step(...)`
+from `moshi/moshi/models/lm.py`:
+
+```python
+LMGen.step(input_tokens=None, moshi_tokens=None, text_token=None)
+```
+
+The existing startup prompt path is the correct repo-native pattern:
+
+```python
+self.step(
+    moshi_tokens=self._encode_zero_frame(),
+    text_token=text_prompt_token,
+    input_tokens=self._encode_sine_frame(),
+)
+```
+
+Prior memory recall for this repo also says to use `mimi.streaming_forever(1)`
+and `lm_gen.streaming_forever(1)`, not `stream(batch_size=1)`, after reset.
+
+Treat the 12.5Hz / 80ms framing as a model-step rhythm, not a reason to add a
+blind `sleep(0.08)` to prompt injection. Existing prompt pre-roll feeds one
+token per model step as fast as inference permits. Wall-clock pacing belongs to
+the live audio transport.
+
+Required wrapper helpers still missing:
+
+- `LMGen.step_listen_only(...)` or equivalent to ingest user audio while forcing
+  assistant audio/text to silence/PAD.
+- `LMGen.inject_text_tokens_async(...)` to inject compact grounding without
+  emitting answer audio.
+- a server-level output gate before Opus audio is appended/sent.
+- one model-owner loop so audio, research, and context injection never call
+  `LMGen.step()` concurrently.
+
+Implemented wrapper spike:
+
+- Script:
+  `skills/personaplex/scripts/personaplex_golden_state_server.py`
+- Golden-state probe:
+  `skills/personaplex/scripts/personaplex_golden_state_probe.py`
+- It imports Moshi/PersonaPlex modules directly from
+  `/home/graham/workspace/experiments/personaplex`, not from the skill venv.
+- It performs the Embry voice/persona pre-roll once at boot and clones
+  `lm_gen.get_streaming_state()` for fast per-session restore.
+- It uses the real local API boundary:
+  `lm_gen.set_streaming_state(...)` and
+  `lm_gen.step(codes, text_token=forced_text)`.
+- It does **not** use generic snippets such as `model.stream(batch_size=1)`,
+  `template_stream.kv_cache`, or `stream.step(..., text_tokens=...)`.
+- It calls `$memory /intent` first.
+- It then runs `$memory /recall`, `$brave-search`, and the selected route
+  product as an `asyncio.as_completed` batch.
+- Route products are first-class staged products:
+  `/answer`, `/clarify`, `/deflect`, or a fail-closed
+  `create-evidence-case` gate.
+- Compliance/evidence-case turns must not release a factual answer until the
+  CAE branch produces a verdict and evidence packet.
+- `/api/grounded-speech` is a deterministic non-mocked proof endpoint:
+  research route -> concise script -> forced PersonaPlex WAV.
+
+Proof from 2026-06-22:
+
+- Health boot timings from the wrapper:
+  `load_ms=13048.25`, `warmup_ms=6962.43`,
+  `golden_pre_roll_ms=29627.2`, `golden_clone_ms=1.45`,
+  `boot_total_ms=49639.43`.
+- Normal research turn:
+  intent `2.75ms`, persona memory `144.17ms`, Brave `1153.57ms`,
+  route product `1925.98ms`.
+- Grounded PersonaPlex WAV receipt:
+  `/mnt/storage12tb/skills/personaplex/outputs/golden-state-wrapper/embry-grounded-20260622T194535Z.json`
+- Grounded PersonaPlex WAV:
+  `/mnt/storage12tb/skills/personaplex/outputs/golden-state-wrapper/embry-grounded-20260622T194535Z.wav`
+  (`760364` bytes, `24kHz`, `15.84s`).
+- WebSocket scripted sanity:
+  handshake `~10.5ms`, intent queued `~13.7ms`, memory queued `~153ms`,
+  Brave queued `~1221ms`, route queued `~2261ms`.
+- Compliance/evidence-case gate sanity for the Ivanti/CVE question:
+  `evidence_gated=true`, route endpoint `create-evidence-case`, and script:
+  "I need to check the evidence case before I answer that..."
+
+## Current Embry Technical Artifacts
+
+- Orpheus provisional reference receipt:
+  `/mnt/storage12tb/skills/voice-segment-selector/checkpoints/embry_orpheus_lora/personaplex_reference_20260622T152415Z/inference_receipt.json`
+- Orpheus reference WAV:
+  `/mnt/storage12tb/skills/voice-segment-selector/checkpoints/embry_orpheus_lora/generated/dd628b1be9e4.wav`
+- PersonaPlex reference pack:
+  `/mnt/storage12tb/skills/personaplex/outputs/reference-packs/embry-personaplex-conversational-20260622T152527Z.json`
+- Native cache/replay E2E receipt:
+  `/mnt/storage12tb/skills/personaplex/outputs/e2e/embry-conversational-20260622T152647Z/personaplex-publish-receipt.json`
+- Generated PersonaPlex voice prompt:
+  `/mnt/storage12tb/skills/personaplex/outputs/e2e/embry-conversational-20260622T152647Z/neutral/voice-prompt.pt`
+- `.pt` sha256:
+  `4bbeb9b0d5245f0c30e5d2fc5ad9eaeb2cde58a2a72c4cca4ba6cbcea694feb6`
+- Built-in UI URL used for smoke review:
+  `https://127.0.0.1:8998/?voice_prompt=voice-prompt.pt`
+- CDP screenshots:
+  `/tmp/codex-ui-verification/agent-skills/personaplex-embry-built-in-ui/20260622T153220Z.png`,
+  `/tmp/codex-ui-verification/agent-skills/personaplex-embry-research-eval-refresh/20260622T155343Z.png`
+
+These are technical cache/replay and UI reachability artifacts. They are not
+publication proof and not live full-duplex research-gated proof.
+
+## WebGPT Review Outcome
+
+Initial review artifact root:
+`/mnt/storage12tb/skills/personaplex/outputs/webgpt-review-20260622T124436Z`
+
+The usable review run is:
+`personaplex-orpheus-bridge-review-inline-nopaths-20260622T124436Z`
+
+Verdict: `INSUFFICIENT_EVIDENCE`.
+
+Key accepted design decision:
+
+- Keep `personaplex` as a separate downstream skill. Orpheus owns training and
+  approved reference production; PersonaPlex owns model-specific cache
+  compilation, validation, replay, and conversation evidence.
+
+Blocking findings translated into implementation requirements:
+
+- generated `.pt` must be replay-tested in a fresh PersonaPlex process;
+- PersonaPlex should be invoked as a subprocess from its pinned runtime, not
+  imported through the skill virtual environment;
+- `.pt` validation must inspect safe-loaded tensor structure, hashes, finite
+  values, and nonempty payloads;
+- persona/register values must be slug-only to prevent path traversal;
+- generated review HTML must escape model-controlled text;
+- output checks must parse text JSON and validate nonempty, nonsilent WAVs;
+- live full-duplex readiness is a separate WebSocket/server-client proof and is
+  not established by the offline E2E gate.
+
+Follow-up WebGPT review artifact root:
+`/mnt/storage12tb/skills/personaplex/outputs/webgpt-review-20260622T0916Z`
+
+The usable raw review run is:
+`personaplex-orpheus-bridge-review-sanitized2-20260622T0925Z`
+
+Wrapper status: completed with degraded focus transport; wrapper parsed verdict
+as `BLOCKED` with empty `verdict_data`, but
+`round-1/02_response.raw.md` contains a structured `NEEDS_CHANGES` review.
+
+Accepted follow-up findings and local repairs:
+
+- strict provenance is now required for release-relevant E2E;
+- `pack-from-receipt` no longer converts `verified: false` into PASS-like
+  review status;
+- unverified receipts require `--allow-unverified-smoke` and are marked
+  `review_status: "unverified_smoke"`;
+- `from-orpheus`/`verify-e2e` reject unverified references unless
+  `--allow-provisional-reference` is explicitly supplied;
+- `from-orpheus` refuses nonempty output directories and stale `.pt` files;
+- each register stages the prompt as fixed `voice-prompt.wav` to avoid reserved
+  filename collisions;
+- generated `.pt` mtime must be newer than the build start time;
+- PersonaPlex Python is required from the PersonaPlex venv or explicit
+  `--personaplex-python`; there is no fallback to the skill interpreter;
+- receipts now record PersonaPlex git head/status, offline patch hash, Python
+  version, and a pip-freeze artifact;
+- output text JSON must be a nonempty list of strings with lexical content;
+- final receipts are written atomically after review HTML exists;
+- technical success status is `CACHE_REPLAY_PASS` with
+  `publication_status: "NOT_PUBLISHED"` and
+  `human_review_status: "NOT_REVIEWED"`.
+
+## Known Gaps
+
+- `experiments/personaplex/moshi/moshi/offline.py` now exposes
+  `--save-voice-embeddings` locally. That patch belongs with the PersonaPlex
+  checkout and must be preserved or upstreamed.
+- Local PersonaPlex venv import smoke currently passes after installing
+  `moshi-personaplex`, `torch`, `sphn`, `soundfile`, `pyloudnorm`, and
+  `hf_transfer`.
+- `skills/personaplex/run.sh` loads `HF_TOKEN` and
+  `HUGGINGFACE_HUB_TOKEN` from interactive zsh evaluation of `~/.zshrc` when
+  the shell environment lacks them. HF auth was checked with the PersonaPlex
+  venv and returned user `grahamaco`.
+- The local shell exports `LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64...` while
+  PersonaPlex Torch is `2.4.1+cu121` with bundled CUDA/cuDNN 12.1 libraries.
+  That mismatch caused cuDNN failures such as
+  `Unable to load ... libcudnn_graph.so.9` and `Invalid handle. Cannot load
+  symbol cudnnCreate`. `run_personaplex_offline_cli` now prepends the
+  PersonaPlex venv's bundled `nvidia/*/lib` paths and removes NoMachine
+  `LD_PRELOAD=/usr/NX/lib/libnxegl.so` for PersonaPlex subprocesses.
+- The skill venv does not include Torch. PersonaPlex `.pt` validation must use
+  the PersonaPlex venv Python, not the skill runtime. The validator now supports
+  a subprocess-backed PersonaPlex Python path.
+- Live E2E with the default
+  `/home/graham/workspace/experiments/personaplex/assets/test/input_assistant.wav`
+  fixture was stopped after roughly 9 minutes because the fixture is 40.0s and
+  `moshi.offline` writes output only after processing the full input. Use
+  `--max-human-input-seconds 2.0` for bounded non-mocked smoke runs; the receipt
+  records original and cropped input metrics.
+- A bounded Embry provisional smoke run reached `CACHE_REPLAY_PASS` after
+  closing large GPU consumers and fixing the CUDA/cuDNN subprocess environment:
+  `/mnt/storage12tb/skills/personaplex/outputs/e2e/embry-provisional-short-validatorfix-20260622T144727Z/personaplex-publish-receipt.json`.
+  This is not a publication gate because the source reference is still
+  provisional/unverified.
+- Current Horus and Embry reference packs are usable as provisional technical
+  smoke inputs only. Horus is a `[sigh] Not again.` smoke WAV; Embry is a short
+  hub smoke WAV. Neither is a final clean human-approved identity anchor.
+- Native cache E2E is not live full-duplex readiness. Full-duplex readiness
+  requires a real PersonaPlex server/WebSocket client proof.
+- Live memory-backed operation has now been verified for wrapper calls to
+  `/intent`, `/recall`, and `/answer` through `http://127.0.0.1:8601`.
+  `/clarify` and `/deflect` remain route paths in code but still need explicit
+  smoke receipts.
+- 2026-06-22 `/memory` persona-current-fact intent flow is the active contract
+  for Embry/Kai/Hawaii blended answers. `/intent` with `scope=persona_memory`
+  returns `question_kind=persona_current_fact_blend`, Brave tool call
+  `Hawaii weather today`, `/recall` over `collections=["persona_memory"]` with
+  `tags=["persona:embry"]`, and dependent `/answer` with
+  `source_packets=["current_facts","persona_memory"]`. The wrapper now consumes
+  that intent plan directly, runs Brave and recall first, and passes
+  `external_sources` plus `recall_snapshot` into `/answer`. Proof:
+  `/tmp/personaplex-memory-intent-flow-proof.json` (`/answer` returned
+  `memory.answer.v1`, `can_answer=true`, `answer_type=persona_current_fact_blend`,
+  `external_sources_count=1`, `recall_item_count=8`,
+  `source_packet_included=true`).
+- `$scillm` is not yet in the wrapper. The current forced speech endpoint uses a
+  deterministic script assembled from memory/Brave/route products.
+- Direct async Deepgram live ASR/VAD is wired into the custom golden-state
+  WebSocket wrapper, not a separate microservice. Incoming client Opus is
+  decoded once, PCM is fed to both Moshi/PersonaPlex and Deepgram, Deepgram
+  `speech_final=true` transcript events trigger grounding, and an output gate masks generated
+  audio/text with silence until required memory/Brave/answer stages finish.
+  New code: `scripts/personaplex_deepgram_live.py` and
+  `scripts/personaplex_memory_flow.py`; live proof harness:
+  `scripts/personaplex_deepgram_live_probe.py`; wrapper entry:
+  `scripts/personaplex_golden_state_server.py`. Deterministic proof under the
+  PersonaPlex venv parsed a representative Deepgram final transcript and
+  closed/opened the gate. Live Deepgram proof receipt:
+  `/mnt/storage12tb/skills/personaplex/outputs/deepgram-live-probe/embry/20260622T203618Z/personaplex-deepgram-live-probe-receipt.json`.
+  It streamed a synthesized 24 kHz speech fixture through browser-style Opus
+  frames, received full transcript
+  `Embry, what is the weather like in Hawaii today, and how would that make you feel about surfing with Kai?`
+  with `speech_final=true`, then emitted `grounding_started`, four
+  `grounding_stage_queued` stages (`intent`, `memory`, `brave`, `route`), and
+  `grounding_complete` with the gate open and `queue_depth=268`.
+
+## Artifact Roots
+
+- Code: `skills/personaplex`
+- Heavy outputs: `/mnt/storage12tb/skills/personaplex/outputs`
+- Work/log/data/model roots are symlinked to `/mnt/storage12tb/skills/personaplex`.

diff --git a/skills/personaplex/scripts/personaplex_deepgram_live.py b/skills/personaplex/scripts/personaplex_deepgram_live.py
new file mode 100644
index 000000000..81843ddcf
--- /dev/null
+++ b/skills/personaplex/scripts/personaplex_deepgram_live.py
@@ -0,0 +1,135 @@
+"""Deepgram live ASR bridge for the PersonaPlex golden-state wrapper."""
+
+from __future__ import annotations
+
+import asyncio
+import json
+import os
+import time
+from dataclasses import dataclass
+from typing import Any
+
+import aiohttp
+import numpy as np
+
+
+def ms_since(start: float) -> float:
+    return round((time.monotonic() - start) * 1000, 2)
+
+
+@dataclass
+class TranscriptTurn:
+    text: str
+    elapsed_ms: float
+    speech_final: bool
+    is_final: bool
+
+
+class OutputGate:
+    def __init__(self) -> None:
+        self.active = False
+        self.reason = ""
+        self.started_at = 0.0
+        self.released_at = 0.0
+
+    def close(self, reason: str) -> None:
+        self.active = True
+        self.reason = reason
+        self.started_at = time.monotonic()
+
+    def open(self) -> None:
+        self.active = False
+        self.released_at = time.monotonic()
+
+    def snapshot(self) -> dict[str, Any]:
+        return {
+            "active": self.active,
+            "reason": self.reason,
+            "elapsed_ms": ms_since(self.started_at) if self.active else 0.0,
+        }
+
+
+class DeepgramLiveClient:
+    def __init__(self, *, sample_rate: int, model: str = "nova-3", enabled: bool = True):
+        self.sample_rate = sample_rate
+        self.model = model
+        self.enabled = enabled and bool(os.environ.get("DEEPGRAM_API_KEY"))
+        self.audio_queue: asyncio.Queue[np.ndarray | None] = asyncio.Queue(maxsize=128)
+        self.turn_queue: asyncio.Queue[TranscriptTurn] = asyncio.Queue()
+        self.started_at = time.monotonic()
+        self._final_parts: list[str] = []
+
+    def enqueue_pcm(self, pcm: np.ndarray) -> None:
+        if not self.enabled:
+            return
+        try:
+            self.audio_queue.put_nowait(np.asarray(pcm, dtype=np.float32).copy())
+        except asyncio.QueueFull:
+            _ = self.audio_queue.get_nowait()
+            self.audio_queue.put_nowait(np.asarray(pcm, dtype=np.float32).copy())
+
+    async def close(self) -> None:
+        if self.enabled:
+            await self.audio_queue.put(None)
+
+    async def run(self) -> None:
+        if not self.enabled:
+            return
+        params = {
+            "model": self.model,
+            "encoding": "linear16",
+            "sample_rate": str(self.sample_rate),
+            "channels": "1",
+            "punctuate": "true",
+            "smart_format": "true",
+            "interim_results": "true",
+            "vad_events": "true",
+            "endpointing": "300",
+        }
+        url = "wss://api.deepgram.com/v1/listen?" + "&".join(f"{k}={v}" for k, v in params.items())
+        headers = {"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"}
+        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, connect=5)) as session:
+            async with session.ws_connect(url, headers=headers, heartbeat=10) as ws:
+                sender = asyncio.create_task(self._send_audio(ws))
+                try:
+                    async for message in ws:
+                        if message.type == aiohttp.WSMsgType.TEXT:
+                            self._handle_message(json.loads(message.data))
+                        elif message.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
+                            break
+                finally:
+                    sender.cancel()
+
+    async def _send_audio(self, ws: aiohttp.ClientWebSocketResponse) -> None:
+        while True:
+            pcm = await self.audio_queue.get()
+            if pcm is None:
+                await ws.send_str(json.dumps({"type": "CloseStream"}))
+                return
+            pcm16 = np.clip(pcm, -1.0, 1.0)
+            await ws.send_bytes((pcm16 * 32767.0).astype("<i2").tobytes())
+
+    def _handle_message(self, payload: dict[str, Any]) -> None:
+        if payload.get("type") != "Results":
+            return
+        channel = payload.get("channel") or {}
+        alternatives = channel.get("alternatives") or []
+        is_final = bool(payload.get("is_final"))
+        speech_final = bool(payload.get("speech_final"))
+        transcript = (alternatives[0].get("transcript") if alternatives else "") or ""
+        transcript = transcript.strip()
+        if not transcript and not (speech_final and self._final_parts):
+            return
+        if is_final:
+            self._final_parts.append(transcript)
+        if speech_final:
+            full_transcript = " ".join(self._final_parts).strip() or transcript
+            self._final_parts.clear()
+            self.turn_queue.put_nowait(
+                TranscriptTurn(
+                    text=full_transcript,
+                    elapsed_ms=ms_since(self.started_at),
+                    speech_final=speech_final,
+                    is_final=is_final,
+                )
+            )

diff --git a/skills/personaplex/scripts/personaplex_deepgram_live_probe.py b/skills/personaplex/scripts/personaplex_deepgram_live_probe.py
new file mode 100644
index 000000000..adbdff24c
--- /dev/null
+++ b/skills/personaplex/scripts/personaplex_deepgram_live_probe.py
@@ -0,0 +1,279 @@
+#!/usr/bin/env python3
+"""Live Deepgram ASR/VAD probe for the PersonaPlex golden-state wrapper."""
+
+from __future__ import annotations
+
+import argparse
+import asyncio
+import datetime as dt
+import hashlib
+import json
+import os
+import ssl
+import subprocess
+import sys
+import time
+import urllib.parse
+from pathlib import Path
+from typing import Any
+
+
+ROOT = Path("/home/graham/workspace/experiments/agent-skills")
+PERSONAPLEX_PYTHON = Path("/home/graham/workspace/experiments/personaplex/.venv/bin/python")
+OUTPUT_ROOT = Path("/mnt/storage12tb/skills/personaplex/outputs/deepgram-live-probe/embry")
+DEFAULT_QUESTION = (
+    "Embry, what is the weather like in Hawaii today, "
+    "and how would that make you feel about surfing with Kai?"
+)
+
+
+def ensure_runtime_python() -> None:
+    if PERSONAPLEX_PYTHON.exists() and Path(sys.executable).resolve() != PERSONAPLEX_PYTHON.resolve():
+        os.execv(str(PERSONAPLEX_PYTHON), [str(PERSONAPLEX_PYTHON), __file__, *sys.argv[1:]])
+
+
+def utc_stamp() -> str:
+    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
+
+
+def write_json(path: Path, payload: Any) -> None:
+    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
+
+
+def sha256_path(path: Path) -> str:
+    digest = hashlib.sha256()
+    with path.open("rb") as handle:
+        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
+            digest.update(chunk)
+    return digest.hexdigest()
+
+
+def synthesize_question_wav(text: str, output_dir: Path) -> Path:
+    raw = output_dir / "user-question-raw.wav"
+    wav = output_dir / "user-question-24khz-mono.wav"
+    espeak = subprocess.run(
+        ["bash", "-lc", "command -v espeak-ng || command -v espeak"],
+        capture_output=True,
+        text=True,
+        check=True,
+    )
+    espeak_path = espeak.stdout.strip().splitlines()[0]
+    subprocess.run([espeak_path, "-w", str(raw), text], check=True)
+    subprocess.run(
+        [
+            "ffmpeg",
+            "-y",
+            "-hide_banner",
+            "-loglevel",
+            "error",
+            "-i",
+            str(raw),
+            "-ar",
+            "24000",
+            "-ac",
+            "1",
+            "-c:a",
+            "pcm_s16le",
+            str(wav),
+        ],
+        check=True,
+    )
+    return wav
+
+
+def wav_metrics(path: Path) -> dict[str, Any]:
+    import soundfile as sf
+
+    data, sample_rate = sf.read(str(path), always_2d=True)
+    info = sf.info(str(path))
+    return {
+        "path": str(path),
+        "sha256": sha256_path(path),
+        "size_bytes": path.stat().st_size,
+        "sample_rate": int(sample_rate),
+        "channels": int(data.shape[1]),
+        "frames": int(data.shape[0]),
+        "duration_s": round(float(info.duration), 3),
+        "peak": float(abs(data).max()) if data.size else 0.0,
+        "rms": float((data * data).mean() ** 0.5) if data.size else 0.0,
+    }
+
+
+async def live_probe(
+    url_base: str,
+    wav_path: Path,
+    output_dir: Path,
+    *,
+    trailing_silence_s: float,
+    wait_after_audio_s: float,
+) -> dict[str, Any]:
+    import aiohttp
+    import numpy as np
+    import soundfile as sf
+    import sphn
+
+    audio, sample_rate = sf.read(str(wav_path), dtype="float32", always_2d=False)
+    if audio.ndim != 1:
+        audio = audio[:, 0]
+    if sample_rate != 24000:
+        raise ValueError(f"expected 24kHz input WAV, got {sample_rate}")
+
+    params = {"deepgram": "1"}
+    url = f"{url_base}/api/chat?{urllib.parse.urlencode(params)}"
+    event_path = output_dir / "deepgram-live-events.jsonl"
+    server_audio_path = output_dir / "server-audio.opus-pages.bin"
+
+    def append_event(payload: dict[str, Any]) -> None:
+        with event_path.open("a", encoding="utf-8") as handle:
+            handle.write(json.dumps({"ts": dt.datetime.now(dt.UTC).isoformat(), **payload}, sort_keys=True) + "\n")
+
+    writer = sphn.OpusStreamWriter(24000)
+    server_audio_chunks: list[bytes] = []
+    control_events: list[dict[str, Any]] = []
+    start = time.monotonic()
+    timings: dict[str, float] = {}
+    ssl_ctx = ssl.create_default_context()
+    ssl_ctx.check_hostname = False
+    ssl_ctx.verify_mode = ssl.CERT_NONE
+
+    async with aiohttp.ClientSession() as session:
+        append_event({"event": "connect_start", "url": url})
+        async with session.ws_connect(url, ssl=ssl_ctx, timeout=90, receive_timeout=90) as ws:
+            timings["connected_ms"] = round((time.monotonic() - start) * 1000, 2)
+            while True:
+                msg = await asyncio.wait_for(ws.receive(), timeout=90)
+                if msg.type == aiohttp.WSMsgType.BINARY and msg.data and msg.data[0] == 0:
+                    timings["handshake_ms"] = round((time.monotonic() - start) * 1000, 2)
+                    append_event({"event": "handshake_marker", "elapsed_ms": timings["handshake_ms"]})
+                    break
+                if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
+                    raise RuntimeError(f"socket closed before handshake: {msg.type} {msg.data!r}")
+
+            async def receive_loop() -> None:
+                while True:
+                    msg = await ws.receive()
+                    if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
+                        append_event({"event": "socket_closed", "type": str(msg.type)})
+                        return
+                    if msg.type != aiohttp.WSMsgType.BINARY or not msg.data:
+                        continue
+                    kind = msg.data[0]
+                    payload = bytes(msg.data[1:])
+                    now_ms = round((time.monotonic() - start) * 1000, 2)
+                    if kind == 1:
+                        server_audio_chunks.append(payload)
+                        if "first_audio_ms" not in timings:
+                            timings["first_audio_ms"] = now_ms
+                            append_event({"event": "first_audio", "elapsed_ms": now_ms, "bytes": len(payload)})
+                    elif kind == 2:
+                        if "first_text_ms" not in timings:
+                            timings["first_text_ms"] = now_ms
+                            append_event({"event": "first_text", "elapsed_ms": now_ms})
+                    elif kind == 4:
+                        decoded = json.loads(payload.decode("utf-8", errors="replace"))
+                        decoded["elapsed_ms"] = now_ms
+                        control_events.append(decoded)
+                        append_event({"event": "control", **decoded})
+
+            recv_task = asyncio.create_task(receive_loop())
+            frame = 1920
+            sent_pages = 0
+            for offset in range(0, len(audio), frame):
+                chunk = audio[offset : offset + frame]
+                if len(chunk) < frame:
+                    chunk = np.pad(chunk, (0, frame - len(chunk)))
+                writer.append_pcm(chunk.astype("float32"))
+                pages = writer.read_bytes()
+                if pages:
+                    await ws.send_bytes(b"\x01" + pages)
+                    sent_pages += 1
+                await asyncio.sleep(0.08)
+            silence_frames = int((trailing_silence_s * 24000) // frame)
+            for _ in range(silence_frames):
+                writer.append_pcm(np.zeros(frame, dtype="float32"))
+                pages = writer.read_bytes()
+                if pages:
+                    await ws.send_bytes(b"\x01" + pages)
+                    sent_pages += 1
+                await asyncio.sleep(0.08)
+            timings["input_sent_ms"] = round((time.monotonic() - start) * 1000, 2)
+            append_event(
+                {
+                    "event": "input_sent",
+                    "elapsed_ms": timings["input_sent_ms"],
+                    "sent_pages": sent_pages,
+                    "trailing_silence_s": trailing_silence_s,
+                }
+            )
+            await asyncio.sleep(wait_after_audio_s)
+            await ws.close()
+            await recv_task
+
+    server_audio_path.write_bytes(b"".join(server_audio_chunks))
+    asr_events = [event for event in control_events if event.get("event") == "asr_turn_final"]
+    grounding_started = [event for event in control_events if event.get("event") == "grounding_started"]
+    grounding_complete = [event for event in control_events if event.get("event") == "grounding_complete"]
+    queued = [event for event in control_events if event.get("event") == "grounding_stage_queued"]
+    return {
+        "ok": bool(asr_events and grounding_started and grounding_complete),
+        "url": url,
+        "timings": timings,
+        "sent_pages": sent_pages,
+        "control_event_count": len(control_events),
+        "control_event_names": [event.get("event") for event in control_events],
+        "asr_events": asr_events,
+        "grounding_started": grounding_started,
+        "grounding_stage_names": [event.get("stage") for event in queued],
+        "grounding_complete": grounding_complete,
+        "server_audio": {
+            "path": str(server_audio_path),
+            "chunks": len(server_audio_chunks),
+            "bytes": server_audio_path.stat().st_size if server_audio_path.exists() else 0,
+        },
+        "events_jsonl": str(event_path),
+    }
+
+
+def parse_args() -> argparse.Namespace:
+    parser = argparse.ArgumentParser()
+    parser.add_argument("--question", default=DEFAULT_QUESTION)
+    parser.add_argument("--url-base", default="ws://127.0.0.1:9008")
+    parser.add_argument("--trailing-silence-s", type=float, default=2.0)
+    parser.add_argument("--wait-after-audio-s", type=float, default=18.0)
+    return parser.parse_args()
+
+
+def main() -> int:
+    ensure_runtime_python()
+    args = parse_args()
+    output_dir = OUTPUT_ROOT / utc_stamp()
+    output_dir.mkdir(parents=True, exist_ok=False)
+    total_start = time.monotonic()
+    wav_path = synthesize_question_wav(args.question, output_dir)
+    probe = asyncio.run(
+        live_probe(
+            args.url_base,
+            wav_path,
+            output_dir,
+            trailing_silence_s=args.trailing_silence_s,
+            wait_after_audio_s=args.wait_after_audio_s,
+        )
+    )
+    receipt = {
+        "schema": "personaplex.deepgram_live_probe.v1",
+        "status": "PASS" if probe["ok"] else "FAIL",
+        "claim_boundary": "Live Deepgram websocket ASR/VAD from Opus user-audio fixture into PersonaPlex wrapper; fixture is synthesized speech, not microphone capture.",
+        "deepgram_api_key_set": bool(os.environ.get("DEEPGRAM_API_KEY")),
+        "question": args.question,
+        "input_wav": wav_metrics(wav_path),
+        "probe": probe,
+        "total_ms": round((time.monotonic() - total_start) * 1000, 2),
+    }
+    receipt_path = output_dir / "personaplex-deepgram-live-probe-receipt.json"
+    write_json(receipt_path, receipt)
+    print(json.dumps({"status": receipt["status"], "receipt": str(receipt_path)}, indent=2))
+    return 0 if receipt["status"] == "PASS" else 1
+
+
+if __name__ == "__main__":
+    raise SystemExit(main())

diff --git a/skills/personaplex/scripts/personaplex_golden_state_server.py b/skills/personaplex/scripts/personaplex_golden_state_server.py
new file mode 100644
index 000000000..e015bd38b
--- /dev/null
+++ b/skills/personaplex/scripts/personaplex_golden_state_server.py
@@ -0,0 +1,767 @@
+#!/usr/bin/env python3
+"""Golden-state PersonaPlex wrapper for grounded Embry experiments.
+
+Imports Moshi/PersonaPlex modules instead of forking ``moshi.server``. It does
+Embry voice/persona pre-roll once at boot, clones the preconditioned streaming
+state, restores it for sessions, runs memory-first + Brave staged grounding,
+and wires optional Deepgram live ASR/VAD into the WebSocket interaction loop.
+"""
+
+from __future__ import annotations
+
+import argparse
+import asyncio
+import dataclasses
+import datetime as dt
+import json
+import os
+import random
+import sys
+import time
+import wave
+from pathlib import Path
+from typing import Any
+
+ROOT = Path("/home/graham/workspace/experiments/agent-skills")
+PERSONAPLEX_ROOT = Path("/home/graham/workspace/experiments/personaplex")
+PERSONAPLEX_PYTHON = PERSONAPLEX_ROOT / ".venv/bin/python"
+if PERSONAPLEX_PYTHON.exists() and Path(sys.executable).resolve() != PERSONAPLEX_PYTHON.resolve():
+    os.execv(str(PERSONAPLEX_PYTHON), [str(PERSONAPLEX_PYTHON), __file__, *sys.argv[1:]])
+
+_nvidia_libs = sorted(Path(PERSONAPLEX_PYTHON).parents[1].glob("lib/python*/site-packages/nvidia/*/lib"))
+if _nvidia_libs and "nvidia/cudnn/lib" not in os.environ.get("LD_LIBRARY_PATH", ""):
+    env = dict(os.environ)
+    existing_ld = env.get("LD_LIBRARY_PATH")
+    env["LD_LIBRARY_PATH"] = ":".join([*(str(path) for path in _nvidia_libs if path.is_dir()), *( [existing_ld] if existing_ld else [] )])
+    os.execve(sys.executable, [sys.executable, __file__, *sys.argv[1:]], env)
+
+import aiohttp
+from aiohttp import web
+import numpy as np
+import sphn
+import torch
+
+from personaplex_deepgram_live import DeepgramLiveClient, OutputGate
+from personaplex_memory_flow import (
+    evidence_case_gate_product,
+    intent_requires_evidence_case,
+    memory_route_product_with_sources,
+    planned_brave_query,
+    planned_recall_payload,
+)
+
+
+BRAVE_RUN = ROOT / "skills/brave-search/run.sh"
+MEMORY_URL = "http://127.0.0.1:8601"
+DEFAULT_VOICE_PROMPT = Path(
+    "/mnt/storage12tb/skills/personaplex/outputs/e2e/"
+    "embry-conversational-20260622T152647Z/neutral/voice-prompt.pt"
+)
+DEFAULT_TEXT_PROMPT = (
+    "You are Embry Lawson. You are warm, concise, grounded, and emotionally "
+    "present. Use retrieved facts when supplied. If evidence is limited, say so."
+)
+DEFAULT_BRAVE_QUERY = "Hawaii weather surf forecast today"
+DEFAULT_OUTPUT_DIR = Path("/mnt/storage12tb/skills/personaplex/outputs/golden-state-wrapper")
+
+def seed_all(seed: int) -> None:
+    torch.manual_seed(seed)
+    if torch.cuda.is_available():
+        torch.cuda.manual_seed(seed)
+        torch.cuda.manual_seed_all(seed)
+    random.seed(seed)
+    np.random.seed(seed)
+
+
+def wrap_with_system_tags(text: str) -> str:
+    cleaned = text.strip()
+    if cleaned.startswith("<system>") and cleaned.endswith("<system>"):
+        return cleaned
+    return f"<system> {cleaned} <system>"
+
+
+def utc_now() -> str:
+    return dt.datetime.now(dt.UTC).isoformat()
+
+
+def ms_since(start: float) -> float:
+    return round((time.monotonic() - start) * 1000, 2)
+
+
+def clone_streaming_state(value: Any) -> Any:
+    if torch.is_tensor(value):
+        return value.detach().clone()
+    if dataclasses.is_dataclass(value):
+        kwargs = {field.name: clone_streaming_state(getattr(value, field.name)) for field in dataclasses.fields(value)}
+        return type(value)(**kwargs)
+    if isinstance(value, dict):
+        return {key: clone_streaming_state(item) for key, item in value.items()}
+    if isinstance(value, list):
+        return [clone_streaming_state(item) for item in value]
+    if isinstance(value, tuple):
+        return tuple(clone_streaming_state(item) for item in value)
+    return value
+
+
+async def timed_post(endpoint: str, payload: dict[str, Any], *, timeout: float = 10.0) -> dict[str, Any]:
+    start = time.monotonic()
+    try:
+        client_timeout = aiohttp.ClientTimeout(total=timeout, connect=min(timeout, 2.0))
+        async with aiohttp.ClientSession(timeout=client_timeout) as session:
+            async with session.post(
+                f"{MEMORY_URL}{endpoint}",
+                json=payload,
+                headers={"Accept": "application/json"},
+            ) as response:
+                text = await response.text()
+                status_code = response.status
+                content_type = response.headers.get("content-type", "")
+        parsed = json.loads(text) if "application/json" in content_type else None
+        return {
+            "ok": 200 <= status_code < 300,
+            "status_code": status_code,
+            "elapsed_ms": ms_since(start),
+            "json": parsed,
+            "text_excerpt": None if parsed is not None else text[:1000],
+        }
+    except Exception as exc:
+        return {
+            "ok": False,
+            "elapsed_ms": ms_since(start),
+            "error_type": type(exc).__name__,
+            "error": str(exc),
+        }
+
+
+async def brave_search(query: str, count: int) -> dict[str, Any]:
+    start = time.monotonic()
+    proc = await asyncio.create_subprocess_exec(
+        "bash",
+        "-lc",
+        f"source ~/.zshrc >/dev/null 2>&1; {BRAVE_RUN} web {json.dumps(query)} --count {count} --json",
+        cwd=str(ROOT),
+        stdout=asyncio.subprocess.PIPE,
+        stderr=asyncio.subprocess.PIPE,
+    )
+    try:
+        stdout_raw, stderr_raw = await asyncio.wait_for(proc.communicate(), timeout=30)
+    except TimeoutError:
+        proc.kill()
+        stdout_raw, stderr_raw = await proc.communicate()
+        return {
+            "ok": False,
+            "elapsed_ms": ms_since(start),
+            "returncode": proc.returncode,
+            "stderr_excerpt": stderr_raw.decode("utf-8", errors="replace")[-1200:],
+            "error": "brave_search_timeout",
+        }
+    stdout = stdout_raw.decode("utf-8", errors="replace")
+    stderr = stderr_raw.decode("utf-8", errors="replace")
+    out: dict[str, Any] = {
+        "ok": proc.returncode == 0,
+        "elapsed_ms": ms_since(start),
+        "returncode": proc.returncode,
+        "stderr_excerpt": stderr[-1200:],
+    }
+    try:
+        out["json"] = json.loads(stdout)
+    except json.JSONDecodeError:
+        out["ok"] = False
+        out["stdout_excerpt"] = stdout[:1200]
+        out["error"] = "Brave output was not JSON"
+    return out
+
+
+def compact_memory(recall: dict[str, Any], limit: int = 280) -> str:
+    items = (recall.get("json") or {}).get("items") or []
+    for item in items:
+        text = item.get("retrieval_text") or item.get("text") or item.get("summary") or item.get("problem")
+        if text:
+            return str(text)[:limit]
+    return "No strong Embry persona memory returned."
+
+
+def compact_brave(brave: dict[str, Any], limit: int = 300) -> str:
+    results = (brave.get("json") or {}).get("results") or []
+    if not results:
+        return "No current Brave Search result returned."
+    top = results[0]
+    return f"{top.get('title', '')}: {top.get('description', '')}"[:limit]
+
+
+def compact_answer_route(route: dict[str, Any], limit: int = 420) -> str:
+    data = route.get("json") or {}
+    if data.get("can_answer"):
+        text = data.get("final_response") or data.get("source_answer") or data.get("answer")
+        if text:
+            return str(text)[:limit]
+    questions = data.get("questions") or data.get("clarifying_questions")
+    if questions:
+        return f"Clarification needed: {questions[0]}"[:limit]
+    if data.get("should_deflect"):
+        return str(data.get("message") or data.get("reason") or "This should be deflected.")[:limit]
+    return "Memory route did not produce a final answer."
+
+
+def write_wav(path: Path, pcm: np.ndarray, sample_rate: int) -> dict[str, Any]:
+    path.parent.mkdir(parents=True, exist_ok=True)
+    clipped = np.clip(pcm, -1.0, 1.0)
+    pcm16 = (clipped * 32767.0).astype(np.int16)
+    with wave.open(str(path), "wb") as handle:
+        handle.setnchannels(1)
+        handle.setsampwidth(2)
+        handle.setframerate(sample_rate)
+        handle.writeframes(pcm16.tobytes())
+    return {
+        "path": str(path),
+        "bytes": path.stat().st_size,
+        "sample_rate": sample_rate,
+        "duration_seconds": round(float(len(pcm16)) / float(sample_rate), 3),
+    }
+
+
+class GoldenEmbryServer:
+    def __init__(self, args: argparse.Namespace):
+        sys.path.insert(0, str(PERSONAPLEX_ROOT))
+        from huggingface_hub import hf_hub_download
+        import sentencepiece
+        from moshi.models import loaders, LMGen
+
+        self.args = args
+        self.device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
+        self.timings: dict[str, float] = {}
+        self.model_lock = asyncio.Lock()
+        self.frame_size = 0
+
+        seed_all(args.seed)
+        boot_start = time.monotonic()
+        load_start = time.monotonic()
+        mimi_weight = hf_hub_download(loaders.DEFAULT_REPO, loaders.MIMI_NAME)
+        tokenizer_path = hf_hub_download(loaders.DEFAULT_REPO, loaders.TEXT_TOKENIZER_NAME)
+        moshi_weight = hf_hub_download(loaders.DEFAULT_REPO, loaders.MOSHI_NAME)
+        self.mimi = loaders.get_mimi(mimi_weight, self.device)
+        self.other_mimi = loaders.get_mimi(mimi_weight, self.device)
+        self.text_tokenizer = sentencepiece.SentencePieceProcessor(tokenizer_path)  # type: ignore
+        lm = loaders.get_moshi_lm(moshi_weight, device=self.device, cpu_offload=args.cpu_offload)
+        lm.eval()
+        self.frame_size = int(self.mimi.sample_rate / self.mimi.frame_rate)
+        self.lm_gen = LMGen(lm, audio_silence_frame_cnt=int(0.5 * self.mimi.frame_rate),
+                            sample_rate=self.mimi.sample_rate, device=self.device,
+                            frame_rate=self.mimi.frame_rate, save_voice_prompt_embeddings=False)
+        self.mimi.streaming_forever(1)
+        self.other_mimi.streaming_forever(1)
+        self.lm_gen.streaming_forever(1)
+        self._sync_cuda()
+        self.timings["load_ms"] = ms_since(load_start)
+
+        self._warmup()
+        self._build_golden_state(args.voice_prompt, args.text_prompt)
+        self.timings["boot_total_ms"] = ms_since(boot_start)
+
+    def _sync_cuda(self) -> None:
+        if self.device.type == "cuda":
+            torch.cuda.synchronize()
+
+    def _warmup(self) -> None:
+        start = time.monotonic()
+        with torch.no_grad():
+            for _ in range(4):
+                chunk = torch.zeros(1, 1, self.frame_size, dtype=torch.float32, device=self.device)
+                codes = self.mimi.encode(chunk)
+                _ = self.other_mimi.encode(chunk)
+                for c in range(codes.shape[-1]):
+                    tokens = self.lm_gen.step(codes[:, :, c : c + 1])
+                    if tokens is None:
+                        continue
+                    _ = self.mimi.decode(tokens[:, 1:9])
+                    _ = self.other_mimi.decode(tokens[:, 1:9])
+        self._sync_cuda()
+        self.timings["warmup_ms"] = ms_since(start)
+
+    def _build_golden_state(self, voice_prompt: Path, text_prompt: str) -> None:
+        if not voice_prompt.exists():
+            raise FileNotFoundError(f"voice prompt not found: {voice_prompt}")
+        start = time.monotonic()
+        self.lm_gen.load_voice_prompt_embeddings(str(voice_prompt))
+        self.lm_gen.text_prompt_tokens = self.text_tokenizer.encode(wrap_with_system_tags(text_prompt))
+        with torch.no_grad():
+            self.mimi.reset_streaming()
+            self.other_mimi.reset_streaming()
+            self.lm_gen.reset_streaming()
+            self.lm_gen.step_system_prompts(self.mimi)
+            self.mimi.reset_streaming()
+        self._sync_cuda()
+        self.timings["golden_pre_roll_ms"] = ms_since(start)
+
+        clone_start = time.monotonic()
+        self.golden_state = clone_streaming_state(self.lm_gen.get_streaming_state())
+        self._sync_cuda()
+        self.timings["golden_clone_ms"] = ms_since(clone_start)
+
+    def restore_golden_state(self) -> float:
+        start = time.monotonic()
+        with torch.no_grad():
+            self.mimi.reset_streaming()
+            self.other_mimi.reset_streaming()
+            self.lm_gen.set_streaming_state(clone_streaming_state(self.golden_state))
+        self._sync_cuda()
+        return ms_since(start)
+
+    async def iter_research_stages(self, question: str, brave_query: str, brave_count: int):
+        start = time.monotonic()
+
+        async def named(name: str, awaitable):
+            result = await awaitable
+            return name, result
+
+        intent_result = await timed_post(
+            "/intent",
+            {"q": question, "scope": "persona_memory", "fast": True},
+        )
+        intent_data = intent_result.get("json") or {}
+        recall_payload = planned_recall_payload(intent_result)
+        search_query = planned_brave_query(intent_result, brave_query)
+        yield {
+            "name": "intent", "elapsed_ms": ms_since(start), "result": intent_result,
+            "inject_text": (
+                "Internal routing note for the next answer: "
+                f"intent={intent_data.get('action')}; recall_profile={intent_data.get('recall_profile')}. "
+                "Do not mention this routing note to the user."
+            )}
+
+        tasks = [
+            asyncio.create_task(named("memory", timed_post("/recall", recall_payload))),
+            asyncio.create_task(named("brave", brave_search(search_query, brave_count))),
+        ]
+        if intent_requires_evidence_case(intent_result):
+            tasks.append(asyncio.create_task(named("route", evidence_case_gate_product(question, intent_result))))
+
+        recall_result: dict[str, Any] | None = None
+        brave_result: dict[str, Any] | None = None
+        route_yielded = False
+        for completed in asyncio.as_completed(tasks):
+            name, result = await completed
+            stage: dict[str, Any] = {"name": name, "elapsed_ms": ms_since(start), "result": result, "inject_text": ""}
+            if name == "memory":
+                recall_result = result
+                stage["inject_text"] = f"Memory grounding for the next answer: {compact_memory(result)}"
+            elif name == "brave":
+                brave_result = result
+                stage["inject_text"] = f"Current web grounding for the next answer: {compact_brave(result)}"
+            elif name == "route":
+                route_yielded = True
+                if result.get("requires_evidence_case"):
+                    stage["inject_text"] = (
+                        "Evidence gate for the next answer: this request needs "
+                        "a create-evidence-case verdict before a factual answer. "
+                        "Acknowledge the need to check evidence; do not provide "
+                        "a compliance conclusion yet."
+                    )
+                else:
+                    stage["inject_text"] = f"Memory route product for the next answer: {compact_answer_route(result)}"
+            yield stage
+
+        if not route_yielded:
+            route_result = await memory_route_product_with_sources(question, intent_result, recall_result, brave_result, timed_post)
+            yield {
+                "name": "route", "elapsed_ms": ms_since(start), "result": route_result,
+                "inject_text": f"Memory route product for the next answer: {compact_answer_route(route_result)}",
+            }
+
+    async def research_turn(self, question: str, brave_query: str, brave_count: int) -> dict[str, Any]:
+        start = time.monotonic()
+        stages: list[dict[str, Any]] = []
+        intent: dict[str, Any] | None = None
+        recall: dict[str, Any] | None = None
+        brave: dict[str, Any] | None = None
+        route: dict[str, Any] | None = None
+        async for stage in self.iter_research_stages(question, brave_query, brave_count):
+            stages.append(stage)
+            if stage["name"] == "intent":
+                intent = stage["result"]
+            elif stage["name"] == "memory":
+                recall = stage["result"]
+            elif stage["name"] == "brave":
+                brave = stage["result"]
+            elif stage["name"] == "route":
+                route = stage["result"]
+        intent = intent or {"ok": False, "error": "intent_not_returned"}
+        recall = recall or {"ok": False, "error": "memory_not_returned"}
+        brave = brave or {"ok": False, "error": "brave_not_returned"}
+        route = route or {"ok": False, "error": "route_not_returned"}
+        evidence_gated = bool(route.get("requires_evidence_case"))
+        script = self.script_from_research(question=question, recall=recall, brave=brave, route=route, evidence_gated=evidence_gated)
+        return {
+            "schema": "personaplex.research_turn.v1",
+            "created_at": utc_now(),
+            "ok": bool(recall.get("ok") and brave.get("ok") and (route.get("ok") or evidence_gated)),
+            "elapsed_ms": ms_since(start),
+            "question": question,
+            "brave_query": brave_query,
+            "evidence_gated": evidence_gated,
+            "stage_order": [
+                {
+                    "name": stage["name"],
+                    "elapsed_ms": stage["elapsed_ms"],
+                    "inject_text_chars": len(stage.get("inject_text") or ""),
+                    "ok": bool((stage.get("result") or {}).get("ok")),
+                }
+                for stage in stages
+            ],
+            "intent": intent,
+            "recall": recall,
+            "brave": brave,
+            "route": route,
+            "script": script,
+            "script_chars": len(script),
+        }
+
+    def script_from_research(
+        self,
+        *,
+        question: str,
+        recall: dict[str, Any],
+        brave: dict[str, Any],
+        route: dict[str, Any],
+        evidence_gated: bool,
+    ) -> str:
+        if evidence_gated:
+            return (
+                "I need to check the evidence case before I answer that. "
+                "I can look at the internal memory and current sources, but I should not give a compliance conclusion until the evidence case is built."
+            )
+        route_text = compact_answer_route(route)
+        if route.get("ok") and route_text != "Memory route did not produce a final answer.":
+            return route_text
+        memory_text = compact_memory(recall)
+        search_text = compact_brave(brave)
+        return (
+            "I found partial context. "
+            f"Memory says: {memory_text}. "
+            f"Current search says: {search_text}. "
+            "I would treat that as preliminary rather than final."
+        )
+
+    def force_speech_to_wav(self, text: str, out_path: Path) -> dict[str, Any]:
+        start = time.monotonic()
+        tokens = self.text_tokenizer.encode(text.strip())
+        audio_chunks: list[np.ndarray] = []
+        with torch.no_grad():
+            self.restore_golden_state()
+            silence = torch.zeros(1, 1, self.frame_size, dtype=torch.float32, device=self.device)
+            codes = self.mimi.encode(silence)
+            for token in tokens:
+                forced = torch.tensor([int(token)], dtype=torch.long, device=self.device)
+                step_tokens = self.lm_gen.step(codes[:, :, :1], text_token=forced)
+                if step_tokens is None:
+                    continue
+                main_pcm = self.mimi.decode(step_tokens[:, 1:9])
+                audio_chunks.append(main_pcm.cpu()[0, 0].numpy())
+            for _ in range(6):
+                step_tokens = self.lm_gen.step(codes[:, :, :1], text_token=torch.tensor([3], dtype=torch.long, device=self.device))
+                if step_tokens is None:
+                    continue
+                main_pcm = self.mimi.decode(step_tokens[:, 1:9])
+                audio_chunks.append(main_pcm.cpu()[0, 0].numpy())
+        self._sync_cuda()
+        pcm = np.concatenate(audio_chunks) if audio_chunks else np.zeros(self.frame_size, dtype=np.float32)
+        wav = write_wav(out_path, pcm, int(self.mimi.sample_rate))
+        return {
+            "text": text,
+            "text_chars": len(text),
+            "text_tokens": len(tokens),
+            "elapsed_ms": ms_since(start),
+            "wav": wav,
+        }
+
+    async def health(self, _request: web.Request) -> web.Response:
+        return web.json_response(
+            {
+                "schema": "personaplex.golden_state_server.health.v1",
+                "ok": True,
+                "device": str(self.device),
+                "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
+                "timings": self.timings,
+                "voice_prompt": str(self.args.voice_prompt),
+                "claim_boundary": "golden-state wrapper booted; /api/chat supports optional Deepgram live ASR/VAD when DEEPGRAM_API_KEY is set",
+            }
+        )
+
+    async def research_endpoint(self, request: web.Request) -> web.Response:
+        payload = await request.json()
+        question = str(payload.get("question") or self.args.default_question)
+        brave_query = str(payload.get("brave_query") or self.args.default_brave_query)
+        brave_count = int(payload.get("brave_count") or 3)
+        result = await self.research_turn(question, brave_query, brave_count)
+        return web.json_response(result)
+
+    async def grounded_speech_endpoint(self, request: web.Request) -> web.Response:
+        payload = await request.json()
+        question = str(payload.get("question") or self.args.default_question)
+        brave_query = str(payload.get("brave_query") or self.args.default_brave_query)
+        brave_count = int(payload.get("brave_count") or 3)
+        output_dir = Path(payload.get("output_dir") or self.args.output_dir)
+        run_id = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
+        research = await self.research_turn(question, brave_query, brave_count)
+        script = str(payload.get("script") or research["script"])
+        async with self.model_lock:
+            speech = self.force_speech_to_wav(script, output_dir / f"embry-grounded-{run_id}.wav")
+        receipt = {
+            "schema": "personaplex.grounded_speech_receipt.v1",
+            "created_at": utc_now(),
+            "ok": bool(research.get("ok") and speech["wav"]["bytes"] > 44),
+            "question": question,
+            "brave_query": brave_query,
+            "research": research,
+            "speech": speech,
+            "claim_boundary": (
+                "This proves research routing plus forced PersonaPlex speech WAV. "
+                "It is not live ASR/VAD full-duplex proof."
+            ),
+        }
+        receipt_path = output_dir / f"embry-grounded-{run_id}.json"
+        receipt_path.parent.mkdir(parents=True, exist_ok=True)
+        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
+        receipt["receipt_path"] = str(receipt_path)
+        return web.json_response(receipt)
+
+    async def chat(self, request: web.Request) -> web.WebSocketResponse:
+        ws = web.WebSocketResponse()
+        await ws.prepare(request)
+        opened = time.monotonic()
+        scripted_question = request.query.get("scripted_question", "")
+        brave_query = request.query.get("brave_query", self.args.default_brave_query)
+        use_deepgram = request.query.get("deepgram", "1") != "0"
+        close = False
+        opus_writer = sphn.OpusStreamWriter(self.mimi.sample_rate)
+        opus_reader = sphn.OpusStreamReader(self.mimi.sample_rate)
+        injection_tokens: asyncio.Queue[int] = asyncio.Queue()
+        output_gate = OutputGate()
+        deepgram = DeepgramLiveClient(
+            sample_rate=int(self.mimi.sample_rate),
+            model=self.args.deepgram_model,
+            enabled=use_deepgram,
+        )
+
+        async with self.model_lock:
+            restore_ms = self.restore_golden_state()
+            await ws.send_bytes(b"\x00")
+            await ws.send_bytes(
+                b"\x04"
+                + json.dumps(
+                    {
+                        "event": "handshake",
+                        "restore_ms": restore_ms,
+                        "elapsed_ms": ms_since(opened),
+                        "scripted_question": bool(scripted_question),
+                        "deepgram_enabled": deepgram.enabled,
+                    }
+                ).encode("utf-8")
+            )
+
+            async def run_grounding(question: str, source: str) -> None:
+                output_gate.close(f"grounding:{source}")
+                await ws.send_bytes(
+                    b"\x04" + json.dumps({
+                        "event": "grounding_started",
+                        "source": source,
+                        "question": question,
+                        "gate": output_gate.snapshot(),
+                    }).encode("utf-8")
+                )
+                try:
+                    stage_count = 0
+                    async for stage in self.iter_research_stages(question, brave_query, 3):
+                        stage_count += 1
+                        tokens = self.text_tokenizer.encode(wrap_with_system_tags(stage["inject_text"])) if stage.get("inject_text") else []
+                        for token in tokens:
+                            injection_tokens.put_nowait(int(token))
+                        await ws.send_bytes(
+                            b"\x04"
+                            + json.dumps(
+                                {
+                                    "event": "grounding_stage_queued",
+                                    "stage": stage["name"],
+                                    "stage_elapsed_ms": stage["elapsed_ms"],
+                                    "stage_ok": bool((stage.get("result") or {}).get("ok")),
+                                    "queued_tokens": len(tokens),
+                                    "queue_depth": injection_tokens.qsize(),
+                                    "gate": output_gate.snapshot(),
+                                }
+                            ).encode("utf-8")
+                        )
+                    output_gate.open()
+                    await ws.send_bytes(
+                        b"\x04" + json.dumps({
+                            "event": "grounding_complete",
+                            "source": source,
+                            "stages": stage_count,
+                            "queue_depth": injection_tokens.qsize(),
+                            "gate": output_gate.snapshot(),
+                        }).encode("utf-8")
+                    )
+                except Exception as exc:
+                    output_gate.open()
+                    await ws.send_bytes(
+                        b"\x04" + json.dumps({
+                            "event": "grounding_error",
+                            "source": source,
+                            "error_type": type(exc).__name__,
+                            "error": str(exc),
+                        }).encode("utf-8")
+                    )
+
+            retrieval_tasks: set[asyncio.Task] = set()
+            if scripted_question:
+                retrieval_tasks.add(asyncio.create_task(run_grounding(scripted_question, "scripted_question")))
+
+            async def deepgram_loop() -> None:
+                if not deepgram.enabled:
+                    while not close:
+                        await asyncio.sleep(0.25)
+                    return
+                asr_task = asyncio.create_task(deepgram.run())
+                try:
+                    while not close and deepgram.enabled:
+                        turn = await deepgram.turn_queue.get()
+                        await ws.send_bytes(
+                            b"\x04" + json.dumps({
+                                "event": "asr_turn_final",
+                                "transcript": turn.text,
+                                "asr_elapsed_ms": turn.elapsed_ms,
+                                "speech_final": turn.speech_final,
+                                "is_final": turn.is_final,
+                            }).encode("utf-8")
+                        )
+                        task = asyncio.create_task(run_grounding(turn.text, "deepgram"))
+                        retrieval_tasks.add(task)
+                        task.add_done_callback(retrieval_tasks.discard)
+                finally:
+                    await deepgram.close()
+                    asr_task.cancel()
+
+            async def receive_loop() -> None:
+                nonlocal close
+                try:
+                    async for message in ws:
+                        if message.type != aiohttp.WSMsgType.BINARY:
+                            continue
+                        data = message.data
+                        if not data:
+                            continue
+                        if data[0] == 1:
+                            opus_reader.append_bytes(data[1:])
+                        elif data[0] == 3:
+                            await ws.send_bytes(b"\x04" + b'{"event":"control_received"}')
+                finally:
+                    close = True
+
+            async def opus_loop() -> None:
+                all_pcm_data = None
+                while not close:
+                    await asyncio.sleep(0.001)
+                    pcm = opus_reader.read_pcm()
+                    if pcm.shape[-1] == 0:
+                        continue
+                    all_pcm_data = pcm if all_pcm_data is None else np.concatenate((all_pcm_data, pcm))
+                    while all_pcm_data.shape[-1] >= self.frame_size:
+                        chunk = all_pcm_data[: self.frame_size]
+                        all_pcm_data = all_pcm_data[self.frame_size:]
+                        deepgram.enqueue_pcm(chunk)
+                        chunk_tensor = torch.from_numpy(chunk).to(device=self.device)[None, None]
+                        with torch.no_grad():
+                            codes = self.mimi.encode(chunk_tensor)
+                            _ = self.other_mimi.encode(chunk_tensor)
+                            for c in range(codes.shape[-1]):
+                                forced_text = None
+                                if not injection_tokens.empty():
+                                    forced_text = torch.tensor(
+                                        [injection_tokens.get_nowait()],
+                                        dtype=torch.long,
+                                        device=self.device,
+                                    )
+                                tokens = self.lm_gen.step(codes[:, :, c : c + 1], text_token=forced_text)
+                                if tokens is None:
+                                    continue
+                                main_pcm = self.mimi.decode(tokens[:, 1:9])
+                                _ = self.other_mimi.decode(tokens[:, 1:9])
+                                if output_gate.active:
+                                    opus_writer.append_pcm(np.zeros(self.frame_size, dtype=np.float32))
+                                    continue
+                                opus_writer.append_pcm(main_pcm.detach().cpu()[0, 0].numpy())
+                                text_token = int(tokens[0, 0, 0].item())
+                                if text_token not in (0, 3):
+                                    piece = self.text_tokenizer.id_to_piece(text_token).replace("▁", " ")
+                                    await ws.send_bytes(b"\x02" + piece.encode("utf-8"))
+
+            async def send_loop() -> None:
+                while not close:
+                    await asyncio.sleep(0.001)
+                    payload = opus_writer.read_bytes()
+                    if payload:
+                        await ws.send_bytes(b"\x01" + payload)
+
+            tasks = [
+                asyncio.create_task(receive_loop(), name="receive_loop"),
+                asyncio.create_task(opus_loop(), name="opus_loop"),
+                asyncio.create_task(send_loop(), name="send_loop"),
+                asyncio.create_task(deepgram_loop(), name="deepgram_loop"),
+            ]
+            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
+            first_errors: list[dict[str, str]] = []
+            for task in done:
+                if task.cancelled():
+                    continue
+                exc = task.exception()
+                if exc is not None:
+                    error = {
+                        "task": task.get_name(),
+                        "error_type": type(exc).__name__,
+                        "error": str(exc),
+                    }
+                    first_errors.append(error)
+                    print(f"chat task failed: {json.dumps(error, sort_keys=True)}", file=sys.stderr, flush=True)
+            if first_errors and not ws.closed:
+                await ws.send_bytes(
+                    b"\x04" + json.dumps({
+                        "event": "chat_loop_error",
+                        "errors": first_errors,
+                    }).encode("utf-8")
+                )
+            for task in pending:
+                task.cancel()
+            for task in retrieval_tasks:
+                task.cancel()
+        return ws
+
+
+def parse_args() -> argparse.Namespace:
+    parser = argparse.ArgumentParser()
+    parser.add_argument("--host", default="127.0.0.1")
+    parser.add_argument("--port", type=int, default=9008)
+    parser.add_argument("--device", default="cuda")
+    parser.add_argument("--cpu-offload", action="store_true")
+    parser.add_argument("--seed", type=int, default=42424242)
+    parser.add_argument("--voice-prompt", type=Path, default=DEFAULT_VOICE_PROMPT)
+    parser.add_argument("--text-prompt", default=DEFAULT_TEXT_PROMPT)
+    parser.add_argument("--default-question", default="Embry, what is the weather like in Hawaii today?")
+    parser.add_argument("--default-brave-query", default=DEFAULT_BRAVE_QUERY)
+    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
+    parser.add_argument("--deepgram-model", default=os.environ.get("DEEPGRAM_MODEL", "nova-3"))
+    return parser.parse_args()
+
+
+def main() -> int:
+    args = parse_args()
+    server = GoldenEmbryServer(args)
+    app = web.Application()
+    app.router.add_get("/health", server.health)
+    app.router.add_post("/api/research-turn", server.research_endpoint)
+    app.router.add_post("/api/grounded-speech", server.grounded_speech_endpoint)
+    app.router.add_get("/api/chat", server.chat)
+    web.run_app(app, host=args.host, port=args.port)
+    return 0
+
+
+if __name__ == "__main__":
+    raise SystemExit(main())

diff --git a/skills/personaplex/scripts/personaplex_memory_flow.py b/skills/personaplex/scripts/personaplex_memory_flow.py
new file mode 100644
index 000000000..e2fdb7985
--- /dev/null
+++ b/skills/personaplex/scripts/personaplex_memory_flow.py
@@ -0,0 +1,87 @@
+"""Memory/Brave route helpers for the PersonaPlex wrapper."""
+
+from __future__ import annotations
+
+import asyncio
+from typing import Any, Awaitable, Callable
+
+TimedPost = Callable[..., Awaitable[dict[str, Any]]]
+
+
+def intent_requires_evidence_case(intent: dict[str, Any]) -> bool:
+    data = intent.get("json") or {}
+    action = str(data.get("action") or "").upper()
+    profile = str(data.get("recall_profile") or "").lower()
+    artifacts = [str(item).lower() for item in (data.get("required_artifacts") or [])]
+    if action == "COMPLIANCE" or "evidence_case" in artifacts or "qra" in artifacts:
+        return True
+    return "qra" in profile or "sparta" in profile or "compliance" in profile or bool(data.get("frameworks"))
+
+
+async def memory_route_product_with_sources(
+    question: str,
+    intent: dict[str, Any],
+    recall: dict[str, Any] | None,
+    brave: dict[str, Any] | None,
+    timed_post: TimedPost,
+) -> dict[str, Any]:
+    data = intent.get("json") or {}
+    action = str(data.get("action") or "").upper()
+    scope = str(data.get("scope") or "persona_memory")
+    if action == "CLARIFY":
+        result = await timed_post("/clarify", {"q": question, "scope": scope, "k": 4})
+        result["route_endpoint"] = "/clarify"
+    elif action in {"NO_MATCH", "OFF_TOPIC", "UNSAFE", "DEFLECT"}:
+        result = await timed_post("/deflect", {"q": question, "persona_id": "embry", "intent_action": action})
+        result["route_endpoint"] = "/deflect"
+    else:
+        answer_args = next((c.get("arguments") or {} for c in data.get("tool_calls") or [] if c.get("endpoint") == "/answer"), {})
+        persona_id = answer_args.get("persona_id") or (data.get("query_plan") or {}).get("extracted_entities", [None])[0] or "embry"
+        brave_json = (brave or {}).get("json") or {}
+        payload = {
+            "q": question,
+            "scope": answer_args.get("scope") or scope,
+            "persona_id": "embry" if str(persona_id).lower() == "embry" else persona_id,
+            "source_packets": answer_args.get("source_packets") or ["current_facts", "persona_memory"],
+            "external_sources": [{"skill": "brave-search", "domain": "current_facts_research",
+                                  "query": brave_json.get("query"), "results": brave_json}] if brave_json else [],
+            "recall_snapshot": (recall or {}).get("json") or {},
+            "current_facts": brave_json,
+            "persona_memory": (recall or {}).get("json") or {},
+        }
+        result = await timed_post("/answer", payload, timeout=20.0)
+        result["route_endpoint"] = "/answer"
+    return result
+
+
+def planned_recall_payload(intent: dict[str, Any]) -> dict[str, Any]:
+    data = intent.get("json") or {}
+    for call in data.get("tool_calls") or []:
+        if call.get("endpoint") == "/recall":
+            args = dict(call.get("arguments") or {})
+            args.setdefault("k", 12)
+            args.setdefault("collections", ["persona_memory"])
+            args.setdefault("tags", ["persona:embry"])
+            return args
+    return {"q": "What persona memories explain how Embry would respond to this question?",
+            "k": 12, "collections": ["persona_memory"], "tags": ["persona:embry"]}
+
+
+def planned_brave_query(intent: dict[str, Any], fallback_query: str) -> str:
+    data = intent.get("json") or {}
+    for call in data.get("tool_calls") or []:
+        if call.get("skill") == "brave-search" and (call.get("arguments") or {}).get("query"):
+            return str((call.get("arguments") or {})["query"])
+    return fallback_query
+
+
+async def evidence_case_gate_product(question: str, intent: dict[str, Any]) -> dict[str, Any]:
+    await asyncio.sleep(0)
+    return {
+        "ok": False,
+        "route_endpoint": "create-evidence-case",
+        "requires_evidence_case": True,
+        "question": question,
+        "intent_action": (intent.get("json") or {}).get("action"),
+        "message": "This turn requires an evidence-case branch before any substantive answer may be spoken.",
+    }
```

## Changed File Contents

### `skills/personaplex/PROJECT_KNOWLEDGE.md`

```text
# Project Knowledge: personaplex

**Last updated:** 2026-06-22 19:49 by agent
**Status:** Bridge skill scaffold with WebGPT-reviewed replay-cache gate,
strict provenance repairs, `.zshrc` HF-token loading, bounded live E2E smoke
support, and a custom golden-state research-gated PersonaPlex wrapper.

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
  `/home/graham/workspace/experiments/personaplex`, not from the skill venv.
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
  `/home/graham/workspace/experiments/personaplex/assets/test/input_assistant.wav`
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

```

### `skills/personaplex/scripts/personaplex_deepgram_live.py`

```text
"""Deepgram live ASR bridge for the PersonaPlex golden-state wrapper."""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any

import aiohttp
import numpy as np


def ms_since(start: float) -> float:
    return round((time.monotonic() - start) * 1000, 2)


@dataclass
class TranscriptTurn:
    text: str
    elapsed_ms: float
    speech_final: bool
    is_final: bool


class OutputGate:
    def __init__(self) -> None:
        self.active = False
        self.reason = ""
        self.started_at = 0.0
        self.released_at = 0.0

    def close(self, reason: str) -> None:
        self.active = True
        self.reason = reason
        self.started_at = time.monotonic()

    def open(self) -> None:
        self.active = False
        self.released_at = time.monotonic()

    def snapshot(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "reason": self.reason,
            "elapsed_ms": ms_since(self.started_at) if self.active else 0.0,
        }


class DeepgramLiveClient:
    def __init__(self, *, sample_rate: int, model: str = "nova-3", enabled: bool = True):
        self.sample_rate = sample_rate
        self.model = model
        self.enabled = enabled and bool(os.environ.get("DEEPGRAM_API_KEY"))
        self.audio_queue: asyncio.Queue[np.ndarray | None] = asyncio.Queue(maxsize=128)
        self.turn_queue: asyncio.Queue[TranscriptTurn] = asyncio.Queue()
        self.started_at = time.monotonic()
        self._final_parts: list[str] = []

    def enqueue_pcm(self, pcm: np.ndarray) -> None:
        if not self.enabled:
            return
        try:
            self.audio_queue.put_nowait(np.asarray(pcm, dtype=np.float32).copy())
        except asyncio.QueueFull:
            _ = self.audio_queue.get_nowait()
            self.audio_queue.put_nowait(np.asarray(pcm, dtype=np.float32).copy())

    async def close(self) -> None:
        if self.enabled:
            await self.audio_queue.put(None)

    async def run(self) -> None:
        if not self.enabled:
            return
        params = {
            "model": self.model,
            "encoding": "linear16",
            "sample_rate": str(self.sample_rate),
            "channels": "1",
            "punctuate": "true",
            "smart_format": "true",
            "interim_results": "true",
            "vad_events": "true",
            "endpointing": "300",
        }
        url = "wss://api.deepgram.com/v1/listen?" + "&".join(f"{k}={v}" for k, v in params.items())
        headers = {"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, connect=5)) as session:
            async with session.ws_connect(url, headers=headers, heartbeat=10) as ws:
                sender = asyncio.create_task(self._send_audio(ws))
                try:
                    async for message in ws:
                        if message.type == aiohttp.WSMsgType.TEXT:
                            self._handle_message(json.loads(message.data))
                        elif message.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                            break
                finally:
                    sender.cancel()

    async def _send_audio(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        while True:
            pcm = await self.audio_queue.get()
            if pcm is None:
                await ws.send_str(json.dumps({"type": "CloseStream"}))
                return
            pcm16 = np.clip(pcm, -1.0, 1.0)
            await ws.send_bytes((pcm16 * 32767.0).astype("<i2").tobytes())

    def _handle_message(self, payload: dict[str, Any]) -> None:
        if payload.get("type") != "Results":
            return
        channel = payload.get("channel") or {}
        alternatives = channel.get("alternatives") or []
        is_final = bool(payload.get("is_final"))
        speech_final = bool(payload.get("speech_final"))
        transcript = (alternatives[0].get("transcript") if alternatives else "") or ""
        transcript = transcript.strip()
        if not transcript and not (speech_final and self._final_parts):
            return
        if is_final:
            self._final_parts.append(transcript)
        if speech_final:
            full_transcript = " ".join(self._final_parts).strip() or transcript
            self._final_parts.clear()
            self.turn_queue.put_nowait(
                TranscriptTurn(
                    text=full_transcript,
                    elapsed_ms=ms_since(self.started_at),
                    speech_final=speech_final,
                    is_final=is_final,
                )
            )

```

### `skills/personaplex/scripts/personaplex_deepgram_live_probe.py`

```text
#!/usr/bin/env python3
"""Live Deepgram ASR/VAD probe for the PersonaPlex golden-state wrapper."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any


ROOT = Path("/home/graham/workspace/experiments/agent-skills")
PERSONAPLEX_PYTHON = Path("/home/graham/workspace/experiments/personaplex/.venv/bin/python")
OUTPUT_ROOT = Path("/mnt/storage12tb/skills/personaplex/outputs/deepgram-live-probe/embry")
DEFAULT_QUESTION = (
    "Embry, what is the weather like in Hawaii today, "
    "and how would that make you feel about surfing with Kai?"
)


def ensure_runtime_python() -> None:
    if PERSONAPLEX_PYTHON.exists() and Path(sys.executable).resolve() != PERSONAPLEX_PYTHON.resolve():
        os.execv(str(PERSONAPLEX_PYTHON), [str(PERSONAPLEX_PYTHON), __file__, *sys.argv[1:]])


def utc_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def synthesize_question_wav(text: str, output_dir: Path) -> Path:
    raw = output_dir / "user-question-raw.wav"
    wav = output_dir / "user-question-24khz-mono.wav"
    espeak = subprocess.run(
        ["bash", "-lc", "command -v espeak-ng || command -v espeak"],
        capture_output=True,
        text=True,
        check=True,
    )
    espeak_path = espeak.stdout.strip().splitlines()[0]
    subprocess.run([espeak_path, "-w", str(raw), text], check=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(raw),
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(wav),
        ],
        check=True,
    )
    return wav


def wav_metrics(path: Path) -> dict[str, Any]:
    import soundfile as sf

    data, sample_rate = sf.read(str(path), always_2d=True)
    info = sf.info(str(path))
    return {
        "path": str(path),
        "sha256": sha256_path(path),
        "size_bytes": path.stat().st_size,
        "sample_rate": int(sample_rate),
        "channels": int(data.shape[1]),
        "frames": int(data.shape[0]),
        "duration_s": round(float(info.duration), 3),
        "peak": float(abs(data).max()) if data.size else 0.0,
        "rms": float((data * data).mean() ** 0.5) if data.size else 0.0,
    }


async def live_probe(
    url_base: str,
    wav_path: Path,
    output_dir: Path,
    *,
    trailing_silence_s: float,
    wait_after_audio_s: float,
) -> dict[str, Any]:
    import aiohttp
    import numpy as np
    import soundfile as sf
    import sphn

    audio, sample_rate = sf.read(str(wav_path), dtype="float32", always_2d=False)
    if audio.ndim != 1:
        audio = audio[:, 0]
    if sample_rate != 24000:
        raise ValueError(f"expected 24kHz input WAV, got {sample_rate}")

    params = {"deepgram": "1"}
    url = f"{url_base}/api/chat?{urllib.parse.urlencode(params)}"
    event_path = output_dir / "deepgram-live-events.jsonl"
    server_audio_path = output_dir / "server-audio.opus-pages.bin"

    def append_event(payload: dict[str, Any]) -> None:
        with event_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": dt.datetime.now(dt.UTC).isoformat(), **payload}, sort_keys=True) + "\n")

    writer = sphn.OpusStreamWriter(24000)
    server_audio_chunks: list[bytes] = []
    control_events: list[dict[str, Any]] = []
    start = time.monotonic()
    timings: dict[str, float] = {}
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    async with aiohttp.ClientSession() as session:
        append_event({"event": "connect_start", "url": url})
        async with session.ws_connect(url, ssl=ssl_ctx, timeout=90, receive_timeout=90) as ws:
            timings["connected_ms"] = round((time.monotonic() - start) * 1000, 2)
            while True:
                msg = await asyncio.wait_for(ws.receive(), timeout=90)
                if msg.type == aiohttp.WSMsgType.BINARY and msg.data and msg.data[0] == 0:
                    timings["handshake_ms"] = round((time.monotonic() - start) * 1000, 2)
                    append_event({"event": "handshake_marker", "elapsed_ms": timings["handshake_ms"]})
                    break
                if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    raise RuntimeError(f"socket closed before handshake: {msg.type} {msg.data!r}")

            async def receive_loop() -> None:
                while True:
                    msg = await ws.receive()
                    if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        append_event({"event": "socket_closed", "type": str(msg.type)})
                        return
                    if msg.type != aiohttp.WSMsgType.BINARY or not msg.data:
                        continue
                    kind = msg.data[0]
                    payload = bytes(msg.data[1:])
                    now_ms = round((time.monotonic() - start) * 1000, 2)
                    if kind == 1:
                        server_audio_chunks.append(payload)
                        if "first_audio_ms" not in timings:
                            timings["first_audio_ms"] = now_ms
                            append_event({"event": "first_audio", "elapsed_ms": now_ms, "bytes": len(payload)})
                    elif kind == 2:
                        if "first_text_ms" not in timings:
                            timings["first_text_ms"] = now_ms
                            append_event({"event": "first_text", "elapsed_ms": now_ms})
                    elif kind == 4:
                        decoded = json.loads(payload.decode("utf-8", errors="replace"))
                        decoded["elapsed_ms"] = now_ms
                        control_events.append(decoded)
                        append_event({"event": "control", **decoded})

            recv_task = asyncio.create_task(receive_loop())
            frame = 1920
            sent_pages = 0
            for offset in range(0, len(audio), frame):
                chunk = audio[offset : offset + frame]
                if len(chunk) < frame:
                    chunk = np.pad(chunk, (0, frame - len(chunk)))
                writer.append_pcm(chunk.astype("float32"))
                pages = writer.read_bytes()
                if pages:
                    await ws.send_bytes(b"\x01" + pages)
                    sent_pages += 1
                await asyncio.sleep(0.08)
            silence_frames = int((trailing_silence_s * 24000) // frame)
            for _ in range(silence_frames):
                writer.append_pcm(np.zeros(frame, dtype="float32"))
                pages = writer.read_bytes()
                if pages:
                    await ws.send_bytes(b"\x01" + pages)
                    sent_pages += 1
                await asyncio.sleep(0.08)
            timings["input_sent_ms"] = round((time.monotonic() - start) * 1000, 2)
            append_event(
                {
                    "event": "input_sent",
                    "elapsed_ms": timings["input_sent_ms"],
                    "sent_pages": sent_pages,
                    "trailing_silence_s": trailing_silence_s,
                }
            )
            await asyncio.sleep(wait_after_audio_s)
            await ws.close()
            await recv_task

    server_audio_path.write_bytes(b"".join(server_audio_chunks))
    asr_events = [event for event in control_events if event.get("event") == "asr_turn_final"]
    grounding_started = [event for event in control_events if event.get("event") == "grounding_started"]
    grounding_complete = [event for event in control_events if event.get("event") == "grounding_complete"]
    queued = [event for event in control_events if event.get("event") == "grounding_stage_queued"]
    return {
        "ok": bool(asr_events and grounding_started and grounding_complete),
        "url": url,
        "timings": timings,
        "sent_pages": sent_pages,
        "control_event_count": len(control_events),
        "control_event_names": [event.get("event") for event in control_events],
        "asr_events": asr_events,
        "grounding_started": grounding_started,
        "grounding_stage_names": [event.get("stage") for event in queued],
        "grounding_complete": grounding_complete,
        "server_audio": {
            "path": str(server_audio_path),
            "chunks": len(server_audio_chunks),
            "bytes": server_audio_path.stat().st_size if server_audio_path.exists() else 0,
        },
        "events_jsonl": str(event_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--url-base", default="ws://127.0.0.1:9008")
    parser.add_argument("--trailing-silence-s", type=float, default=2.0)
    parser.add_argument("--wait-after-audio-s", type=float, default=18.0)
    return parser.parse_args()


def main() -> int:
    ensure_runtime_python()
    args = parse_args()
    output_dir = OUTPUT_ROOT / utc_stamp()
    output_dir.mkdir(parents=True, exist_ok=False)
    total_start = time.monotonic()
    wav_path = synthesize_question_wav(args.question, output_dir)
    probe = asyncio.run(
        live_probe(
            args.url_base,
            wav_path,
            output_dir,
            trailing_silence_s=args.trailing_silence_s,
            wait_after_audio_s=args.wait_after_audio_s,
        )
    )
    receipt = {
        "schema": "personaplex.deepgram_live_probe.v1",
        "status": "PASS" if probe["ok"] else "FAIL",
        "claim_boundary": "Live Deepgram websocket ASR/VAD from Opus user-audio fixture into PersonaPlex wrapper; fixture is synthesized speech, not microphone capture.",
        "deepgram_api_key_set": bool(os.environ.get("DEEPGRAM_API_KEY")),
        "question": args.question,
        "input_wav": wav_metrics(wav_path),
        "probe": probe,
        "total_ms": round((time.monotonic() - total_start) * 1000, 2),
    }
    receipt_path = output_dir / "personaplex-deepgram-live-probe-receipt.json"
    write_json(receipt_path, receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(receipt_path)}, indent=2))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

```

### `skills/personaplex/scripts/personaplex_golden_state_server.py`

```text
#!/usr/bin/env python3
"""Golden-state PersonaPlex wrapper for grounded Embry experiments.

Imports Moshi/PersonaPlex modules instead of forking ``moshi.server``. It does
Embry voice/persona pre-roll once at boot, clones the preconditioned streaming
state, restores it for sessions, runs memory-first + Brave staged grounding,
and wires optional Deepgram live ASR/VAD into the WebSocket interaction loop.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime as dt
import json
import os
import random
import sys
import time
import wave
from pathlib import Path
from typing import Any

ROOT = Path("/home/graham/workspace/experiments/agent-skills")
PERSONAPLEX_ROOT = Path("/home/graham/workspace/experiments/personaplex")
PERSONAPLEX_PYTHON = PERSONAPLEX_ROOT / ".venv/bin/python"
if PERSONAPLEX_PYTHON.exists() and Path(sys.executable).resolve() != PERSONAPLEX_PYTHON.resolve():
    os.execv(str(PERSONAPLEX_PYTHON), [str(PERSONAPLEX_PYTHON), __file__, *sys.argv[1:]])

_nvidia_libs = sorted(Path(PERSONAPLEX_PYTHON).parents[1].glob("lib/python*/site-packages/nvidia/*/lib"))
if _nvidia_libs and "nvidia/cudnn/lib" not in os.environ.get("LD_LIBRARY_PATH", ""):
    env = dict(os.environ)
    existing_ld = env.get("LD_LIBRARY_PATH")
    env["LD_LIBRARY_PATH"] = ":".join([*(str(path) for path in _nvidia_libs if path.is_dir()), *( [existing_ld] if existing_ld else [] )])
    os.execve(sys.executable, [sys.executable, __file__, *sys.argv[1:]], env)

import aiohttp
from aiohttp import web
import numpy as np
import sphn
import torch

from personaplex_deepgram_live import DeepgramLiveClient, OutputGate
from personaplex_memory_flow import (
    evidence_case_gate_product,
    intent_requires_evidence_case,
    memory_route_product_with_sources,
    planned_brave_query,
    planned_recall_payload,
)


BRAVE_RUN = ROOT / "skills/brave-search/run.sh"
MEMORY_URL = "http://127.0.0.1:8601"
DEFAULT_VOICE_PROMPT = Path(
    "/mnt/storage12tb/skills/personaplex/outputs/e2e/"
    "embry-conversational-20260622T152647Z/neutral/voice-prompt.pt"
)
DEFAULT_TEXT_PROMPT = (
    "You are Embry Lawson. You are warm, concise, grounded, and emotionally "
    "present. Use retrieved facts when supplied. If evidence is limited, say so."
)
DEFAULT_BRAVE_QUERY = "Hawaii weather surf forecast today"
DEFAULT_OUTPUT_DIR = Path("/mnt/storage12tb/skills/personaplex/outputs/golden-state-wrapper")

def seed_all(seed: int) -> None:
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    random.seed(seed)
    np.random.seed(seed)


def wrap_with_system_tags(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("<system>") and cleaned.endswith("<system>"):
        return cleaned
    return f"<system> {cleaned} <system>"


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def ms_since(start: float) -> float:
    return round((time.monotonic() - start) * 1000, 2)


def clone_streaming_state(value: Any) -> Any:
    if torch.is_tensor(value):
        return value.detach().clone()
    if dataclasses.is_dataclass(value):
        kwargs = {field.name: clone_streaming_state(getattr(value, field.name)) for field in dataclasses.fields(value)}
        return type(value)(**kwargs)
    if isinstance(value, dict):
        return {key: clone_streaming_state(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clone_streaming_state(item) for item in value]
    if isinstance(value, tuple):
        return tuple(clone_streaming_state(item) for item in value)
    return value


async def timed_post(endpoint: str, payload: dict[str, Any], *, timeout: float = 10.0) -> dict[str, Any]:
    start = time.monotonic()
    try:
        client_timeout = aiohttp.ClientTimeout(total=timeout, connect=min(timeout, 2.0))
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.post(
                f"{MEMORY_URL}{endpoint}",
                json=payload,
                headers={"Accept": "application/json"},
            ) as response:
                text = await response.text()
                status_code = response.status
                content_type = response.headers.get("content-type", "")
        parsed = json.loads(text) if "application/json" in content_type else None
        return {
            "ok": 200 <= status_code < 300,
            "status_code": status_code,
            "elapsed_ms": ms_since(start),
            "json": parsed,
            "text_excerpt": None if parsed is not None else text[:1000],
        }
    except Exception as exc:
        return {
            "ok": False,
            "elapsed_ms": ms_since(start),
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


async def brave_search(query: str, count: int) -> dict[str, Any]:
    start = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        "bash",
        "-lc",
        f"source ~/.zshrc >/dev/null 2>&1; {BRAVE_RUN} web {json.dumps(query)} --count {count} --json",
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_raw, stderr_raw = await asyncio.wait_for(proc.communicate(), timeout=30)
    except TimeoutError:
        proc.kill()
        stdout_raw, stderr_raw = await proc.communicate()
        return {
            "ok": False,
            "elapsed_ms": ms_since(start),
            "returncode": proc.returncode,
            "stderr_excerpt": stderr_raw.decode("utf-8", errors="replace")[-1200:],
            "error": "brave_search_timeout",
        }
    stdout = stdout_raw.decode("utf-8", errors="replace")
    stderr = stderr_raw.decode("utf-8", errors="replace")
    out: dict[str, Any] = {
        "ok": proc.returncode == 0,
        "elapsed_ms": ms_since(start),
        "returncode": proc.returncode,
        "stderr_excerpt": stderr[-1200:],
    }
    try:
        out["json"] = json.loads(stdout)
    except json.JSONDecodeError:
        out["ok"] = False
        out["stdout_excerpt"] = stdout[:1200]
        out["error"] = "Brave output was not JSON"
    return out


def compact_memory(recall: dict[str, Any], limit: int = 280) -> str:
    items = (recall.get("json") or {}).get("items") or []
    for item in items:
        text = item.get("retrieval_text") or item.get("text") or item.get("summary") or item.get("problem")
        if text:
            return str(text)[:limit]
    return "No strong Embry persona memory returned."


def compact_brave(brave: dict[str, Any], limit: int = 300) -> str:
    results = (brave.get("json") or {}).get("results") or []
    if not results:
        return "No current Brave Search result returned."
    top = results[0]
    return f"{top.get('title', '')}: {top.get('description', '')}"[:limit]


def compact_answer_route(route: dict[str, Any], limit: int = 420) -> str:
    data = route.get("json") or {}
    if data.get("can_answer"):
        text = data.get("final_response") or data.get("source_answer") or data.get("answer")
        if text:
            return str(text)[:limit]
    questions = data.get("questions") or data.get("clarifying_questions")
    if questions:
        return f"Clarification needed: {questions[0]}"[:limit]
    if data.get("should_deflect"):
        return str(data.get("message") or data.get("reason") or "This should be deflected.")[:limit]
    return "Memory route did not produce a final answer."


def write_wav(path: Path, pcm: np.ndarray, sample_rate: int) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(pcm, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm16.tobytes())
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sample_rate": sample_rate,
        "duration_seconds": round(float(len(pcm16)) / float(sample_rate), 3),
    }


class GoldenEmbryServer:
    def __init__(self, args: argparse.Namespace):
        sys.path.insert(0, str(PERSONAPLEX_ROOT))
        from huggingface_hub import hf_hub_download
        import sentencepiece
        from moshi.models import loaders, LMGen

        self.args = args
        self.device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
        self.timings: dict[str, float] = {}
        self.model_lock = asyncio.Lock()
        self.frame_size = 0

        seed_all(args.seed)
        boot_start = time.monotonic()
        load_start = time.monotonic()
        mimi_weight = hf_hub_download(loaders.DEFAULT_REPO, loaders.MIMI_NAME)
        tokenizer_path = hf_hub_download(loaders.DEFAULT_REPO, loaders.TEXT_TOKENIZER_NAME)
        moshi_weight = hf_hub_download(loaders.DEFAULT_REPO, loaders.MOSHI_NAME)
        self.mimi = loaders.get_mimi(mimi_weight, self.device)
        self.other_mimi = loaders.get_mimi(mimi_weight, self.device)
        self.text_tokenizer = sentencepiece.SentencePieceProcessor(tokenizer_path)  # type: ignore
        lm = loaders.get_moshi_lm(moshi_weight, device=self.device, cpu_offload=args.cpu_offload)
        lm.eval()
        self.frame_size = int(self.mimi.sample_rate / self.mimi.frame_rate)
        self.lm_gen = LMGen(lm, audio_silence_frame_cnt=int(0.5 * self.mimi.frame_rate),
                            sample_rate=self.mimi.sample_rate, device=self.device,
                            frame_rate=self.mimi.frame_rate, save_voice_prompt_embeddings=False)
        self.mimi.streaming_forever(1)
        self.other_mimi.streaming_forever(1)
        self.lm_gen.streaming_forever(1)
        self._sync_cuda()
        self.timings["load_ms"] = ms_since(load_start)

        self._warmup()
        self._build_golden_state(args.voice_prompt, args.text_prompt)
        self.timings["boot_total_ms"] = ms_since(boot_start)

    def _sync_cuda(self) -> None:
        if self.device.type == "cuda":
            torch.cuda.synchronize()

    def _warmup(self) -> None:
        start = time.monotonic()
        with torch.no_grad():
            for _ in range(4):
                chunk = torch.zeros(1, 1, self.frame_size, dtype=torch.float32, device=self.device)
                codes = self.mimi.encode(chunk)
                _ = self.other_mimi.encode(chunk)
                for c in range(codes.shape[-1]):
                    tokens = self.lm_gen.step(codes[:, :, c : c + 1])
                    if tokens is None:
                        continue
                    _ = self.mimi.decode(tokens[:, 1:9])
                    _ = self.other_mimi.decode(tokens[:, 1:9])
        self._sync_cuda()
        self.timings["warmup_ms"] = ms_since(start)

    def _build_golden_state(self, voice_prompt: Path, text_prompt: str) -> None:
        if not voice_prompt.exists():
            raise FileNotFoundError(f"voice prompt not found: {voice_prompt}")
        start = time.monotonic()
        self.lm_gen.load_voice_prompt_embeddings(str(voice_prompt))
        self.lm_gen.text_prompt_tokens = self.text_tokenizer.encode(wrap_with_system_tags(text_prompt))
        with torch.no_grad():
            self.mimi.reset_streaming()
            self.other_mimi.reset_streaming()
            self.lm_gen.reset_streaming()
            self.lm_gen.step_system_prompts(self.mimi)
            self.mimi.reset_streaming()
        self._sync_cuda()
        self.timings["golden_pre_roll_ms"] = ms_since(start)

        clone_start = time.monotonic()
        self.golden_state = clone_streaming_state(self.lm_gen.get_streaming_state())
        self._sync_cuda()
        self.timings["golden_clone_ms"] = ms_since(clone_start)

    def restore_golden_state(self) -> float:
        start = time.monotonic()
        with torch.no_grad():
            self.mimi.reset_streaming()
            self.other_mimi.reset_streaming()
            self.lm_gen.set_streaming_state(clone_streaming_state(self.golden_state))
        self._sync_cuda()
        return ms_since(start)

    async def iter_research_stages(self, question: str, brave_query: str, brave_count: int):
        start = time.monotonic()

        async def named(name: str, awaitable):
            result = await awaitable
            return name, result

        intent_result = await timed_post(
            "/intent",
            {"q": question, "scope": "persona_memory", "fast": True},
        )
        intent_data = intent_result.get("json") or {}
        recall_payload = planned_recall_payload(intent_result)
        search_query = planned_brave_query(intent_result, brave_query)
        yield {
            "name": "intent", "elapsed_ms": ms_since(start), "result": intent_result,
            "inject_text": (
                "Internal routing note for the next answer: "
                f"intent={intent_data.get('action')}; recall_profile={intent_data.get('recall_profile')}. "
                "Do not mention this routing note to the user."
            )}

        tasks = [
            asyncio.create_task(named("memory", timed_post("/recall", recall_payload))),
            asyncio.create_task(named("brave", brave_search(search_query, brave_count))),
        ]
        if intent_requires_evidence_case(intent_result):
            tasks.append(asyncio.create_task(named("route", evidence_case_gate_product(question, intent_result))))

        recall_result: dict[str, Any] | None = None
        brave_result: dict[str, Any] | None = None
        route_yielded = False
        for completed in asyncio.as_completed(tasks):
            name, result = await completed
            stage: dict[str, Any] = {"name": name, "elapsed_ms": ms_since(start), "result": result, "inject_text": ""}
            if name == "memory":
                recall_result = result
                stage["inject_text"] = f"Memory grounding for the next answer: {compact_memory(result)}"
            elif name == "brave":
                brave_result = result
                stage["inject_text"] = f"Current web grounding for the next answer: {compact_brave(result)}"
            elif name == "route":
                route_yielded = True
                if result.get("requires_evidence_case"):
                    stage["inject_text"] = (
                        "Evidence gate for the next answer: this request needs "
                        "a create-evidence-case verdict before a factual answer. "
                        "Acknowledge the need to check evidence; do not provide "
                        "a compliance conclusion yet."
                    )
                else:
                    stage["inject_text"] = f"Memory route product for the next answer: {compact_answer_route(result)}"
            yield stage

        if not route_yielded:
            route_result = await memory_route_product_with_sources(question, intent_result, recall_result, brave_result, timed_post)
            yield {
                "name": "route", "elapsed_ms": ms_since(start), "result": route_result,
                "inject_text": f"Memory route product for the next answer: {compact_answer_route(route_result)}",
            }

    async def research_turn(self, question: str, brave_query: str, brave_count: int) -> dict[str, Any]:
        start = time.monotonic()
        stages: list[dict[str, Any]] = []
        intent: dict[str, Any] | None = None
        recall: dict[str, Any] | None = None
        brave: dict[str, Any] | None = None
        route: dict[str, Any] | None = None
        async for stage in self.iter_research_stages(question, brave_query, brave_count):
            stages.append(stage)
            if stage["name"] == "intent":
                intent = stage["result"]
            elif stage["name"] == "memory":
                recall = stage["result"]
            elif stage["name"] == "brave":
                brave = stage["result"]
            elif stage["name"] == "route":
                route = stage["result"]
        intent = intent or {"ok": False, "error": "intent_not_returned"}
        recall = recall or {"ok": False, "error": "memory_not_returned"}
        brave = brave or {"ok": False, "error": "brave_not_returned"}
        route = route or {"ok": False, "error": "route_not_returned"}
        evidence_gated = bool(route.get("requires_evidence_case"))
        script = self.script_from_research(question=question, recall=recall, brave=brave, route=route, evidence_gated=evidence_gated)
        return {
            "schema": "personaplex.research_turn.v1",
            "created_at": utc_now(),
            "ok": bool(recall.get("ok") and brave.get("ok") and (route.get("ok") or evidence_gated)),
            "elapsed_ms": ms_since(start),
            "question": question,
            "brave_query": brave_query,
            "evidence_gated": evidence_gated,
            "stage_order": [
                {
                    "name": stage["name"],
                    "elapsed_ms": stage["elapsed_ms"],
                    "inject_text_chars": len(stage.get("inject_text") or ""),
                    "ok": bool((stage.get("result") or {}).get("ok")),
                }
                for stage in stages
            ],
            "intent": intent,
            "recall": recall,
            "brave": brave,
            "route": route,
            "script": script,
            "script_chars": len(script),
        }

    def script_from_research(
        self,
        *,
        question: str,
        recall: dict[str, Any],
        brave: dict[str, Any],
        route: dict[str, Any],
        evidence_gated: bool,
    ) -> str:
        if evidence_gated:
            return (
                "I need to check the evidence case before I answer that. "
                "I can look at the internal memory and current sources, but I should not give a compliance conclusion until the evidence case is built."
            )
        route_text = compact_answer_route(route)
        if route.get("ok") and route_text != "Memory route did not produce a final answer.":
            return route_text
        memory_text = compact_memory(recall)
        search_text = compact_brave(brave)
        return (
            "I found partial context. "
            f"Memory says: {memory_text}. "
            f"Current search says: {search_text}. "
            "I would treat that as preliminary rather than final."
        )

    def force_speech_to_wav(self, text: str, out_path: Path) -> dict[str, Any]:
        start = time.monotonic()
        tokens = self.text_tokenizer.encode(text.strip())
        audio_chunks: list[np.ndarray] = []
        with torch.no_grad():
            self.restore_golden_state()
            silence = torch.zeros(1, 1, self.frame_size, dtype=torch.float32, device=self.device)
            codes = self.mimi.encode(silence)
            for token in tokens:
                forced = torch.tensor([int(token)], dtype=torch.long, device=self.device)
                step_tokens = self.lm_gen.step(codes[:, :, :1], text_token=forced)
                if step_tokens is None:
                    continue
                main_pcm = self.mimi.decode(step_tokens[:, 1:9])
                audio_chunks.append(main_pcm.cpu()[0, 0].numpy())
            for _ in range(6):
                step_tokens = self.lm_gen.step(codes[:, :, :1], text_token=torch.tensor([3], dtype=torch.long, device=self.device))
                if step_tokens is None:
                    continue
                main_pcm = self.mimi.decode(step_tokens[:, 1:9])
                audio_chunks.append(main_pcm.cpu()[0, 0].numpy())
        self._sync_cuda()
        pcm = np.concatenate(audio_chunks) if audio_chunks else np.zeros(self.frame_size, dtype=np.float32)
        wav = write_wav(out_path, pcm, int(self.mimi.sample_rate))
        return {
            "text": text,
            "text_chars": len(text),
            "text_tokens": len(tokens),
            "elapsed_ms": ms_since(start),
            "wav": wav,
        }

    async def health(self, _request: web.Request) -> web.Response:
        return web.json_response(
            {
                "schema": "personaplex.golden_state_server.health.v1",
                "ok": True,
                "device": str(self.device),
                "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                "timings": self.timings,
                "voice_prompt": str(self.args.voice_prompt),
                "claim_boundary": "golden-state wrapper booted; /api/chat supports optional Deepgram live ASR/VAD when DEEPGRAM_API_KEY is set",
            }
        )

    async def research_endpoint(self, request: web.Request) -> web.Response:
        payload = await request.json()
        question = str(payload.get("question") or self.args.default_question)
        brave_query = str(payload.get("brave_query") or self.args.default_brave_query)
        brave_count = int(payload.get("brave_count") or 3)
        result = await self.research_turn(question, brave_query, brave_count)
        return web.json_response(result)

    async def grounded_speech_endpoint(self, request: web.Request) -> web.Response:
        payload = await request.json()
        question = str(payload.get("question") or self.args.default_question)
        brave_query = str(payload.get("brave_query") or self.args.default_brave_query)
        brave_count = int(payload.get("brave_count") or 3)
        output_dir = Path(payload.get("output_dir") or self.args.output_dir)
        run_id = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        research = await self.research_turn(question, brave_query, brave_count)
        script = str(payload.get("script") or research["script"])
        async with self.model_lock:
            speech = self.force_speech_to_wav(script, output_dir / f"embry-grounded-{run_id}.wav")
        receipt = {
            "schema": "personaplex.grounded_speech_receipt.v1",
            "created_at": utc_now(),
            "ok": bool(research.get("ok") and speech["wav"]["bytes"] > 44),
            "question": question,
            "brave_query": brave_query,
            "research": research,
            "speech": speech,
            "claim_boundary": (
                "This proves research routing plus forced PersonaPlex speech WAV. "
                "It is not live ASR/VAD full-duplex proof."
            ),
        }
        receipt_path = output_dir / f"embry-grounded-{run_id}.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        receipt["receipt_path"] = str(receipt_path)
        return web.json_response(receipt)

    async def chat(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        opened = time.monotonic()
        scripted_question = request.query.get("scripted_question", "")
        brave_query = request.query.get("brave_query", self.args.default_brave_query)
        use_deepgram = request.query.get("deepgram", "1") != "0"
        close = False
        opus_writer = sphn.OpusStreamWriter(self.mimi.sample_rate)
        opus_reader = sphn.OpusStreamReader(self.mimi.sample_rate)
        injection_tokens: asyncio.Queue[int] = asyncio.Queue()
        output_gate = OutputGate()
        deepgram = DeepgramLiveClient(
            sample_rate=int(self.mimi.sample_rate),
            model=self.args.deepgram_model,
            enabled=use_deepgram,
        )

        async with self.model_lock:
            restore_ms = self.restore_golden_state()
            await ws.send_bytes(b"\x00")
            await ws.send_bytes(
                b"\x04"
                + json.dumps(
                    {
                        "event": "handshake",
                        "restore_ms": restore_ms,
                        "elapsed_ms": ms_since(opened),
                        "scripted_question": bool(scripted_question),
                        "deepgram_enabled": deepgram.enabled,
                    }
                ).encode("utf-8")
            )

            async def run_grounding(question: str, source: str) -> None:
                output_gate.close(f"grounding:{source}")
                await ws.send_bytes(
                    b"\x04" + json.dumps({
                        "event": "grounding_started",
                        "source": source,
                        "question": question,
                        "gate": output_gate.snapshot(),
                    }).encode("utf-8")
                )
                try:
                    stage_count = 0
                    async for stage in self.iter_research_stages(question, brave_query, 3):
                        stage_count += 1
                        tokens = self.text_tokenizer.encode(wrap_with_system_tags(stage["inject_text"])) if stage.get("inject_text") else []
                        for token in tokens:
                            injection_tokens.put_nowait(int(token))
                        await ws.send_bytes(
                            b"\x04"
                            + json.dumps(
                                {
                                    "event": "grounding_stage_queued",
                                    "stage": stage["name"],
                                    "stage_elapsed_ms": stage["elapsed_ms"],
                                    "stage_ok": bool((stage.get("result") or {}).get("ok")),
                                    "queued_tokens": len(tokens),
                                    "queue_depth": injection_tokens.qsize(),
                                    "gate": output_gate.snapshot(),
                                }
                            ).encode("utf-8")
                        )
                    output_gate.open()
                    await ws.send_bytes(
                        b"\x04" + json.dumps({
                            "event": "grounding_complete",
                            "source": source,
                            "stages": stage_count,
                            "queue_depth": injection_tokens.qsize(),
                            "gate": output_gate.snapshot(),
                        }).encode("utf-8")
                    )
                except Exception as exc:
                    output_gate.open()
                    await ws.send_bytes(
                        b"\x04" + json.dumps({
                            "event": "grounding_error",
                            "source": source,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }).encode("utf-8")
                    )

            retrieval_tasks: set[asyncio.Task] = set()
            if scripted_question:
                retrieval_tasks.add(asyncio.create_task(run_grounding(scripted_question, "scripted_question")))

            async def deepgram_loop() -> None:
                if not deepgram.enabled:
                    while not close:
                        await asyncio.sleep(0.25)
                    return
                asr_task = asyncio.create_task(deepgram.run())
                try:
                    while not close and deepgram.enabled:
                        turn = await deepgram.turn_queue.get()
                        await ws.send_bytes(
                            b"\x04" + json.dumps({
                                "event": "asr_turn_final",
                                "transcript": turn.text,
                                "asr_elapsed_ms": turn.elapsed_ms,
                                "speech_final": turn.speech_final,
                                "is_final": turn.is_final,
                            }).encode("utf-8")
                        )
                        task = asyncio.create_task(run_grounding(turn.text, "deepgram"))
                        retrieval_tasks.add(task)
                        task.add_done_callback(retrieval_tasks.discard)
                finally:
                    await deepgram.close()
                    asr_task.cancel()

            async def receive_loop() -> None:
                nonlocal close
                try:
                    async for message in ws:
                        if message.type != aiohttp.WSMsgType.BINARY:
                            continue
                        data = message.data
                        if not data:
                            continue
                        if data[0] == 1:
                            opus_reader.append_bytes(data[1:])
                        elif data[0] == 3:
                            await ws.send_bytes(b"\x04" + b'{"event":"control_received"}')
                finally:
                    close = True

            async def opus_loop() -> None:
                all_pcm_data = None
                while not close:
                    await asyncio.sleep(0.001)
                    pcm = opus_reader.read_pcm()
                    if pcm.shape[-1] == 0:
                        continue
                    all_pcm_data = pcm if all_pcm_data is None else np.concatenate((all_pcm_data, pcm))
                    while all_pcm_data.shape[-1] >= self.frame_size:
                        chunk = all_pcm_data[: self.frame_size]
                        all_pcm_data = all_pcm_data[self.frame_size:]
                        deepgram.enqueue_pcm(chunk)
                        chunk_tensor = torch.from_numpy(chunk).to(device=self.device)[None, None]
                        with torch.no_grad():
                            codes = self.mimi.encode(chunk_tensor)
                            _ = self.other_mimi.encode(chunk_tensor)
                            for c in range(codes.shape[-1]):
                                forced_text =

[truncated: omitted 4451 characters]

```

### `skills/personaplex/scripts/personaplex_memory_flow.py`

```text
"""Memory/Brave route helpers for the PersonaPlex wrapper."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

TimedPost = Callable[..., Awaitable[dict[str, Any]]]


def intent_requires_evidence_case(intent: dict[str, Any]) -> bool:
    data = intent.get("json") or {}
    action = str(data.get("action") or "").upper()
    profile = str(data.get("recall_profile") or "").lower()
    artifacts = [str(item).lower() for item in (data.get("required_artifacts") or [])]
    if action == "COMPLIANCE" or "evidence_case" in artifacts or "qra" in artifacts:
        return True
    return "qra" in profile or "sparta" in profile or "compliance" in profile or bool(data.get("frameworks"))


async def memory_route_product_with_sources(
    question: str,
    intent: dict[str, Any],
    recall: dict[str, Any] | None,
    brave: dict[str, Any] | None,
    timed_post: TimedPost,
) -> dict[str, Any]:
    data = intent.get("json") or {}
    action = str(data.get("action") or "").upper()
    scope = str(data.get("scope") or "persona_memory")
    if action == "CLARIFY":
        result = await timed_post("/clarify", {"q": question, "scope": scope, "k": 4})
        result["route_endpoint"] = "/clarify"
    elif action in {"NO_MATCH", "OFF_TOPIC", "UNSAFE", "DEFLECT"}:
        result = await timed_post("/deflect", {"q": question, "persona_id": "embry", "intent_action": action})
        result["route_endpoint"] = "/deflect"
    else:
        answer_args = next((c.get("arguments") or {} for c in data.get("tool_calls") or [] if c.get("endpoint") == "/answer"), {})
        persona_id = answer_args.get("persona_id") or (data.get("query_plan") or {}).get("extracted_entities", [None])[0] or "embry"
        brave_json = (brave or {}).get("json") or {}
        payload = {
            "q": question,
            "scope": answer_args.get("scope") or scope,
            "persona_id": "embry" if str(persona_id).lower() == "embry" else persona_id,
            "source_packets": answer_args.get("source_packets") or ["current_facts", "persona_memory"],
            "external_sources": [{"skill": "brave-search", "domain": "current_facts_research",
                                  "query": brave_json.get("query"), "results": brave_json}] if brave_json else [],
            "recall_snapshot": (recall or {}).get("json") or {},
            "current_facts": brave_json,
            "persona_memory": (recall or {}).get("json") or {},
        }
        result = await timed_post("/answer", payload, timeout=20.0)
        result["route_endpoint"] = "/answer"
    return result


def planned_recall_payload(intent: dict[str, Any]) -> dict[str, Any]:
    data = intent.get("json") or {}
    for call in data.get("tool_calls") or []:
        if call.get("endpoint") == "/recall":
            args = dict(call.get("arguments") or {})
            args.setdefault("k", 12)
            args.setdefault("collections", ["persona_memory"])
            args.setdefault("tags", ["persona:embry"])
            return args
    return {"q": "What persona memories explain how Embry would respond to this question?",
            "k": 12, "collections": ["persona_memory"], "tags": ["persona:embry"]}


def planned_brave_query(intent: dict[str, Any], fallback_query: str) -> str:
    data = intent.get("json") or {}
    for call in data.get("tool_calls") or []:
        if call.get("skill") == "brave-search" and (call.get("arguments") or {}).get("query"):
            return str((call.get("arguments") or {})["query"])
    return fallback_query


async def evidence_case_gate_product(question: str, intent: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(0)
    return {
        "ok": False,
        "route_endpoint": "create-evidence-case",
        "requires_evidence_case": True,
        "question": question,
        "intent_action": (intent.get("json") or {}).get("action"),
        "message": "This turn requires an evidence-case branch before any substantive answer may be spoken.",
    }

```


## Review Questions

1. Are there correctness bugs or edge cases in the implementation?
2. Are there security, data-loss, concurrency, or rollback risks?
3. Are the tests or validation steps sufficient for the stated change?
4. Is the change scoped tightly, or does it introduce unrelated behavior?
5. What exact fixes should be made before this is committed?

## Required Output Format

Return one bounded artifact-review result. If the target is being sent through
`$ask webgpt-review`, prefer the JSON schema required by that runtime. Otherwise
return this structure in markdown:

1. Merge-blocking findings, with evidence, impact, exact fix, and the test that
   should fail before the fix.
2. Important test gaps required before merge.
3. Merge recommendation: SAFE_TO_MERGE, SAFE_WITH_CONDITIONS,
   CHANGES_REQUESTED, or NOT_SAFE.
4. Prompt clarity self-improvement: identify ambiguous objective wording,
   conflicting output contracts, missing required files/evidence, underspecified
   blocking thresholds, and a clearer bounded review request for the next run.

