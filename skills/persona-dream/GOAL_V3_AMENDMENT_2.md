# GOAL_V3 Amendment 2 — dreaming is variation, not one-shot per cluster

Date 2026-07-23. Authorized by operator, verbatim: "different variation of the
same dream is human and agentic"; "humans are conflicted with positive and
negative views of the same memory which multi-hop graph traversal to different
memories. so should agents."

## What changed and why

The prior selector treated each memory cluster as single-use: once any of its
memories fed a dream, the cluster was permanently blocked
(`BLOCKED_CYCLE_NO_UNUSED_CLUSTERS`). That models dreaming wrong. Humans do not
get a new memory each night; they re-process the SAME experiences, and the same
memory is held with BOTH positive and negative valence at once. Resolving that
conflict is an associative, multi-hop traversal across the memory graph.

VERIFIED substrate (live probe, this session): 202/312 Embry memories carry
both a positive and a negative emotion; 192 graph edges point from one memory to
another (`graph_edges_raw`: {relation, target_memory_id}).

## New selection mechanism (`select_cluster`, v2 receipt)

1. Seed from a valence-CONFLICTED memory (holds both positive and negative
   emotion), most-conflicted first.
2. Traverse that memory's graph edges to gather associates.
3. VARIATION = which valence dominates this dream (positive/negative, alternating
   by variation_index) + which associative path was taken. The dream prompt is
   told which reading to lean into, without changing the facts.
4. A previously-dreamed cluster is RE-DREAMABLE as a new variation. Only an
   EXACT prior variation (same members + same emphasis, tracked in
   `reports/goal_v5/variation_ledger.json`) is blocked.

## Invariants preserved (NOT weakened)

- **Counterpart isolation gate (tau round-1 CRITICAL):** traversal stays WITHIN
  the seed's counterpart. Cross-counterpart multi-hop — the fuller form of the
  operator's model — reintroduces the Brandon→Kai leak and is DEFERRED to a
  separate change that amends the counterpart gate itself via a tau
  creator/reviewer loop. It is not done here.
- **Loop guard (GOAL_V4.3):** residue carrying persona_dream affect provenance
  is still excluded from seeding. We never dream about dream-colored speech.
- Variation lineage (seed_memory, valence_emphasis, variation_index,
  variation_key) is recorded so the downstream D-vs-M study can tell variations
  apart and never draw the same variation into both arms (panel option-c
  confound addressed).

## Open follow-up — cross-persona dreams connected by theory of mind

Operator, verbatim: "personas have conflicted views of the same experience
which connect to other persona dreams through theory of mind."

The fuller model: the SAME shared experience is held with different (and
internally conflicted) valence by DIFFERENT personas, and one persona's dream of
it connects to another's dream of it THROUGH theory of mind — persona A dreaming
its model of how persona B experienced the shared moment.

This RESOLVES the counterpart-isolation tension rather than violating it. The
tau round-1 CRITICAL leak was the pipeline SILENTLY attributing one counterpart's
material to another with no ToM framing. The correct cross-persona form is the
opposite: the connection is EXPLICITLY theory-of-mind — "Embry's model of how
Horus saw this," grounded in the record's existing `cross_persona_hooks` field,
labeled as a model of the other mind, never asserted as first-person fact about
that persona. ToM framing is what keeps it safe.

Substrate already present: every memory carries `cross_persona_hooks`
(candidate_counterpart_personas, shared_event, possible_contrast,
canon_constraint), and phases 13/14 already emit ToM content.

This is the next design. It amends the counterpart gate to ALLOW cross-persona
content when and only when it is hook-grounded, ToM-framed, and non-asserting
about the other persona — and it goes through a tau creator/reviewer loop
(schema tau.generic_dag_spec.v1), not a direct edit, because it moves a gate
that previously caught a CRITICAL leak.
