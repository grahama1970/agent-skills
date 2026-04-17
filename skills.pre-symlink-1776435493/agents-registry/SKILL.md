---
name: agents-registry
description: >
  Generate and query the centralized agent identity registry. Scans
  .pi/agents/*/AGENTS.md, parses frontmatter, outputs agents-registry.json
  and optionally syncs to /memory for semantic search.
internal: true
triggers:
  - list agents
  - list personas
  - agent registry
  - who handles
  - which persona
  - find agent by capability
  - agent capabilities
  - persona roster
metadata:
  short-description: Centralized agent identity registry
provides:
  - agent-enumeration
  - capability-routing
  - persona-metadata
composes:
  - memory
taxonomy:
  - precision
  - composition
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Agent Registry

Centralized, queryable persona metadata. Scans `.pi/agents/*/AGENTS.md`,
parses YAML frontmatter, and produces a materialized JSON view for fast
sync loading by TS code (D-Bus bridge, skill-selector, orchestrator).

## Usage

```bash
# Generate registry (writes .pi/agents-registry.json)
./run.sh generate

# Generate and sync to /memory (ArangoDB agents collection)
./run.sh generate --sync-memory

# List all agents
./run.sh list

# Query by capability
./run.sh query --capability sparta-quality-assessment

# Query by agent name
./run.sh query --agent brandon-bailey
```

## Architecture

```
Source of Truth          Materialized View          Queryable Index
─────────────          ─────────────────          ───────────────
.pi/agents/*/          .pi/agents-registry.json   ArangoDB `agents` collection
  AGENTS.md     ──→    (fast sync loading for     (semantic search via
                        TS bridge, extensions)      /memory recall)
```
