---
name: project-infographic
description: >
  Create and update project infographics as reproducible browser-rendered artifacts. Use when
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
  - agentic-evals
taxonomy:
  - design
  - validation
  - coordination
disciplines:
  - content-creation
  - ui-design-engineering
---

# Project Infographic

Create browser-rendered project infographics from a durable design brief and
visual contract. Do not start with Mermaid, SVG wiring, PowerPoint-style hero
graphics, PNG export, or a rendered image when the project meaning is still
unsettled.

This skill is for project-specific explanatory infographics. It must prove that
the agent understands the project before drawing it. The target output is a
legible, zoomable, selectable browser-rendered explanation of how the project
works, similar to a technical workbench map with numbered stages, legends,
source-grounded artifact names, decision points, failure paths, and human review
loops.

This skill creates explanatory technical infographics, not app screens,
dashboards, KPI pages, status monitors, landing pages, or Mermaid diagrams. A
dashboard reports current state. An infographic explains system meaning, flow,
causality, and review logic.

## Non-Goals

Do not produce:

- incomprehensible Mermaid charts
- dense all-to-all arrow diagrams
- generic PowerPoint hero graphics
- decorative architecture posters
- vague boxes labeled with buzzwords
- visuals that require the author to explain what the arrows mean
- images that look polished but do not teach the project workflow
- performative dashboard theater

If the requested project has multiple stages, the infographic must explain the
stages visually. A viewer should be able to follow the project from input,
through processing and feedback, to outputs and failure handling without reading
external prose.

## Workflow

1. Read the project knowledge file if present and treat it as the narrative spine for the infographic.
2. If project knowledge is absent, stale, or missing the relevant project mechanism, update it through `project-knowledge` before rendering.
3. Inspect only the project files, docs, and artifacts needed to verify project-knowledge claims or fill explicitly labeled gaps.
4. Write or update the design brief before generating any image.
5. Mark each visual claim as `implemented`, `intended`, `missing`, or `artifact-derived`.
6. Define explicit failure criteria for rejecting the visual.
7. Define the numbered stages and what each stage receives, does, writes, decides, and hands off.
8. Load `references/good-infographic-patterns.md` and `references/dashboard-theater-antipatterns.md`; choose one approved infographic pattern and name dashboard-theater structures to reject.
9. Define the visual composition contract before writing HTML: poster rhythm, primary visual spine, section geometry, icon language, card density, connector style, and what would make the result look like a dashboard.
10. If the user challenged prior output as vague, performative, confusing, illegible, dashboard-like, or wrong, stop patching the prior render. Rebuild the design brief and composition contract first.
11. If the visual grammar is unsettled or a prior HTML pass drifted into dashboard/card layout, create a generated-image style reference first. Treat it as a style-lock artifact only, not as the authoritative source.
12. Build the style-reference image prompt with `references/style-lock-image-prompt-template.md`; it must comply with `best-practices-prompt` and output a prompt packet with source map, rejection checks, and HTML conversion notes.
13. Convert the approved style reference into a deterministic fixed-poster HTML/CSS/SVG template with selectable text and inline SVG connectors. Use `references/html-svg-reconstruction-rules.md`. Do not trace or OCR generated text blindly.
14. For complex workflow infographics, create a standalone fixed-poster HTML/CSS/SVG render target with an inline SVG connector layer.
15. Verify the HTML/CSS/SVG render in a browser before claiming visual completion.
16. Export a PNG only when explicitly requested or when the project needs a static thumbnail, README preview, visual regression artifact, or external sharing artifact.
17. Copy the HTML/CSS/SVG source and verification evidence into the project. Preserve any generated style reference separately as historical/reference material, not as the authoritative source.
18. Keep the brief, HTML/CSS/SVG source, verification notes, optional generated prompt packet, optional style reference image, and optional PNG together so future agents can update the infographic.

Use `surf` only when the infographic needs to reflect a real UI surface.
Use `project-knowledge` as the default source of project purpose, durable
decisions, current state, and workflow narrative. Source files and artifacts are
verification inputs, not a substitute for project knowledge. Use `create-figure`
for deterministic charts, `create-image` for generated image artifacts, and
`review-design` when the visual needs an external critique before implementation.
Project-knowledge updates must be source-grounded. If the agent cannot verify a
missing mechanism from project files, artifacts, or human direction, it must mark
the gap as `missing` or `open assumption` and stop before rendering.

This skill does not access ArangoDB directly. If project memory is needed, use
`project-knowledge` or `memory` through their skill interfaces.

## Deliverable Contract

The authoritative deliverable is the browser-rendered HTML/CSS/SVG infographic.

Primary artifact:

