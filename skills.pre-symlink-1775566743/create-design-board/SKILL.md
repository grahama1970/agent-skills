---
name: create-design-board
version: 1.0.0
description: >
  Generate and maintain iterative design boards from image directories.
  Composite PNG grids, markdown boards with size previews, round tracking,
  and side-by-side comparison tables.
provides:
  - design-board
  - image-comparison
  - visual-iteration
composes:
  - assess
  - review-persona
  - task-monitor
  - create-figure
  - create-gsn-diagram
  - create-image
triggers:
  - create design board
  - design board
  - show design board
  - compare designs
  - update design board
  - append to board
  - assess persona for design
allowed-tools:
  - Bash
  - Read
taxonomy:
  - design
  - visual
  - iteration
  - persona
---

# create-design-board

Point at a directory of images, get a design board. Supports iterative
rounds, composite PNG grids, size previews, and comparison tables.

**Critical lessons** (learned the hard way across 9 rounds of Embry OS icon design
and the /learn-datalake viewer design):

1. Every design iteration MUST start with persona assessment. Visual direction,
   typography, color palette, and icon metaphors all derive from the persona's
   personality, background, and domain. Without this step, you'll waste rounds
   on directions that don't fit (cursive/serif E killed 2 rounds before we
   assessed Embry Lawson's persona).
2. The board must capture design REASONING, not just images. Round 8→9 of the
   Embry icon went through font weight reduction (500→300), glow shell
   elimination, and font reassessment — none of which was on the board until
   we caught the gap. Image tables without context are useless for future rounds.
3. **Persona rationale is MANDATORY.** Every design decision must include the
   persona's thought process IN THEIR VOICE — why they chose this layout, why
   they rejected alternatives, what their workflow demands. Without rationale,
   `/test-interactions` doesn't know WHAT to test or WHY, and the manifest
   can't define success criteria. Learned on 2026-03-14 when the /learn-datalake
   board had trait→decision mapping but no thought process — the human couldn't
   evaluate whether the choices were right because the reasoning was absent.
4. **Rendered mockup images are MANDATORY for interface boards.** ASCII wireframes
   are supplements, not replacements. For UI/interface mockups, write HTML/CSS
   with the actual theme colors, fonts, and layout, then render to PNG via
   browser screenshot. NEVER use diffusion models (`/create-image`, FLUX, etc.)
   for UI mockups — they produce stretched images with garbled text. Diffusion
   models are only appropriate for icons, logos, and artwork. Learned on
   2026-03-14 when the /learn-datalake QuarantineView mockup was generated via
   `/create-image` FLUX and came out stretched with unreadable text, while the
   CascadeView was rendered from HTML/CSS and looked pixel-perfect.
5. **Board structure must follow: image → dialogue → next pane.** The board must
   be scannable pane-by-pane. For each pane/component in a view: show the mockup
   image FIRST, then the designer↔persona dialogue about it, then move on. NEVER
   bury images after walls of ASCII wireframes, spec tables, or rationale text.
   Spec tables go in collapsed `<details>` blocks. The human reads: see image,
   read conversation, next pane. Learned on 2026-03-15 when the /learn-datalake
   board was 1,423 lines of spec tables with buried dialogue — the human said
   "the whole point of a design board is clarity, legibility, and organization"
   and graded it D. Restructuring to image→dialogue→pane cut it to 657 lines
   and made it actually readable.
6. **Per-pane mockups, not just full-view composites.** Each view needs BOTH a
   full-view composite screenshot AND individual per-pane/per-section mockups.
   A single composite for a 3-panel view shows the layout but not the details.
   Individual pane mockups (960px wide HTML rendered to PNG) let the human
   inspect each component's typography, spacing, colors, and data density.
   For a view with N panes, produce N+1 images: 1 composite + N pane mockups.
   Learned on 2026-03-15 when Views 1-7 each had only ONE composite screenshot
   and the human asked "why do you still refuse to create an image per component?"
7. **Reality-check every feature via `/dogpile` before designing dialogue.**
   Run `/dogpile` for each major feature BEFORE writing persona dialogue about
   it. Research may kill features that no practitioner actually uses, saving
   hours of design and implementation effort. Include findings as a "Reality
   Check" subsection. If research validates the feature, proceed with confidence.
8. **`/dogpile` can search at the wrong altitude — domain personas must correct it.**
   Research may return results at the wrong abstraction level (e.g., industry-wide
   cadence vs. program-level cadence). Always let domain personas push back on
   research findings — they know their operational reality. Record both the
   research AND the persona correction as canon.
   Format: `**Persona** (pushback on /dogpile research): "..."`.
9. **Shared components need one mockup, multiple entry points documented.**
   When a component (slide-over, panel, modal) is accessed from multiple views,
   create one HTML mockup and document each view's entry point (trigger button,
   context passed, persona who uses it). Avoid duplicating the mockup per view.
