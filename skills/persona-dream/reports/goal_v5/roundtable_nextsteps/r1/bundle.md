# persona-dream roundtable — next steps given the research goals (round 1)

Three-seat collaborative panel (ChatGPT / Claude / Kimi), identical bundle to
each. Not a scoring contest — collective insight on what to do next. Your prior
architecture is built and partly tested; below is the verified state, a fresh
research brief, and the decision.

## Purpose (operator-fixed, do not re-litigate)

persona-dream is Embry's AFFECT ENGINE, FOR AGENTS: experience → memory → dream
→ theory-of-mind → composed conversational tone/emotion in the chatterbox voice.
The consumer of the affect is an AGENT, not a human. The human cares only that
(a) the pipeline is reliable, (b) the dream is accurate given experience, (c) it
measurably nuances the voice. Safety rule: color the tone with the dream, never
change a right answer.

## Verified state (all committed at agent-skills@main; read-backs this session)

1. GOAL_V4: dreams color live voice through the real runtime, safety-gated;
   `check_goal_v4_boundary.py` re-drives live = PASS.
2. GOAL_V3 Amendment 2 — dreaming is VARIATION, not one-shot. The old
   NO_UNUSED_CLUSTERS ceiling (hit at 12 distinct clusters) is lifted: a used
   cluster is re-dreamable as a distinct variation, seeded from a
   valence-conflicted memory (202/312 carry both + and − emotion),
   graph-traversed within the counterpart (192 cross-memory edges), with valence
   emphasis + variation lineage recorded. Proven end-to-end: a re-dream of the
   Kai cluster (variation #3, negative emphasis) passed all gates. 13 dreams now.
3. Cross-persona dreams connected by THEORY OF MIND (one persona modeling how
   another experienced a shared event, grounded in each record's
   cross_persona_hooks) — designed, compiled as a tau creator/reviewer DAG,
   NOT executed (blocked on a shared ChatGPT tab held by a concurrent job;
   filed #980). This is the piece that reconciles cross-counterpart material
   with the isolation gate that once caught a CRITICAL leak.
4. M-arm (direct-memory affect) built for all 13 cycles, reusing the dream
   arm's exact mapping + weight formula. CAVEAT: deterministic crosswalk, NOT
   LLM-compute-matched — so the D-vs-M contrast is not yet fair.
5. AGENT-perception panel (the endpoint, judged by agents since the consumer is
   an agent): 2 blinded seats (kimi, claude). Dream-derived vs direct-memory
   dispositions DISTINGUISHABLE in 12/13 cycles (both judges agree); dream read
   as more experience-grounded than direct memory in 8/13 (judges agree
   per-cycle); both independently flagged the known pre-fix Brandon/Kai cycle as
   the lone indistinguishable one.

## Fresh research brief (Brave, 2026-07-24, identical for all seats)

- Agentic-memory evaluation is converging on LLM-as-a-judge as the more
  reliable protocol, with the caveat that prompt design matters and validity
  ≠ reliability (arxiv 2602.19320 "Anatomy of Agentic Memory"; 2603.07670
  "Memory for Autonomous LLM Agents"; 2605.08538 human-inspired memory
  architecture uses GPT-4o LLM-as-judge + deterministic consolidation/
  reconsolidation).
- LLM-as-judge reliability at scale (arxiv 2606.19544, 21 judges / ~541k
  judgments): agreement, consistency, and BIAS must be audited; position bias
  is real — swap content order. "Weak judges, strong panel": adding judges
  helps ONLY if they disagree on the right things; agreeing judges = one
  verdict bought thrice.
- ToM caution (arxiv 2603.28925): an LLM's self-/artifact-attributions of mind
  are dissociable from actual ToM capability — relevant to how much weight to
  put on an agent-judge's "disposition" reading.

## The decision (answer all four)

Q1 — READ THE PERCEPTION RESULT. Given 12/13 distinguishable (both agree) but
only 8/13 dream-more-grounded, and that the M-arm is a deterministic crosswalk
(not LLM-matched): what does this actually license us to claim right now, and
what is the single highest-value next experiment? Candidates: (a) build the
LLM-compute-matched M-arm and re-run the panel; (b) scale the panel to 3–5
seats with position-swap/bias audit per 2606.19544; (c) both, and in what
order.

Q2 — THE JUDGE PANEL. Our 2 judges agreed almost perfectly (12/13, and per-cycle
on grounding). Per "weak judges, strong panel," near-total agreement may mean we
"bought one verdict twice" rather than a robust panel. How do we tell signal
(the affect really is that legible) from redundancy (correlated judges)? Concrete
design: how many seats, what diversity, what bias controls (position swap,
blinded A/B already done), and what agreement statistic (Krippendorff/Cohen)
would make the result credible?

Q3 — THE M-ARM FAIRNESS GAP. The deterministic crosswalk M-arm is the weakest
link in the D-vs-M claim. What EXACTLY makes an M-arm "compute-matched" to the
dream's LLM-derived ToM without accidentally making it a covert mini-dream
(which would bias D≈M)? Specify the derivation contract.

Q4 — GOAL FRAMING. Is the agent-perception endpoint (distinguishable +
experience-grounded, judged by agent consumers) the RIGHT terminal proof for
"dreams measurably nuance the agent's voice", or is there a more direct
agent-utility test (e.g. does dream-conditioned affect change a downstream
agent's behavior/choice in a task, not just its rated disposition)? If the
latter, sketch the cheapest such task.

End with: POSITION SUMMARY (≤5 bullets), RECOMMENDED NEXT ACTION (one concrete
command/experiment), and DISAGREEMENTS with anything above.