- self-contained HTML/CSS/SVG infographic
- fixed poster canvas
- zoomable in browser
- selectable/searchable text
- inline SVG connectors
- no dashboard/app-shell layout

Optional artifact:

- PNG screenshot/export only when explicitly requested or needed for README,
  sharing, visual regression, or embedding elsewhere

Do not optimize the artifact for PNG first. Optimize it for a readable,
zoomable, inspectable browser-rendered infographic.

## Good Infographic Design Patterns

Use `references/good-infographic-patterns.md` before writing or rebuilding a
complex infographic. Choose one primary pattern and at most one supporting
pattern:

- Stack-to-feedback-loop poster
- Evidence-envelope pipeline
- Human-review course-correction map
- Hub-and-spoke workbench

Good infographic outputs have:

- poster composition: fixed canvas, strong title, subtitle, legend, and bottom thesis
- narrative spine: clear beginning -> transformation -> decision -> outcome
- numbered bands or lanes: each section teaches one layer of the system
- visual hierarchy: one dominant object, secondary stages, supporting details
- dense but readable structure: compact labels, meaningful grouping, no empty dashboard whitespace
- connector logic: arrows, branches, diamonds, loops, fan-outs, and return paths
- icon-led scanning: simple line icons that identify stage roles quickly
- color semantics: colors mean artifact type, risk state, review state, or system boundary
- editorial compression: fewer words per box, more meaning per visual relationship

## Reject Performative Dashboard Theater

Use `references/dashboard-theater-antipatterns.md` before accepting a visual.
Reject outputs that use:

- KPI strips
- fake health metrics
- status cards
- queue panels
- nav sidebars
- app chrome
- generic product-page layouts
- equal-sized card grids
- metric tiles
- system-overview dashboards
- landing-page hero sections
- Mermaid-style boxes with prettier borders
- large whitespace that removes workflow density
- monitor UI unless the actual requested artifact is a monitor

## Style-Lock Recovery Mode

Use style-lock recovery when any of these are true:

- the user explicitly asks to create an image first
- a prior HTML/CSS/SVG attempt looked like a dashboard, app screen, status map,
  generic cards, or semantic box inventory instead of an infographic
- the visual grammar is not settled enough to implement directly
- the user provides an existing infographic image and asks to match its visual
  language

Style-lock recovery is a design step, not the final production pipeline:

1. Write a source-grounded prompt from the accepted design brief and numbered
   stage contract.
2. Use `references/style-lock-image-prompt-template.md` to create a
   `StyleLockPromptPacket` JSON object. The packet must contain the image prompt,
   source map, non-authoritative warnings, rejection checks, and HTML conversion
   notes.
3. Generate or select one style reference image that establishes visual grammar:
   layout rhythm, icon density, central emphasis, connector routing, section
   balance, and failure-loop treatment.
4. Review the image for visual grammar only. Do not trust generated text,
   counts, file paths, sockets, identifiers, or implementation status.
5. Record the prompt packet and image path in the image spec under
   `Style Reference / Historical Material`.
6. Rebuild the approved composition as HTML/CSS/SVG using project-grounded text
   from the design brief, not OCR from the image.
7. Future routine updates should modify the structured spec/template. Do not
   generate a new image for every project-knowledge change unless the visual
   language itself needs redesign.

The generated image may be visually authoritative for style, but it is never
authoritative for facts. The HTML/CSS/SVG remains the canonical artifact after
conversion.

## Recommended Paths

```text
docs/diagrams/<project>-<topic>-design-brief.md
docs/diagrams/<project>-<topic>.html
docs/diagrams/<project>-<topic>-image-spec.md
docs/diagrams/assets/<project>-<topic>.png  # optional export/convenience artifact
docs/diagrams/<project>-<topic>-style-lock-prompt.json  # when style-lock recovery is used
```

## Design Brief Contents

Every design brief must include:

- purpose
- target reader
- core message
- project-knowledge source section with the exact file path and relevant entries
- source-grounded project understanding
- source map with file, artifact, or project-knowledge references
- truth labels for implemented, intended, missing, and artifact-derived concepts
- required panels or regions
- numbered stages with input, operation, artifact, decision, output, and failure path for each stage
- visual composition contract: primary visual spine, stage geometry, icon set,
  card density, connector strategy, and dashboard anti-patterns to avoid
- style-reference plan when style-lock recovery is needed
- required artifact names to show
- readability constraints
- HTML/CSS/SVG render plan, including target aspect ratio, poster dimensions, and source path
- explicit rejection/failure criteria
- open assumptions that need human review

Use `references/design-brief-template.md` as the default structure.

## Image Spec Contents

Every image spec should include:

