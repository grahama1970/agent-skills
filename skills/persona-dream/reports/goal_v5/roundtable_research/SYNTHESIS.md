# Research-framing roundtable synthesis (2026-07-24) — kimi + claude, strong convergence

gpt dropped on browser transport (#980-class, two attempts). kimi (16.4KB) and
claude (11.9KB) responded fully; brave-search brief seeded to both. They
converged tightly and independently landed on the same corrections — treat these
as high-confidence.

## Converged (both seats, independent)

1. **Lead the paper with the MECHANISM + FIREWALL, not the loop or the mood.**
   - "Self-evolving persona loop" is REJECTED as already-done (AutoPersonas
     arXiv 2607.08252 ships a multi-timescale recursive loop with self-locking
     audits; Generative Agents did reflection).
   - Endogenous request-independent mood is REJECTED as novel — affective
     computing has had it 15+ years (ALMA/WASABI/PAD mood models with
     stimulus-decoupled decay). Position it as integration/plumbing, not a
     contribution.
   - The genuinely novel package: conflict-seeded dream → self-reflective
     journal WITH the event-fact/self-narrative FIREWALL. "Confabulation safe by
     construction — licensed to invent its inner life, structurally barred from
     inventing its history." AutoPersonas has no principled answer to "what is
     the loop allowed to fabricate"; we do.
2. **NARROW the thesis. "Personality = self-reflective instability" is
   overstated** (and fights the self-locking audit). Both: humans have STABLE
   CORE conflicts; pure instability is incoherence. Adopt **"theme-stable
   variation" / "narrative identity = self-reflective elaboration of PERSISTENT
   conflicts"** (McAdams actor-agent-author; dialogical self / I-positions).
3. **The grounding→conflict pivot is EXPLORATORY, not a finding.** Partially
   redeemed (conflict was designed into the architecture before the eval, so
   finding tension = the mechanism working) but NOT confirmed. Clean answer:
   label this session's conflict numbers hypothesis-generating, PRE-REGISTER the
   metrics, and re-run on fresh cycles. "The drift charge dissolves if
   pre-registered; sticks forever if exploratory numbers are published as the
   finding."
4. **Self-locking is the existential risk; measure it at MULTIPLE levels** (the
   loop guard/thermal limiter are mechanisms, not metrics):
   - THEME level: stability is OK/healthy (2–5 stable theme clusters = continuity).
   - VARIATION level: within-theme novelty must persist (nearest-neighbor cosine
     of each new conflict formulation < ~0.85; 5 consecutive > 0.85 = attractor
     collapse). Kimi's Conflict Fractal Dimension (correlation dimension of the
     journal trajectory; productive ~2.0–2.5, locking ~1.2–1.5) is the compact
     version.
   - FUNCTIONAL level (the one AutoPersonas MISSES): a fixed probe battery after
     each cycle — lexical mood diversity can MASK behavioral collapse
     ("guarded_quietly_wanting" vs "wistful_defended_yearning" may be one
     attractor renamed). If mood-label entropy stays high but probe-response
     divergence → 0, that's the worst self-locking.
   - SEED COVERAGE: fraction of the 202 conflicted memories actually visited
     over N cycles (revisiting 8 while 194 sit untouched is locking even if prose
     varies).
5. **Use NCT/ANIQ/NISE as CONTROLS, not passing grades**, via a DIFFERENTIAL
   falsifiable prediction: the persona should score LOWER on self-concept
   clarity (Campbell SCC) but HIGHER on autobiographical reasoning than a
   stable-prior baseline. NCT should DECOMPOSE across the two memory layers
   (event-fact stable, self-narrative evolving) — "the only system for which NCT
   should decompose." This is a construct-derived prediction, the signature of a
   principled theory vs post-hoc.
6. **The LOAD-BEARING experiment is DREAM vs DIRECT-REFLECTION ablation.** If a
   journal written straight from the same conflicted memories (no dream stage)
   produces the same identity trajectory, the dream is decoration and the paper
   collapses. Plus a GENERIC-CONFABULATION control (journal prompt, no
   dream/memory input): if free-floating entries are indistinguishable from
   dream-conditioned ones, self-discovery is fluent text, not a construct.

## Converged next action (near-identical from both)

Run the **30-cycle A/B ablation with PRE-REGISTERED metrics** BEFORE any further
exploratory analysis:
- Arm A: full loop (conflict-seeded dream → watch → self-reflective journal →
  mood). Arm B: reflection-only (same conflicted memories, same sampling policy,
  journal written directly, no dream). Same seed persona + canon. (+ optional
  Arm C: frozen persona card, for the SCC differential baseline.)
- Freeze `metrics.yaml` first: mood-cluster count, within-theme novelty curve,
  seed coverage, probe-battery behavioral divergence (incl. ≥4 cautionary
  probes/cycle → ~n=120 caution obs/arm, fixing the behavioral power problem),
  firewall breaches (zero event-facts originating in journals), caution-erosion.
- Blinded panel at cycles 10/20/30: autobiographical reasoning + "reads like a
  self that is developing," position-swapped, arm-blind.
- Success: A > B on within-theme novelty and autobiographical reasoning; A keeps
  ≥3 mood clusters through cycle 30; firewall zero breaches; raters prefer A's
  development above chance. Falsification: A ≈ B (dream is decoration);
  A collapses to one attractor; firewall breaches.

## Surviving dissent to surface

- Kimi: the grounding null is MORE damning than acknowledged — the dream adds
  tension, not TRUTH; for a "credible personality" add a grounding-maintenance
  requirement (event-fact consistency >98% + dream→memory-node provenance),
  stricter than the current firewall.
- Kimi + Claude: the safety GATE is a post-hoc band-aid; the architecture should
  prevent mood from overriding caution AT THE GENERATION layer — a first-class
  content-safety veto, not a filter.
- Both: 7/20 behavioral is a pilot, presented too confidently; power it to 100+
  probes before it can headline.
- Claude: fix the competitive framing — endogenous mood is a differentiator vs
  LLM-persona neighbors but NOT vs affective computing broadly; a reviewer will
  shred the related-work otherwise.
