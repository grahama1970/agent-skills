# monitor-website local design guard — grahama.co

This is the operational design guard for `$monitor-website`. It is intentionally
specific enough for a maintenance agent to reject lazy design work without
opening every site file first.

Canonical design source: `site/DESIGN.md`.
Executable CSS source: `site/app/globals.css`.
Machine-readable visual-world source: `site/design-world.yml`.

## 1. Operating rule

Treat unusualness as intentional unless current evidence shows it is a factual,
accessibility, provenance, or broken-path defect.

The site is allowed to be dense, strange, nonlinear, and entertaining. It is not
allowed to be inaccurate, inaccessible, stale, fake, or generically corporate.

## 2. Required concrete design anchors

A valid grahama.co design change must respect these shipped anchors:

- dark ground: `--ink: #0c0908`;
- warm text: `--text: #ece2d3`;
- evidence brass: `--brass: #e2ac62`;
- failure/contradiction ember: `--ember: #d1703c`;
- semantic state sage: `--sage: #93a289`;
- display face: self-hosted `Fraunces`;
- body face: system sans;
- monospace: machine output only;
- global wrap: `--wrap: min(1260px, 92vw)`;
- global gutter: `--gut: clamp(18px, 3.2vw, 44px)`;
- section rhythm: `padding-block: clamp(64px, 9vw, 140px)`.

Do not propose a design change that ignores these tokens unless the task is an
explicit redesign.

## 3. Selector anchors

The design review must know these selectors exist and carry meaning:

- `.hero-grid` — main argument/evidence composition;
- `.hero-main` — first-person written argument;
- `.hero-side` — proof/inventory instrumentation;
- `.kicker` — human utility label, not monospace;
- `.h2` — Fraunces section argument;
- `.cards` and `.card` — secondary investigations;
- `.case-composition` and `.tau-case` — flagship proof cases;
- `.shot-link`, `.shot`, `.shot-img` — project visual preview;
- `.project-actions` — source path/action row;
- `.github-repo-link` — canonical repo, overview repo, or skill contract link;
- `.machine` — program output only.

## 4. Accessibility guard

Curiosity filters are about taste, not broken usability. Repairs should preserve
or improve:

- `data-qid` and `data-qs-action` on interactive controls;
- meaningful link text and `aria-label` values;
- non-empty informative image `alt` text;
- `:focus-visible` outline behavior;
- `prefers-reduced-motion` handling;
- no horizontal overflow in supported responsive widths;
- readable contrast on the dark shell.

## 5. Evidence rule

For browser-visible design judgment, use Surf first when available:

```bash
skills/surf/run.sh tab.list --json
skills/surf/run.sh snap --tab-id <id> --output /tmp/grahama-current.png --json
```

Then cite the screenshot path. Headless or DOM-only evidence is secondary.

## 6. Preferred repair slices

Prefer small, proof-backed changes:

1. `site/BRAND.md` / `site/DESIGN.md` contract specificity.
2. Proof/source exactness.
3. Accessibility names and alt text.
4. Canonical repo and skill-contract path clarity.
5. Project-specific visual identity.
6. Discovery trails that reward curiosity.
7. Responsive geometry and overflow repair.

## 7. Anti-repairs

Do not recommend or apply a change whose main effect is to make the site more
like a normal R&D-tech, AI-services, SaaS, or defense-tech homepage.

Reject:

- light corporate resets;
- service/industry grid as primary structure;
- generic ROI/awards/social-proof sections;
- anonymous hero imagery;
- one visual wrapper applied to every project;
- prose-only "bespoke" claims;
- vague `DESIGN.md` edits without tokens, selectors, spacing, motion,
  accessibility, and validation commands.

## 8. Implementation touchpoints

Before proposing a repair, identify the owning source file:

- `site/app/page.tsx` for homepage sequence, receipts, and supporting cards.
- `site/app/explore/page.tsx` for public project index source paths.
- `site/components/cases/tau-case.tsx` for the Tau dominant case.
- `site/visual-assets.yml` for image provenance and evidence role.
- `site/project-visibility.json` for public/private/source routing.

Do not solve a metadata defect with CSS. Do not solve an accessibility defect
with visual polish. Patch the owner.

## 9. Required validation commands

Use the command that matches the claim:

```bash
skills/monitor-website/run.sh design-contract-check --json
skills/monitor-website/run.sh copy-audit --json
skills/monitor-website/run.sh design-render-check --json
skills/monitor-website/run.sh visual-assets-check --json
skills/monitor-website/run.sh case-composition-check --json
skills/monitor-website/run.sh disclosure-check --json
```

A final formal bespoke-design claim requires:

```bash
skills/monitor-website/run.sh design-certify --json
```

Do not convert missing formal certification into a reason to make the site
conventional.
