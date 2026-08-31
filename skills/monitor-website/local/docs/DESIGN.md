# monitor-website local design guard — grahama.co

Canonical site design file: `site/DESIGN.md`.

Use this guard during `$monitor-website` design-render checks, audits, and
maintenance plans.

## Operating rule

Treat unusualness as intentional unless current evidence shows it is a factual,
accessibility, provenance, or broken-path defect.

The site is allowed to be dense, strange, nonlinear, and entertaining. It is not
allowed to be inaccurate, inaccessible, or fake.

## Evidence rule

For browser-visible design judgment, use Surf first when available:

```bash
skills/surf/run.sh tab.list --json
skills/surf/run.sh snap --tab-id <id> --output /tmp/grahama-current.png --json
```

Then cite the screenshot path. Headless or DOM-only evidence is secondary.

## Preferred repair slices

1. Proof/source exactness.
2. Accessibility names and alt text.
3. Canonical repo and skill-contract path clarity.
4. Project-specific visual identity.
5. Discovery trails that reward curiosity.

## Anti-repairs

Do not recommend or apply a change whose main effect is to make the site more
like a normal R&D-tech, AI-services, or defense-tech homepage.
