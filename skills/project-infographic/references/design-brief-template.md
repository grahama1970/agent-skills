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

## Project-Knowledge Source

State the exact project-knowledge file path used as the narrative spine.

Include:

- file path
- last observed update date, hash, or version if available
- relevant entries or decisions used
- stale/missing entries that had to be updated before rendering
- source files or artifacts used to verify those entries

Do not use project-knowledge as a substitute for verification when the visual
makes operational claims. If the missing mechanism cannot be verified from
project files, artifacts, or human direction, mark it as `missing` or `open
assumption` and stop before rendering.

## Visual Non-Goals

List what the image must not become. Default non-goals:

- no incomprehensible Mermaid chart
- no dense all-to-all arrows
- no PowerPoint-style hero graphic
- no generic architecture poster
- no polished image that hides missing or weak implementation
- no performative dashboard theater
- no app screen, KPI page, status monitor, or landing page unless explicitly requested

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

## Visual Composition Contract

Define the poster composition before writing HTML/CSS/SVG. This section should
make the visual structure explicit enough that another agent does not turn the
brief into a dashboard or generic card grid.

Load and apply:

- `references/good-infographic-patterns.md`
- `references/dashboard-theater-antipatterns.md`

State the selected approved pattern before listing layout details. Choose one
primary pattern and at most one supporting pattern.

Include:

- selected approved pattern
- primary visual spine: horizontal bands, central hub, radial fanout, swimlanes,
  or loop
- stage geometry: where each numbered stage sits and how the reader follows it
- central emphasis: the object or mechanism that must visually dominate
- icon language: line icons, badges, document/database/person symbols, or no icons
- connector strategy: straight handoffs, curved fanout, dashed dependencies,
  yes/no branches, retry loops
- density target: sparse poster, dense workflow map, or mixed hero plus detail
- dashboard rejection notes: forbidden card grids, KPI panels, nav shells,
  status lanes, and metric blocks
- style reference path if one exists

If a generated image is used to recover visual grammar, treat it as a
style-lock reference only. State which visual features are being copied and
which generated text, counts, paths, or implementation details are ignored as
non-authoritative.

## Visual Acceptance Test

State how the rendered artifact will be judged as an infographic rather than a
dashboard.

Accept if:

- it has a strong title, subtitle, legend, and visual thesis
- it has numbered sections or a clear narrative spine
- it shows transformation, handoff, gates, loops, or causality
- it uses color and icons to reduce reading burden
- it is dense enough to teach the system without becoming a wall of prose
- it keeps failure, review, blocked, adversarial, or repair paths visible when those paths exist

Reject if:

- it looks like a SaaS dashboard
- it looks like an app screen
- it looks like a status page
- it looks like a generic architecture card grid
- it contains fake metrics or health panels
- it removes failure or review paths to make a happy-path diagram

## Render Target

For complex workflow infographics, use standalone HTML/CSS as the durable visual
source with inline SVG connectors as the authoritative browser-rendered artifact.
Use a fixed poster artboard and an inline SVG connector layer for arrows/branches.
PNG/PDF export is optional and only needed for thumbnails, README previews,
visual regression, or external sharing.

Define:

- HTML path
- optional exported PNG path, if needed
- screenshot or browser verification path when available
- target viewport/aspect ratio and exact poster dimensions
- inline SVG `viewBox`; if poster dimensions change, update the viewBox and viewport together
- whether assets are embedded, local, or external
- browser verification command or artifact path
- optional PNG export command, if a PNG is requested
- style-lock reference path and prompt, if a generated image was used to settle
  visual grammar
- style-lock prompt packet path, if `references/style-lock-image-prompt-template.md`
  was used to build the generated-image prompt

Do not use Mermaid, PNG, or a generated PowerPoint-style image as the primary
source for dense workflow explanations. The browser-rendered HTML/CSS/SVG is the
source of truth.

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
- use inline SVG for connectors, branches, and arrowheads
- keep labels short enough to read in the rendered image
- include a legend only for real color or line semantics
- keep failure/human-review paths visible instead of burying them in prose

## Failure Criteria

Reject the image if it hides the main mechanism, overclaims implementation,
turns feedback loops into a generic pipeline, uses illegible arrows, cannot be
traced to the listed sources, fails to explain the numbered stages, lacks a
visual composition contract, or looks like a generic Mermaid chart, PowerPoint
hero graphic, semantic box map, dashboard, app screen, status page, or card
inventory. For complex workflow infographics, also reject it if there is no
editable HTML/CSS/SVG source or no fresh browser verification. Also reject it if
the browser render has clipped text, overlapping labels, connector drift,
unreadable body text, or a dashboard/nav/sidebar/KPI skeleton. If a PNG is
exported, reject it unless the browser-rendered artifact was verified at a
documented viewport first.

## Open Assumptions

List assumptions requiring human review before rendering.
