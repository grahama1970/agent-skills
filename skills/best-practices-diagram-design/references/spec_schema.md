# Diagram spec schema

The typed boundary is `DiagramSpec` in `scripts/diagram_design_check.py` (Pydantic, `extra="forbid"`).

| Field | Type | Notes |
|---|---|---|
| `view` | `decision_tree | flowchart | sequence | structure | fanout | lifecycle` | Semantic view, selected before renderer. |
| `nodes` | `[{id, label, kind, outcome_domain?}]` | `kind`: action, decision, terminal, handoff, fork, join. Decision domains should be finite Boolean/enum values. |
| `edges` | `[{source, target, branch_label?, outcome?, routing?, kind?}]` | `kind`: control (default), annotation, dependency. Semantic checks only traverse control edges. |
| `requirements` | `{intent, required_order, required_preconditions, required_outcome_targets}` | Source-bound process contract; layout/rendering cannot modify it. |
| `gates`, `terminal_states` | `[node_id]` | Backward-compatible indexes; canonical semantics come from `node.kind`. |
| `label_limit` | integer | Authoring limit only; rendered text fit is checked from measured geometry. |

A required precondition is `{target, gate, outcome}`. A required outcome target is `{gate, outcome, target}`.

The `create-svg` fanout adapter currently supports four targets. `FANOUT_TOO_MANY` reports that capability limit; it is not a universal diagram-design rule.

See `fixtures/good_decision_tree.json` for the accepted gated flowchart and `fixtures/bad_fanout_star.json` for a relabeled star rejected by `INTENT_VIEW_MISMATCH` and `PRECONDITION_BYPASS` with counterexample paths.
