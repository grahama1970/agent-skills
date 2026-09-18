# Diagram spec schema

The typed boundary model is `DiagramSpec` in `scripts/diagram_design_check.py`
(Pydantic, `extra="forbid"`). Fields:

| field | type | required | notes |
|---|---|---|---|
| `view` | `decision_tree \| flowchart \| sequence \| structure \| fanout \| lifecycle` | yes | chosen per `references/view_selection.md` |
| `nodes` | `[{id, label}]` | yes, ≥1 | `label` is the on-box text |
| `edges` | `[{source, target, branch_label?, routing?}]` | no, default `[]` | `routing`: `orthogonal` (default) \| `curved` \| `straight` |
| `gates` | `[node_id]` | no, default `[]` | node ids that are decision points; every outgoing edge from a gate must have `branch_label` |
| `terminal_states` | `[node_id]` | no, default `[]` | required (≥1) for process views (`decision_tree`, `flowchart`, `sequence`, `lifecycle`) |
| `label_limit` | `int` | no, default `60` | overridable per-spec character limit for non-fanout labels |

Fan-out views use fixed limits regardless of `label_limit`: source node
labels ≤80 chars, target node labels ≤40 chars (Excalidraw fan-out box
sizing), and a hard ceiling of 4 targets from a single source
(`create-svg` fan-out compiler contract).

See `fixtures/good_decision_tree.json` (accepted) and
`fixtures/bad_fanout_star.json` (rejected, `VIEW_TOPOLOGY_MISMATCH`) for
worked examples.