10. **Human interjection protocol.** The human MUST be able to interject in
   persona dialogues. Format: `**Human** (interjection): "..."`. Human corrections
   replace the original dialogue and become canon. Human can also direct personas
   to `/dogpile` mid-conversation. Document this protocol in the board's preamble.
11. **Functional spec BEFORE mockups (FAIL if missing).** Every interface design
   board MUST include a concrete list of exactly what the interface will do —
   the pipeline/workflow steps it visualizes, with skills, inputs, outputs, and
   human gates documented per step. This goes BEFORE any mockups. Without this,
   the designer has nothing to compare their mockups against and the mockups
   drift into generic dashboards that don't match the actual system. Learned on
   2026-03-16 when the music-lab design board R1 produced generic dashboard
   mockups (empty card covers, invisible pipeline content) because there was no
   concrete pipeline spec to compare against. R2 fixed this by writing the full
   7-phase pipeline first, then designing views to show each phase's artifacts.
   `/review-plan` will grade design boards as **FAIL** if no functional spec
   section exists before the first mockup image.

## Rules (non-negotiable)

1. **DESIGN_BOARD.md is the single source of truth.** Every round, every
   decision, every eliminated direction MUST be recorded there. If it's not
   on the board, it didn't happen.
2. **Update the board after EVERY round** — not just image tables. Include:
   - What changed and WHY (font weight, color, layout decisions)
   - What was eliminated and WHY (directions that don't fit persona)
   - User feedback quotes that drove the change
   - Cross-round progression (e.g. "Round 8→9: eliminated glow shell")
3. **The `append` command adds image tables.** Design reasoning must be added
   separately — either via `--notes` (brief) or by manually appending a
   "Key Decisions" section after the image table. The tool handles images;
   YOU handle reasoning.
4. **Never skip persona assessment.** Round 1 must start with `assess-persona`.
5. **Board structure: image → dialogue → next pane.** Each view section follows:
   - Full-view composite image (overview)
   - For each pane: pane mockup image → Steve↔Nico dialogue → `<details>` spec
   - Test implications summary at end of view section
   - Appendices (info architecture, data flow, test manifest) at board end
   Spec tables, ASCII wireframes, and implementation details go in collapsed
   `<details><summary>Spec</summary>` blocks — never inline.
5. **Persona rationale in first person.** Every design decision MUST include
   the persona speaking in their own voice explaining WHY. The format is:
   ```markdown
   > **Why [design choice]?**
   >
   > "[Persona's reasoning in first person, referencing their workflow,
   > preferences, and constraints from their persona YAML]"
   >
   > **Test implication**: [What `/test-interactions` should verify based
   > on this rationale — specific, measurable criteria]
   ```
   This is not optional. Without persona rationale:
   - `/test-interactions` doesn't know what to test or why
   - The manifest can't define success criteria from the user's perspective
   - The human reviewer can't evaluate whether choices are correct
   - Future rounds lose context on why decisions were made
6. **Render UI mockups from HTML/CSS, not diffusion models.** For each view:
   1. Write an HTML file with inline CSS using the exact theme (colors, fonts,
      spacing from the board's palette)
   2. Populate with realistic data (real filenames, plausible scores, actual
      labels — not Lorem Ipsum)
   3. Render to PNG via browser screenshot (`playwright screenshot`,
      `wkhtmltoimage`, or Python `playwright`/`selenium`)
   4. Save HTML to `figures/<view>_mockup.html` (viewable in browser)
   5. Save PNG to `figures/<view>_mockup.png` (embedded in board)

   The HTML file IS the mockup — it's deterministic, readable, and pixel-accurate.
   The PNG is a screenshot for embedding in DESIGN_BOARD.md.

   **When to use `/create-image` (diffusion models):**
   - Icons, logos, artwork, visual concepts
   - NOT for UI layouts, dashboards, data tables, or anything with text

   ASCII wireframes may accompany HTML mockups as technical reference, but every
   view section MUST have a `![View Mockup](figures/view_mockup.png)` image.
   The Verification Checklist enforces this.

## Workflow (learned from 9 rounds of Embry OS icon design)

1. **Assess persona** (`assess-persona`) — Read persona YAML, extract traits,
   map to typographic and visual attributes. This eliminates wrong directions
   before any images are generated.
2. **Generate visuals** — For UI/interface boards: write HTML/CSS and render to PNG
   (see Rule 6). For icon/logo/artwork boards: use `/create-image`
3. **Build board** (`board` or `append`) — Create/update the design board markdown
4. **Generate composite** (`composite`) — Visual grid for quick comparison
5. **Collect feedback** — User reviews, provides quotes
6. **Update board with reasoning** — ALWAYS update DESIGN_BOARD.md after every
   round. Add BOTH the image table (via `append`) AND a design decisions section
   explaining what changed, what was eliminated, and why. The board must tell
   the story of the design evolution, not just show thumbnails.
7. **Repeat** from step 2 with narrowed direction

## Interface & Pipeline Design Boards

Not all design boards are about icons. For UI interfaces, pipeline outputs, and
report formats, the design board must show **what the output actually looks like**.

### Rules for Interface Boards

1. **Show the exact output.** Include rendered examples of what the skill produces —
   report sections, pipeline stages, data tables. Not descriptions of them.
2. **Use HTML color swatches** in markdown, not plain hex strings. Colors must be
   visible in the document:
   ```html
   <span style="background:#e74c3c;color:white;padding:2px 8px;border-radius:3px">RED #e74c3c</span>
   ```
3. **Generate figures** using available skills, don't describe them in ASCII:
   - `/create-figure workflow` — pipeline flow diagrams (SVG/PNG)
   - `/create-gsn-diagram` — assurance case / evidence structure diagrams
   - `/create-figure architecture` — system architecture diagrams
   - Mermaid code blocks — for inline flowcharts in markdown
4. **Include a rendered output example.** Show what one complete unit of output
   looks like (one report section, one evidence case, one pipeline run). Use
   real data from a test fixture, not placeholder text.
5. **Link generated figures** from `figures/` subdirectory. Design boards that
   describe visual output without showing it are unacceptable.

### Interface Board Sections

| Section | Purpose | How |
|---------|---------|-----|
| Color Palette | Show actual colors | HTML `<span>` swatches |
| Pipeline Flow | Show processing stages | `/create-figure workflow` SVG |
| Evidence Structure | Show CAE/GSN tree | `/create-gsn-diagram` SVG |
| Output Example | Show one rendered unit | Actual markdown/HTML output |
| Viewer Layout | Show UI arrangement | HTML/CSS rendered to PNG (see Rule 6) |

### Shared Component Pattern (Slide-Over Panels)

When a component is accessed from multiple views, design it as a **slide-over panel**
(not a modal or page navigation). Slide-overs preserve context — the user sees the
triggering view behind the panel.

- **Width**: 480px (standard), `#0f1216` background, 1px `#1e252d` left border
- **Entry points**: Document each view's trigger button/action
- **One mockup**: Create one HTML mockup of the panel, link it once, reference from all views
- **Example**: A detail panel accessed from a data table ("+ Detail" button), a graph view
  ("Verify" on node), and a list view ("Check" on row). Same React component, multiple triggers.

### Human Interjection Protocol

For boards with persona dialogues, the human must be able to:
1. **Interject** with domain knowledge: `**Human** (interjection): "..."`
2. **Correct** persona misconceptions: `**Human** (correction): "..."`
3. **Direct** personas to research: `**Human** (directing /dogpile): "..."`
4. **Provide context** before persona speaks: `**Human** (context for Persona): "..."`

Human corrections replace the original dialogue and become canon. This protocol
must be documented in the board's preamble section (before View 1).

### Persona Assessment for Interfaces

For interface design boards, persona assessment maps to:
- **Audience expertise** — determines information density and jargon level
- **Review workflow** — determines what needs to be scannable vs. detailed
- **Compliance context** — determines printability, color choices, accessibility

## Commands

### `assess-persona` -- Assess persona YAML for design direction (ALWAYS DO THIS FIRST)

Reads a persona YAML file and generates a persona-to-design mapping section
for the design board. Maps personality traits to typography, color, iconography,
and visual style recommendations. Composes `/assess` and `/review-persona`.

```bash
./run.sh assess-persona --persona /path/to/persona.yaml --output ./DESIGN_BOARD.md
./run.sh assess-persona --persona /path/to/persona.yaml  # stdout only
```

### `board` -- Generate design board markdown from image directory

```bash
./run.sh board --images ./icons/v7/ --output ./icons/DESIGN_BOARD.md --title "Embry OS Icon Concepts"
```

### `append` -- Add a new round to an existing board

```bash
./run.sh append --images ./icons/v8/ --board ./icons/DESIGN_BOARD.md --round "Round 6" --notes "Clean sans-serif E with dense starfield"
```

### `composite` -- Generate composite PNG grid

```bash
./run.sh composite --images ./icons/v7/ --output ./icons/v7/board.png --cols 3 --bg "#0e0e1c" --title "Round 5"
```

### `compare` -- Side-by-side comparison of specific images

```bash
./run.sh compare --images img1.png img2.png img3.png --output comparison.png --labels "Option A" "Option B" "Option C"
```

### `sizes` -- Generate size variant previews

```bash
./run.sh sizes --image ./icons/v7/F2_minimal_nebula.png --output ./icons/v7/F2_sizes/
```

### Options

| Flag       | Description                              |
|------------|------------------------------------------|
| `--images` | Directory of PNGs/JPGs or list of files  |
| `--output` | Output file or directory                 |
| `--title`  | Board or section title                   |
| `--cols`   | Grid columns (default: 3)               |
| `--bg`     | Background color (default: `#0e0e1c`)   |
| `--round`  | Round name for append                    |
| `--notes`  | Round notes for append                   |
| `--labels` | Labels for compare mode                  |
| `--board`  | Existing board markdown for append       |

## Verification Checklist (MANDATORY — run before declaring board complete)

**After generating a design board, you MUST verify these items. Do NOT skip this.**

1. **Per-pane mockups exist.** For each view with N panes, `figures/` must
   contain N+1 images: 1 full-view composite + N individual pane mockups.
   A single composite per view is NOT sufficient. Each pane must have its
   own 960px-wide HTML mockup rendered to PNG.

2. **Board follows image → dialogue → pane structure.** Each view section must:
   - Start with the full-view composite
   - Then for each pane: show pane mockup, then Steve↔Nico dialogue about it
   - Spec tables must be in `<details>` blocks, not inline
   - Test implications at end of view section
   - NO ASCII wireframes without an accompanying rendered mockup

3. **Images are linked in the board.** Every PNG in `figures/` must appear
   as a `![description](figures/filename.png)` reference in DESIGN_BOARD.md.
   Unlinked images are invisible to readers.

4. **No spec-table dominance.** The board must be readable by a human scanning
   pane-by-pane. If spec tables, CSS values, or implementation details appear
   outside of `<details>` blocks, they must be brief (< 5 rows). Long specs
   go in collapsed sections.

5. **Color swatches are HTML spans, not plain hex.** Every color in the palette
   table must use `<span style="background:...">` for visual rendering.

6. **Persona rationale exists for every pane.** Each pane must have both a
   Steve quote (designer disposition) and a Nico quote (persona response).
   Check:
   - Does the dialogue flow naturally after the image?
   - Are pushbacks clearly marked and resolved?
   - Would `/test-interactions` be able to derive tests from the dialogue?

7. **Test implication → manifest mapping table exists.** The board must include
   a summary table mapping persona rationale to test scenarios with pass criteria.
   This table is the bridge between design intent and `/test-interactions` manifest.

8. **Board length is proportional to content, not ceremony.** A 7-view workbench
   should be ~500-700 lines, not 1400+. If the board exceeds 800 lines, audit
   for duplicated rationale, redundant spec tables, and dialogue that restates
   what Steve already said. Cut ruthlessly.

9. **Reality check section exists for complex features.** Any feature that
   involves a non-obvious workflow (auto-generated data, cross-view shared
   components, cascade feedback loops) must have a "Reality Check" subsection
   with `/dogpile` research findings BEFORE the persona dialogue about it.
   The research validates or kills the feature before design effort is spent.

10. **Shared component entry points documented.** If a component (slide-over,
    modal, panel) is accessible from multiple views, each view's section must
    reference the component and explain HOW that persona accesses it (button
    label, trigger action, context). One mockup, N entry point descriptions.

11. **Human interjection format present.** If the board includes persona
    dialogues, verify that `**Human** (interjection)` or `**Human** (context)`
    lines exist where the human provided domain corrections. Boards without
    any human voice in multi-persona dialogues are suspect — the human likely
    wasn't engaged in the review.

**If any check fails, fix it before returning the board to the user.**

## Common Mistakes

### WRONG: Skipping persona assessment and jumping to visuals
```bash
./run.sh board --images ./icons/v1/ --output DESIGN_BOARD.md
# No persona assessment — wrong visual direction wastes rounds
```

### RIGHT: Always assess persona first
```bash
./run.sh assess-persona --persona /path/to/persona.yaml --output DESIGN_BOARD.md
./run.sh board --images ./icons/v1/ --output DESIGN_BOARD.md
```

### WRONG: Using /create-image (diffusion) for UI mockups
```bash
# FLUX generates stretched images with garbled text for UI layouts
create-image "dashboard with sidebar and data table" --output mockup.png
```

### RIGHT: Write HTML/CSS and render to PNG for UI mockups
```bash
# Write HTML with exact theme colors, render via browser screenshot
playwright screenshot mockup.html --output mockup.png
```

### WRONG: Board with only image tables and no design reasoning
```markdown
| Round 1 | img1.png | img2.png |
```

### RIGHT: Board captures WHAT changed, WHY, and persona rationale
```markdown
## Round 1 → 2: Eliminated serif fonts
> **Embry**: "Serif feels too traditional for a systems dashboard..."
> **Test implication**: Verify all text uses Inter/sans-serif family
```
