---
name: ops-chatterbox
description: >
  Diagnose local Chatterbox or Chatterbox-Turbo TTS services, Docker containers,
  health endpoints, render receipts, paralinguistic tag handling, voice delivery
  capability fields, and Chatterbox caller misuse. Use when the user asks for
  ops-chatterbox, Chatterbox health, Chatterbox Docker status, Chatterbox TTS
  smoke tests, or Chatterbox voice-delivery diagnostics.
allowed-tools: Bash
metadata:
  triggers:
    - ops-chatterbox
    - Chatterbox health
    - Chatterbox Docker status
    - Chatterbox TTS smoke
    - Chatterbox voice delivery diagnostics
    - Chatterbox tag handling
    - diagnose Chatterbox
  runtime_self_improvement: basic
  provides:
    - chatterbox-service-diagnostics
    - chatterbox-container-readback
    - chatterbox-render-smoke
    - chatterbox-usage-assessment
  composes:
    - ops-docker
    - best-practices-chatterbox-agent
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

# Ops Chatterbox

Use this skill for service-level Chatterbox diagnosis. Chatterbox is the speech
renderer; caller skills own facts, identity, dream state, answer invariance,
memory policy, and conversation logic.

## Commands

```bash
skills/ops-chatterbox/run.sh doctor --json
skills/ops-chatterbox/run.sh health --url http://127.0.0.1:8018/health --json
skills/ops-chatterbox/run.sh container --name chatterbox-fork-agent-server --json
skills/ops-chatterbox/run.sh render-smoke --live --text "Chatterbox smoke test." --json
skills/ops-chatterbox/run.sh assess path/to/caller.py --json
```

All commands emit JSON receipts. A diagnostic command should return a receipt
even when a service is unavailable; use `--strict` when a caller needs a
non-zero exit for `ok:false`.

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

Live HTTP, Docker, and render probes must also include the target URL or
container, elapsed time, and the redacted source of the evidence. Never print
secret environment values; container diagnostics may list env key names and
which keys were redacted.

## Boundary Rules

- A `/health` payload that echoes a requested `voice_delivery` field is not
  proof that audio changed.
- Per-render `affect_effect`, `pace_effect`, `tag_handling`, audio artifact
  metadata, and transcript or ASR readback are stronger evidence than request
  echo.
- Keep `answer_text` separate from `tts_render_text` when adding sparse
  paralinguistic tags or nonverbal cues.
- Do not pass raw user-supplied bracket or XML speech controls directly to TTS.
- Treat Chatterbox-Turbo native event tags and base-engine emotion knobs as
  different channels unless a live receipt proves the selected backend applies
  both.

For voice-agent policy, read `$best-practices-chatterbox-agent`; this ops skill
does not replace that design contract.

## Common Misuse

Run `assess <file>` before adding Chatterbox calls to another skill. It flags
patterns such as:

- treating `tag_handling.tags_interpreted` or request echo as acoustic proof;
- passing `[laugh]`, `[sigh]`, or similar controls without tag/transcript gates;
- using `finished_response_audio` without hashing or copying the audio artifact;
- mutating `answer_text` instead of using a separate `tts_render_text`;
- calling a live render path without preserving request and response JSON.

## Proof Boundary

`sanity.sh` and the default agentic eval fixture prove deterministic CLI and
receipt behavior only. They do not prove the local Chatterbox service is
running, that a model is loaded, or that a rendered voice sounds emotionally
different. Live claims require `health`, `doctor`, or `render-smoke --live`
receipts from the target service.
