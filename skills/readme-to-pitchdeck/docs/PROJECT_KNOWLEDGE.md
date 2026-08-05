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

## Implemented 2026-08-05: React deck renderer + claim-review UI (v1)

- `emit-ui` CLI command (`src/readme_to_pitchdeck/ui_emitter.py`) emits
  `ui_deck_bundle.v1` JSON after the same fail-closed `validate_bundle` gates as
  the PPTX build; covered by pytest positive + fail-closed leak tests and
  sanity.sh stage 5.
- `ui/` React 19 + Vite + Tailwind 4 app: 1920×1080 scaled canvas, keyboard nav,
  fwd/back slide transitions (prefers-reduced-motion respected), overview grid,
  speaker-notes panel, read-only claim-review view with validation-gap banner.
  All 10 SlideLayout values render (card layouts share a CardGrid component).
  Verified live 2026-08-05 via surf on the minimal fixture: slide nav, claims
  view (29 candidate/2 approved badges), data-qid coverage from live DOM.
- Interaction contract: data-qid + data-qs-action + title on every onClick
  element (static gate `scripts/verify_ui_contracts.py`, sanity stage 6);
  `useRegisterAction` is a local fail-silent copy posting to
  VITE_ACTION_REGISTRY_URL when configured.
- Deviations from the original open-slide plan: v1 is a hand-rolled renderer in
  the house stack (no open-slide dependency yet — its `@base-ui/react` stack and
  comment loop remain candidates for v2); presenter second-window and
  Playwright PDF export not yet built.
- Not established: visual approval of real (sparta) decks; the sparta example
  requires SPARTA_ROOT sources and real screenshots, and emit-ui correctly
  fails closed on it.

## Memory sync (added 2026-08-05)

- `memory-sync` CLI (`src/readme_to_pitchdeck/memory_sync.py`, loguru + typed
  boundary + no-shell subprocess) stores a deck summary via
  `skills/memory/run.sh learn`, scope `agent-skills` (exempt from the memory
  quality gate's taxonomy requirement, which blocked scope
  `readme-to-pitchdeck`).
- VERIFIED 2026-08-05: doc `lessons_v2/308496916443` read back by `_key` and by
  `'"pitchdeck" IN doc.tags'` via `memory sample`.
- NOT ESTABLISHED: the doc ranking into default `/memory recall` top-k (it did
  not surface in top-8 for exact-problem queries ~1 min after storage; learn's
  own --verify also warned "Stored item not in top recall result"). Suspected
  embedding/index lag or ranking behavior in the memory service — a memory-side
  question, not a storage failure. Tag-filtered sample is the reliable
  retrieval path today.

## Claim-review chat via shared ux-lab ChatWell (added 2026-08-05)

- Corrections on record: (a) `skills/ux-lab` exists in this repo on main — an
  earlier "missing from checkout" claim was a zsh glob failure misread as
  absence; (b) a shared chat extraction already exists
  (`skills/ux-lab/ui/ChatWell.tsx` re-exporting ComplianceChatWell, plus
  SharedChatShell) — it did not need to be created.
- `ui/src/components/DeckChat.tsx` mounts the shared ChatWell (imported from
  `@ux-lab/ui/ChatWell` via a repo-relative Vite alias; typed via a local
  declaration shim so strict tsconfig does not lint the shared sources) in the
  claims view only. Presenter mode stays chat-free.
- Claim boundary preserved: the interpreter is deterministic over the emitted
  bundle (gaps / candidates / show <id>) and for approve|reject|qualify it
  emits the exact ledger edit + re-verify + re-emit commands — chat never
  mutates deck content. VITE_DECK_AGENT_URL optionally forwards free-form
  turns to a live agent endpoint (falls back to local commands on failure).
- VERIFIED live 2026-08-05 via surf: ChatWell mounted with shared-chat qids,
  starter chip "Open gaps" produced the 24-gap answer from the bundle;
  screenshot at /mnt/storage12tb/skills/readme-to-pitchdeck/outputs/ui-chat-claims.png.
- ux-lab note: the ui package `index.ts` does not re-export ChatWell (only
  ComplianceChatWell); consumers use the `ChatWell.tsx` module path. Repo copy
  and ~/.pi copy of index.ts differ — treat the repo as canonical.

## Visual sync into Qdrant (added 2026-08-05)

- Correction on record: Qdrant IS part of the workstation memory pipeline
  (embry-qdrant on :6333; graph_memory has qdrant_client/qdrant_recall); an
  earlier session claim that it wasn't was wrong and made without probing.
- `visual-sync` (`src/readme_to_pitchdeck/visual_sync.py`) indexes rendered
  slide PNGs into skill-scoped `readme_to_pitchdeck_visual_assets_v1`
  (text_mm/image_mm, 1024-d jina-v5-omni) with memory pointer docs in
  `readme_to_pitchdeck_visual_assets` via memory `/upsert` — vectors never in
  ArangoDB (persona-dream contact-sheet pattern).