- current authoritative HTML/CSS/SVG path and optional image/PNG path, if any
- accepted design brief path
- visual style and layout constraints
- style reference image or generated-image prompt when style-lock recovery was used
- legend
- required title and subtitle
- major bands or regions
- required nodes and edges
- stage-by-stage labels
- per-stage artifacts, decision gates, success paths, and failure paths
- bottom callout or key takeaway
- generated-image prompt only when a generated image, illustration asset, or
  style-lock reference was used; for browser-rendered infographics, preserve
  any prior prompt as historical reference, not as the source of truth
- HTML/CSS/SVG source path when the visual is rendered from browser layout
- browser verification path/command when available
- PNG export command only when a PNG is requested or required
- update rules
- change log

## Rules

- Prefer explicit node/edge contracts over vague prompts.
- Use concise labels; image models often fail with paragraph-heavy text.
- Make the main idea visually central, not implied in side notes.
- Use numbered panels or bands for stages. Each stage must answer: input, action, artifact, decision, output, and failure/human path.
- Use arrows sparingly to show handoffs between stages, not every possible relationship.
- Include a legend only when colors or line styles encode real semantics.
- Prefer standalone fixed-poster HTML/CSS plus inline SVG connectors for complex workflow infographics. Browser-rendered HTML/CSS keeps text readable, layout inspectable, and future edits deterministic; inline SVG keeps arrows, branches, dashed dependency paths, and curved connector routing precise.
- Use generated-image backends only for style-lock references or illustration-style assets, not as the primary renderer or ongoing regeneration mechanism for dense project workflow explanations.
- The HTML/CSS/SVG must be self-contained or have project-local assets and render without a dev server when practical.
- Treat complex workflow infographics as fixed poster canvases, not dashboards. Use a bounded artboard such as `width: 1440px; height: 2000px; position: relative;` inside a centered wrapper. Do not let the primary diagram become a responsive app layout with generic cards.
- Preserve the generated source prompt verbatim in the spec.
- For evolving projects, update the spec before regenerating the image.
- If the project has a UI shell or host platform, inspect it lightly before drawing boundaries.
- If the user asks to compare to an existing image, match complexity and layout intent, not exact visual content.
- If the user says the image is performative, confusing, lazy, illegible,
  dashboard-like, or does not represent the project, do not patch the image.
  Rebuild the design brief and visual composition contract from source evidence
  first. If the failure is visual rather than factual, use style-lock recovery
  before another HTML/CSS/SVG implementation attempt.
- Do not overclaim clean artifacts. Use `artifact-derived view` when a view is synthesized from multiple artifacts rather than implemented as a first-class file.
- Do not hide weak or missing implementation behind a polished visual. Label gaps directly.
- Avoid spaghetti arrows. Prefer a central loop or spine plus side panels.
- Do not store generated images, screenshots, or batch outputs inside this skill folder.
- Store project-owned PNGs beside the project spec; put heavy or batch artifacts on `/mnt/storage12tb`.
- Do not add README, CHANGELOG, or large reference docs unless the user asks for a human-facing package.

## Visual Composition Contract

Before writing the fixed-poster HTML/CSS/SVG, define the poster composition in
plain language. The contract must be specific enough that another agent could
build the same layout without inventing a dashboard.

Include:

- selected approved pattern from `references/good-infographic-patterns.md`
- primary visual spine: horizontal bands, central hub, radial fanout, swimlanes,
  or loop
- stage geometry: where each numbered stage sits and how it reads from left to
  right or top to bottom
- central emphasis: which object must visually dominate
- icon language: simple line icons, badges, document/database/person symbols,
  or no icons
- connector strategy: straight handoffs, curved fanout, dashed dependencies,
  yes/no branches, retry loops
- density target: sparse poster, dense workflow map, or mixed hero plus detail
- dashboard rejection notes: which card grids, KPI panels, nav shells, status
  lanes, or metric blocks are forbidden
- style reference path if one exists

For image-first recovery, the composition contract should explicitly say which
parts of the generated image are being copied as style and which generated text
or details are being ignored as non-authoritative.

## Visual Acceptance Test

The output is acceptable only if a human can immediately tell it is an
infographic/poster.

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

## HTML/CSS/SVG Render Contract

For complex workflow infographics, the durable source should be an HTML file
with embedded or adjacent CSS and inline SVG connectors. The HTML/CSS/SVG is the
editable visual source and authoritative artifact. PNGs are optional
convenience exports.

The HTML/CSS/SVG render must:

