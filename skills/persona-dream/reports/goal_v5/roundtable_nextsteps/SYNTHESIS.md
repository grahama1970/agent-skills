# Next-steps roundtable synthesis (2026-07-24) — 2 seats (claude, kimi), converged

webgpt seat was tab-contended (#980); claude + kimi responded fully. Brave
research brief shared to both. They converged tightly and both corrected the
project agent's framing of the perception result.

## They downgraded my perception claim (adopt this)

- 12/13 "distinguishable" is against a DETERMINISTIC crosswalk M-arm — near a
  floor result (an LLM-composed disposition of course differs from a template).
  Its real value was the validity check: both judges independently flagged the
  known pre-fix Brandon/Kai cycle as the lone indistinguishable one.
- 8/13 "dream more grounded" is CONFOUNDED: it could be dream value, or merely
  LLM-fluency vs template-flatness. NOT licensed: "dreams beat memory."
- Licensed now: dreams produce distinguishable, legible affect dispositions
  (a reliability claim), NOT that they are more grounded (a validity claim).
- The claude seat is now CONTAMINATED (it saw the sealed key in this bundle).
  Any panel re-run must use FRESH sessions.

## Converged plan (both seats, in order)

1. **Build the LLM-compute-matched M-arm FIRST** (fix the confound before
   scaling any measurement). Contract (merged):
   - Same LLM, same token budget, same output schema as the dream arm.
   - Input: the cycle's raw memories ONLY — no dream artifacts, no
     valence-conflict seed, no graph traversal, no cross-memory edges, no
     cross_persona_hooks.
   - Operation: single-memory EXTRACTIVE affect reading. Forbidden:
     cross-memory synthesis, ToM/perspective-taking, narrative, counterfactual
     or imagined content (the anti-mini-dream clause).
   - Valence→tone via a frozen lookup, not LLM-chosen.
   - ENFORCED, not just instructed: novel-content audit (NER/string-grounding)
     — any M-output containing entities/events absent from the source is
     regenerated; log the regeneration rate (high rate = leaking boundary).
   - Sharpened claim it enables: "recombinative dreaming adds affect nuance
     beyond extractive LLM affect-reading of the same memories at matched
     compute."
2. **Re-run the 2-seat panel with FRESH sessions + embedded position-swap**
   (A/B randomized per packet per 2606.19544). One experiment = fair contrast +
   bias audit. Targets: distinguishable ≥10/13, grounding ≥10/13, swap
   consistency ≥90%.
3. **Scale to 4–5 diverse seats ONLY if step 2 holds.** Model-family diversity
   (Claude/GPT/Kimi/Gemini/open-weight), position swap + content-label swap +
   dummy identical-A/B catch trials + free-description (rubric-free) seat;
   Krippendorff's α (≥0.67 tentative, ≥0.80 solid) on distinguishability and
   grounding separately; report PER-ITEM ENTROPY — uniform near-1.0 agreement
   across easy AND hard/catch items is the redundancy signature ("one verdict
   bought five times").

## The terminal proof should change (both seats)

Agent-perception (rated disposition) is a NECESSARY INTERMEDIATE, not the
terminal proof. Per the ToM-dissociation caution (2603.28925), a judge's
disposition label is an attribution, dissociable from any functional effect.
Terminal proof = a BEHAVIORAL utility test: does dream-conditioned affect change
a CONSUMER agent's behavior/choice under content-identical, tone-varied
deliveries (safety rule preserved).
- Cheapest (kimi): "affect-consistent reply selection" — one inference per
  scenario; does the consumer pick the disposition-consistent reply above chance.
- Stronger (claude): a proceed/verify/escalate decision on an ambiguous
  operational question, D-tone vs M-tone, identical propositions; measure
  whether tone shifts action choice / confidence. Also stress-tests the
  content-invariance safety rule for free.

## Surviving dissent (for the human)

1. Kimi: 5 seats is not automatically right — if the fair 2-seat+swap re-run
   shows high consistency but low grounding, the problem is the DREAM PIPELINE's
   grounding mechanism, not panel size; adding judges won't fix it. Scale-vs-
   debug is a human call at that fork.
2. Cheapest behavioral probe: kimi = affect-consistent-reply (single inference);
   claude = the decision task. kimi says do the single-inference one first.
3. #980 sequencing: the cross-persona-ToM dreams are the most novel piece
   scientifically, but both seats say keep it PARKED until D-vs-M is fair —
   otherwise every downstream claim inherits the confound.
