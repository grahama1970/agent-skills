# Project Infographic Design Brief Template

Use this template before generating or updating a project infographic.

## Purpose

State what the infographic must teach in one sentence.

## Target Reader

Name the primary reader and any secondary reader. Define project-specific terms
that the reader must understand.

## Core Message

State the central project mechanism or decision. This must be visually central,
not implied in notes.

## Visual Non-Goals

List what the image must not become. Default non-goals:

- no incomprehensible Mermaid chart
- no dense all-to-all arrows
- no PowerPoint-style hero graphic
- no generic architecture poster
- no polished image that hides missing or weak implementation

## Source-Grounded Understanding

List the source files, project-knowledge entries, artifacts, screenshots, or
human decisions used to ground the visual.

## Truth Labels

Use one of these labels for every non-obvious concept:

- `implemented` — observed in source, tests, docs, or artifacts.
- `intended` — requested or planned, but not yet proven in implementation.
- `missing` — required for the story but absent or incomplete.
- `artifact-derived` — synthesized from multiple artifacts rather than a first-class artifact.

## Required Panels

Define the major panels or regions. Prefer a central loop or spine plus side
panels over dense all-to-all arrows.

## Render Target

For complex workflow infographics, use standalone HTML/CSS as the durable visual
source and export PNG/PDF from a browser render.

Define:

- HTML path
- exported PNG path
- target viewport/aspect ratio
- whether assets are embedded, local, or external
- screenshot verification command or artifact path

Do not use Mermaid or a generated PowerPoint-style image as the primary source
for dense workflow explanations.

## Numbered Stage Contract

For each numbered stage, define:

| Stage | Input | Operation | Artifact/state written | Decision/gate | Success handoff | Failure/human path |
|-------|-------|-----------|------------------------|---------------|-----------------|--------------------|
| 1 | | | | | | |

Every complex project infographic must be understandable from this table before
any image is generated.

## Required Artifact Names

List exact artifact names that must appear, with one short role label each.

## Readability Constraints

Define constraints such as maximum panels, label length, arrow style, legend
placement, color semantics, and minimum font size.

Default constraints:

- use numbered horizontal bands or panels for stages
- use arrows only for stage handoffs and feedback loops
- use HTML/CSS grid or flex layout as the primary renderer for complex workflows
- keep labels short enough to read in the rendered image
- include a legend only for real color or line semantics
- keep failure/human-review paths visible instead of burying them in prose

## Failure Criteria

Reject the image if it hides the main mechanism, overclaims implementation,
turns feedback loops into a generic pipeline, uses illegible arrows, cannot be
traced to the listed sources, fails to explain the numbered stages, or looks
like a generic Mermaid chart or PowerPoint hero graphic. For complex workflow
infographics, also reject it if there is no editable HTML/CSS source or no
fresh browser screenshot verification.

## Open Assumptions

List assumptions requiring human review before rendering.
