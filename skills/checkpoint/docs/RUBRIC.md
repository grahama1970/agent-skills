# Checkpoint Session Rubric v1

## Grades

Five levels. Each is a graph node in ArangoDB. Pick the ONE that matches.

| Grade | Label | Criteria | Tag |
|-------|-------|----------|-----|
| **1** | `unresolved` | Problem not solved. Session ended without a working solution. Blockers remain. | `grade:unresolved` |
| **2** | `workaround` | Problem bypassed, not solved. Hack, manual fix, or "good enough for now." Will break again. | `grade:workaround` |
| **3** | `solved` | Problem solved with rework. Took multiple attempts, corrections, or human intervention to get right. | `grade:solved` |
| **4** | `clean` | Problem solved first try or with minimal iteration. No rework. Tests pass. | `grade:clean` |
| **5** | `reusable` | Solution is generalizable. Created a new skill, pattern, or approach that applies beyond this specific problem. | `grade:reusable` |

## How to Pick (decision tree for agents)

Follow this chart top-to-bottom. Take the first exit that matches.

```mermaid
flowchart TD
    START["Session ended"] --> Q1{"Was the problem\nsolved?"}

    Q1 -->|NO| UNRESOLVED["grade:unresolved\n─────────────────\nProblem not solved.\nBlockers remain."]
    UNRESOLVED --> STORE_NEG["Store chain as\nproven-failure\nfor /recommend-skill-chain"]

    Q1 -->|YES| Q2{"Was it a hack\nor temporary fix?"}

    Q2 -->|YES| WORKAROUND["grade:workaround\n─────────────────\nBypassed, not fixed.\nWill break again."]
    WORKAROUND --> STORE_NEG

    Q2 -->|NO| Q3{"Did it require\ncorrections or\nmultiple attempts?"}

    Q3 -->|YES| SOLVED["grade:solved\n─────────────────\nFixed with rework.\nHuman corrected agent."]
    SOLVED --> STORE_POS["Store chain as\nproven-success\nfor /recommend-skill-chain"]

    Q3 -->|NO| Q4{"Is the solution\nreusable beyond\nthis problem?"}

    Q4 -->|YES| REUSABLE["grade:reusable\n─────────────────\nNew skill, pattern,\nor generalizable fix."]
    REUSABLE --> STORE_POS

    Q4 -->|NO| CLEAN["grade:clean\n─────────────────\nFirst try. No rework.\nTests pass."]
    CLEAN --> STORE_POS

    STORE_POS --> TAXONOMY["/taxonomy/batch-tag\nassign Mind + Bridge"]
    STORE_NEG --> TAXONOMY

    TAXONOMY --> COMMIT["git commit + push\nproject AND skills"]
    COMMIT --> DONE["Checkpoint complete\n─────────────────\nFindable via /recall\nBM25 + semantic + graph"]

    style UNRESOLVED fill:#e74c3c,color:#fff
    style WORKAROUND fill:#e67e22,color:#fff
    style SOLVED fill:#f1c40f,color:#000
    style CLEAN fill:#2ecc71,color:#fff
    style REUSABLE fill:#3498db,color:#fff
    style STORE_POS fill:#27ae60,color:#fff
    style STORE_NEG fill:#c0392b,color:#fff
    style TAXONOMY fill:#8e44ad,color:#fff
    style COMMIT fill:#2c3e50,color:#fff
    style DONE fill:#1abc9c,color:#fff
```

## Observable Signals (for automatic grading)

| Signal | Maps to |
|--------|---------|
| Session has unresolved blockers | `unresolved` |
| User said "stop", "nevermind", "skip" | `unresolved` |
| User said "good enough", "for now", "hack" | `workaround` |
| Agent received corrections ("no, not that", "try again") | `solved` |
| Tests passed on first run, no rework | `clean` |
| New skill created, or solution stored for reuse | `reusable` |

## Graph Structure

Each grade is a **node** in the `checkpoint_grades` collection. Checkpoints link to their grade via `graded_as` edges. This enables:

```
/memory recall "clean solutions for SPARTA validation"
    → BM25 matches "SPARTA validation" in problem text
    → filter by tag grade:clean
    → returns only first-try clean solutions

/trace from grade:reusable
    → traverses graded_as edges → checkpoints → taxonomy edges → related controls
    → finds all generalizable solutions and what domains they apply to

/trace from grade:unresolved
    → traverses graded_as edges → checkpoints → episode edges → full transcripts
    → finds all unsolved problems with their conversation history
```

### Multi-hop traversal example

```mermaid
graph LR
    G["grade:clean"] -->|graded_as| CP["CHECKPOINT:\nSPARTA threshold fix"]
    CP -->|taxonomy| T1["Mind:Detect"]
    CP -->|taxonomy| T2["Bridge:Precision"]
    CP -->|checkpoint_of| EP["Episode\n(full transcript)"]
    CP -->|skill_chain| SC["/assess → /dogpile → /plan"]

    style G fill:#2ecc71,color:#fff
    style CP fill:#34495e,color:#fff
    style T1 fill:#9b59b6,color:#fff
    style T2 fill:#9b59b6,color:#fff
    style EP fill:#e67e22,color:#fff
    style SC fill:#3498db,color:#fff
```

**Query:** "What clean solutions exist for Detect+Precision problems?"
→ Start at `grade:clean` → follow `graded_as` → filter by `Mind:Detect` + `Bridge:Precision` → return skill chains

## Rubric Version

Store `rubric_version: 1` in every checkpoint solution_doc. When the rubric changes (levels added/renamed), bump the version. This enables:
- Drift detection: "grades assigned under v1 may not compare to v2"
- Migration: batch-retag old checkpoints when rubric changes
