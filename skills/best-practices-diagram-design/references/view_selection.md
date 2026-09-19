# View selection

Choose the view from the reader's question and immutable requirements; choose the renderer afterward.

| Reader question / requirement | View | Enforceable distinction |
|---|---|---|
| What happens next, including decisions, retries, and shared endings? | `flowchart` | Explicit control flow; declared cycles and merges allowed. |
| Which mutually exclusive choices lead to distinct leaves? | strict `decision_tree` | One root, no cycles, one parent per non-root. |
| Which actor sends what, and in what order? | `sequence` | Participants, messages, ordering, interaction fragments. |
| What states can an entity occupy and what triggers transitions? | `lifecycle` | States, events, guards, lifecycle boundary. |
| What exists, owns, contains, or depends on what? | `structure` | Typed elements, containment, relationship kinds, scope. |
| What executes concurrently and how does it complete? | `flowchart` with fork/join | Explicit `all`, `any`, or `detached` completion policy. |
| What independent relationships radiate from a source? | `fanout` | No sequential requirement among targets. |
| Who performs each process step? | flowchart plus swimlanes | Ownership overlay; control-flow semantics remain explicit. |

The motivating gated escalation is a `flowchart`, not a strict decision tree: multiple success outcomes merge into one logical `resume` terminal. “Acquire lock” is an action; “Lock acquired?” is a decision.

## Semantics, not shape

Do not reject a star merely because it is a star. A star may correctly represent independent dependencies. Instead, bind the approved process contract and run `PRECONDITION_BYPASS`: remove the required gate/outcome edge and search from every entry. If a protected target remains reachable, the diagram is wrong and the checker returns the bypass path.

Likewise, do not reject a straight connector by style alone. Reject measured intersections and clipping in the rendered scene.
