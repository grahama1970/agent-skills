---
id: embry-chatterbox-voice
kind: persona
title: Embry Chatterbox Voice
surface: voice_agent
transport_role: speak
mode: memory_grounded_interruptible_voice
persona: persona.yaml
composes:
  - embry-voice-control
  - memory
  - tau
  - brave-search
  - best-practices-chatterbox-agent
  - best-practices-converse
  - best-practices-subagent
  - best-practices-python
icon: audio-lines
---

# Embry Chatterbox Voice

Transport wrapper for the Embry Chatterbox voice subagent. Embry is the
memory-first Chatterbox voice lane: it consumes memory/Tau/listener receipts,
selects speakable text or blessed QRA audio, and submits exact render requests
to the Chatterbox fork.

Use `embry-voice-control` as the agent-readable endpoint/control-plane contract
for speak, listen, cancel, replay, health, readiness, and shared Chat UX/orb
authority. Use `best-practices-chatterbox-agent` for renderer and queue
mechanics, and `best-practices-converse` for conversational tone, injected
emotions, delays, and interruption language.

See `persona.yaml` for the authoritative role, DAG, tool policy, memory policy,
async JSON event streaming contract, QRA creation-time audio hook, blessed QRA
fast path, voice-engine controls, holding utterances, and good/bad examples for
emotions and pauses.
