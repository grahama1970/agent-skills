# Ask Argue Protocol Contract

`/ask argue` is a bounded adversarial decision protocol. It is not a loose
debate, consensus chat, or generic roundtable. The protocol forces one side to
make the strongest defensible case for a proposition and the other side to make
the strongest defensible case against it, then a neutral judge applies a fixed
rubric.

## CLI Surface

```bash
./run.sh ask "argue for and against moving embeddings to Qdrant" --argue

./run.sh ask "devil's advocate this architecture plan" \
  --argue \
  --argue-personas "Architect:FOR,Skeptic:AGAINST" \
  --argue-rounds 2
```

Natural chat prompts such as `argue both sides`, `for and against`, `devil's
advocate`, and `both sides of this decision` route to `--argue`.

## Roles

| Role | Obligation |
| --- | --- |
| `FOR` | Make the strongest defensible argument for the proposition. |
| `AGAINST` | Make the strongest defensible argument against the proposition. |
| `JUDGE` | Apply the rubric to the argument turns without adding new evidence. |

The FOR and AGAINST sides may acknowledge weaknesses, but they must stay inside
their assigned side. The judge may identify tradeoffs, but must not invent new
facts or treat memory as evidence.

## Judge Rubric

The default rubric is fixed:

- `evidence_strength`
- `failure_mode_coverage`
- `assumption_quality`
- `target_relevance`
- `falsifiability`
- `implementation_cost_or_risk`

The judge decides argument strength under this rubric, not by confidence,
verbosity, or rhetorical polish.

## Verdicts

Allowed verdicts:

- `FOR`
- `AGAINST`
- `NO_CLEAR_WINNER`
- `INSUFFICIENT_EVIDENCE`

`FOR` and `AGAINST` require decisive reasons and positive evidence-strength for
the winning side. `NO_CLEAR_WINNER` is used when the sides are comparably strong
or trade off across rubric dimensions. `INSUFFICIENT_EVIDENCE` is used when the
available inspected evidence is too weak to make a responsible call.

## Required Judge JSON

The moderator must include a fenced JSON block:

```json
{
  "verdict": "FOR",
  "winner": "for",
  "rubric_scores": {
    "evidence_strength": {"for": 4, "against": 2, "winner": "for"},
    "failure_mode_coverage": {"for": 3, "against": 4, "winner": "against"},
    "assumption_quality": {"for": 4, "against": 3, "winner": "for"},
    "target_relevance": {"for": 5, "against": 4, "winner": "for"},
    "falsifiability": {"for": 3, "against": 3, "winner": "tie"},
    "implementation_cost_or_risk": {"for": 4, "against": 2, "winner": "for"}
  },
  "decisive_reasons": [
    "The FOR side tied its claim to inspected rollback and maintenance evidence."
  ],
  "confidence": "medium"
}
```

Each score must be a number from `0` to `5`; each rubric winner must be `for`,
`against`, or `tie`.

## Deterministic Gate

`validate_argue_verdict_payload()` enforces the JSON gate:

- verdict is one of the four allowed values
- winner is consistent with verdict
- confidence is `high`, `medium`, or `low`
- every rubric key is present
- every side score is numeric and within range
- `FOR` or `AGAINST` verdicts include decisive reasons
- `FOR` or `AGAINST` verdicts have positive winning-side evidence strength

This gate is intentionally narrow. It does not prove reasoning quality; it
prevents malformed, unsupported, or non-auditable judge outputs from being
treated as a valid project-agent decision.

## Persistence

By default, `/ask argue` persists compact state, verdict metadata, and durable
lessons only when useful. Full transcript persistence requires an explicit full
persistence mode. Do not store full repo snippets, full diffs, or transient
persona chatter by default.

## Non-Goals

- Not a generic debate feature.
- Not a generic DAG/workflow engine.
- Not a substitute for inspected evidence.
- Not a source-editing mode.
- Not permission for subagents to recursively call `/ask`.
