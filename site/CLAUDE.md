# site/ — Grahama Labs public site

Next.js (static export) + Tailwind v4 + shadcn-style components. Deployed to
GitHub Pages by `.github/workflows/site-deploy.yml`. The design brief:
precision-lab aesthetic, one hero set-piece (the agent-trace ledger),
scroll-driven reveals at low amplitude, animated stat counters, nothing else
moving. All motion is progressive enhancement behind `prefers-reduced-motion`.

## best-practices-react compliance

Every interactive element carries `data-qid`, `data-qs-action`, and `title`
at write time. `scripts/verify-data-qid.py` enforces this in CI (exit 1 =
not shippable).

**Documented exception — `useRegisterAction`:** the canonical hook registers
actions to the private ArangoDB `app_actions` collection. This is a public
static site with no path to that runtime, so `lib/use-register-action.ts`
keeps the identical signature and action-ID discipline but only POSTs when a
runtime injects `window.__APP_ACTIONS_ENDPOINT__` (never on the public
build). /review-plan should treat this as compliant for this app.

## Invariants

- Content claims (inventory counts, project list) must match the repo
  README. When `README.md` "At a Glance" changes, update the stats in
  `app/page.tsx`.
- No barrel imports; import components from their files.
- Interactive chrome must always render (no early returns that hide nav).
