---
name: create-react-designs
description: >
  Create production-grade React/Tailwind/ShadCN designs with a multi-persona feedback loop.
  Generates "ready to connect" front-ends, uses a Persona Council (Simulacrum + Taxonomy)
  to critique designs, consults experts if confidence is low, and iterates until
  production quality is reached.
allowed-tools: [Bash, Read, Write, Connect, Browser]
triggers:
  - create react designs
  - design ui
  - generate frontend
  - make react app
  - production ui
  - persona council design
metadata:
  short-description: Production-grade React/ShadCN design lab with Persona Council
  author: "Horus"
  version: "0.1.0"

provides:
  - create-react-designs
composes: [task-monitor]
disciplines:
  - ui-design-engineering
---

# Create React Designs

A production-grade UI design lab where AI Personas collaborate to build "ready to connect" React front-ends.

## Core Feature: Persona Council

Unlike simple "critique" loops, this skill uses a **Persona Council**:

1.  **Primary Persona**: The main user (e.g., "Embry").
2.  **Confidence Check**: If the Primary's _Precision_ (Taxonomy) is low or _Ambiguity_ is high, they **automatically consult experts**.
3.  **Expert Consultation**: The system queries relevant Expert Personas (e.g., "Senior UX Designer", "Accessibility Specialist") for targeted advice.
4.  **Synthesis**: All feedback is synthesized into a unified, high-fidelity patch plan.

## Workflow

1.  **Create**: Scaffolds a production-ready Next.js + ShadCN app (strict TS, linting).
2.  **Council**: Runs the multi-persona review session via VLM.
3.  **Iterate**: Applies architectural and visual changes using high-reasoning models.
4.  **Finalize**: Prepares the code for backend integration (clean cleanup).

## Quick Start

```bash
cd .pi/skills/create-react-designs

# 1. Create a design with Embry as the lead
./run.sh create "Sci-Fi Trading Terminal" --persona "Embry"

# 2. Run the full loop (Create -> Council -> Iterate -> Finalize)
./run.sh loop "Sci-Fi Trading Terminal" --persona "Embry" --max-cycles 3
```

## Commands

### `create`

Scaffold a new production-grade design.

```bash
./run.sh create "PROMPT" [--out DIR]
```

### `council`

Run a Persona Council session.

```bash
./run.sh council --url http://localhost:3000 --persona "Embry" --out outputs/run-01
```

### `iterate`

Apply feedback from the Council.

```bash
./run.sh iterate --dir outputs/run-01
```

### `loop`

Run the full end-to-end process.

```bash
./run.sh loop "PROMPT" --persona NAME
```
