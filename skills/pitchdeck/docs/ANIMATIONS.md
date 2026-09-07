# Progressive reveal: browser / native PPTX coverage matrix

One authored `AnimationEffect` row is one concept. The browser plays rows
through Web Animations (`ui/src/animations.ts`); native export writes real
`p:timing` click/timing trees (`src/pitchdeck/pptx_timing.py`) into both the
canonical exporter (`emit-document-pptx`) and the legacy bundle builder
(`build`). Rows, click grouping, With/After Previous starts, durations and
delays use the same arithmetic in both players (`timeline()` mirrored by
`_click_groups`). PDF stays an explicitly static, full-content rendering:
`p:timing` only affects slideshows, never the static render — the retained gate
proves the first-build content is readable in the PDF.

## Proof boundary — read this before claiming parity

Native coverage below is proven by STRUCTURAL inspection: unzipped slide XML
with correct `p:spTgt` shape targets, click groups, node types, durations and
delays, verified live by `scripts/eval_progressive_reveal.py` (retained gate
`fixtures/progressive_reveal.json`). A valid XML tree and a LibreOffice PDF are
NOT native slideshow playback evidence. Playback in Microsoft PowerPoint
(desktop/web) and Google Slides import behavior are UNVERIFIED here.
`presetID` mainly labels the effect in PowerPoint's animation pane; playback is
carried by the behaviors (`p:set` visibility, `p:animEffect` filters, `p:anim`
ppt_x/y/w/h, `p:animScale`, `p:animRot`, `p:animClr`, `p:animMotion`) — the
same elements observed in the supplied style-corpus decks
(`outputs/progressive-reveal/research/`).

## Per-effect matrix

Browser entries below describe implementation, not exhaustive live visual proof
for every effect. The retained browser gate exercises representative intermediate
frames; counting the 25 menu options establishes only catalog enumeration.


Preset confidence: `grounded` = ID observed in the supplied decks' XML;
`unverified` / `inferred` = pane labels not confirmed against the supplied native XML.
Neither labels nor emitted behaviors establish application playback.

| Effect | Phase(s) | Browser | Native PPTX behaviors | presetID (confidence) |
|---|---|---|---|---|
| appear | entr/exit | yes | set visibility (exit: Disappear) | 1 (grounded) |
| fade | entr/exit | yes | animEffect fade | 53 (grounded entrance ID; exit label unverified) |
| fly | entr/exit | yes | ppt_x/ppt_y from/to off-slide, direction subtype | 2 (grounded, left=8 grounded) |
| wipe | entr/exit | yes | animEffect wipe(dir) | 22 (grounded) |
| zoom | entr/exit | yes | ppt_w/ppt_h scale from 0 (in) or 2x (out) | 23 (grounded) |
| peek | entr/exit | yes | animEffect wipe(dir) + quarter-offset slide | 12 (unverified) |
| split | entr/exit | yes | animEffect split(in/outHorizontal/Vertical) | 16 (unverified) |
| expand | entr/exit | yes | fade + ppt_w from 0 | 50 (inferred) |
| stretch | entr/exit | yes | ppt_w or ppt_h from 0 | 17 (inferred) |
| rise | entr/exit | yes | fade + ppt_y from +h/2 | 34 (inferred) |
| grow-turn | entr/exit | yes | fade + ppt_w/ppt_h from 0 — APPROXIMATION: the turn (initial rotation) is not exported | 31 (inferred) |
| blinds | entr/exit | yes | animEffect blinds(horizontal/vertical) | 3 (unverified) |
| box | entr/exit | yes | animEffect box(in/out) | 4 (unverified) |
| bars | entr/exit | yes | animEffect randombar(horizontal/vertical) | 14 (unverified) |
| checker | entr/exit | yes | animEffect checkerboard(across/down) | 5 (unverified) |
| strips | entr/exit | yes | animEffect strips(downLeft…) | 18 (inferred) |
| spin | emphasis | yes | animRot by amount×360° | 8 (unverified) |
| grow-shrink | emphasis | yes | animScale to amount | 6 (unverified) |
| transparency | emphasis | yes | anim style.opacity to 1−amount | 9 (unverified) |
| dim | emphasis | yes (same mechanics as transparency in the browser too) | anim style.opacity to 1−amount | 9 (same as transparency by design) |
| pulse | emphasis | yes | animScale autoRev to 1+amount | 35 (inferred) |
| font-color | emphasis | yes | animClr style.color to color | 3 (inferred emphasis ID) |
| fill-color | emphasis | yes | set fill.on/solid + animClr fillcolor | 1 (inferred emphasis ID) |
| line-color | emphasis | yes | set stroke.on + animClr stroke.color | 7 (inferred emphasis ID) |
| motion-line | motion | yes | animMotion relative line path (dx, dy slide fractions) | 42 (grounded) |

## Target applicability and named limits

- Canonical elements, whole groups, semantic `body:N` rows, card/flow
  `body:N`/`visual:N` concepts and the legacy `visual` asset export with real
  shape targets (multi-shape concepts ride one click as withEffect nodes).
- This exporter does not yet resolve individual targets nested inside a group:
  canonical diagram `…/node/…` and `…/edge/…` targets (and grouped children)
  are SKIPPED with a per-target reason in the emit receipt
  (`receipt.animations[].skipped`, legacy `gaps`), never silently retargeted.
  In the browser they animate fully.
- Legacy roadmap/collaboration/appendix layouts do not name per-item shapes;
  their targets are likewise receipted as skipped.
- Reduced motion, GUI authoring, preview/undo and CAS write protection are
  browser features; the export carries whatever the author applied.
- Custom motion paths, letter/word-level text animation, repeat/rewind, media
  triggers and paragraph-range (`p:pRg`) builds are not authored and not
  exported.
