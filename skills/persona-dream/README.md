# Persona Dream

![Persona Dream — the research loop: the day and prior conversation enter memory, memory yields a tension, the tension yields a dream, and three things return to memory — what she concluded, the imagery and voice the dream produced, and what a human said back, each as a typed record.](assets/readme/research-loop.webp)

Persona Dream gives a persistent multimodal voice persona — a long-lived agent
with durable memory, a stable character, and access to text, images, audio, and
video — a controlled way to turn experience into a synthetic dream and examine
what comes back.

> **Does letting an AI persona dream about what has happened to it actually help
> — more than plainly remembering or reflecting — and is it still recognizably
> itself afterwards?**
>
> "No" is a real answer, and finding it is success.

This is not a movie generator. The dream is an **inspectable intermediate
representation** whose every conclusion stays linked to the supporting memories
and media; a dream may influence later reasoning, but it may never silently
become literal history or rewrite identity.

## Start here

I use this README as the durable research map, not as a status log. Choose the
authoritative entry point for the question you have:

| You need | Go to |
|---|---|
| Run the smallest local workflow | [Quick Start](#quick-start) |
| Inspect the executable runtime contract | [`SKILL.md`](SKILL.md) |
| Check current machine state, blockers, and next step | [`CURRENT_STATUS.json`](CURRENT_STATUS.json) |
| Check what is and is not proven | [Current Proof Boundary](docs/EVIDENCE.md#current-proof-boundary) and [What this project does not claim](docs/EVIDENCE.md#what-this-project-does-not-claim) |
| Read the immutable goal and gate sequence | [`GOAL.md`](GOAL.md) |
| Resume operational work | [`local/HANDOFF.md`](local/HANDOFF.md) |
| Review forensic chronology or superseded findings | [`PROJECT_KNOWLEDGE.md`](PROJECT_KNOWLEDGE.md) |
| Inspect transfer decisions | [`TRANSFER_LEDGER.md`](TRANSFER_LEDGER.md) |
| Inspect per-run evidence | revision-scoped receipts under `reports/` |

## Interface walkthrough

Each phase is a surface you can look at. These are committed screenshots of the
real thing, in pipeline order.

**Phase 01 — Idea and memory residue.** The dream starts from what the persona
already remembers; the board shows which memories were recalled and how they
were linked.

![Phase 01 Idea and memory residue board](assets/readme/phase01-idea-memory-residue.webp)

![Embry portrait D3 Theory-of-Mind trace graph](assets/readme/phase01-embry-portrait-d3-graph.webp)

**Phases 02-03 — Story and crew.** The story contract and the personas
selected to carry it.

![Phase 02 Story contract surface](assets/readme/phase02-story-content-pane.webp)

![Phase 03 Crew selection surface](assets/readme/phase03-crew-content-pane.webp)

**Phases 04-05 — Contact sheets and voices.** Candidate imagery and the voice
each persona is rendered with.

![Phase 04 Contact Sheets surface](assets/readme/phase04-contact-sheets-content-pane.webp)

![Phase 05 Voices surface](assets/readme/phase05-voices-content-pane.webp)

**Phases 06-08 — Script, storyboard, media lock.** Where the dream becomes a
sequence, and where frames are frozen against further edits.

![Phase 06 Script contract surface](assets/readme/phase06-script-content-pane.webp)

![Phase 07 Storyboard surface](assets/readme/phase07-storyboard-content-pane.webp)

![Phase 08 Media Lock accepted storyboard frames](assets/readme/phase08-media-lock.webp)

**Phases 09-10 — Provider dry-run and contract.** The scorecard and the
fail-closed provider state, which is what a blocked run actually looks like.

![Phase 09 Video Provider dry-run scorecard](assets/readme/phase09-video-provider-scorecard-20260710.webp)

![Phase 10 Provider Contract current fail-closed state](assets/readme/phase10-provider-contract-current.webp)

The control-by-control detail is in
[`docs/interface-walkthrough.md`](docs/interface-walkthrough.md).

## Quick Start

| What you want | Command |
|---|---|
| Explore a persona's memory residue | `./run.sh generate --persona <name>` |
| Build a fixture-backed dream packet | `./run.sh generate --persona <name> --fixture <file>` |
| Bias recall toward a topic | `./run.sh generate --persona <name> --about "<topic>"` |
| Create bounded video-planning material | `./run.sh generate --mode video_plan --persona <name>` |
| Write an explicitly approved reflection to Memory | `./run.sh generate --persona <name> --write-memory` |

These commands exercise the current runtime. They do not perform the unproven
live-provider, Watch, graph-persistence, or behavior-evaluation stages.

### The journal workflow

The end-to-end loop, from the day's events to a discussion carried back into memory:

```bash
RUN_DIR=/tmp/persona-dream-journal
DAY=$(date -u +%F)

# What happened today, in her words, written into memory
./run.sh ingest-day --date "$DAY" --from-commits \
    --project-state "where the work actually stands" \
    --affect "how the human seemed today"

# Dream on it, blended with who she already is
./run.sh generate          --persona embry --day "$DAY" --output-dir "$RUN_DIR"
./run.sh speak-journal     --run-dir "$RUN_DIR"
./run.sh render-journal-ux --run-dir "$RUN_DIR" --out "$RUN_DIR/index.html"

# Keep what the dream concluded, and the media it produced
./run.sh generate --persona embry --day "$DAY" --write-memory --output-dir "$RUN_DIR"
./run.sh store-dream-artifacts --run-dir "$RUN_DIR" --day "$DAY"

# Talk to her about it; the turn is durable
./run.sh append-conversation --run-dir "$RUN_DIR" \
    --role human --text "why did that memory surface?"

# Carry what was said back into memory, so the next dream can draw on it
./run.sh carry-conversation --run-dir "$RUN_DIR" --date "$DAY"
```

What each one actually gets you:

- `ingest-day` compresses the day into at most 8 first-person events across
  code, project-state and affect, writes them to memory, and gates on reading
  them back.
- `generate` draws by quota — a reserved share for today, the rest for identity
  — then writes the annotated `journal.md` and the tag-stripped
  `journal_spoken.txt`, bound to each other by hash.
- `speak-journal` produces a live `journal.wav` in the run directory, bound by
  sha256 to that exact spoken text, with an ASR transcript.
- `render-journal-ux` writes a self-contained local page, verified in Chrome.
- `append-conversation` appends a turn under an exclusive lock. An Embry turn is
  refused unless it carries a requested tone and rendered audio.
- `--write-memory` keeps what the dream concluded, as a memory marked dreamt.
- `store-dream-artifacts` registers the imagery, audio and video by modality,
  each bound to the hash of the bytes it describes, linked back to the dream
  that produced it so the multimodal graph can be walked.
- `carry-conversation` upserts the discussion into memory as *attributed
  speech*, so a later dream can draw on it. This closes the loop.

Memory is **append-only** by design: destructive AQL is refused and there is no
delete route, because a memory a system can quietly rewrite is not a memory. A
record that goes bad is therefore *tombstoned*, not removed —
`./run.sh deprecate-memory` rewrites it with `deprecated: true`, a reason, and
what supersedes it, preserving the original text verbatim. Readers skip
deprecated records; the `/memory` owner can sweep them later. Nothing this
project writes can make its own history disappear.

Run `ingest-day` on two different days and the journals differ — that is the
point, and it is the thing that did not work until 2026-08-04, when five
consecutive dreams were producing byte-identical entries.

See [`docs/EVIDENCE.md`](docs/EVIDENCE.md) for the claim-by-claim boundary and
what each receipt does *not* prove.

---

## Architecture: the bounded loop

```
accepted dream
  -> Watch observations          (what the persona saw, adjudicated)
  -> first-person journal        (grounded, explicitly synthetic)
  -> bounded arc delta           (what may change, and by how much)
  -> continuity ledger           (the authority object; atomic, epoch-checked)
  -> session mood before turn 1  (deterministic, bound before the user speaks)
  -> Chatterbox voice delivery   (the mood requested of the renderer;
                                  measured not audible)
  -> recognition check           (is it still recognizably Embry?)
```

Each arrow is a gate with its own receipt. The loop is only as strong as the
weakest joined leg, and joining every leg in one run is what P2 is for.

## Journal and discussion loop

The bounded loop above is agent-internal: it produces persona state, and its
audience is the next turn. There is a second path out of the same dream whose
audience is a person.

```
accepted memories
+ current-day events                    (ingested and blended by quota)
      |
      v
persona-specific contradiction / tension
      |
      v
synthetic dream and interpretation
      |
      +--> journal.md
      |      first-person entry
      |      tone/emotion annotations
      |      source-memory and graph footnotes
      |
      +--> journal_spoken.txt
             annotation-stripped, hash-equivalent
                   |
                   v
      psychological mood
      -> Chatterbox delivery-tone request
      -> live journal.wav in the run directory
                   |
                   v
      journal / discussion UX             (verified in a browser; read-only)
                   |
                   v
      append-only conversation.jsonl      (durable)
                   |
                   v
      carried back as typed records       (a later dream draws on them)
```

Every leg above has a passing receipt. What none of them establish is benefit:
the loop running is a mechanism result.

**Journal annotations are not renderer control tokens.** They stay in the
readable entry for inspection and are stripped before speech, because
Chatterbox's `/health` reports `inline_text_tag_behavior:
synthesized_as_literal_text` — an inline `[wistful]` reaching the renderer is
spoken aloud as the word "wistful". The delivery tone is supplied separately as
metadata.

Five distinctions this project keeps apart, because collapsing any two of them
is how an overclaim gets made:

```
persona psychological mood     (what she woke up feeling)
 != journal annotation         (how a passage is meant to read)
 != requested delivery tone    (what we asked the renderer for)
 != proven audible emotion     (measured absent)
 != human-perceived emotion    (never tested)
```

### Why the five-cycle pilot produced identical journals

The five-cycle pilot produced byte-identical journals (sha `f812641f9dbbc7e2`,
cycles 001-005). The obvious reading is that nothing about any given day was
ever written to memory, which is true. Two measured defects in the memory
service make it worse:

- **A stored document is not retrievable.** `/store` returns success, the row is
  really in ArangoDB, and `/recall` never returns it — not even when queried
  with the document's own text.
- **`/recall` did not filter by scope.** Asking for one scope returned documents
  from others, so the five recall "strata" were not strata; they were five
  semantic queries over one undifferentiated pool.

Both were upstream defects in the memory service, both were fixed on
2026-08-04, and both fixes were independently re-verified here rather than taken
on report.

So the pilot showed the pipeline runs repeatedly. It did not show
day-to-day experiential change, and adding day events alone would not have
produced any. Details and receipts: [`docs/EVIDENCE.md`](docs/EVIDENCE.md).

## What this is for

If you are evaluating this as research, the question it exists to answer is
narrow and falsifiable:

> **Does letting a persona dream about what happened to it produce anything a
> plain memory readout or a written reflection would not — and is it still
> recognizably itself afterwards?**

"No" is a real answer. The project is built so that a null or negative result
survives contact with the surfaces: claims are bound to receipts, receipts state
what they do *not* prove, and a gate fails closed when a claim outruns its
evidence. One finding is already negative and stayed that way — on the tested
backend the requested delivery envelope does not reach the waveform, measured
against the renderer's own noise floor, and the project stopped claiming
emotional delivery rather than retrying for a better draw.

### Why dreaming, and not just remembering

**This is the hypothesis, not a finding.** Durable memory preserves what
happened. The proposal is that a synthetic dream produces *bounded
interpretations* of it that affect later reasoning differently from a structured
reflection would — and that for any of it to compound, the interpretation has to
become memory rather than staying an output.

Running it daily creates a provenance-linked longitudinal record. Whether that
record produces useful adaptation, no change, or harmful drift is precisely what
#1196 exists to find out, and nothing here has established it.

So the load-bearing arrow is the one going *back*:

```
lived experience  ─┐
prior conclusions ─┴─► tension ─► dream ─► interpretation
                                          + imagery, voice
                                          + what a human said back
                                                    │
     all of it returns to memory ◄──┘
     as TYPED records:
       lived events         -> episodic memory
       dream interpretation -> synthetic, marked dreamt
       dream media          -> modality-bound synthetic artifact
       human commentary     -> attributed speech
```

Three things return, not one: what she concluded, the media the dream produced,
and the discussion a human had with her about it.

**This was broken until 2026-08-04, and the failure is instructive.** The
reflection write targeted a collection that rejects a dream interpretation with
`422 no extractable taxonomy` — and it failed *soft*, so every run reported
success while the single most important write errored. Five consecutive dreams
came out byte-identical, and the reason was not the dream logic: no dream could
build on another because no dream was ever kept. It is now written to
`persona_memory` and gated on reading it back.

### The voice is meant to follow the personality

The reason a delivery tone exists at all is that it is **derived, not set**. Each
dream surfaces a dominant tension — concealment, inadequacy, belonging, duty —
and that tension is mapped at runtime to a delivery tone the renderer accepts.
Nobody chooses "sound uncertain here". She sounds however that day's unresolved
thing came out.

The intended consequence is that as the persona accumulates, the voice moves
with her: a week of competence tensions and a week of isolation tensions should
not sound the same, without anyone tuning a knob between them.

**The channel is built end to end and its last hop is inert.** The mood is
derived, mapped, requested, survives normalization instead of collapsing to a
default, and is recorded on every spoken journal. What does not happen is any
change to the audio. Measured against the renderer's own same-parameter noise
floor, no requested tone moved a single acoustic metric, and the engine in use
lists the affect parameters (`exaggeration`, `cfg_weight`) among those it
ignores. There was never a path from the request to the waveform.

So this is a blocked capability with a named blocker, not an unexplored idea. It
needs a backend that exposes affect axes which measurably move the audio; until
one does, the mapping is kept because it is honest provenance for what was
*requested*, and every surface says the emotion is not audible.

**Where this is going, and what is not built yet.** Today the register comes from
a single dream's dominant tension — one night, one axis. That is the shallow
version. Dreams are memories, they carry links to the memories they interpreted,
and conversations attach to the journals they were about, so dreams stand in
relation to each other: a tension can recur, intensify, or be resolved and come
back. The intended behaviour is that those relationships colour the register — a
tension surfacing for the fifth time, or one that a human pressed hard on last
week, should not sound like one appearing for the first time.

None of that modulation exists yet. What exists is the substrate it needs: the
links are in the graph, dreamt records are distinguishable from lived ones, and
conversation turns are bound to the entry that provoked them. Recurrence and
intensity across related dreams are not computed, and nothing reads them. It is
named here as design intent so a reader can tell the difference between what the
architecture supports and what it currently does.

Three properties are worth a researcher's attention:

- **Consecutive days differ.** Five cycles once produced byte-identical
  journals. They now differ, and differ *because of the day* — one entry opens
  on the human being terse, another on impatience about stranded work.
- **Dreamt and lived are never confused.** For one day she carries 11 lived
  memories and 4 dreamt ones. Everything dreamt is marked synthetic *and*
  self-declaring in its own text — `In a dream I interpreted my recent
  experience: …`, `From a dream: the imagery I saw …` — so a retrieval path that
  drops the metadata still cannot promote an interpretation into something that
  happened. Dream imagery is not a photograph, and the data says so.
- **Commentary does not become autobiography.** A question a human asked comes
  back as `human said, about my journal entry: …` — attributed speech bound to
  the journal it was about, never as an event that happened to her. This is the
  boundary that makes the loop safe to close at all.

What is **not** shown is that any of this helps. That the loop closes is a
mechanism result, not a benefit result; the controlled ablations against direct
memory and structured reflection are the experiment, and they have not been run.

## Where it stands

Honest one-liner: **the mechanism runs a full cycle and the return arc closes.
What is unproven is whether any of it helps, and one component — audible
delivery tone — was measured and does not work.**

What runs today, with receipts behind it:

- a dream grounded in recalled memories, every conclusion linked to its source
- a first-person `journal.md` with tone annotations and provenance footnotes
- a hash-bound spoken form, and Embry reading it aloud into `journal.wav`
- a local journal and discussion page, verified in a browser
- the day's code, project-state and affect events written into memory and
  blended into that day's dream, so consecutive days differ
- a discussion carried back into memory as attributed speech, which a later
  dream draws on — the loop closes

What does not work yet, stated plainly:

- **The mood reaches the audio, and the renderer decides how it sounds.**
  Reporting the inert delivery envelope upstream produced four fixes in a day.
  Tone is now *calibrated*: `./run.sh` sends `emotion_realization=audible` and
  the renderer derives the affect from the tone name itself — `grief_safe`
  resolves to intensity 0.3 / valence −0.7, `firm_boundary` to 0.95 / −0.85,
  each reported in a per-render `affect_effect` receipt. All eight axes this
  skill maps produce eight distinct settings, verified live.

  This skill sets **no affect numbers at all**. It briefly did — a hand-picked
  intensity table, tuned by measuring acoustics — and that was the renderer's
  calibration work being done downstream, badly, by one consumer. It has been
  deleted rather than retuned. persona-dream says what the dream *felt like*;
  Chatterbox decides what that sounds like.

  Whether a *listener* perceives the intended feeling is untested — that is
  `chatterbox#7`, and it should now target the calibrated affect path.

- **Nothing shows that dreaming helps.** The loop closes, days differ, and
  provenance holds — but whether a dream beats a plain memory readout or a
  written reflection is the actual research question, and the controlled
  comparison has not been run.

The full claim-by-claim boundary, every receipt, and what each one does *not*
prove: [`docs/EVIDENCE.md`](docs/EVIDENCE.md).

If you are here for the methodology rather than the dreaming — how claims are
bound to receipts, how a superseded claim is caught, and how human commentary is
kept from becoming an agent's autobiography — that is
[`docs/CLAIM_PROVENANCE.md`](docs/CLAIM_PROVENANCE.md). It transfers
independently of whether dreaming works.

## What happens next, and what would falsify it

The obvious question is whether any of this helps. It is unanswered, and the
honest position is that it *cannot* be answered from what exists today —
accumulation only began working on 2026-08-04, so there is no history to study
yet. Nothing here has run long enough to have changed anyone.

That makes the first step unglamorous and unavoidable.

**1. Run the matched comparison now (#1195).** It does not wait for anything.
It runs against a frozen historical case with existing media and Watch
observations, makes no provider calls, and holds the source memories, task,
scoring rule and model budget fixed while varying only how the evidence is
processed: direct memory readout, structured reflection, a text-only dream, and
a dream whose rendered media were independently observed. Every condition can
win, tie, or lose.

**2. Accumulate daily.** A longitudinal claim needs a longitudinal record, and
today's is one day old. Running `ingest-day` → `generate --write-memory` →
`store-dream-artifacts` → `carry-conversation` daily produces the material the
adaptation study examines. This gates #1196, not #1195.

> **One thing is genuinely unsettled and we would welcome argument about it:**
> what should she be measurably *better at*? Whatever is chosen decides what a
> result means, and it is possible to design a task that guarantees the media
> condition wins or that it cannot. We have deliberately not picked one quietly.

**3. Make the journal and chat surface an interface, not a viewer.** The page is
built and verified in a browser: it renders the entry with tone chips, footnotes
that resolve to their source memories, the audio of her reading it, and the
conversation history. What it cannot do is take part. The chat pane composes a
JSONL line for you to copy, and appending a turn or carrying it back into memory
are CLI commands — so a human can *read* the loop in the page but has to leave it
to *close* the loop.

That gap matters more for research use than for engineering: a colleague
evaluating whether discussion changes later dreams should be able to have the
discussion where they are reading, not in a terminal. Making the page write
turns directly, and showing carried turns arriving back in the next dream, is
what turns the surface into an instrument.

The interaction model is not being invented here. It is adapted from the SPARTA
Explorer chat surface, which already solves the harder half of this problem: a
human and an agent discussing a conclusion while every claim stays traceable to
the evidence that supports it. Product overview:
[`grahama1970/sparta-public`](https://github.com/grahama1970/sparta-public).
The requirement it carries over is the one that matters here — a discussion
surface must never let commentary quietly become evidence, which is the same
boundary this project enforces when a turn re-enters memory as attributed
speech.

**4. Longitudinal adaptation (#1196).** Does the persona measurably change over
many dreams, and is she still recognizably herself? Two failure modes matter
equally: no change at all, which would mean dreaming adds nothing; and drift,
which would mean it adds the wrong thing. The bounded arc delta and recognition
check exist to catch the second.

### What each outcome would mean

| Outcome | Consequence |
|---|---|
| Dreaming beats memory and reflection | scope the claim to the tested case; replicate before generalizing |
| No detectable difference | a completed result — record it and stop claiming the mechanism helps |
| Difference only with rendered media | keep the media lane; it is expensive and would need to earn that |
| Persona drifts | the safety constraint failed; that is a finding about bounding, not about dreaming |
| Underpowered to tell | say so, and fix the design rather than reporting the null as evidence |

A null result retires the mechanism rather than embarrassing it. That is what
the transfer ledger's adopt / constrain / reject / retire column is for, and it
already contains one retirement and one negative that stuck.

### Known limits we are not hiding

- **N=1 and synthetic.** One persona. No population, so nothing here speaks to
  individual differences.
- **The tension axes are not instruments.** They are invented vocabulary matched
  lexically, not validated psychometrics, and should be treated as latent
  variables awaiting validation.
- **No human subjects.** No trust, delegation, or perception measurement. The
  one perceptual study was blocked as technically confounded and stayed blocked.
- **Tone does not reach the waveform on this backend.** Measured, not assumed,
  and the surfaces were corrected rather than the experiment re-run for a better
  draw. Reporting it upstream ([`chatterbox#20`](https://github.com/grahama1970/chatterbox/issues/20),
  since fixed) made `pace` genuinely audible and made the renderer declare which
  delivery fields are request-only — so the negative result produced a working
  channel, which is the point of publishing negatives.

If you want the methodology rather than the hypothesis — how claims are bound to
receipts and how a claim that outruns its evidence is refused — that is
[`docs/CLAIM_PROVENANCE.md`](docs/CLAIM_PROVENANCE.md), and it holds whatever
these experiments return.

## Embry and Kai: Example workflow, not a benefit result

The current fixture begins with a deceptively ordinary choice: Embry and Kai
fake a sick day from their summer jobs to surf Kahaluʻu Bay on Hawaiʻi's Big
Island. Heat softens the board wax. A lava reef narrows the safe choices. The
lineup adds social pressure, while Embry's history with Kai gives every warning
and hesitation relational weight.

One voice-test line captures the tension:

> "Kai, wait. If we paddle now, we're cutting across the lineup."

The pipeline can draw on character images, older text memories, surf audio,
video references, environmental evidence, and relationship history.

The test is not whether it can make an attractive surf clip. The test is
whether Embry can later watch the actual returned media, distinguish a renderer
failure from a meaningful pattern, form a bounded interpretation, and use that
experience in a future conversation without claiming the dream literally
happened.

Chatterbox receives and renders the requested delivery tone. That proves the
mood-to-renderer contract and the spoken-journal path; it is not expression.
The requested tone was measured against the renderer's own stochastic spread
and produced no acoustic effect. It does not decide the psychology or
rewrite Embry's durable identity.

---

## Research detail

The settled research goal and gate sequence live in [`GOAL.md`](GOAL.md).
Detailed hypotheses, protocols, and workstream descriptions live in
[`docs/research.md`](docs/research.md). For current checked state, use
[`CURRENT_STATUS.json`](CURRENT_STATUS.json).

## Pipeline detail

The numbered 01-16 stage contract, inputs, outputs, and operator notes live in
[`docs/pipeline.md`](docs/pipeline.md). Use [`SKILL.md`](SKILL.md) for the
executable runtime contract.

## Technical architecture

The detailed component and data-flow design lives in
[`docs/architecture.md`](docs/architecture.md). The bounded-loop section above
is the README-level architecture.

## Verification detail

Commands, expected outputs, artifact schemas, and acceptance procedures live in
[`docs/verification.md`](docs/verification.md). The current claim boundary
remains in [`docs/EVIDENCE.md`](docs/EVIDENCE.md), and per-run
evidence remains under `reports/`.

## What is borrowed, what is coined

The vocabulary here comes from several traditions, and a reader should not have
to guess which terms carry their established meaning and which are ours. No
claim below rests on borrowed authority.

**Borrowed and applied as specified.** Two methods are used in their standard
form and are load-bearing in the receipts:

- *Wilson score interval* for the reliability lower bound, chosen over a normal
  approximation because the counts are small and near the boundary.
- *ITU-R BS.1770 K-weighted loudness* for the audio measurements, so the tone
  work is calibrated against a published standard rather than an ad-hoc metric.

**Borrowed vocabulary, used loosely.** These name ideas from psychology and
cognitive science, but nothing here implements or tests the constructs as that
literature defines them:

- *Theory of Mind*, *false belief*, *counterfactual reasoning* — the PCTOM-R
  workstream borrows the framing of reasoning about another agent's mental
  state. It does not use a validated ToM instrument, and results here should not
  be read as evidence about Theory of Mind in the psychological sense.
- *Memory consolidation*, *day residue*, *dream lag* — the daily-events and
  recall design is inspired by the idea that recent experience is reprocessed
  and re-weighted over time. That inspiration is not a claim that this
  mechanism resembles biological consolidation.

**Coined here, and not validated.** These are ours, and a reviewer should treat
them as untested constructs rather than instruments:

- **PCTOM-R** (Prospective Counterfactual Theory of Mind) is a project name for
  a workstream, not a recognised construct.
- **The eight tension axes** — concealment/disclosure, competence/inadequacy,
  belonging/isolation, duty/desire — are invented vocabulary, detected by
  lexical matching against word lists. They are not validated psychometrics,
  carry no normative data, and should be treated as latent variables awaiting
  validation. Their labels are evocative on purpose and that is a hazard: a
  reader can mistake a word-list hit for a measured psychological state.

**No literature review has been done.** This project has not surveyed the
relevant work, and its design was not derived from specific papers. That is a
real gap for anyone assessing novelty or prior art, and it is stated here rather
than papered over with a reading list assembled after the fact.

## References

- [`SKILL.md`](SKILL.md) - current operational contract
- [`create-persona`](../create-persona/SKILL.md) - persona authority and identity-consistency validation
- [`memory`](../memory/SKILL.md) - Memory First, multimodal recall, ToM, and persistence contract
- [`watch`](../watch/SKILL.md) - evidence-first dream-media perception
- [`create-movie`](../create-movie/SKILL.md) - downstream polished media lane
- [Graph Memory Operator](https://github.com/grahama1970/graph-memory-operator) - graph, retrieval, and persistence implementation
- Nested creative helpers live under `skills/persona-dream/skills/`.

