---
name: project-infographic
description: >
  Create and update project infographics as reproducible image artifacts. Use when
  a user asks for a project chart, architecture infographic, visual system map,
  generated diagram image, image spec, or an updateable visual contract for a
  project.
triggers:
  - project infographic
  - architecture infographic
  - create a project chart
  - create an image diagram
  - image spec for a chart
  - updateable visual contract
  - generated systems chart
provides:
  - infographic-spec
  - generated-diagram
  - visual-contract
  - project-architecture-map
composes:
  - project-knowledge
  - create-image
  - create-figure
  - review-design
  - surf
taxonomy:
  - design
  - validation
  - coordination
---

# Project Infographic

Create image-based project infographics from a durable design brief and visual
contract. Do not start with Mermaid, SVG wiring, PowerPoint-style hero graphics,
or a rendered image when the project meaning is still unsettled.

This skill is for project-specific explanatory images. It must prove that the
agent understands the project before drawing it. The target output is a legible
step-by-step visual explanation of how the project works, similar to a technical
workbench map with numbered stages, legends, source-grounded artifact names,
decision points, failure paths, and human review loops.

## Non-Goals

Do not produce:

- incomprehensible Mermaid charts
- dense all-to-all arrow diagrams
- generic PowerPoint hero graphics
- decorative architecture posters
- vague boxes labeled with buzzwords
- visuals that require the author to explain what the arrows mean
- images that look polished but do not teach the project workflow

If the requested project has multiple stages, the infographic must explain the
stages visually. A viewer should be able to follow the project from input,
through processing and feedback, to outputs and failure handling without reading
external prose.

## Workflow

1. Read the project knowledge file if present.
2. Inspect only the project files, docs, and artifacts needed to avoid false architecture claims.
3. Write or update the design brief before generating any image.
4. Mark each visual claim as `implemented`, `intended`, `missing`, or `artifact-derived`.
5. Define explicit failure criteria for rejecting the visual.
6. Define the numbered stages and what each stage receives, does, writes, decides, and hands off.
7. If the user challenged prior output as vague, performative, confusing, illegible, or wrong, stop rendering and get the design brief right first.
8. For complex workflow infographics, create a standalone HTML/CSS render target before exporting PNG.
9. Verify the HTML/CSS render in a browser screenshot before claiming visual completion.
10. Export the PNG only after the design brief is accepted or the user explicitly asks to proceed without review.
11. Copy the HTML/CSS and PNG into the project, preserving the original generated image.
12. Keep the brief, HTML/CSS, prompt, and PNG together so future agents can update the image.

Use `surf` only when the infographic needs to reflect a real UI surface. Use
`project-knowledge` when project purpose, durable decisions, or current state
must be reflected. Use `create-figure` for deterministic charts, `create-image`
for generated image artifacts, and `review-design` when the visual needs an
external critique before implementation.

This skill does not access ArangoDB directly. If project memory is needed, use
`project-knowledge` or `memory` through their skill interfaces.

## Recommended Paths

```text
docs/diagrams/<project>-<topic>-design-brief.md
docs/diagrams/<project>-<topic>.html
docs/diagrams/<project>-<topic>-image-spec.md
docs/diagrams/assets/<project>-<topic>.png
```

## Design Brief Contents

Every design brief must include:

- purpose
- target reader
- core message
- source-grounded project understanding
- source map with file, artifact, or project-knowledge references
- truth labels for implemented, intended, missing, and artifact-derived concepts
- required panels or regions
- numbered stages with input, operation, artifact, decision, output, and failure path for each stage
- required artifact names to show
- readability constraints
- HTML/CSS render plan, including target aspect ratio and export path
- explicit rejection/failure criteria
- open assumptions that need human review

Use `references/design-brief-template.md` as the default structure.

## Image Spec Contents

Every image spec should include:

- current image path, if any
- accepted design brief path
- visual style and layout constraints
- legend
- required title and subtitle
- major bands or regions
- required nodes and edges
- stage-by-stage labels
- per-stage artifacts, decision gates, success paths, and failure paths
- bottom callout or key takeaway
- exact source image prompt
- HTML/CSS source path when the visual is rendered from browser layout
- update rules
- change log

## Rules

