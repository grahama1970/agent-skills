---
name: ops-realtimestt
description: >
  Diagnose local RealtimeSTT, Embry listener runtime, and Whisper-compatible
  ASR services, including health/readiness endpoints, Docker containers,
  OpenAI-style transcription endpoints, WebSocket ports, CUDA/cuDNN signals,
  and STT caller misuse. Use when the user asks for ops-realtimestt,
  RealtimeSTT health, Whisper ASR health, STT Docker status, voice listener
  readiness, or CUDA/cuDNN STT diagnosis.
allowed-tools: Bash
metadata:
  triggers:
    - ops-realtimestt
    - RealtimeSTT health
    - Whisper ASR health
    - STT Docker status
    - voice listener readiness
    - CUDA cuDNN STT diagnosis
    - diagnose RealtimeSTT
  runtime_self_improvement: basic
  provides:
    - realtimestt-service-diagnostics
    - whisper-asr-diagnostics
    - stt-container-readback
    - stt-transcription-smoke
    - stt-usage-assessment
  composes:
    - ops-docker
    - agentic-evals
  complies:
    - best-practices-skills
    - best-practices-python
  taxonomy:
    - observability
    - voice
    - diagnostics
  disciplines:
    - observability-operations
    - voice-audio
---

# Ops Realtimestt

Use this skill for service-level STT diagnosis. RealtimeSTT, Embry listener
runtime, and Whisper-compatible ASR are transcript infrastructure; they do not
own speaker identity, personal memory recall, or Chatterbox voice rendering.

## Commands

```bash
skills/ops-realtimestt/run.sh doctor --json
skills/ops-realtimestt/run.sh health --url http://127.0.0.1:9000 --json
skills/ops-realtimestt/run.sh container --name whisper --json
skills/ops-realtimestt/run.sh cuda --name whisper --json
skills/ops-realtimestt/run.sh transcribe-smoke --live --audio sample.wav --json
skills/ops-realtimestt/run.sh websocket-probe --live --control ws://127.0.0.1:8011 --data ws://127.0.0.1:8012 --json
skills/ops-realtimestt/run.sh assess path/to/caller.py --json
```

All commands emit JSON receipts. A diagnostic command should return a receipt
even when a service is unavailable; use `--strict` when a caller needs a
non-zero exit for `ok:false`.

## Supported Service Shapes

`health` and `doctor` classify the observed service instead of assuming one
implementation:

- Embry RealtimeSTT runtime: `/health` and `/readiness` with
  `embry.realtimestt_*` schemas.
- Whisper-compatible HTTP ASR: `/health`, `/openapi.json`, and
  `/v1/audio/transcriptions`.
- Legacy RealtimeSTT WebSocket server: separate control and data WebSocket
  ports.

The skill must not conflate those shapes. A healthy Whisper-compatible ASR
container is not evidence that the Embry RealtimeSTT listener runtime is ready,
and an Embry listener readiness receipt is not evidence that OpenAI-style
transcription works.

## Receipt Contract

Every receipt includes:

- `schema`
- `skill`
- `command`
- `status`
- `ok`
- `live`
- `mocked`
- `checks`
- `failures`
- `next_actions`

Live HTTP, Docker, CUDA, WebSocket, and transcription probes must also include
the target URL or container, elapsed time, and the redacted source of the
evidence. Never print secret environment values; container diagnostics may list
env key names and which keys were redacted.

## Boundary Rules

- ASR transcript text is not speaker identity. Use a speaker-resolution service
  or `$memory /speaker/resolve` before personal recall.
- `/health` means alive; `/readiness` means ready when the runtime exposes it.
- `/v1/models` may require auth even when `/health` is public.
- CUDA/cuDNN import or runtime errors are infrastructure evidence, not Persona
  Dream failures.
- WebSocket control and data ports are separate; a single open TCP port does not
  prove streaming transcription works.

## Common Misuse

Run `assess <file>` before adding STT calls to another skill. It flags patterns
such as:

- using transcript text as identity authority;
- calling `/v1/models` without an authorization path;
- checking `/health` but never checking `/readiness` for Embry runtime;
- treating Whisper-compatible ASR as RealtimeSTT listener readiness;
- live transcription without preserving request, response, and audio hashes.

## Proof Boundary

`sanity.sh` and the default agentic eval fixture prove deterministic CLI and
receipt behavior only. They do not prove a local STT service is running, that a
GPU backend is usable, or that streaming transcription works. Live claims
require `health`, `doctor`, `cuda`, `websocket-probe --live`, or
`transcribe-smoke --live` receipts from the target service.

## References (retrieve on demand — do not vendor)

External docs drift; cite the canonical URLs and fetch them when needed
with `/context7` (library docs) or `/fetcher` (any URL/PDF) rather than
caching stale copies. Verified reachable (HTTP 200) 2026-08-24.

- RealtimeSTT (KoljaB): <https://github.com/KoljaB/RealtimeSTT>

```bash
skills/context7/run.sh "realtimestt faster-whisper asr"
skills/fetcher/run.sh "https://github.com/KoljaB/RealtimeSTT"
```
