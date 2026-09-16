# Visual explainer contract ($create-architecture)

Every workflowScript ships with a diagram of its control flow. The diagram is
part of the interview review, not documentation written after the fact.

## What the diagram must show

1. **Lanes** — every `runs.run` child as a node, labeled with its agent role
   (scout/worker/reviewer) and one-word purpose (gate, prepare, recover,
   review, repair, publish, post, close, audit).
2. **Edges** — control flow: sequential awaits, loop-backs (repair rounds,
   iterations), and branch conditions on structured verdicts.
3. **Gates** — decision diamonds with their verdict enums
   (`ready | blocked_human | continue`, `ready | changes_requested |
   external_block`, `pass | blocked`).
4. **Terminal states** — the named exit states with their trigger condition.
5. **Shared assets** — external files the workflow invokes by path
   (`model-preflight.sh`, config `<repo>/.pi/<name>.json`), drawn as inputs.

## How to produce it

Compose `$create-architecture` over the workflowScript source: the module view
(lanes and their sequence) plus the execution-flow view (branch/loop edges to
terminal states). Store the result as:

```text
~/.pi/agent/workflows/<name>.diagram.md
```

The diagram file header records the interview answers (goal, terminal states,
cap source, provider roster) so the visual and the contract travel together.

## Review rule

The human (or requesting project agent) reviews the diagram at the interview
step and again whenever a terminal state, lane, or provider roster changes. A
workflowScript whose diagram no longer matches its control flow is treated as
undocumented: refresh the diagram before the next launch.
