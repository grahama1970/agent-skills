---
name: chatterbox-speak
description: >
  Thin front door for speaking a line through the live Chatterbox service with a
  named voice, tone, context note, and emotional intensity. Use when a project
  agent says "speak", "say this out loud", "speak as embry", "chatterbox speak",
  "render this with a sigh", or wants one-shot voiced output with a receipt
  without the full embry-voice-control turn pipeline.
triggers:
  - speak this as embry
  - chatterbox speak
  - say something out loud
  - render this line with chatterbox
  - speak with high intensity
provides:
  - voice-render
composes:
  - agentic-evals
  - analyze-chatterbox-emotions
  - memory
  - ask
  - best-practices-chatterbox
  - triage-error
  - interview
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-chatterbox
runtime_self_improvement: basic
taxonomy:
  - voice-audio
---

# chatterbox-speak

One-shot speech: text + voice + tone + intensity -> live Chatterbox render ->
WAV + JSON receipt. Rendering, backend routing, tag handling, and affect
receipts are owned by the Chatterbox service (`http://127.0.0.1:8018`); this
skill validates the request, calls `/synthesize` (or `/synthesize-batch` for
planned pauses), validates the response, and writes a receipt. It is NOT the conversation control plane — that is
`embry-voice-control`.

## Emotion delivery: what works at each intensity (human-verified 2026-09-10)

The caller chooses intensity 1-10 from context. Rungs author the variants;
three bands pool them for weighted-random selection with session no-repeat:
low (1-3), medium (4-7), high (8-10). Target roughly 15-20 verified macros per
emotion: ~5 per band, deepest in medium where most conversation lives.

| Band | Rungs | Pattern that works | Cost |
|---|---|---|---|
| high | 8-10 | ElevenLabs v3 whole-sentence in the Embry clone (`[laughs] [giggles] [chuckles] [sighs]` woven mid-thought) | ~1-4s, cache or mask with a Turbo reaction beat |
| medium | 4-7 | Turbo native: `[happy]` line tag + at most one `[laugh]`/`[chuckle]` + `...` pause, tone playful_light | <1s |
| low | 1-3 | Plain Turbo tone (neutral_warm) or a cached v3 interjection clip at sentence boundaries | ~0s added |

**Tag vocabulary gotcha (human-caught):** Turbo accepts only SINGULAR event tags
(`[chuckle] [laugh] [sigh] [gasp] [surprised] [angry] [sarcastic]` — service
`accepted_tags`); the PLURAL forms (`[chuckles] [laughs] [sighs]`) are ElevenLabs
v3-clone only. A plural tag on Turbo hits `unknown_tag_behavior: synthesized_as_literal_text`
— it SPEAKS the word "chuckles". Use singular for `turbo_native` entries, plural
only for `v3_whole_sentence`.

**Confirmed emotions (2026-09-11, human 'these are good'):** happy, celebration,
crying (v3 splice), sadness, surprised, angry (controlled/firm, not shouting).
**Sarcastic** inverts the ladder — mockery risk rises with intensity, so it tops
out ~7; HIGH intensity pivots to a warm self-deprecating JOKE. Sarcasm/joke gate
to BENIGN `/deflect` only (OFF_TOPIC/NO_MATCH), never safety/confusion.

**Highest-intensity peak routing** (`fixtures/emotion_peak_routing.json` v2,
REVISED per WebGPT strategic review — `outputs/webgpt-escalation-review.md`):
safety/conduct gates the permitted ACTION, user NEED gates the response, and
valence/arousal/preference only shape DELIVERY. Delivery routes: positive peak →
brief interruptible Hawaiian hum (preference-gated, never fluent speech, never a
forced climax); tension → acknowledge/repair first, at most ONE self-targeted
joke only with affirmative evidence humor is welcome; distress/grief/fear/confusion
or uncertain → QUIET SUPPORT (the fallback — not humor/hum). ABUSE is a CONDUCT
ladder, not an emotion peak: Stage0 repair → Stage1 Embry boundary → Stage2 final
warning (Embry default) → Stage3 end session, counting episodes only AFTER a
delivered boundary. A failed joke changes style, NEVER enforcement. **Horus is an
optional, disclosed AI *moderation voice* (not a 'supervisor'), DISABLED for
automatic moderation until user-tested**; he may voice a boundary but is never
what makes Embry's 'no' valid. Deterministic controller owns transitions; runtime
in embry-voice-control.

