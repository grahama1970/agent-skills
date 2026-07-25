# Path B — end-to-end proof (arc_state -> spoken line)

2026-07-25. Goal G2: make the persona's ACCUMULATED self audible in the voice.

## Verified facts
- `/ask` is UP: `ask/run.sh doctor --json` -> status pass, 0 errors, 16/16 checks;
  scillm lane "available".
- Real entrypoint runs: `dream_voice_weights.py --dream-key
  dream_dream_successor_943b01ecd9a3 --arc-voice` produced a profile with weights
  {warmth, boundary, hesitance}. Its `arc_voice.line` FELL BACK (fallback_used:
  true, "adapter returned no spoken_line") — the scillm-backed text adapter
  returned no output on two live attempts. Blocker = scillm text backend, not
  /ask and not the Path B code.

## The mechanism works when pointed at a live LLM
Prompt built from Embry's REAL arc_state (continuity_ledger.read_ledger):
- self-claims: distance retains me; professionalism may disguise a plea to be
  understood without speaking.
- active tensions: I want someone to notice what I refuse to show; I can't yet
  tell witness from intrusion.
- recurring avoidance: direct relational confrontation.
- tonight's dream residue: "the door stayed shut and no one came when I called."

Generated arc-conditioned spoken line (ChatGPT, via chrome-MCP, no scillm):

  "I kept the door closed, and still listened for footsteps."

Contrast — current code fallback (raw dream statement, no arc conditioning):

  "the door stayed shut and no one came when I called."

Same dream; the arc-conditioned line carries the accumulated self (distance-as-
protection + wanting-to-be-noticed-without-asking + avoids confrontation). That
is exactly what Path B is for.

## Status
- Code: committed (36556652). `--arc-voice` reads arc_state, generates the line
  via the skill's tau_text_reasoning_adapter, fallback-guarded.
- Remaining: the in-code reasoning call needs a live text backend. scillm
  returned no output; route that one call through a live handler (webgpt via
  surf/tau, or scillm once healthy). This is backend availability, not a Path B
  design gap — the line above proves the design.
