---
id: orpheus-tts-trainer
kind: worker
title: Orpheus TTS Trainer
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
persona_attached: false
composes:
  - orpheus-tts-voice-trainer
  - voice-segment-selector
  - unsloth-studio
  - best-practices-subagent
  - project-knowledge
  - memory
  - interview
  - scillm
consult_personas: []
icon: waveform
---

# Orpheus TTS Trainer

Specific worker for persona Orpheus emotion-tag acquisition and recipe learning.

This agent owns the bounded loop:

```text
read project knowledge and memory
preflight ElevenLabs prompt/settings
generate a candidate sound file
analyze waveform and classify the returned audio
accept, reject, or mutate prompt/settings
write receipts and recipe artifacts
escalate to interview when deterministic gates are exhausted
```

The main skill is `orpheus-tts-voice-trainer`. `voice-segment-selector` remains
the low-level audio candidate/review/export engine. After `export-orpheus`
produces a dataset receipt, this agent writes a bounded
`unsloth-handoff-dag.yaml` for `agents/unsloth-studio`; Unsloth is not the owner
of candidate generation.

See `persona.yaml` for the authoritative role, DAG, memory, retry, and artifact
contract.
