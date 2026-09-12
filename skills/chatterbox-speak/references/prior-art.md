# Prior art & build-vs-adopt (conversation-arc runtime)

Brave/web research (2026-09-12) confirms the two-concurrent-agent design is a
**named, mature pattern**. Most of the runtime should be **adopted, not built**.
chatterbox-speak's unique value is the emotional/persona cover layer on top.

## The pattern has a name: Talker-Reasoner

Our A (speak+listen) / B (solve) split is the **Talker-Reasoner pattern**
(LiveKit): "a fast Talker keeps the conversation flowing while a slower Reasoner
thinks in the background — no more dead air." Academic backing:

- RelayS2S — two parallel paths (fast + slow) on turn detection (arxiv 2603.23346).
- DDTSR — "listen-while-thinking and speak-while-thinking" (arxiv 2602.23266).
- LTS-VoiceAgent — Listen-Think-Speak, semantic triggering (arxiv 2601.19952).
- "Thinking While Speaking" / conversational infill — a small talker model speaks
  while a foundation model reasons (alphaXiv 2511.07397).

## Our stack: RealtimeSTT (ears) + Chatterbox Turbo (mouth)

We do NOT adopt Pipecat/LiveKit's STT/TTS providers. The real substrate already
exists locally under `~/workspace/experiments/`:

- `RealtimeSTT/` — the ears. Its **Embry Unix Listener Event Spine** publishes
  RealtimeSTT callbacks to the **`embry-voice-control` journal**. That journal IS
  the event stream A monitors (the `solver_event.v1` log-tail is the same idea).
- `chatterbox/` — the mouth (Chatterbox Turbo service on :8018; this skill's fork).
- `pi-mono-embry-interrupt-contract/` and `pi-mono-embry-interrupt-opencode/` —
  the **interrupt/barge-in contract** work already in flight (pi-mono forks).
- `embry-os/` — the KDE-native runtime host (PipeWire/D-Bus/systemd daemons).

We borrow only the coordination *pattern* from Pipecat/LiveKit/EdgeVox — the
Talker-Reasoner split and the interrupt controller — implemented over our
RealtimeSTT listener spine + Chatterbox mouth + the embry-interrupt-contract.

| Sub-problem | Use | Note |
|---|---|---|
| Listen lane: VAD, endpointing, user barge-in detection | **RealtimeSTT** (ours) | Agent A's ears; fires the interrupt signal |
| Mouth: TTS render/playback + mid-utterance flush | **Chatterbox Turbo** (ours) | must support stop/cancel mid-clip for barge-in |
| Interrupt coordination pattern (VAD→TTS flush→cancel B) | borrow **EdgeVox `InterruptController`** / **Pipecat interruptions** design | implement over RealtimeSTT+Chatterbox; VAD<20ms, flush<100ms targets |
| Talker-Reasoner orchestration (concurrent speak/listen/solve) | borrow **LiveKit Talker-Reasoner** design | implement in embry-voice-control |
| Latency-masking cover (fillers, thinking sounds, backchannels) | our emotional persona hums / fused-hmm | AWS Lex/Agora/itellico show the pattern is standard; the persona layer is ours |
| Solver→voice progress stream | `solver_event.v1` JSONL log tail | standard agent-SSE shape (`agent-stream`, OpenAI Agents SDK, AsyncVoice); log-tail is the minimal form |

## What chatterbox-speak actually owns (the differentiator)

Do NOT reinvent transport/VAD/barge-in/interruption. chatterbox-speak owns only:

- the **emotional cover layer** — verified hums (bone-dry, pitch-normalized,
  memory-linked), emotion→arc (reassure/answer), fused-hmm openers, Turbo tag
  rules, pause macros;
- the **fast-agent contract** (`fixtures/fast_agent_prompt.md`) — classify,
  map the shared arc, pace to predicted ETA, generate cover, barge-in;
- the deterministic **fallback + palette + visualization** (`conversation_arc.py`
  planner, table/chart/SVG).

`embry-voice-control` wires this contract into a Talker-Reasoner runtime built on
OUR stack — **RealtimeSTT** for the ears/VAD/barge-in and **Chatterbox Turbo** for
the mouth — borrowing the interrupt-controller and Talker-Reasoner *patterns* from
Pipecat/LiveKit/EdgeVox rather than their providers. Our fast agent supplies the
emotionally-shaped cover beats and hum decisions; B streams `solver_event.v1`.
Reuse the pattern; keep our STT/TTS; build the persona.
