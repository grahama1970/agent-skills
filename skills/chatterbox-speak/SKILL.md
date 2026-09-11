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
