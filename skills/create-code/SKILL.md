---
name: create-code
description: >
  Orchestrate the end-to-end coding process for the Horus persona.
  Composes research (/dogpile), isolated execution (/hack, /battle),
  structured implementation (/task, /orchestrate), and brutal code review (/review-code).
allowed-tools: Bash, Read
triggers:
  - create code
  - build feature
  - implement algorithm
  - horus coding workflow
  - new project from idea
metadata:
  short-description: End-to-end Horus coding orchestration pipeline
---

# Create Code Skill

The `create-code` skill is the primary coding engine for the **Horus** persona. it orchestrates a multi-stage "Hardened Coding" workflow that ensures code is researched, isolated, tested, and brutally critiqued before completion.

---

## Horus Coding Workflow

The skill follows a strict 6-stage pipeline:

### 1. Idea & Initial Scoping

Horus starts with a high-level idea or requirement.

- **Stage 1 Gate**: Clarification interview to define scope and constraints.

### 2. Deep Research (/dogpile)

Horus research existing implementation patterns, libraries, and potential pitfalls.

- Calls `/dogpile search "<idea> implementation patterns"`
- Aggregates context into a research summary.

### 3. Isolated Execution Environment (/hack, /battle)

Horus spins up an isolated Docker container to safely test snippets or run adversarial simulations.

- Uses `.pi/skills/hack` for container management.
- Uses `.pi/skills/battle` if security hardening or competition is required.

### 4. Structured Implementation (/task, /orchestrate)

Implementation is driven by `0N_TASKS.md` files with enforced quality gates.

- Uses `/task` to break down the idea into actionable items.
- Uses `/orchestrate` to execute tasks, requiring:
  - **Sanity Tests**: Every task must have a verification script.
  - **Assertions**: Core logic must be asserted.
  - **Definition of Done (DoD)**: Strict criteria for task completion.

### 5. Brutal Code Review (/review-code)

Horus submits the code for a multi-round "Brutal Review".

- Calls `/review-code` using **Copilot GPT-5** (or highest reasoning model available).
- Focuses on "No-Vibes" technical correctness, efficiency, and Horus's specific persona standards.

### 6. Final Research & Consolidation (/dogpile)

Horus performs a final dogpile search with the working code and full context to find any last-minute edge cases or optimizations.

- Consolidation of the project into the Horus/Memory knowledge graph.

---

## Usage

```bash
# Start a new coding project from an idea
./run.sh start "Implement a high-performance vector store with ArangoDB"

# Resume an existing creation in a directory
./run.sh resume /path/to/project

# Run specific stages
./run.sh research "idea"
./run.sh review /path/to/code
```

## Commands

| Command     | Description                                  |
| ----------- | -------------------------------------------- |
| `start`     | Launch full 6-stage workflow from an idea    |
| `research`  | Run Stage 2 Dogpile research                 |
| `sandbox`   | Spin up Stage 3 isolated environment         |
| `implement` | Run Stage 4 Task/Orchestrate pipeline        |
| `review`    | Run Stage 5 Brutal Code Review               |
| `finalize`  | Run Stage 6 Final research and memory commit |

---

## Key Principles

1. **Isolation First**: Never run untrusted or experimental code on the host.
2. **Quality Gates**: No code proceeds without passing sanity tests and DoD.
3. **Brutal Critique**: Embody Horus's uncompromising standard for technical excellence.
4. **Memory Integration**: Always check and update the knowledge graph.