- VERIFIED 2026-08-05 live: 8 points upserted with matching read-back count;
  semantic query "scattered evidence trails" returned slide 2 "The problem"
  as top hit on both vector names.
- Video is not yet indexed (no video assets exist in any deck manifest today);
  when a video asset kind lands, extend visual-sync with frame sampling before
  embedding.
- Gap: visual-sync depends on live services (:8603/:6333/:8601) so it is not
  in sanity.sh; add an opt-in sanity-live.sh gate if it becomes load-bearing.

## Superseded plan (kept for context): open-slide adoption (decided 2026-08-05)

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

## In-browser slide editing (added 2026-08-05)

- Edit mode (pencil toggle) makes slide title/message/body bullets clickable
  (`deck:edit:<slide>:<field>` qids); an edit panel POSTs /api/slide-edit →
  Vite dev middleware → `run.sh apply-edit` → `slide_edit.py`. The edit is
  applied IN MEMORY, the full emit_ui_bundle validation re-runs, and only on
  PASS are deck.public.yaml and deck.data.json rewritten together. bundle_dir
  comes from emit_ui_receipt.json server-side, never from the client.
- Editable: title, message, notes, footer, body:<index>. Not editable via UI:
  claim ids, visibility, sources, layout (ledger/manifest decisions).
