# persona-dream roundtable 5, round 1 — the cluster ceiling, and how to run the study anyway

Same three-seat collaborative panel (ChatGPT / Claude / Kimi). Identical bundle
to every seat. This is a working session, not a scoring contest: your prior
architecture (GOAL_V5: answer-invariance gate, timing realization channel,
ToM oracle, cross-turn D/M/F/S listener study with D>M primary) is built and
partly executed. One new hard constraint has appeared and needs the panel.

## What changed since roundtable 4 (all VERIFIED this session)

1. Chatterbox fixed all six tickets we filed (#1–#6), verified live from our
   side: native chunk pauses now actuate (700ms request → 1.0s measured
   silence, no max_chars hack), the render response carries applied-controls
   (requested vs normalized per chunk), unknown tones now surface
   requested-vs-normalized, a repeat_group_id exists for variance control.
   GOAL_V4 checker re-driven against the patched server: PASS.
2. Gate 0 (answer-invariance / semantic-equivalence): built, 12/12 including
   all 8 adversarial attacks (negation flip, number change, entity swap,
   intensifier, dropped clause, etc.). The operator rule "color the tone,
   never change a right answer" is now a mechanical check.
3. Gate 1 (a voice channel that provably moves the audio): the timing channel
   is QUALIFIED. Dream boundary tag → composer → 700ms pause → measured 0.94s
   median silence vs 0.19s flat, 5/5 separated. Presets and inline text tags
   were both killed with root causes (presets sub-variance; `[firm]` is spoken
   aloud, not interpreted).
4. Gate 2 (do the dream's emotions match the memories?): pilot ran — 3 blinded
   seats annotated 5 packets; D profiles 5/5 supported on valence+tag; the
   blinded panel independently re-caught the one known pre-fix counterpart
   artifact (Brandon-memories → Kai-ToM). Oracle sensitivity validated.

## The new hard constraint (the reason for this round)

We ran a batch to grow the oracle from 5 packets toward the charter's 20.
Result, VERIFIED from the run log and receipts:
- 7 new dream cycles succeeded (12 passing cycles total now).
- Then cycles 9–15 ALL failed instantly with `BLOCKED_CYCLE_NO_UNUSED_CLUSTERS`.

Root cause (read from `autonomous_dream_cycle.py:137`): the pipeline refuses to
dream about a memory cluster it has already used (the anti-repeat / loop-guard
design). Embry's current `persona_memory` yields a FINITE number of distinct
counterpart×episode clusters, and we have now consumed all of them. **20
packets is not reachable by running more cycles — 12 is the ceiling with the
current source memories.**

Current 12-packet tag distribution (dominant tag): warmth 5, boundary 2,
hesitance 2, reflection 2, yearning 1. (Skewed to warmth; boundary/hesitance
thin; no negative-valence-heavy clusters.)

## Fresh external evidence (Brave, 2026-07-23, identical for all seats)

- MOS/listener-test practice (HuggingFace audio course; Zilliz; FutureBee):
  subjective TTS eval standardly uses MOS on 1–5 scales with multiple
  listeners per item; no single fixed N — power depends on effect size and
  per-item listener count, argues for a variance pilot before fixing N.
- MemEmo (arxiv 2602.23944): a 2026 framework specifically for *evaluating
  emotion in agent memory systems* — directly adjacent; emotion efficacy in
  memory systems is "inconclusive" in current work, i.e. the accuracy
  question we're gating on is an open research problem, not a solved one.
- Dynamic Affective Memory Management (arxiv 2510.27418): Bayesian
  entropy-minimizing affect-memory updates — a comparator for our
  memory→affect derivation.
- "Artificial Emotion" survey (arxiv 2508.10286): argues extrinsic
  per-utterance conditioning "traps models within human linguistic
  categories" — a point in favor of our dispositional, experience-derived
  bet, but also a caution that our tag vocabulary is such a category set.

## Questions for this round (answer all; be concrete)

Q1 — THE CEILING. Given 12 distinct clusters is the real maximum from current
memory, choose and justify ONE primary path:
 (a) run the study at n=12 packets, accept lower power, report it honestly;
 (b) expand Embry's source memories (write/import more episodes) to unlock
     more clusters before the study — at the cost of time and the risk of
     lower-quality synthetic memories diluting the corpus;
 (c) relax the anti-repeat rule to allow a cluster to be re-dreamed from a
     different angle/age-band (needs a GOAL_V3 amendment; risks the D-vs-M
     contrast if the "same" cluster appears in both arms);
 (d) something else.
Rank, and name what you'd need to see to prefer a different option.

Q2 — POWER AT n=12. If we run at 12: how many packets minimally support the
Gate 2 accuracy claim (charter said ≥15/20; what's the honest revised bar at
12)? And for the DOWNSTREAM listener study, does 12 conversation contexts ×
4 arms × K listeners have any chance of detecting D>M, or is the cluster
ceiling actually a listener-study blocker too? Give a rough power intuition
and the cheapest way to find out (variance pilot design).

Q3 — THE TAG SKEW. warmth 5 / boundary 2 / hesitance 2 / reflection 2 /
yearning 1, no strong negative-valence clusters. Does this skew threaten the
study (e.g. can't test whether a "guarded/hostile" disposition is audible if
no such dream exists)? Is a balanced subset of fewer packets better than all
12 skewed? What's the right selection rule?

Q4 — IS THE DREAM STEP EARNING ITS COST? Blunt version for the operator: we
just spent an hour of compute and hit a wall at 12. The dream pipeline is
expensive (image generation, ArcFace gating, VLM, per-cycle ~14 min) and
finite in yield. The MemEmo/affective-memory literature suggests the
memory→affect question is unsolved generally. Steelman BOTH: (i) the dream
step is worth continuing to the listener study; (ii) we should short-circuit
to the D-vs-M test on the 12 we have and let the result decide, rather than
invest in more cycles/memories first.

End with: POSITION SUMMARY (≤5 bullets), a RECOMMENDED NEXT ACTION (one
concrete command/experiment), and DISAGREEMENTS with anything in this bundle.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260723T230348Z:99463636>>>

Do not print anything after that marker.
