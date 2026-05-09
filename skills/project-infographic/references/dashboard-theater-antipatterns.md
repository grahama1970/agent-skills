# Dashboard Theater Anti-Patterns

Use this reference to reject performative visuals. The project-infographic skill
does not create app screens, dashboards, status monitors, landing pages, or
generic architecture card grids unless the user explicitly asks for that
specific surface.

A dashboard reports current state. An infographic explains system meaning, flow,
causality, and review logic.

## Reject These Structures

- KPI strips
- fake health metrics
- fake live status values
- status cards
- queue panels
- nav sidebars
- app chrome
- product landing-page hero sections
- equal-sized card grids
- metric tiles
- generic system-overview dashboards
- monitor UI when the requested artifact is a project infographic
- Mermaid-style boxes with prettier borders
- large whitespace that removes workflow density
- happy-path-only pipelines that hide review, failure, blocked, or adversarial paths

## Common Failure Modes

### Semantic Box Map

Symptoms:

- factually correct labels
- boxes have no editorial hierarchy
- every node has similar size and visual weight
- arrows only indicate adjacency, not causality
- the viewer cannot identify the main mechanism in five seconds

Reject because the visual catalogs concepts instead of teaching the workflow.

### Fake Dashboard

Symptoms:

- health/pass/fail tiles
- counts without live source proof
- queue/status lanes
- generic action cards
- table-like sections
- app-shell framing

Reject because it implies operational truth rather than explaining system
meaning.

### PowerPoint Architecture Poster

Symptoms:

- broad boxes labeled with abstractions
- cloud/container/database icons without concrete artifacts
- few or no failure paths
- no human review gate
- no bottom invariant

Reject because it looks polished but does not teach how the project works.

### Mermaid With Makeup

Symptoms:

- linear node chain
- default flowchart logic
- dense arrow spaghetti
- no poster composition
- no clear hierarchy

Reject because it is a graph export, not an infographic.

## Acceptance Boundary

Accept only when the visual has:

- a strong title, subtitle, legend, and bottom thesis
- numbered sections or a clear narrative spine
- transformation, handoff, gates, loops, or causality
- color and icons that reduce reading burden
- enough density to teach the system without becoming a wall of prose
- visible failure, review, blocked, adversarial, or repair paths when those paths exist
