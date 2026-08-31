# grahama.co — design contract

This is the implementation-level design contract for grahama.co. It is specific
on purpose: a vague `DESIGN.md` is not a contract.

Companion files:

- `site/BRAND.md` — brand/personality/audience intent.
- `site/VOICE.md` — prose and first-person voice contract.
- `site/design-world.yml` — machine-readable visual-world contract.
- `site/DESIGN_WORLD.md` — readable visual-world summary.
- `site/app/globals.css` — executable CSS source of truth.

## 1. Design goal

Make grahama.co feel like Graham's artifact room: dark, curious, severe,
entertaining, technically exact, and personal. It should be discovered rather
than consumed as a normal value proposition.

The site is not an enterprise AI/R&D-tech positioning page, not a services menu,
not a Palantir clone, and not a Straive-style AI operations funnel.

## 2. CSS source of truth

The shipped implementation lives in `site/app/globals.css`. This document names
rules that future edits must preserve; it does not replace the CSS.

Required source markers:

- `@font-face` registers `Fraunces` from `/fonts/fraunces-site-subset.woff2`.
- `:root` declares the core color, font, wrapping, and gutter tokens.
- `@theme inline` maps the site tokens for retained Tailwind components.
- `prefers-reduced-motion` blocks exist for the animated surfaces.

## 3. Design tokens

Core CSS variables in `site/app/globals.css`:

```css
--ink: #0c0908;
--ink-1: #110d0b;
--ink-2: #181211;
--ink-3: #211917;
--paper: #f2eadc;
--text: #ece2d3;
--muted: #a99787;
--faint: #8f7f72;
--brass: #e2ac62;
--ember: #d1703c;
--sage: #93a289;
--line: rgba(236, 226, 211, 0.13);
--line-2: rgba(236, 226, 211, 0.055);
--serif: 'Fraunces', 'Iowan Old Style', Palatino, Georgia, serif;
--sans: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
--mono: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace;
--gut: clamp(18px, 3.2vw, 44px);
--wrap: min(1260px, 92vw);
```

Token roles:

- `--ink` is the main ground. Do not invert the site to a white corporate page.
- `--paper` is for scoped evidence plates and export surfaces, not the default
  canvas.
- `--brass` is evidence/attention, not generic decoration.
- `--ember` marks contradiction, failure, risk, or heat.
- `--sage` marks semantic state, pass/continuity, or living system signals.
- `--mono` is for machine output only: SHAs, paths, counts, generated values,
  receipt payloads, and source identifiers.

## 4. Typography

Font files:

- `/fonts/fraunces-site-subset.woff2`
- `/fonts/fraunces-var.woff2` for downstream resume PDF instancing via
  `scripts/build_resume_fonts.py`.

Roles:

- Display: `Fraunces`, via `--serif`.
- Reading prose: system sans via `--sans`.
- Utility labels: system sans small-caps, not monospace.
- Data figures: Fraunces or tabular numeric treatment.
- Machine output: `--mono` only.

Executable CSS anchors:

- `body`: `font-size: 17px`, `line-height: 1.62`, `letter-spacing: 0.005em`.
- `.kicker`: sans, `font-size: 0.72rem`, `letter-spacing: 0.14em`, uppercase.
- `.h2`: Fraunces, `font-size: clamp(2rem, 4.4vw, 3.5rem)`,
  `line-height: 1.03`, `letter-spacing: -0.02em`.
- `#work .h2`, `#dream .h2`, `#competence .h2`, and `#ledger .h2` deliberately
  vary Fraunces axes. Do not normalize every heading to one setting.
- `.machine`: `font-family: var(--mono)`, `font-size: 13px`, tabular numbers.

Hard rule: monospace on human labels is prohibited. `design-render-check` and
`site/design-world.yml` define the allowed machine-output selectors.

## 5. Spacing and layout

Global rhythm:

- `.wrap`: `width: var(--wrap); margin-inline: auto;`.
- `section`: `padding-block: clamp(64px, 9vw, 140px);`.
- `html`: `scroll-padding-top: 4.5rem`.
- `.rule`: one-pixel separator using `--line`.

Hero/layout anchors:

- `.hero-grid` is the main two-column argument/evidence composition.
- `.hero-main` owns the written argument and CTAs.
- `.hero-side` owns proof/inventory instrumentation.
- Mobile ordering is intentional: eyebrow, headline, outcomes, actions, repo
  model, intake, bio. Do not let a generic responsive collapse reorder the story.

Project/case layout anchors:

- `.cards` holds project cards.
- `.card` is a secondary investigation object, not the dominant case format.
- `.case-composition` holds flagship proof compositions.
- `.tau-case` is the dominant proof case for Tau.
- `.shot-link`, `.shot`, and `.shot-img` form the project visual preview.
- `.project-actions` is the explicit source-action row and may contain both a
  canonical system repo and a skill-contract link.

## 6. Components and interaction styles

Required selector contracts:

