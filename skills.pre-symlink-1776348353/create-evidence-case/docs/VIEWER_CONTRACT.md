# Viewer Contract

The `/create-evidence-case` viewer is triage-first.

Primary states:
- `SATISFIED` - grounded and disposition-ready
- `NEEDS_CLARIFICATION` - user action required before disposition
- `INCONCLUSIVE` - evidence insufficiency without a user-fixable ambiguity
- `NOT_SATISFIED` - hard failure or fabricated/off-corpus rejection

Supporting fields:
- `needs_clarification: bool`
- `primary_state: str`
- `clarification_items: list[object]`
- `blocking_reason_classes: list[str]`

`clarification_items[]` shape:
```json
{
  "kind": "misspelling|possible_typo|framework_misspelling|not_in_corpus|fabricated_context|insufficient_evidence",
  "label": "short term or issue label",
  "detail": "operator-facing explanation",
  "recoverable": true
}
```

UI semantics:
- recoverable ambiguity -> NVIS amber
- hard failure/fabricated context -> NVIS red
- evidence insufficiency -> NVIS blue
- satisfied -> NVIS green

The main screen shows:
- primary state
- next action
- top blockers / clarification items
- top evidence summary

Detailed provenance, gate trace, and decomposition stay behind secondary panels.
