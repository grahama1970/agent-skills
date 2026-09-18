# View selection (harvested research)

Match the diagram TYPE to the intent. Choosing the wrong view is the root
cause the incident that created this skill: a gated sequential escalation
ladder (detector → lock → tier1 → tier2 → tier3, each gated by a
resolved?-check) was drawn as a fan-out star (one node, five parallel-looking
targets, no gates). It read as "pick any of five options" when it was
actually "walk this ladder one gated step at a time."

| Intent | Correct view | Renderer | Wrong-view smell |
|---|---|---|---|
| Sequential steps + decision logic | `decision_tree` / `flowchart` | graphviz/mermaid | drawn as unconnected boxes with no arrows, or as a fan-out |
| Time-ordered interactions between actors (who calls whom, in order) | `sequence` | mermaid sequence diagram | drawn as a flowchart, losing actor lanes and message order |
| Structure, components, dependencies (what depends on what) | `structure` / C4 | graphviz, `create-architecture` | drawn as a flowchart implying execution order that doesn't exist |
| Entry/exit states, lifecycle transitions | `lifecycle` | graphviz/mermaid state diagram | drawn as a flowchart without transition conditions |
| Genuinely parallel, independent choices (≤4, no ordering/lock between them) | `fanout` | `create-svg` fan-out compiler | used for a sequence that actually has gates or ordering — the star bug |

## The star-for-sequence test

Before accepting a `fanout` view, ask: if I resolve target A, does that change
whether B is still reachable, or is there a lock/gate between them? If yes to
either, it is not a fan-out — it is a `decision_tree`/`flowchart` with gates.
The checker's `VIEW_TOPOLOGY_MISMATCH` rule encodes a narrow, checkable proxy
for this: a single source node fanning out to 3+ targets with zero declared
gates, on a `decision_tree`/`flowchart` view.