- VERIFIED live 2026-08-05: browser edit of 01-cover title persisted to YAML
  and re-rendered; forbidden-phrase edit ("production-ready and fully
  validated") rejected with FORBIDDEN_UNQUALIFIED_CLAIM and zero disk changes;
  over-length title rejected by pydantic (pytest). Screenshot:
  /mnt/storage12tb/skills/readme-to-pitchdeck/outputs/ui-edit-mode.png
- Edit API is dev-server-only by design; a production deployment needs an
  authenticated equivalent before exposing writes.

## Video assets (added 2026-08-05)

- `AssetKind.VIDEO` (.mp4/.webm allowlist in validation): embeds as a native
  movie shape (`add_movie`, mime by suffix) in PPTX; renders as `<video
  controls>` in the browser UI; wrong container for kind video is a hard
  ASSET_UNSUPPORTED_FORMAT error. pytest covers build (MEDIA shape read back
  from the reopened PPTX via ffmpeg-generated fixture clip) and the negative.
- Known limits: Google Slides import drops embedded video (re-link from
  Drive/YouTube); PDF/contact-sheet renders show the poster frame; visual-sync
  indexes only rendered slide PNGs — video frame sampling remains the noted
  extension.

## Slide inspector + continuous alteration (added 2026-08-05)

- Operator direction: the agent never produces a finished deck — the UI is a
  workbench for continuous human alteration with the compiler as safety net.
- Keynote (icloud.com tab, DOM-verified via surf) is the reference pattern: a
  selection-scoped right inspector (Slide → Appearance toggles → Background
  fills), NOT a global font toolbar; text formatting is selection-contextual.
- `Inspector.tsx` renders in edit mode: layout selector (all 10 layouts),
  footer, speaker notes, bullet add/delete — every change through
  /api/slide-edit → apply-edit (EDITABLE_FIELDS now includes layout;
  body:add / body:del.<index> operations). VERIFIED live: slide 02-problem
  switched statement→split and gained a bullet, YAML + re-emit round-trip.
- Per-element fonts/colors remain intentionally out of scope: theme-layer
  decisions, tuned in the exported PPTX or theme, preventing design-system and
  claim-rendering drift.

## Animations first-class + asset drop (added 2026-08-05, operator directive)

- Operator: "animations should be first class citizens in the react app."
  Implemented as typed manifest data, not CSS toggles: SlideSpec.transition
  (none/fade/slide/slide_up/zoom) and SlideSpec.reveal (none/stagger_up/
  stagger_fade) flow schema → validation → emit-ui → renderer → inspector
  dropdowns; VisualSpec.position (left/right/full) controls layout placement.
  Invalid values rejected by pydantic (verified: 'wobble' fails closed).
  PPTX/Marp exports intentionally ignore transition/reveal (documented).
- Drag-and-drop assets: drop an image/video onto the slide in edit mode →
  alt-text dialog (required) → /api/asset-drop → asset-add CLI: file copied
  into bundle assets/, AssetSpec appended (kind video for mp4/webm), bound as
  slide visual, full validation before manifests + deck.data.json rewrite;
  rejection deletes the copied file (no orphans). asset-clear detaches.
- VERIFIED live 2026-08-05: PNG dropped via API onto 02-problem rendered in
  split layout, zoom transition + staggered bullets active
  (anim-zoom-fwd in DOM); 14/14 pytest incl. asset ops + invalid-transition.
- Pending: right-click context menu on visuals (inspector covers position/
  clear today); free pixel positioning intentionally rejected — divergence
  between browser and PPTX geometry would break the single-manifest promise.

## Freeform layout — true drag-anywhere positioning (added 2026-08-05)

- /brave-search validation changed the earlier "no free positioning" stance:
  python-pptx places shapes at absolute EMU coordinates, so geometry stored as
  FRACTIONS of the canvas renders identically in browser (x*1920/1080) and
  PPTX (x*13.333in/7.5in). One manifest, two faithful targets — the earlier
  divergence objection only applied to unmanaged CSS.
- SlideLayout.FREEFORM + FreeformElement (typed: x/y/w/h fractions bounded to
  the canvas, text or asset, size_pt/bold/color/align). Switching a slide's
  layout to freeform synthesizes elements from its existing title/message/
  bullets/visual. Element ops via apply-edit: element:<id>:frame|text|size,
  element:add:text, element:del:<id>.
- Claim boundary holds: element text is included in the forbidden-phrase and
  claim-visibility scans (tested); out-of-bounds frames rejected by pydantic.
- UI: react-rnd drag/resize on the scaled canvas; double-click text to edit;
  "Add text box" in inspector; plain absolute divs outside edit mode.
- VERIFIED 2026-08-05: browser API drag of the title to (0.100, 0.050)
  produced a PPTX text box at exactly those fractions (Emu read-back);
  7 rnd handles live in DOM; 15/15 pytest.

## Gemini design spec assessed + implemented (2026-08-05)

- Phase 1 (bi-directional Markdown sync) REJECTED as written: their parser
  regenerates slide ids per keystroke, drops claims/sources/geometry, commits
  client state before validation (violating its own fail-closed directive),
  and its layout regex is broken. ADAPTED to the real document model: dual-pane
  YAML source editor (SourcePane, Ctrl+\ toggle) over deck.public.yaml via
  GET/POST /api/source → source-edit CLI → schema + full bundle validation.
  VERIFIED: source-pane title edit re-rendered the canvas; malformed YAML 422
  with zero disk changes.
- Phase 2 (floating toolbar) adapted to real element ops: bold/size±/align/
  delete on the selected freeform element (element:<id>:bold|align added).
- Phase 3 (visual layout picker): wireframe gallery for all 11 layouts
  replaces the text dropdown in the inspector.
- Phase 4 (live overflow lint): client-side advisory lint (bullets>5,
  bullet>110 chars, title>60, freeform text density) mirroring the PPTX
  builder's sizing thresholds; OverflowBadge overlay in edit mode. Advisory
  only — server gates remain the authority.

## WebGPT comprehensive review — verdict RETHINK (2026-08-05)

Full review: docs/WEBGPT_REVIEW_2026-08-05.md (submitted via surf webgpt.submit
to human-designated tab 837366723 with proof metadata: requested==controlled,
tab_was_created=false; bundle = review.md + 3 UI screenshots).

Fixed same-day (all CONFIRMED against source, regression-tested, 16/16):
- P0-1 partial: footer, visual.items/callouts/caption now in the visible-text
  scan (forbidden phrases + claim boundary).
- P0-2a: silent PPTX body truncation is now a TARGET_CONTENT_TRUNCATED error;
  capacity map matches actual renderer slices (statement/split/cards 4,
  flow 6, roadmap 9, collaboration 3, appendix 6). The gate immediately
  caught 5 over-capacity slides in the curated sparta example (real instances
  of the reported bug; flow/roadmap capacities corrected rather than content
  trimmed).
- P0-2b: switching a slide off freeform clears stale elements (hidden-
  qualifier hole closed).
- P0-3: deck.id/visibility/source_policy immutable through the source editor.
- P1-7 partial: emit-ui purges stale copied assets (cleared assets stop being
  served).
- P1-10: chat 'qualify' guidance corrected ('qualified' is not a ClaimStatus).
- P1-11 partial: freeform pt→px conversion corrected to 144dpi (pt*2).

Accepted backlog (architectural; NOT yet implemented — the RETHINK core):
1. Content-run model: every visible text run claim-bound / non-claim /
   allowlisted-decorative; renderers consume runs, not raw strings (P0-1 full).
2. RenderPlan + post-build PPTX text-run verification vs plan (P0-2 full).
3. Draft vs publish export split with watermark + require-approved default
   for publish (P1-4).
4. Structural qualifier binding replacing the negation-window heuristic (P1-5).
5. Claim-level source resolution + approval provenance/staleness (P1-6).
6. Asset intake hardening: default-private, magic bytes, re-encode, limits,
   content-addressed emit dirs (P1-7 full).
7. Revision CAS + atomic revision-dir writes + undo/redo history (P1-8).
8. Production document service (auth, ACLs, audit, isolated export worker)
   replacing dev middleware (P1-9).
9. Chat proposal objects through the command API (P1-10 full).
10. Font policy: same family both targets, autofit/shrink policy, target-render
    text verification (P1-11 full).
11. Mode architecture Design|Claims|Source|Present; designer gaps (multiselect,
    z-order, align/distribute/snap, undo/redo first) (P2-12).
12. Freeform as explicit "detach from layout" with origin mapping; template+
    overrides hybrid (P2-13).
13. Claim-aware Markdown outline projection (constrained, id-stable) as a
    future authoring surface; Marp stays one-way (P2-14).
14. Reviewer's 14-case proof bundle as the release gate (item 15).
