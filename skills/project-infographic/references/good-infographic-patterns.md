# Good Infographic Design Patterns

Use this reference to choose a positive visual target before rendering. The goal
is a technical editorial infographic: a poster that explains a system through
visual hierarchy, section bands, causal flow, decision gates, loops, icons, and
color semantics.

A dashboard reports current state. An infographic explains system meaning, flow,
causality, and review logic.

## Core Patterns

### 1. Stack-to-Feedback-Loop Poster

Best for systems with platform layers, processing stages, product surfaces, and
human review.

Structure:

```text
title -> legend -> orchestrator strip -> platform layer -> evidence pipeline
-> product/chat fanout -> human review loop -> bottom invariant
```

Use when:

- the project has multiple layers
- there is one critical operator surface
- failure and recovery paths matter
- future agents must update the visual as the project evolves

### 2. Evidence-Envelope Pipeline

Best for proof, assurance, extraction, or evidence systems.

Structure:

```text
source -> extraction -> retrieval -> evidence case -> typed artifacts
-> gate -> publish or repair
```

Use when:

- the main idea is grounded evidence
- outputs are typed artifacts
- proof boundaries and non-authoritative suggestions must stay visible

### 3. Human-Review Course-Correction Map

Best for workflows that repair generated artifacts without false-green promotion.

Structure:

```text
bad input classes -> repair path -> review gate
-> approved update or adversarial retention
```

Use when:

- failed originals are retained
- correction candidates are separate from originals
- human review is required before promotion

### 4. Hub-and-Spoke Workbench

Best for chat-centered or operator-centered products.

Structure:

```text
central operator surface -> surrounding pages/tools
-> source-backed artifacts -> review gates
```

Use when:

- one interface is the critical path
- multiple pages or tools depend on one evidence envelope
- the visual must explain how the operator moves through the system

## Good Infographic Traits

- Poster composition: fixed canvas, strong title, subtitle, legend, and bottom thesis.
- Narrative spine: clear beginning -> transformation -> decision -> outcome.
- Numbered bands or lanes: each section teaches one layer of the system.
- Visual hierarchy: one dominant object, secondary stages, supporting details.
- Dense but readable structure: compact labels, meaningful grouping, no empty dashboard whitespace.
- Connector logic: arrows, branches, diamonds, loops, fan-outs, and return paths.
- Icon-led scanning: simple line icons that identify stage roles quickly.
- Color semantics: colors mean artifact type, risk state, review state, or system boundary.
- Editorial compression: fewer words per box, more meaning per visual relationship.

## Pattern Selection Rule

Choose one primary pattern and at most one supporting pattern. Do not blend all
patterns equally. The chosen primary pattern must be named in the design brief's
Visual Composition Contract.