- use a fixed poster artboard with explicit pixel dimensions and a documented export viewport; optional outer wrappers may scale/center the poster for local preview, but the infographic itself must have stable geometry
- use semantic sections for title, legend, numbered stages, loops, artifacts, and failure paths
- use CSS grid/flex layout rather than graph syntax as the primary layout system
- keep all visible text selectable and readable in the browser before export
- use an inline SVG connector layer for arrows, branch paths, dashed dependency lines, yes/no routes, cross-section connectors, and curved routing
- keep content blocks, cards, labels, badges, legends, and typography in HTML/CSS rather than putting all text into SVG
- use SVG only for icons/connectors/simple arrows, not as an opaque full-diagram blob
- avoid external CDNs unless the project explicitly allows networked rendering
- render from a local `file://` URL or documented static preview command
- be verified in a fresh browser render before the infographic is treated as usable
- if the poster dimensions change, update the inline SVG `viewBox` and documented export viewport together; do not let content growth silently desynchronize connector coordinates

Use Mermaid only as a scratchpad or small embedded subdiagram when it improves a
local detail. Mermaid must not be the final source for a complex project
infographic.

### Fixed Poster + Inline SVG Pattern

Use this pattern for dense project workflow images:

```html
<main class="poster" aria-label="Project workflow infographic">
  <svg class="connectors" viewBox="0 0 1440 2000" aria-hidden="true">
    <defs>
      <marker id="arrow-blue" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">
        <path d="M0,0 L10,5 L0,10 Z" fill="#155eef"></path>
      </marker>
    </defs>
    <path d="M180 420 H360" stroke="#155eef" stroke-width="3" marker-end="url(#arrow-blue)"></path>
  </svg>
  <section class="lane lane-blue">...</section>
</main>
```

```css
.poster {
  width: 1440px;
  height: 2000px;
  margin: 0 auto;
  position: relative;
  background: #f8fafc;
}
.connectors {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 1;
}
.lane,
.card {
  position: relative;
  z-index: 2;
}
```

The SVG layer should route flow. The HTML/CSS layer should carry the meaning. This keeps the result editable, selectable, and visually close to a real technical infographic instead of a dashboard.

## Browser Verification

Before completion, verify the HTML/CSS/SVG artifact in a browser at the
documented poster viewport. Producing an HTML file is not proof by itself; the
agent must inspect the rendered artifact and report the visual checks.

Required verification report:

- HTML source path
- viewport width and height
- browser command or static preview command
- screenshot or visual verification path when available
- confirmation that no text is clipped, overlapped, unreadably small, or hidden outside the poster
- confirmation that connectors align with their intended source/target blocks
- confirmation that visible labels remain selectable in the browser HTML
- confirmation that the artifact looks like an infographic/poster, not a dashboard

PNG export is optional. If a PNG is requested or required, also report:

- exported PNG path
- exported PNG dimensions
- exact export command

Optional PNG export pattern:

```bash
npx playwright screenshot \
  --viewport-size=1440,2000 \
  file://$PWD/docs/diagrams/<project>-<topic>.html \
  docs/diagrams/assets/<project>-<topic>.png
```

If Playwright is unavailable, use a documented Chromium/headless-browser
screenshot command or the project's approved `surf` screenshot path. In all
cases, report the command, viewport, verification path, and visual inspection
result.

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
- looks like a semantic box map, status dashboard, app mockup, or card inventory
  even if the labels are factually correct
- uses Mermaid-style syntax, default flowchart styling, or dense unstyled node chains as the final artifact
- lacks an editable HTML/CSS/SVG source for a complex workflow infographic
- cannot be rendered locally in a browser for visual verification
- treats a PNG as the authoritative source instead of the browser-rendered HTML/CSS/SVG
- exports a PNG without verifying the browser-rendered artifact at the documented viewport
- has clipped text, overlapping labels, connector drift, or unreadable body text in the browser screenshot
- uses labels that are too small, dense, or ambiguous to read
- relies on arrows so heavily that the flow cannot be followed
- uses responsive dashboard layout conventions instead of a fixed poster/diagram canvas
- uses a nav/sidebar/KPI-card/dashboard skeleton as the primary structure
- presents metrics, health cards, queues, or generic status panels that are not required by the project narrative
- looks like an application screen instead of a poster/diagram artifact
- lacks a visual composition contract for a complex infographic
- repeats a previously rejected visual structure after the user identified it as
  dashboard-like or performative
- uses generated-image text, paths, counts, or implementation labels as factual
  proof instead of the design brief/project sources
- puts most meaningful text inside SVG instead of selectable HTML/CSS blocks
- cannot be traced back to project knowledge, source files, or artifacts

## Validation

After creating the artifact, report:

- design brief path
- HTML/CSS/SVG source path, for complex workflow infographics
- image spec path, if generated
- optional image/PNG path, if exported
- browser verification path or screenshot path when available
- whether an optional PNG was exported and where it lives
- which project sources/artifacts grounded the visual
- any assumptions that still need review
