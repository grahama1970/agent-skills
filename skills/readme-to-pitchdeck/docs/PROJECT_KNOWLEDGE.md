# README to Pitch Deck — project knowledge

## Current state

Version 0.1.0 is a deterministic local compiler. It reads local Markdown sources,
extracts candidate claims and referenced images, emits typed YAML manifests, validates
public/private and qualifier boundaries, builds editable 16:9 PPTX files, reopens them for
structural verification, and can render PDF/PNG/contact sheets with Linux tools.

## Durable decisions

- README prose is never auto-approved.
- Public/private filtering is a hard build boundary.
- Status/proof claims are high risk and require qualifiers.
- Mandatory non-claims are first-class claim-ledger entries.
- Missing required assets fail closed; optional gaps remain visible.
- PPTX is the portable editable interchange; Google Slides is a human tuning surface.
- Manifests and receipts, not the cloud deck, are the source-controlled truth.

## Known gaps

- README-to-slide planning is heuristic and deliberately conservative.
- The compiler does not inspect the repository implementation to verify README claims.
- It does not call web search, GitHub, Google Slides, image generation, or an LLM.
- It does not compare rendered slides to a design template.
- It does not guarantee pixel-identical Google Slides import.
- Visual approval remains a contact-sheet and human-review step.

## Planned: React deck renderer + claim-review UI (decided 2026-08-05)

- Add a browser deck target beside the PPTX builder: both emitters consume the same
  validated `deck.public.yaml`, so all fail-closed claim gates run before either target.
- Base runtime (revised same day after /brave-search validation): **open-slide**
  (github.com/1weiho/open-slide, MIT, React + Tailwind, 6k stars, actively pushed) —
  not a from-scratch build. It provides the 1920×1080 canvas, scaling, navigation,
  present/presenter mode, and an agent-native click-to-comment review loop
  (`@slide-comment` markers + `/apply-comments`). The compiler emits open-slide page
  components from the validated manifest. Deviation to track: open-slide uses
  `@base-ui/react`, not Radix/shadcn; our claim-review additions stay shadcn.
- Stack is React + Tailwind + shadcn (Radix/CVA), matching Sparta Explorer — NOT Slidev.
  Slidev (Vue) was evaluated from a source clone and rejected as a dependency: its PPTX
  export is image-per-slide (python-pptx keeps the editable-PPTX job), and its animation
  machinery is ~100 lines of CSS plus a click-index state machine, cheap to replicate.
  Replicate its conventions: layout taxonomy (cover/section/two-cols/image-left…),
  click-reveal semantics, transition names (slide-left/right/up/down, fade), fixed 16:9
  canvas with transform scaling, presenter-notes window fed by `speaker_notes.md`,
  print CSS + headless-Chromium PDF export wired into the existing render gate.
- Ownership boundary (operator 2026-08-05): `/ux-lab` stays a light wrapper — it gets
  only a project registry entry and hub card. All non-shared UX (deck renderer, slide
  layouts, claim-ledger review view) lives in this skill under `ui/`. Only genuinely
  shared primitives graduate to the ux-lab shared UI package.
- v1 scope: slide canvas + scaling, 6–8 manifest layouts, click reveals, 4 transitions,
  keyboard nav, overview grid, presenter notes, print/PDF export. Deferred: drawing,
  recording, code embeds (assets come from /create-figure instead).
- Animations in PPTX remain out of scope by design: python-pptx has no animation API
  (scanny/python-pptx #400, #1106) and Google Slides import drops PowerPoint
  animations/transitions anyway. The browser target is the animation surface.

## Future promotion gates

Before adding autonomous research or rewriting:

1. add an `agentic-evals` fixture with positive, negative, and adversarial trials;
2. retain deterministic claim/source validation before optional LLM judgment;
3. make external network effects opt-in and receipt-bound;
4. add a native Google Slides API adapter only after OAuth/config doctor and export
   round-trip tests exist;
5. add image regeneration as a separate composed skill rather than hiding it in the
   compiler.

## Readiness

- Deterministic planning/build/verify: `USABLE_WITH_GAPS` until installed `sanity.sh`
  passes on the target workstation.
- Google Slides visual handoff: `NOT_ESTABLISHED` until a generated deck is imported and
  reviewed there.
- Automated factual verification against a codebase: `NOT_IMPLEMENTED`.