- `.shot-link` wraps a project visual and must have `data-qid` and
  `data-qs-action`.
- `.shot-img` must carry meaningful `alt` text unless the image is genuinely
  decorative and another accessible label covers the same content.
- `.github-repo-link` renders source links. It may show a canonical repository,
  a public overview repository, or an agent-facing skill contract, but the label
  must make the distinction clear.
- `:focus-visible` uses `outline: 2px solid var(--brass)` and `outline-offset:
  2px`.
- `.sr-only` remains available for accessible-only copy.

Do not use badges as marketing decoration. Evidence badges derive from metadata
such as sanity coverage, public/private visibility, or proof state.

## 7. Motion

Allowed motion is semantic and recorded in `site/effects.yml`:

- the `d3-force` capability constellation;
- rotating search placeholders using real client-style questions;
- the G꜀ mark's slow subscript-c breath;
- state/relationship motion that explains a real proof or inspection event.

Banned motion:

- fake counters;
- fake traces;
- animated evidence values;
- decorative loading choreography that pretends work is happening;
- motion without `prefers-reduced-motion` handling.

## 8. Accessibility

Curiosity filters are about taste, not broken usability.

Required:

- keyboard-visible focus on all interactive controls;
- `data-qid` + `data-qs-action` on interactive site controls;
- meaningful link names for repo/action links;
- non-empty `alt` text on informative project images;
- no horizontal document overflow in supported responsive widths;
- `prefers-reduced-motion` handling for animation;
- contrast decisions must stay readable on `--ink`.

Not allowed:

- empty project-card image alt text;
- source links whose visible or accessible label hides whether the target is a
  canonical repo, public overview, or skill wrapper;
- inaccessible mystery. Mystery is allowed; broken controls are not.

## 9. Project-specific visual worlds

The global shell can stay dark/editorial, but project surfaces should not be
interchangeable.

- Tau: visible bounded DAG, rejected shortcuts, join/reviewer gates,
  append-only receipts, fail-closed state.
- Sparta: operational evidence UI, cyan/yellow decision states, human judgment,
  inconclusive/clarify boundaries.
- Memory: graph recall, candidate ranking, canonical record, path/receipt return.
- Extractor: document geometry, page crops, tables, structured envelope,
  complete/degraded/blocked truth state.
- Voice/Dream: waveform, transcript timing, interruption state, affect receipt,
  boundary between renderer and reasoning.
- Creative media: cinematic and strange is permitted; do not audit-theme it into
  the same palette-only diagram language.

## 10. Anti-patterns

Reject changes that make the site look or sound like:

- Straive-style offshore AI services;
- Palantir-style enterprise sovereign/mission grandeur;
- generic R&D-tech innovation lab;
- a startup SaaS value-proposition homepage;
- a normal portfolio optimized for impatient skimmers.

Reject implementation shortcuts:

- vague design docs with no tokens, selectors, spacing, or proof commands;
- prose-only claims of visual readiness;
- screenshots without Surf when Surf is available;
- generated media presented as evidence;
- wrapper links presented as canonical system repositories.

## 11. Implementation touchpoints

When editing the site, start from the component or surface that owns the visible
behavior:

- `site/app/page.tsx` owns the homepage sequence, receipts section, supporting
  project cards, and Tau dominant case placement.
- `site/app/explore/page.tsx` owns the public project index and graph-to-card
  source path experience.
- `site/components/cases/tau-case.tsx` owns the Tau dominant investigation.
- `site/components/capability-constellation.tsx` owns the force graph and its
  drag/settle behavior.
- `site/components/capability-search.tsx` owns the rotating query prompt and
  search-result discovery path.
- `site/visual-assets.yml` owns visual asset provenance and whether an image may
  be treated as evidence.
- `site/content.json` owns authored public project card copy; generated refresh
  jobs must not flatten that prose.
- `site/project-visibility.json` distinguishes source, public overview, private
  evidence, and hidden projects.

Prefer changing the smallest owning surface. Do not patch `globals.css` to force
a local visual outcome when a component, metadata file, or provenance manifest is
the real source of the behavior.

## 12. Validation commands

Run the lightest command that proves the claim being made:

```bash
skills/monitor-website/run.sh design-contract-check --json
skills/monitor-website/run.sh copy-audit --json
skills/monitor-website/run.sh design-render-check --json
skills/monitor-website/run.sh visual-assets-check --json
skills/monitor-website/run.sh case-composition-check --json
skills/monitor-website/run.sh disclosure-check --json
skills/monitor-website/run.sh responsive-geometry-check --url http://127.0.0.1:3003/ --json
```

For browser-visible judgment, Surf comes first:

```bash
skills/surf/run.sh tab.list --json
skills/surf/run.sh snap --tab-id <id> --output /tmp/grahama-current.png --json
```

A final bespoke-design certification is separate from ordinary design work:

```bash
skills/monitor-website/run.sh design-certify --json
```

`design-certify` may fail with missing blind-rater evidence. That is not a
reason to flatten the site into a category page.
