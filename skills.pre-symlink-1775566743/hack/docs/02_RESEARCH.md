# Research: Dynamic Learning & Foundational Knowledge

## Core Philosophy

The `hack` skill must balance **Dynamic Exploitation** (up-to-the-minute threats) with **Foundational Knowledge** (theory/history).

> "A book is already out of date." — User

## Tier 1: Dynamic Exploit Discovery (Priority)

To stay relevant, the agent must fetch, parse, and ingest live exploit data.

### Sources & Methods

1.  **Exploit-DB**:
    - **Method**: CSV Database / HTML Scraping.
    - **Action**: Fetch `files.csv` daily. Parse for new CVEs and PoC paths.
2.  **Packet Storm Security**:
    - **Method**: RSS Feeds.
    - **Action**: Monitor `files` feed for fresh uploads.
3.  **GitHub**:
    - **Method**: GitHub Search API (via `github-search` skill logic).
    - **Query**: `topic:exploit`, `topic:poc`, `language:python created:>2025-01-01`.

### Implementation Strategy

- **Command**: `hack learn --source <name>`
- **Storage**: Local structured JSON/SQLite in `~/.pi/skills/hack/data`.
- **Usage**: `hack search <cve>` queries this local cache first.

## Tier 2: Foundational Knowledge (Automated Library)

While books age, they provide the _theory_ (e.g., "How does ROP work?") that doesn't change as fast as the exploits.

### Tool: Calibre-Web-Automated

- **Verdict**: **Useful as a Sidecar**.
- **Integration**: It lacks a strong Write API for agents.
- **Agentic Pattern**: **"Filesystem Handoff"**.
  - The agent places found books (PDF/EPUB) into an `inbox/` directory.
  - Calibre-Web-Automated watches `inbox/`, auto-ingests, converts, and organizes.
  - Agent reads from the organized structure if needed, or treats it as "read-only memory."

### Answer to User

- **Do we need books?** Yes, for deep theory (Low-level internals, hardware specs).
- **Do we need Calibre-Web-Automated?** Yes, to automate the _management_ so the agent doesn't waste cycles organizing files.

## Tier 3: Formal Verification (Precision Microscope)

Leveraging `lean4-prove` for design-level security validation.

### Red Team: Finding Exploit Paths (Attack Sketches)

1.  **Break Security Claims**: Formalize properties like "noninterference" or "constant-time" as theorems, then try to **refute** them.
2.  **Witness Search**: Negate the property ("There exists an execution where bad thing happens") and let the prover find a witness (a minimal exploit recipe).
3.  **Assumption Mining**: Explicitly state assumptions (e.g., "no speculation") and verify if they hold in production.

### Blue Team: Validating Mitigations (Proof-Carrying Code)

1.  **Prove Invariants**: Formalize "trusted core" logic (hypervisor boundaries, crypto wrappers) and prove invariants (e.g., "no unauthorized mapping").
2.  **Regression Proofs**: Turn minimal counterexamples (from Red Team) into regression tests or proved theorems.

### Implementation Strategy

- **Command**: `hack prove` (Delegates to `lean4-prove` skill)
- **Usage**:
  - `hack prove --claim "secrets don't leak"`
  - `hack prove --negate --claim "secrets leak"` (Find witness)
