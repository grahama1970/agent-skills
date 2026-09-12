# Conversation arc — covering Agent-B latency

This is the culmination of chatterbox-speak: how the **fast Voice/Cover agent
(Agent A)** maps a whole turn into an ordered timeline of *verified* elements —
a fused-hmm opener, progress lines, mood-matched hums, and an emotional
answer-arc — **shaped to the predicted Agent-B solve latency** so there is never
dead air and Embry lands the answer with the right emotional shape from
beginning to end.

Tool: `scripts/conversation_arc.py` (deterministic, ~0ms, stdlib self-check).
It composes ONLY elements the banks already verify — it invents no new render
tricks.

## Mental model: two agents, one mouth

```
Agent B (slow, high-reasoning)  ──emits solve ETA + stage events──►  Agent A (fast)
  $debugger / $ops-excalidraw / memory /answer                        maps the arc,
  produces the real answer                                            owns the mouth
```

Agent A does not wait silently. Given B's **predicted latency**, it lays down a
timeline that fills that whole window, then delivers B's answer through an
emotional arc. When B finishes early, barge-in hands off (runtime lives in
`embry-voice-control`).

## The element palette — what you mix and match

| Element | Bank / source | Role in the arc | Rule |
|---|---|---|---|
| **fused-hmm opener** | `outputs/sfx-library/fused-hmm/` | buys the first ~2.5s while B spins up | ≤2 per conversation; band by complexity (≥3 parts → high `Hmmmm… [sighs]`) |
| **progress line** | `fixtures/progress_macros.json` (stage pools) | says *where she is* (intent→recall→searching→answer) | plain Turbo lexical, <1s, no tags, weighted-random no-repeat |
| **hum bed** | `fixtures/song_hum_macros.json` (via `hum_render.py`) | fills a **wide** wait (>7s) under/between speech | bone-dry, mood-matched, gain −1.5..−5 dB under speech (`filler_gain.py`) |
| **pause** | `fixtures/pause_macros.json` | a short natural hold on a narrow gap | compiled to real silence |
| **answer arc** | `speak.py` ARCS (`answer` / `reassure`) | delivers B's solution across tone phases | grief/fear/sad → `reassure`; else → `answer` |

## The latency budget (how the fast agent sizes the arc)

```
opener (~2.5s) + Σ progress lines (~1.4s each + ~0.6s pause)  ≥  predicted_latency_ms
```

- Start with the opener.
- Walk the stage sequence `intent → recall → searching`, one progress line each.
- After each line, look at the **remaining** gap to the answer:
  - remaining **> 7s** → drop in a **hum bed** to fill (don't spam progress lines);
  - else → a short **pause**.
- Fire an "answer imminent" beat, then deliver the **answer arc** phases.
- The plan's `covers_latency` must be `true` (planned_total_ms ≥ predicted).

## Emotional shape, beginning to end

The arc is not flat cover then answer — it has an emotional trajectory:

- **grief / fear / sadness** → `reassure` arc: `careful_concerned → neutral_warm →
  relieved`; hums are the quiet Hawaiian/longing beds tied to Embry's memories.
- **neutral / positive / hard-technical** → `answer` arc: `careful_concerned →
  calm_precise → memory_confident → playful_light`.

Emotion also picks the **hum**: `conversation_arc.py` matches the hum's `mood`/
`evokes` to the emotion (e.g. grief → a longing bed linked to the Kai/surf
memories via `memory_links`).

## Worked example — grief, 30s Agent-B latency

```bash
python3 scripts/conversation_arc.py plan --latency-ms 30000 --emotion grief \
  --intensity 4 --complexity 3 \
  --situation "listener grieving, asked a hard 3-control question" \
  --answer-text "SC-7 draws the boundary; here's why it matters." \
  --json out/arc.json --svg out/arc.svg --dag out/arc.dag.json
```

Timeline the fast agent maps (11 elements, 38.1s covers 30s):

```
     0ms speech  fused_hmm     fused-hi-02          "Hmmmm... [sighs] let me dig into that."
  2480ms speech  progress      progress:intent      "Let me make sure I've got what you're asking."
  3880ms sfx     hum           hum:st-louis-blues   bone-dry bed, -3 dB under speech
 15880ms speech  progress      progress:recall
 17280ms sfx     hum           hum:st-louis-blues
 29280ms speech  progress      progress:searching
 30680ms pause   pause         pause:beat
 31280ms speech  progress      progress:answer      "Okay — here's what I found."
 32680ms speech  answer_phase  arc:reassure:careful_concerned
 34480ms speech  answer_phase  arc:reassure:neutral_warm
 36280ms speech  answer_phase  arc:reassure:relieved
```

## Seeing it — two visuals

**SVG timeline** (lanes = speech / sfx / pause, emotion band, red "answer due"
marker at the predicted latency): `--svg out/arc.svg`, open in a browser.

**Terminal chart** via `$phart-dag-chart` (the arc is emitted as `ask.dag.v1`):

```bash
python3 scripts/conversation_arc.py plan ... --dag out/arc.dag.json
$phart-dag-chart chart out/arc.dag.json
```

```text
DAG decision tree · arc-grief-high (phart 1.5 git)
schema=ask.dag.v1

 ┌──────────────┐
 │ 00_fused_hmm │
 └──────────────┘
         │  v
  ┌─────────────┐
  │ 01_progress │
  └─────────────┘
         │  v
    ┌────────┐
    │ 02_hum │      (… chain continues through the answer phases)
    └────────┘
```

## Boundaries

- This **plans** the arc. The concurrent runtime, stage-event channel, and
  barge-in handoff live in `embry-voice-control`.
- Renderer `[tags]` appear only on `fused_hmm`/`answer_phase` render lines (they
  are render instructions); `progress`/`pause` lines are plain. Nothing here is
  written to `$memory` canonical text.
- Every element is bank-verified; the arc composes them, it does not invent new
  affect tricks.