- Prefer explicit node/edge contracts over vague prompts.
- Use concise labels; image models often fail with paragraph-heavy text.
- Make the main idea visually central, not implied in side notes.
- Use numbered panels or bands for stages. Each stage must answer: input, action, artifact, decision, output, and failure/human path.
- Use arrows sparingly to show handoffs between stages, not every possible relationship.
- Include a legend only when colors or line styles encode real semantics.
- Prefer standalone HTML/CSS for complex workflow infographics. Browser-rendered HTML/CSS keeps text readable, layout inspectable, and future edits deterministic.
- Use generated-image backends only for illustration-style assets, not as the primary renderer for dense project workflow explanations.
- The HTML/CSS must be self-contained or have project-local assets, render without a dev server when practical, and export cleanly to PNG/PDF via browser screenshot.
- Preserve the generated source prompt verbatim in the spec.
- For evolving projects, update the spec before regenerating the image.
- If the project has a UI shell or host platform, inspect it lightly before drawing boundaries.
- If the user asks to compare to an existing image, match complexity and layout intent, not exact visual content.
- If the user says the image is performative, confusing, lazy, illegible, or does not represent the project, do not patch the image. Rebuild the design brief from source evidence first.
- Do not overclaim clean artifacts. Use `artifact-derived view` when a view is synthesized from multiple artifacts rather than implemented as a first-class file.
- Do not hide weak or missing implementation behind a polished visual. Label gaps directly.
- Avoid spaghetti arrows. Prefer a central loop or spine plus side panels.
- Do not store generated images, screenshots, or batch outputs inside this skill folder.
- Store project-owned PNGs beside the project spec; put heavy or batch artifacts on `/mnt/storage12tb`.
- Do not add README, CHANGELOG, or large reference docs unless the user asks for a human-facing package.

## Required Visual Structure

Default to this structure for complex project infographics:

1. Title and subtitle that state the project mechanism.
2. Compact legend for color semantics and boundaries.
3. Source/input band showing where information enters the system.
4. Numbered workflow bands that explain each project stage.
5. Central loop or spine when the project learns, retries, updates, or evolves.
6. Artifact callouts with exact file or artifact names and short role labels.
7. Decision diamonds only for real gates such as pass/fail, promote/reject, approve/block, or needs-human-review.
8. Failure and human-review band showing blocked, rejected, adversarial, repair, or escalation paths.
9. Bottom takeaway that states the operational invariant the viewer should remember.

## HTML/CSS Render Contract

For complex workflow infographics, the durable source should be an HTML file
with embedded or adjacent CSS. The HTML is the editable visual source; the PNG is
an export artifact.

The HTML/CSS render must:

- use semantic sections for title, legend, numbered stages, loops, artifacts, and failure paths
- use CSS grid/flex layout rather than graph syntax as the primary layout system
- keep all visible text selectable and readable in the browser before export
- use SVG only for small icons, connectors, or simple arrows, not as an opaque diagram blob
- avoid external CDNs unless the project explicitly allows networked rendering
- render from a local `file://` URL or documented static preview command
- be verified with a fresh browser screenshot before the PNG is treated as usable

Use Mermaid only as a scratchpad or small embedded subdiagram when it improves a
local detail. Mermaid must not be the final source for a complex project
infographic.

For each numbered stage, define:

- what enters the stage
- what code, skill, daemon, or human action runs
- what artifact or state is written
- what decision is made
- what advances on success
- what happens on failure or ambiguity

## Failure Criteria

Reject or revise the infographic if it:

- omits the primary user job or project mechanism
- fails to explain the project as numbered stages
- turns an adaptive or evidence-driven system into a generic linear pipeline
- shows unimplemented features as implemented
- hides important failures, dead ends, or negative evidence
- hides where information comes from or where successful evidence is written
- claims operational truth from static or synthesized data
- looks like a PowerPoint hero graphic instead of an explanatory workflow
- uses Mermaid-style syntax, default flowchart styling, or dense unstyled node chains as the final artifact
- lacks an editable HTML/CSS source for a complex workflow infographic
- cannot be rendered locally in a browser for screenshot verification
- uses labels that are too small, dense, or ambiguous to read
- relies on arrows so heavily that the flow cannot be followed
- cannot be traced back to project knowledge, source files, or artifacts

## Validation

After creating the artifact, report:

- design brief path
- HTML/CSS source path, for complex workflow infographics
- image spec path, if generated
- image path
- browser screenshot verification path
- whether the PNG was copied from the generated image directory
- which project sources/artifacts grounded the visual
- any assumptions that still need review
