# Voice contract — grahama.co

These are **invariants**, not optional copy. The deterministic `scripts/copy_audit.py`
gate enforces the machine-checkable ones; the rest are review discipline. When a
proposed change conflicts with an invariant, the invariant wins.

## Identity
- The practice is always **I** and **my** — never a fictional first-party "we/our/us".
- Graham is plainly **one person**, not a studio pretending to be larger.

## Sentence order (how a claim is built)
1. Start with the recognizable **problem**.
2. State what I **built or investigated**.
3. Show the **evidence**.
4. State the **limitation or open gate**.

## Language
- Prefer concrete verbs: *built, tested, captured, failed, replayed, measured*.
- Explain a technical term near first use; use jargon for precision, never status.
- Contractions and natural cadence are fine.
- **Banned** (copy-audit denylist): world-class, revolutionary, cutting-edge,
  seamless, transformative, industry-leading, leverage, unlock, game-changing,
  and kin. No unsupported superlatives. No placeholder/lorem.

## Evidence
- *Publicly inspectable*, *technical abstract*, and *available under NDA* are
  **factual access states**, not badges of quality.
- A semantic or graph relationship **never proves** a capability.
- A null, blocked, or failed result **is publishable** — and gets equal visual weight.
- Private work **cannot borrow** the evidence status of a related public project;
  no private repo/path/count leaks.
- No fabricated evidence: no fake traces, no animated counters, no number the
  generators didn't emit.

## Creative and technical work
- Neither is decoration for the other.
- A cinematic frame carries provenance (project · artifact type · run/date ·
  illustrative | generated | captured | measured).
- A technical receipt gets equivalent visual care.

## Motion (operator-scoped exceptions)
- Default posture: exhibits, not theater. Motion must make **new information
  understandable** — if it can't answer "what do I now understand because this
  moved?", it's removed.
- Sanctioned exceptions (operator-approved): the constellation's layout, the
  search placeholder rotation, the G꜀ mark's slow glow, the hero video, the
  "unusual path" draw. All honour `prefers-reduced-motion` (render final state).
- Banned: infinite decorative node motion, perpetual pulsing status, looping
  progress, self-erasing/"telemetry" animations, competing entrance animations.

## Enforcement
- `scripts/copy_audit.py` — collective-"we", superlatives, placeholders,
  public/private evidence-label conflicts; runs in the `monitor-website refresh`
  gate. Exit non-zero blocks the change.
- Blind human read: ≥5/6 reviewers rate ≥4/5 for "sounds like one accountable
  person", "concrete not promotional", "technically credible", "understandable
  outside the repo".
