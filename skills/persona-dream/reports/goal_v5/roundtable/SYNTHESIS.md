# Roundtable 5 synthesis (2026-07-23) — the cluster ceiling

Seats: ChatGPT (837360856) and Kimi (837360820) responded, on-topic, full
(11.8KB / 9.7KB). Claude seat DROPPED: its tab (837360812) was commandeered by
an unrelated live "transport verification" conversation and no tab remained on
the bound persona-dream chat; two recovery attempts (submit timeout, extract)
failed. Round ran with 2 of 3 seats. Round 2 (with claude refolded if the tab
frees) offered but not auto-run — the two live seats converged with near-zero
dissent, so the decision is ready for the operator.

## The constraint that triggered this round

The dream batch produced 7 new cycles (12 passing total) then hit
`BLOCKED_CYCLE_NO_UNUSED_CLUSTERS` on cycles 9–15: the pipeline refuses to
re-dream a used memory cluster (anti-repeat, autonomous_dream_cycle.py:137) and
Embry's current memory is exhausted at 12 distinct clusters. 20 packets is not
reachable by running more cycles.

## Unanimous (both live seats)

1. **Run at n=12. Do NOT expand memory or relax anti-repeat first.** Both:
   expanding risks diluting the "experience-derived" claim with synthetic
   episodes; relaxing anti-repeat poisons the D-vs-M contrast (same cluster in
   both arms → listeners detect content similarity, not affect). Treat 12 as
   the finite population/census of Embry's current corpus and scope the
   conclusion to exactly that.
2. **The known pre-fix Brandon→Kai artifact is a negative control, not a D
   treatment.** → 11 valid post-fix D blocks + 1 sealed negative = 12 packets.
3. **Gate 2 bar at 12:** ChatGPT: ≥9/11 post-fix supported + 0 counterpart
   errors + the negative must be re-caught. Kimi: ≥10/12. Both: report the
   exact binomial confidence interval, never a bare proportion. FAIL at ≤8/12.
4. **n=12 detects only a LARGE effect.** The unit of generalization is the
   CONTEXT/cluster (~12), not the listener — more listeners cut measurement
   error but cannot manufacture independent dreams. ~80% power only for
   Cohen's d ≈ 0.77–0.89. So a full confirmatory study is NOT powered; a
   kill-test / variance pilot IS the right move.
5. **Short-circuit to D-vs-M now; let the effect size decide.** Do not spend
   another hour of cycles or risk corpus expansion before measuring whether
   dreaming even beats plain memory. The dream step is "justified only
   retroactively by a detectable D>M effect" (Kimi).
6. **Tag skew (warmth 5 / boundary 2 / hesitance 2 / reflection 2 /
   yearning 1, no negative-valence):** use ALL 12 as the primary analysis,
   stratify by tag, and scope the claim to positive-valence dispositions.
   A balanced subset (→8 packets) is worse — collapses power. Cannot claim
   the method produces guarded/hostile/grief dispositions; that is a declared
   missing stratum, not fixable by balancing.

## Converged next action (both seats' recommended command)

1. **GATE2-CENSUS-12**: run the full oracle on all 12 packets (11 post-fix +
   1 sealed negative), 3 blinded annotators, majority valence + dominant-tag
   per packet, exact binomial CI, PASS/PARTIAL/FAIL, freeze the eligible
   manifest. (Packets + M-arm profiles already built:
   reports/goal_v5/tom_oracle/, 12 packets.)
2. **Build compute-matched M profiles** for the frozen manifest (the current
   lexicon M-arm is v0 / not compute-matched — flagged by both as a
   correctness precondition for the D-vs-M test).
3. **Listener variance pilot** (needs humans): 5 listeners × 12 contexts ×
   {D,M,F,S}, MOS "emotional authenticity" + forced-choice tag, mixed-effects
   `score ~ arm + (1|listener) + (1|context)`, extract context/listener/
   residual variance → power curve. Pre-sealed futility rule: upper 80%
   cluster-bootstrap bound for D-over-M below 0.58 → FUTILITY_DREAM_NOT_OVER_MEMORY.

## Dissent / caution surfaced to the operator

- ChatGPT vs Kimi Gate-2 bar: 9/11-post-fix vs 10/12 — minor, both stricter
  than the naive 9/12; adopt the stricter framing (≥10/12 AND 0 counterpart
  errors AND negative re-caught).
- **Kimi's adversarial flag (important):** given the operator's concerns about
  hallucinated progress elsewhere today, apply the SAME scrutiny to the dream
  pipeline's self-reported receipts — the oracle passes were AI-seat-scored.
  Kimi asks the operator to independently re-run Gate 0 and Gate 2 on a random
  3-packet sample. This is a check on ME, and it is correct.
- Neither seat endorses the 20-packet target as necessary; both prefer 12
  well-gated packets over 20 loosely-gated ones.
