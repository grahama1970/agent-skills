# Theme picker acceptance

Main top-bar theme selection for canonical and legacy decks. Preview, customize,
save, apply/cancel and guarded undo change theme metadata, not authored content.

## Evidence

Receipts root: `/mnt/storage12tb/skills/pitchdeck/outputs/theme-picker/`.

- `header-final/theme_picker.json`: 8/8 live trials pass. Both deck formats,
  source/geometry/claim/asset invariance, invalid/stale refusal, filesystem
  failure rollback, saved themes/reload/undo and real PPTX/PDF exports.
- `header-final/responsive_browser.json`: 4/4 trials pass, including rejection
  of forced canvas scaling. The overview reset gives trials a known starting
  slide without disabling the product's last-slide resume behavior.
- `header-source.json`: 54 layout references across the five supplied PPTX
  files use the same image bytes and `alphaModFix amt="10000"` (10% opacity).
  Example: ReqML_GE_Presentation.pptx, slideLayout46.xml, media/image4.png.
- `header-final/live.json`: the browser fetches that exact image, default
  image opacity is 10%, Apply/Cancel stay visible with Customize expanded,
  and the exported PPTX retains the image at independently customized opacity.
- `header-final/topbar-header-preview.png`: parent Surf capture of the real
  top-bar dropdown, brown header and faint image overlay.
- `header-final/natural_language_editing.json`, `editing.json`, `usability.json`:
  16/16 additional live regression trials pass after the header-image repair.
  Together with theme/responsive, the final five gates pass 28/28 trials.
  `header-final/sanity.log` and `ui-build.log` retain sanity/typecheck/build proof.
  Historical failures remain under `regressions/` and `parent-header-final/`.

The default header fill is opaque brown; image opacity is a separate control.
Titles remain opaque. The old 12% fill default was an implementation choice,
not a measurement from the supplied decks, and has been replaced.

PDF rendering uses packaged Fraunces via process-local Fontconfig. Real PDF
readback reports embedded/subset Fraunces-Bold, not a substituted Noto Sans.
Editable PPTX requests the typeface but does not embed fonts; recipients may
need the supplied TTFs. Source glyph coverage is limited to the site's subset.

## Boundaries

- Fixture-backed live browser/API/CLI proof is not arbitrary-deck or publication
  approval. Browser/PPTX geometry and optical sizing can still differ.
- Guarded rollback covers ordinary I/O failures, not crash/power-loss atomicity
  or isolation against an uncooperative writer between filesystem operations.
- No recording consent, new animation engine or demo-first model evaluation
  is claimed here. Narrative guidance remains a separate work item.
- Parent landing/readback receipt target: the receipts root's `delivery.json`.
  Generated release metadata is not a substitute for source/blob readback.