**De-escalation joke search** (`scripts/joke_search.py`, `fixtures/joke_corpus.json`):
for an ABUSIVE-flagged conversation, search a GENTLE on-topic safe joke to defuse
(never at the user's expense — mockery escalates; not if genuinely distressed).
Primary corpus is HuggingFace `shuttie/dadjokes` — 49,400 wholesome jokes
(offensive-word scrubbed) at `/mnt/storage12tb/skills/chatterbox-speak/joke_corpus_dadjokes.json`,
keyword-searchable OFFLINE with no key, safest for a tense moment. Falls back to
the small committed JokeAPI seed if absent; auto-upgrades to dynamic Humor API
(`HUMOR_API_KEY`) only if a live 50k+ search is ever wanted. Weave the searched
joke into a warm Embry line with the SINGULAR `[chuckle]` (Turbo), never plural.

Hard rules (each earned by a human-rejected render):
- Never splice clips mid-clause; prosody breaks and it sounds robotic. Whole
  sentences only; SFX/clips at boundaries.
- Never overlap-mix SFX under speech (rejected: robotic).
- Emotion in the insert must not exceed the speaking voice's intensity
  (a huge sob next to flat Turbo speech = fake).
- `[crying]` on Turbo is inert (measured; upstream issue #186 concurs) and
  `[excited]` does not exist. Sadness = `[sigh]` + halting text + compiled
  pauses on Turbo; crying arcs come from cached v3 clones at boundaries.
- Numeric intensity on base-affect reads aggressive, not emotional. Turbo
  ignores exaggeration/cfg_weight (source-verified). Temperature (0.05-1.5)
  is the real Turbo expressiveness knob.

Live assets: `outputs/sfx-library/manifest.json` (SFX macros, orchestration
rules, intensity pools), `happy-variations-webgpt.json` /
`sadness-variations-webgpt.json` (banks; human_verified status per entry),
ElevenLabs clone voice `embry-nonverbal` (orfFiGOiB0Kn2nOHPNIP). Recall
verified recipes first: `compare-memory recall '<situation>'` — the banks
teach what works; the project agent selects by context metadata (use_when /
avoid_when, emotion metatags like `emotion:celebratory` + `avoid:aggressive`).

## Pronunciation normalization (control ids and acronyms)

Chatterbox has no SSML, say-as, or lexicon feature; it mispronounces acronyms
and alphanumeric ids (resemble-ai/chatterbox#400 confirms — the maintainers'
workaround is spacing acronym letters). `scripts/pronounce.py` is the standard
fix used by on-device-TTS teams: a deterministic rule-based preprocessing pass
run before render (`speak` applies it by default; `--no-normalize` to skip).

- Control ids spelled digit-by-digit, letters spaced: `SC-7` -> "S C seven",
  `111-A` -> "one one one A", `AC-2(3)` -> "A C two three".
- Bare acronyms spaced to be read as letters: `CUI` -> "C U I", `HTML` -> "H T M L".
- Only IRREGULAR terms need `fixtures/pronunciation_lexicon.json` (said as a word
  or expanded): `NIST` -> "nist", `ITAR` -> "eye-tar". The rule covers the rest
  for free, so the lexicon stays small and human-verified by ear.
- Native `[tags]` and prose numbers/years (`2026`) are left untouched.

No LLM and no per-utterance `$memory` recall: substitution must be exact and
instant. The lexicon is seeded from the existing control/definition collections
and extended as renders prove entries; the receipt records `original_text` vs
`spoken_text`. `python3 scripts/pronounce.py` runs the self-check.

## Conversation arc — covering Agent-B latency (the culmination)

`scripts/conversation_arc.py` is how the fast Voice/Cover agent (Agent A) maps a
WHOLE turn into an ordered timeline of verified elements — fused-hmm opener ->
progress lines -> mood-matched hum beds -> emotional answer-arc — **sized to the
predicted Agent-B solve latency** so there is never dead air and Embry lands the
answer with the right emotional shape start to finish. It composes ONLY
bank-verified elements (below); it invents no new affect tricks.

```bash
python3 scripts/conversation_arc.py plan --latency-ms 30000 --emotion grief \
  --intensity 4 --complexity 3 --situation '...' --answer-text '...' \
  --json out/arc.json --svg out/arc.svg --dag out/arc.dag.json
$phart-dag-chart chart out/arc.dag.json   # terminal-visible arc
```

**Runtime is streamed, not a frozen guess.** The fast agent speaks a quick initial
arc (opener, instantly; restate if complexity>=2) then consumes Agent B's JSON
event stream (`solver_event.v1`: `{stage, eta_ms, answer_text?, done}`) and adapts
each beat via `conversation_arc.py next_element(state)` — wide remaining ETA -> hum
bed, narrow -> pause, `answer_ready`/`done` -> barge to the answer. B slow -> keep
covering (never dry); B fast -> barge early. `conversation_arc.py stream --events
solver.jsonl` demos it; `plan_arc` is the same policy simulated against the
predicted latency (instant floor + preview only). Runtime + barge-in owned by
`embry-voice-control`.

Inputs are SOURCED, not guessed: `--latency-ms` from `$memory POST /execution-stats`
(`recommended_timeout_ms`), `--emotion`/`--intensity` from `$memory POST /intent`
`delivery_context` (+ `/speaker/resolve`), `--complexity` = parts in the request.
The numbered step-by-step recipe is in `references/conversation-arc.md`.

**Confused about composing an arc? Scan `references/arc-examples.md`** — working
vs non-working arcs keyed off the request (greeting / worried / grief), each
non-working case naming the rule it breaks. Fastest way from stuck to a correct arc.

Latency budget: `opener(~2.5s) + Σ progress(~1.4s + ~0.6s pause) ≥ predicted_latency_ms`.
Walk `intent -> recall -> searching`; after each line, a **remaining gap > 7s**
gets a **hum bed** (bone-dry, mood-matched, gain-fit under speech), else a short
pause; then an imminence beat and the **answer arc**. Emotion picks the arc
(`grief/fear/sad -> reassure`, else `answer`) AND the hum (mood/`memory_links`
match). Two visuals: a self-contained SVG timeline (`--svg`) and a `$phart-dag-chart`
terminal chart (`--dag`, emitted as `ask.dag.v1`). **Full mix-and-match guide,
latency math, and a worked 30s grief example: `references/conversation-arc.md`.**
Boundary: this PLANS the arc; the concurrent runtime + barge-in live in
`embry-voice-control`; renderer tags appear only on fused_hmm/answer render lines,
never in `$memory` canonical text.

**Testing it audibly.** `fixtures/arc_scenarios.json` is a 12-turn bank
(simple->medium->complex: greeting, one-line fact, control walk-through, compare,
mild frustration, worried deadline, 3-control synthesis, grief+hard question, deep
debug, diagram request, tension repair). `scripts/arc_scenarios.py check` proves
each turn PLANS a latency-covering arc with the expected arc+band (retained eval
`fixtures/arc_scenarios_eval.json`, READY, non-vacuous). `arc_scenarios.py render
--id <id> --play` assembles that scenario's arc into one WAV and plays it for
human ear-verification (perceived delivery stays human-owned). Open tuning
question the audible pass exists to answer: simple turns currently over-cover
(an ~11s arc for "Morning") because the answer arc always runs full phases —
listen and decide whether short turns need a trimmed arc. `arc_scenarios.py chart --id <id>` (and `render` before
play) renders the arc GRAPHICALLY via `$phart-dag-chart` with timed, descriptive
nodes (opener -> say_intent -> hum bed -> say_recall -> ... -> answer phases) so
you can check the planned arc against the actual conversation while you hear it.

## Pause, thinking, and song-hum macros

Three named vocabularies the agent selects by context (all human-verified by ear):

- **Pause macros** (`fixtures/pause_macros.json`, `scripts/pauses.py`): the agent
  writes `[pause:<name>]` (micro/beat/breath/hesitation/transition/considered/weight);
  `speak --planned-pauses` resolves it to `[pause:<ms>ms]` for the compiler, which
  generates real silence. Unknown name fails closed (never spoken).
- **Thinking macros** (`fixtures/thinking_macros.json`, `outputs/sfx-library/fused-hmm/`):
  filled-pause openers before an effortful answer (grounded: fillers cluster before
  hard content and aid the listener; um>uh difficulty gradient). **Human verdict
  2026-09-11:** ISOLATED "hmm" clips sound inhuman in every synthesized form
  (v3 speaking "Hmm", SFX wandering or steady pitch, bare mm, breath). WHAT WORKS:
  fuse the hmmmm INTO a whole line in Embry's own v3 clone voice — "Hmmmm, let me
  see." / high-intensity "Hmmmm... [sighs] let me dig into that." No separate clip,
  no seam. Rules: ≤ 2 fused openers per conversation; 10 varied "let me see" tails
  (no-repeat); band by complexity (≥3-part problem → high hmmmm+sigh). Cover speech
  renders at `--pace slow` (~18% longer) to buy background solve time. SONG hums
  gain-fit UNDER speech per use (`scripts/filler_gain.py`: −1.5..−5 dB from measured
  speech RMS, varying, never louder than speech). Proven live: `two_agent_e2e.py`.
- **Progress macros** (`fixtures/progress_macros.json`): Embry speaks *where she is*
  as each work stage begins — stages mirror the `$memory` pipeline
  (intent → recall → clarify/deflect/answer/draft) AND the heavy Lane-B work
  activities: `debugging` ($debugger breakpoints), `diagramming` ($ops-excalidraw
  diagram search/create), `searching` (research), plus a `working_long` heartbeat.
  Short lexical lines rendered LIVE on Turbo (<1s), weighted-random per stage with
  session no-repeat.
- **Delivery cover = TWO concurrent agents** (`scripts/cover_plan.py`): every macro
  carries a `delivery_cover` — the instant filler that plays WHILE the real answer
  builds (best-practices-chatterbox-agent two-agent model):
  - **Agent A — Voice/Cover agent (fast lane).** Near-instant, low-reasoning; owns
    the mouth. Its macro selection is **primarily driven by `$memory` recall**:
    `/intent fast:true` returns `delivery_context` (affect category, tone influence,
    confidence) on the deterministic/classifier path, and `/recall persona_memory`
    pulls the verified recipe/hum banks (`emotion:*` recipes, song hums by
    mood/tempo, `use_when`/`avoid_when`) plus `/speaker/resolve` for who's listening.
    `cover_plan.py` then COMPILES that recalled delivery signal into concrete macro
    steps (thinking sound → progress line → pause, or a mood-matched hum) in ~0ms;
    the deterministic `(stage, intensity, tags)` table is the instant FLOOR when
    recall is empty or too slow to beat the speech deadline. Only a context tagged
    `ambiguous` escalates to a tiny model (glm-5.3-flash) to break a tie.
    Boundary: memory returns engine-neutral `delivery_context`/mood/tempo/tags,
    NEVER renderer tags or macro markup — Agent A compiles those.
  - **Agent B — Solver agent (slow lane).** High-reasoning; does the real work —
    sets breakpoints via $debugger, finds/draws diagrams via $ops-excalidraw,
    gathers evidence, composes the answer.
  - **Channel:** B emits stage events (`debugging`/`diagramming`/`searching`/
    `answer`…); A maps each to the matching progress pool and voices it. When B's
    answer is ready, barge-in hands off and Embry speaks B's content.
  The concurrent two-agent runtime is owned by `embry-voice-control`;
  chatterbox-speak owns the renderer + macro vocabulary + the deterministic planner.
### Recall-first: reuse or build a macro (Agent A loop)

Memory-first. Before speaking any cover/macro, Agent A **recalls**; it builds a new
macro only when nothing fits, and **stores** what it builds so the next turn recalls
it instead of rebuilding.

1. **Recall.** Query the situation against the recipe/hum banks:
   `POST /recall {q: "<situation in natural language>", collections: ["persona_memory", "lessons_v2"], tags: ["persona:embry", "emotion:<x>" | "song_hum"], k: 8}`.
   Use an item when `found` + confidence high + `should_scan` false, and its
   `use_when` matches while `avoid_when` does not.
2. **Reuse.** Play that macro's steps; respect the band pool + session no-repeat.
3. **Build (only if no fit).** Compose from **verified levers ONLY** — the bank
   primitives: emotion channel by band (v3 whole-sentence high / Turbo native mid /
   plain-or-clip low), a thinking clip, a progress stage, a pause macro, a
   mood-matched hum. Never invent tags or patterns the banks do not already verify;
   the hard rules above still apply.
4. **Store back.** Write the new macro so future recall finds it:
   `POST /store` (or `/upsert`) to `persona_memory`/`lessons_v2` with `retrieval_text`
   (the situation + why), `use_when`, `avoid_when`, the composed steps referenced by
   macro-id/params (engine-neutral — NO renderer `[tags]` in canonical text), status
   `provisional_agent_recommendation`, and tags. Independent `/recall` readback confirms.
5. **Verify by ear.** A human keep/cut flips status to `human_confirmed_*` or removes
   it. One preference is not a universal rule.

Boundary: canonical Memory text carries the plan by macro-id/params + engine-neutral
fields, never `[tags]`; Agent A compiles to renderer tags at playback.

- **Song-hum macros** (`fixtures/song_hum_macros.json`): public-domain Hawaiian /
  hapa-haole tunes Embry hums. `scripts/hum_render.py` is the ONE reproducible
  pipeline (no per-turn bespoking): `render` (ElevenLabs SFX -> ffmpeg bone-dry
  44.1k stereo + compressor + `-1.5 dBTP` limit into a steady under-speech bed),
  `register` (upsert enriched persona_memory docs with style/year/tempo_bpm/
  emotion_category/connected_memory_keys + `hum_evokes_memory` edges via /upsert),
  `all`, `self-check`. Hums must be BONE DRY (no reverb, no era cues) and
  loudness-consistent (~-20 LUFS) so none plays louder than the others.
  `/upsert` auto-embeds `retrieval_text` via the jina embedder into Qdrant
  (verified `semantic_sync_state: synced`, `scores.dense` > 0), so recall matches
  by mood/style/tempo. Multi-hop RANKING of the new edges needs the memory
  project's `persona-graph-materialize` (skills never hand-roll traversal AQL). Retained `$agentic-evals`
  proof: `fixtures/hum_pipeline.json` (self-check contract, fail-closed on bad
  command, and a live `hum_eval_probe.py` asserting a hum recalls with dense>0 and
  clean canonical text) — READY, both claims PROVEN. ALL picks are compositions published 1930 or earlier
  (US PD as of 2026, Duke CSPD). The 1930s film-era hits (Sweet Leilani 1937,
  My Little Grass Shack 1933) are NOT yet PD and are excluded. Hawaiian War Chant:
  hum the original 1860s Leleiohōku melody, never the copyrighted 1936 arrangement.
  Clips render on the 12TB drive; taste facts + tempo/category/ElevenLabs metadata
  live in `$memory` `persona_memory` (`kind: persona_music_preference`,
  `tags: persona:embry`) for semantic recall by mood/tempo/category via the text_mm
  embedder. Note: the multimodal embedder is text+image, NOT audio — recall matches
  the DESCRIPTION, not the waveform; ElevenLabs SFX humming evokes the style, not a
  note-accurate (or copyright-touching) rendition.

## Usage

```bash
./run.sh speak --voice embry --text 'Say something. [sigh]' \
  --context 'operator asked for a firm demo line' \
  --tone firm_boundary --planned-pauses --play

./run.sh voices        # list known voices and live tones
./run.sh speak --help
```

- `--voice`: named voice from the voice map (`embry` today; add entries in
  `scripts/speak.py` VOICES). Or pass `--ref-audio <container path>` directly.
- `--intensity low|medium|high` maps to 0.3 / 0.6 / 0.9. Omit it to let inline
  tags like `[sigh]` be consumed natively on turbo. Explicit intensity routes
  to the base-affect backend, which speaks tags as literal words — the receipt's
  `tag_handling` / `affect_effect` fields record which side of that tradeoff
  you got.
- `--tone`: any live calibrated tone (see `./run.sh voices`), e.g.
  `neutral_warm`, `grief_safe`, `firm_boundary`, `playful_light`.
- `--context`: caller-supplied grounding note. Stored in the receipt for audit;
  it does not change rendering. Choose tone/intensity from it yourself (see
  `$best-practices-chatterbox`).
- `--planned-pauses`: delegates spaced ` ... ` and `[pause:*]` compilation to
  `best-practices-chatterbox plan-silence`, then uses the service's existing
  `render_chunks` path with `crossfade_ms=0`. Silence is generated by the service,
  not simulated by sleeping during playback.
- `--play`: local playback via `pw-play`; playback failure exits nonzero.
- `--analyze`: runs `/analyze-chatterbox-emotions` on the rendered WAV and embeds
  the waveform/affect analysis in the receipt. Agentic evals use this as the
  post-render evidence gate.
- `--session <id> --to <speaker>`: persona-dream-style session continuity.
  Holds a bounded mood (`mood_intensity` moves halfway toward each requested
  intensity, clamped 0-1) and last tone across turns; a turn with no intensity
  keeps speaking with the held mood. Session state is turn-scoped continuity in
  `outputs/sessions/<id>.json` — it is NOT persona memory and is never written
  to `$memory` (matches the memory delivery_context decay contract).
- `--recall-context`: read-only `$memory /recall` with `speaker:<to>` tags;
  top items land in the receipt as grounding evidence. It does not change
  rendering — tone/intensity choice from context stays with the caller. `--to`
  is caller-asserted; real voice identity belongs to `$memory /speaker/resolve`
  in embry-voice-control.

Receipts and copies of the WAV go to
`/mnt/storage12tb/skills/chatterbox-speak/outputs/`.

## Contextual agentic evaluations

`fixtures/webgpt_audio.json` replaces the isolated-user-sentence test campaign.
`fixtures/contextual_conversations.jsonl` contains six representative cases,
not a completed expansion of the old 50-scenario bank. Each record includes
context origin, relationship, relevant prior turn IDs, dialogue, the current
user turn, actual Embry response, and renderer delivery plan. Synthetic context
is explicitly labeled and is never written to Memory.

```bash
./run.sh eval-context prompt fixtures/contextual_conversations.jsonl /tmp/contextual-prompt.txt
# Submit the compiled prompt through Ask's documented webgpt/Tau workflow.
# Freeze its live node receipt; --judge-node must name that actual Ask artifact.
./run.sh eval-context evaluate fixtures/contextual_conversations.jsonl celebration \
  /mnt/storage12tb/skills/chatterbox-speak/outputs/celebration.jsonl \
  --judge-node /absolute/ask-run/node-artifacts/handler-webgpt/node-receipt.json --render
../agentic-evals/run.sh run fixtures/webgpt_audio.json --timeout-seconds 480 \
  --output /mnt/storage12tb/skills/chatterbox-speak/outputs/contextual-report.json
```

The retained suite replays a frozen, independently obtained WebGPT judgment;
it does not pretend each repeated trial is a fresh semantic evaluation. Changing
any contextual input invalidates the judgment hash. Quotes must match relevant
conversation turns; evaluator identity, source prompt/response hashes, and actual
Ask/Surf transport receipts are preserved. Expected fixture verdicts are withheld
from the judge and never used to manufacture its judgment.

Every accepted-input trial writes a unique JSONL record containing the full case,
`agent_evaluation`, contextual verdict, waveform verdict, actual WAV/analyzer
paths and hashes, missing proof, and playback status. Invalid inputs return typed
validation errors retained by agentic-evals. The current output path is replaced
per trial; immutable trial JSONL remains under `outputs/contextual/<uuid>/`.
Playback is serial under a workstation lock. Rendered speech is Embry's response,
not the user's utterance. Exact pause checks inspect zero PCM samples at the
planned chunk boundaries as well as retaining the analyzer's detected pauses.

`contextual_appropriateness`, `technical_audio`, `audio_realization`, and
`perceived_delivery` are separate. An acoustic proxy or valid requested label
cannot establish perceived delivery; it remains `NOT_ESTABLISHED`. Missing
judgment or waveform also remains `NOT_ESTABLISHED`. Exit 2 means missing proof,
exit 1 means rejection/technical failure, and exit 0 is reserved for full PASS.
The fixture deliberately expects missing perceptual proof rather than declaring
the skill ready. Analyzer quality flags are retained, not relaxed to force green.
Native tags use Turbo with intensity as a *contextual target*, not an applied
numeric knob; numeric-intensity cases contain no native tags. Both contrast and
flat/overblown/wrong-context controls are retained. The real caller-context CLI
canary has no agent judgment and therefore cannot establish appropriateness.

## Terminal-first human review: one question at a time

```bash
# Entire automated batch/recommendations already exist; this never rerenders them.
./run.sh review celebration
# After that actual judgment is submitted, review the next scenario separately:
./run.sh review quiet-achievement
../agentic-evals/run.sh run fixtures/terminal_review.json --timeout-seconds 180 \
  --output /mnt/storage12tb/skills/chatterbox-speak/outputs/terminal-review-evals.json
```

`review` composes the existing `interview` Question/Session/InterviewApp and pane
registry. It requires an actual terminal and shows exactly one scenario question:
context, relevant turns, expected-target evidence/gaps, provisional recommendation,
numbered candidates, identity and required rationale. No browser or HTTP service
is required. The React work is parked, not an acceptance requirement.

- `1`–`5`: select candidate; Up/Down then Enter reaches later candidates, Reject
  all and Defer. Selection does not advance or submit.
- `Ctrl+P`: replay the current numbered candidate; `Ctrl+O`: play context.
  Existing WAVs use `pw-play` under the existing workstation playback lock.
  Replays stay on this question; wait for playback before submitting.
- `Ctrl+N`: reviewer identity; `Ctrl+R`: rationale. Both are required. Explain
  intended outcome, heard result, mismatch and proposed adjustment.
- `Ctrl+S` or the existing Submit pane: explicitly submit. Escape cancels without
  saving. The command returns after one scenario; it does not advance automatically.

Terminals shorter than 15 rows use compact mode: redundant title/header/tabs/footer
are hidden, while the question stays scrollable above a one-line shortcut hint.
At 7 rows × 113 columns, numbered selection scrolls that candidate into view;
`Ctrl+N` and `Ctrl+R` bring their input fields into view without submitting.

Human events append under `outputs/human-reviews/<request-id>.jsonl`, bind the
scenario, recommendation, packet and WAV hashes, and are independently reopened
before success is reported. Amendments link the latest event without overwriting
it. Repeated identical request IDs are idempotent; changed payloads are rejected.
The event's `selection` is the existing typed comparison preference for actual
candidate choices; Reject all/Defer have no candidate preference. Test simulations
are isolated under `outputs/review-test-only/`, contain `selection: null`, and
never enter actual human history or Memory. An actual non-null `selection` may
be extracted and passed to the existing `compare-memory store --selection` only
when explicitly authorized; there is no automatic preference/threshold mutation.

### Expected response precedes new rendering

New `compare render` calls require `expected_response` inside the existing input
JSONL, declared from context before candidate tuning. It contains `context_sha256`
(over context, prior turns and current user turn), `response_text`,
`response_meaning`, `emotional_intent`, `delivery_plan`, `rationale`, exact
`context_evidence` turn quotes, `render_plan`, and `pause_tolerance_frames: 0`.
`comparison_target.ExpectedResponse` is the strict boundary. Use the existing
`best-practices-chatterbox/run.sh plan-silence --text ... --tone ...` result for
`render_plan`; native tags/placement and spaced ` ... ` stay in the declared
render text, exact delays are compiled into `render_chunks.pause_after_ms`.
The input/source hash is frozen before narration or candidate rendering. Missing
targets, stale context, stale compiled pauses and tag/intensity incompatibilities
fail before any audio work. No separate target artifact is required.

Historical packets retain their original authored wording/delivery and evaluation
scope. Their precise missing expected-target facts are shown as **legacy partial
target evidence**, not filled from the later winner or retroactively hash-bound.
No historical WAV is rerendered to migrate this contract.

Measured PCM pause mismatch is **audio-realization FAIL**, with structured
Pydantic error details and evidence path. Native event routing/applied-tag echoes
are not audible-event proof: unobserved native events remain **NOT_ESTABLISHED**
and cannot be an audio-realization eligible winner. For plans with no native
events, realization PASS covers exact pauses only, not perceived emotional tone.
No new acoustic event classifier or thresholds are introduced.

## Labeled reply comparison and human preferences

`compare` adds a finite review workflow, not a UI application. The retained
`fixtures/reply_variants.jsonl` extends all six synthetic contextual cases with
10 authored reply-delivery plans each. Default **five** evenly cover the supplied
expressive-to-restrained range; `--variants` accepts **5–10**. Candidate IDs are
packet-scoped. Grief varies quiet presence, not indiscriminate high arousal.
The original single-candidate negative controls and audio-quality evidence remain.
`tuned_reply_variants.jsonl` supplies five wording-and-delivery alternatives for
the subsequent five batch rows, including context-appropriate alternatives to
wrong-context celebration. Its original scenario remains the baseline; each
candidate's optional `response_text` is its actual Embry reply. These are authored
calibration candidates, not accepted production defaults. The current live batch
is six rows (three underlying context families), not the old 50-scenario expansion.

```bash
./run.sh compare render fixtures/reply_variants.jsonl celebration \
  /mnt/storage12tb/skills/chatterbox-speak/outputs/comparison.jsonl
./run.sh compare prompt /absolute/comparison.jsonl /absolute/recommendation-prompt.txt
# Submit that prompt through Ask tau-dag --handler webgpt; run Ask's browser prompt preflight first.
./run.sh compare recommend /absolute/comparison.jsonl /absolute/ask/node-receipt.json \
  /absolute/recommendation.jsonl
./run.sh compare replay /absolute/recommendation.jsonl /absolute/replay-report.json
# ONLY after an actual human reply:
./run.sh compare select /absolute/recommendation.jsonl --candidate C03 \
  --reason 'Actual human explanation' --evaluator-identity 'Actual human identity' \
  --human-reply 'Verbatim actual human reply'
../agentic-evals/run.sh run fixtures/reply_variants.json --timeout-seconds 480 \
  --output /mnt/storage12tb/skills/chatterbox-speak/outputs/variant-evals.json
```

Embry first narrates context and relevant dialogue separately, then announces each
candidate ID and label before playing its **Embry reply**, never the user turn.
One existing workstation lock spans the whole sequence. Every WAV uses production
`speak --planned-pauses --play` and the owning analyzer; labels and narration are
not scored as candidate replies. Native tags never receive explicit intensity.
Numeric-intensity variants have no native vocal tags; pause directives compile out.

The Ask recommendation is retained **before** human selection, quotes actual turn
IDs, assesses every candidate's wording and delivery, and cites exact hash-bound
waveform measurements. An eligible winner requires both contextual PASS and
technical PASS. If no candidate qualifies, `eligible_winner` is null and the
agent's named relative-best choice is only a calibration candidate, explicitly
NO ACCEPTABLE WINNER. Do not substitute the technically cleanest waveform for
contextual fit. Finish every row in the declared batch and retained trial suite
before presenting the batch for human selection.
It is not chosen by maximizing an acoustic score. It cannot certify perceived
emotion. The generated Markdown packet lists context, WAV paths, clear IDs,
technical failures, and the agent's contextual recommendation. Playback returncode
zero is device-delivery evidence, not proof the human heard it. Full voice-quality
readiness and comparison-workflow checks remain separate.

JSONL preserves context provenance, plans, WAV/analysis/Ask hashes and separate
contextual, technical, and perceived verdicts. Existing packet/recommendation files
cannot be overwritten. `replay` reopens actual evidence and rejects stale bytes;
it explicitly reports artifact-backed replay, not a fresh WebGPT response. A
selection is a separate unique JSONL record with reason, caller-attested evaluator
identity, verbatim human reply, concurrence and immutable recommendation link.
No selection is synthesized before the human responds. This CLI attests supplied
human input; it is not identity authentication or an independent listening study.

Each actual preference carries a `PROPOSED_NOT_APPLIED` learning handoff targeting
`analyze-chatterbox-emotions` and `best-practices-chatterbox`. It does **not** edit
shared thresholds or persona Memory. Scoped engineering lessons may be retained
through the documented Memory owning API, separate from persona/user memories:

```bash
./run.sh compare-memory store /absolute/recommendation.jsonl /absolute/store-receipt.json
./run.sh compare-memory recall 'quiet companionship after loss' /absolute/lessons.json
./run.sh compare prompt /absolute/next-packet.jsonl /absolute/next-prompt.txt --lessons /absolute/lessons.json
./run.sh compare recommend /absolute/next-packet.jsonl /absolute/ask/node-receipt.json \
  /absolute/next-recommendation.jsonl --lessons /absolute/lessons.json
# Only after actual human selection, optionally store that separate preference:
./run.sh compare-memory store /absolute/recommendation.jsonl /absolute/human-store.json \
  --selection /absolute/human-preference.jsonl
```

Memory lessons use stable hash identities and scoped tags, with context/scenario
hashes, evidence references, rationale and status `provisional_agent_recommendation`.
Only an actual retained human choice can produce `human_confirmed_preference`.
The CLI uses Memory `/upsert` to preserve full metadata in its observed live
`lessons_v2` collection; it verifies full metadata with `/list` and independently
verifies the exact key and clean solution through `/recall`. Canonical Memory
text never contains renderer markup. Before later recommendations, recall relevant
lessons and record the exact keys the evaluator says influenced its reasoning.
Lessons remain provisional guidance, not ground truth or altered frozen criteria.
Calibration requires several human choices,
context-stratified review, and held-out checks; one preference cannot establish a
universal tone/intensity rule. Synthetic bank cases are never real user memories.

## Boundaries

- Speaks only caller-approved text; no answer generation, memory routing, or
  wake word (use `embry-voice-control` for that).
- Fails closed when the service is down, `ok`/`live` are false, or the WAV is
  missing/unreadable; errors carry the service's Pydantic-style detail.
- Waveform quality judgment stays with `/analyze-chatterbox-emotions`.
