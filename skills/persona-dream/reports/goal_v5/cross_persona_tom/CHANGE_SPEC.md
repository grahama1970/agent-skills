# Change spec: allow cross-persona ToM-framed claims through the counterpart gate

## Current code (the gate to amend)

`skills/persona-dream/scripts/autonomous_dream_cycle.py`:

```python
def counterpart_violations(claims: list, counterpart_id: str, id_field: str) -> list:
    """GOAL_V3 counterpart gate (probe-able): a claim's target must be the
    selected counterpart or the bounded unknown_person."""
    allowed = {counterpart_id, "unknown_person"}
    return [c.get(id_field) for c in claims if str(c.get("target")) not in allowed]
```

## Why it exists (must not regress)

tau review round-1 CRITICAL: Brandon-cluster root memories produced Kai-targeted
theory-of-mind claims — one counterpart's material silently attributed to
another. This gate blocks any claim whose `target` is not the selected
counterpart or `unknown_person`.

## The required change (operator model: cross-persona dreams connect via ToM)

A dream may legitimately reference ANOTHER persona's view of a SHARED experience
— but ONLY as Embry's theory-of-mind MODEL of that other mind, grounded in the
memory record's existing `cross_persona_hooks` field, never as a first-person
assertion of fact about the other persona.

Amend `counterpart_violations` (or add a sibling gate) so a claim with a
non-counterpart `target` is ALLOWED if and only if ALL of:
1. `claim["tom_frame"] == "model_of_other"` (explicitly a model of another mind,
   not a first-person fact),
2. `claim["target"]` is listed in some source memory's
   `cross_persona_hooks[].candidate_counterpart_personas` (hook-grounded),
3. the claim text is non-asserting about the other persona (no canon fact
   claimed about them; the hook's `canon_constraint` is respected).

A claim with a non-counterpart target that is NOT tom_frame=model_of_other, or
NOT hook-grounded, remains a VIOLATION (the original leak stays blocked).

## Acceptance (reviewer VERDICT: PASS/FAIL)

- The exact tau round-1 leak still fails: a first-person claim targeting a
  non-counterpart persona with no ToM frame → still a violation.
- A hook-grounded `tom_frame=model_of_other` claim about a hooked persona →
  allowed.
- A `tom_frame=model_of_other` claim about a persona NOT in any source hook →
  still a violation (no ungrounded mind-reading).
- A fixture probe exists covering all three cases and passes.
- No change to the intra-counterpart selection logic (Amendment 2) or the loop
  guard.
