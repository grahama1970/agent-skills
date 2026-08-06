Scope

The attached bundle contains the review brief and three screenshots, but not the implementation or machine-readable test receipts. I therefore traced the described paths against the repository implementation at commit 80f6c3e86f0587ba5a8e5b5c137655daca4ddeeb. I did not independently rerun the 15 tests or the CDP session, so the reproductions below are source-traced rather than executed in a fresh checkout.

Findings
1. P0 — There is a direct source-pane path for unbound, forbidden text to reach both the browser and PPTX

The central invariant—every rendered statement is bound to a ledger claim—is not enforced. Validation scans only title, message, body, and freeform-element text. It does not scan or bind visual.items, visual.callouts, visual.caption, or footer. Yet visual.items are rendered by both the React flow layout and the PPTX flow renderer.

Concrete repro through the YAML source pane:

YAML
layout: flow

visual:
  type: native_diagram
  items:
    - Production-ready
    - Used by 500 enterprise teams

Keep the slide’s existing valid source_refs and unrelated claim_ids. Submit the source edit and export. Both statements bypass the forbidden-phrase scan and have no claim relationship, but appear in the browser and PPTX.

There is also a conventional UI bypass: add_after creates a new slide with claim_ids: [] while inheriting source references from the current slide. The user can then replace “Draft content” with any assertion not caught by the small forbidden-phrase list, and validation succeeds.

Required redesign: Replace raw strings distributed across slide fields with a common content-run model consumed by every renderer:

YAML
content:
  - id: run-market-result
    role: message
    kind: claim
    claim_id: claim-market-result
    text: Cuts review time by 70%.

  - id: run-scope
    role: qualifier
    kind: non_claim
    claim_id: nonclaim-pilot-scope
    text: Based on a 12-user internal pilot.

Every visible textual run must be exactly one of:

a claim-bound run;

a required non-claim/qualifier;

explicitly decorative text from a narrow allowlist.

A renderer should be unable to accept arbitrary prose outside that model. ClaimGuard.allowed_claim_ids currently exists but is not used to establish this coverage.

2. P0 — Validation and rendering disagree about what is visible, allowing qualifiers to disappear from export

The validator considers all body entries, all freeform elements, and speaker notes when checking a required qualifier. The individual renderers consume different subsets.

A concrete high-risk case:

Put the substantive claim in message.

Give the claim the required qualifier Based on a 12-user pilot.

Put that qualifier in body item five.

Use the statement layout.

Validation passes because it examines every body item. The React statement layout renders every body item. The PPTX statement renderer silently uses only spec.body[:4], so the qualifier disappears from the exported presentation. The PPTX reopen gate still passes because it checks only that the slide has some text—not that expected claim and qualifier text survived.

The freeform conversion creates another version of the same defect:

Put a qualifier in a freeform element.

Switch the slide back to a typed layout.

The layout edit changes layout but does not remove the old elements.

Validation continues to count the hidden element as visible.

The typed React and PPTX renderers ignore it.

That produces a typed slide whose visible claim is unqualified even though validation reports that the qualifier is present.

Speaker notes can likewise satisfy required_qualifier; that is unsafe unless the ledger explicitly marks the qualifier as notes_ok. A normal legal, evidentiary, or status qualifier should default to placement: visible.

Required redesign: Introduce one target-independent RenderPlan containing the exact content runs, boxes, and target dispositions. Then require:

every expected run is either rendered or produces a blocking TARGET_CONTENT_UNSUPPORTED error;

no renderer silently truncates arrays;

required qualifiers and mandatory non-claims survive in visible target text;

post-build PPTX verification compares extracted visible text-run IDs or hashes against the render plan;

dropped content is a build error, not a layout heuristic.

3. P0 — The source pane can turn the public target into a private deck and then export it from the public surface

The public/private boundary is document-controlled rather than server-controlled. Through the whole-deck YAML pane, a user can change:

YAML
deck:
  visibility: private
  source_policy: public_and_private

They can then bind existing private slides, claims, sources, or assets. The validator correctly concludes that those references are legal for a private deck. But the result is still written to the editor’s public output directory, displayed by the same browser application, and exported by the route hardcoded to deck.public.yaml.

This defeats the intended protection because the manifest is allowed to redefine the classification of the target that is supposed to constrain it.

Required redesign: Make the target classification immutable server-side:

project: sparta-explorer
deck target: public
permitted deck visibility: public
permitted source policy: public_only
permitted source/claim/asset classifications: public

A request to edit deck.public.yaml must fail if any of those fields change. Private editing should use a separate deck ID, output namespace, authorization rule, and artifact store. Never infer the security target from fields supplied inside the mutable payload.

4. P1 — “Public export” currently permits candidate claims without a meaningful draft boundary

Both UI emission and PPTX generation default require_approved_claims to false. The Vite export route invokes build without --require-approved-claims, so the ordinary PPTX/PDF export path accepts candidate claims as warnings. The same concern applies to the one-way Markdown export unless its invocation adds a stricter policy elsewhere.

Candidate-bearing exports can be legitimate internal drafts. The problem is that the UI presents one undifferentiated export action for a deck called “public.”

Design sketch:

Export draft: candidate claims allowed; every slide receives a non-removable DRAFT — UNAPPROVED CLAIMS treatment; filename contains .draft; receipt enumerates candidate IDs.

Publish public deck: approved claims only; stale approvals, unresolved warnings, missing qualifiers, and unapproved assets block.

Public publish should be the strict default. Draft export should require a deliberate secondary action.

A readiness value such as USABLE_WITH_GAPS should never be visually equivalent to publication readiness.

5. P1 — The forbidden-phrase and qualifier logic is syntactic and readily bypassed

The current negation detector treats a forbidden phrase as qualified when any token such as “no,” “not,” or “without” appears within a character window around it.

This sentence can therefore be accepted:

No blockers are discussed. The system is production-ready.

The nearby “No” is unrelated to the production-readiness assertion but falls inside the prefix window.

Other gaps include:

footer, visual.items, visual.callouts, visual.caption, and visibly displayed missing-asset alt text are not scanned;

a required qualifier can be hidden in notes;

the check establishes phrase presence, not that the phrase qualifies the particular claim;

punctuation, sentence boundaries, and multiple claims are not represented.

Required redesign: Do not infer qualification from nearby language. Bind qualification structurally:

YAML
claim_id: claim-production-status
required_qualifiers:
  - nonclaim-not-production-ready
qualifier_placement: visible

The rendered content graph must show both runs on the same slide and target. A textual scanner can remain as a defense-in-depth lint, but not as the authority for claim safety.

6. P1 — Claim source authority is incomplete

A non-rejected claim must have at least one source_ref, but claim-level source references are not resolved against the source manifest during bundle validation. The validator resolves the slide’s source_refs, not the bound claim’s source references.

A public approved claim can therefore reference:

YAML
source_refs:
  - source_id: does-not-exist

or a private source, while the slide itself supplies an unrelated valid public source. The slide can pass because the claim is marked public and the slide’s source is allowlisted.

Approval is also just an enum value. There is no required approver, approval timestamp, source-snapshot digest, or staleness rule.

Required redesign:

Resolve every claim source reference.

For a public target, require each bound claim’s sources to be public and allowlisted.

Derive slide source references from bound content runs rather than maintaining an independent, potentially unrelated list.

Record approval provenance:

YAML
approval:
  status: approved
  approved_by: reviewer-id
  approved_at: 2026-08-05T...
  source_snapshot_sha256: ...
  expires_at: ...

When a referenced source digest changes, mark the approval stale or return the claim to candidate.

7. P1 — Asset handling can auto-classify confidential material as public and leave it retrievable after removal

A dropped asset is assigned the deck’s visibility automatically. Dropping a confidential screenshot into a public deck therefore creates a public asset record without a separate classification or approval decision.

There is also a stale-artifact path:

Drop confidential.png.

UI emission copies it into ui/public/assets/....

Clear or replace the slide visual.

The old copied asset is not removed from the output directory.

Its previous static URL can remain retrievable.

The emitter copies current assets into an existing directory but does not build a clean immutable output or remove unreferenced files.

The upload middleware buffers an unrestricted base64 body in memory and validates primarily by filename suffix. That is acceptable for a trusted local prototype, not for a production boundary.

Required redesign:

New assets default to private, candidate, and unreviewed.

Public classification requires an explicit approval action.

Record digest, media type, origin, owner, license status, and review status.

Enforce byte, dimension, page/frame, and duration limits before decoding.

Verify magic bytes and decode/re-encode raster images.

Sanitize or isolate SVG and complex media processing.

Emit each revision into a new content-addressed directory and atomically publish that directory. Never reuse a mutable public/assets directory.

8. P1 — The edit pipeline validates before persistence, but it does not rewrite YAML and JSON atomically

The receipts say that YAML and emitted JSON are rewritten together. The actual order is:

Validate.

emit_ui_bundle writes assets and deck.data.json.

The edit operation writes the YAML manifest afterward.

A process failure, permissions error, or disk error between steps two and three leaves JSON from the new revision and YAML from the previous revision. Asset operations have analogous multi-file write windows.

There is also no lock, base revision, ETag, or compare-and-swap. Two concurrent edits can both load revision N and then overwrite one another. This will become acute as soon as undo/redo, autosave, multiple tabs, or collaboration is added.

The freeform canvas is optimistic: it updates the local frame before the server request succeeds. On rejection, it displays an error but does not restore the accepted geometry.

Required redesign:

JSON
{
  "command": "element.move",
  "deck_id": "sparta-public",
  "base_revision": 42,
  "idempotency_key": "...",
  "payload": {
    "slide_id": "s3",
    "element_id": "title",
    "frame": [0.1, 0.05, 0.6, 0.12]
  }
}

The backend should:

lock or compare-and-swap revision 42;

apply and validate entirely in memory;

emit every artifact into a temporary revision directory;

fsync and atomically rename/switch the revision pointer;

return revision 43;

reject stale edits with 409 Revision Conflict.

Undo/redo then becomes a durable command/revision history rather than a fragile client-only stack.

9. P1 — The Vite middleware is a useful local adapter, but the production boundary must be a real document service

The current middleware has no authentication, project authorization, CSRF/origin policy, request quotas, per-deck revision control, durable audit history, or sandboxed export boundary. It also derives absolute filesystem paths from a local receipt. execFile rather than a shell is a good choice, but it is not an authorization or isolation mechanism.

Vite’s server is a development server and defaults to local exposure; its own documentation cautions about host exposure, allowed-host configuration, and using its preview server as a production server. 
vitejs
+2
vitejs
+2

The minimal safe production shape does not require a large microservice system:

Static React application
          │
          ▼
Authenticated deck API
  ├─ deck revisions + claim ledger
  ├─ typed command validation
  ├─ project/deck ACLs
  ├─ immutable public/private target
  └─ append-only audit log
          │
          ▼
Isolated compiler/export worker
  ├─ immutable input revision
  ├─ no network by default
  ├─ CPU/memory/time limits
  └─ content-addressed output artifacts
          │
          ▼
Private artifact storage
  └─ short-lived signed download links

The minimum endpoints are:

GET  /decks/{id}?revision=42
POST /decks/{id}/commands
POST /decks/{id}/assets
POST /decks/{id}/exports
GET  /exports/{job-id}

Every command should carry base_revision, actor identity, idempotency key, and target classification. Export should compile an immutable revision—not whatever files happen to be present when the worker starts.

10. P1 — The local chat is not a direct mutation bypass, but it is not yet a credible approval surface

I did not find a direct deck-mutation path in the current local chat. Its deterministic interpreter reads emitted data, and live-agent replies are displayed as React text rather than injected HTML. That is the right ownership boundary.

However:

show <id> claims to show the full claim record, but the UI bundle omits source refs, visibility, notes, evidence excerpts, approval provenance, and source digests.

It searches only claims already bound to deck slides, not the complete ledger.

qualify <id> instructs the user to set status to qualified, but qualified is not a valid ClaimStatus; valid values are only candidate, approved, and rejected.

Approval advice is prose rather than a typed, reviewable proposal.

Design sketch: Chat should produce a proposal object:

JSON
{
  "op": "claim.approve",
  "claim_id": "claim-17",
  "base_revision": 42,
  "source_snapshot_sha256": "...",
  "required_qualifier": "...",
  "reason": "..."
}

The UI then presents the source excerpt, visibility, risk, resulting slide changes, and an explicit confirmation. Submission goes through the same authenticated command API as every other edit. Chat should never receive a special mutation path.

11. P1 — Text will diverge before geometry; the current browser-to-PPTX font conversion is already inconsistent

The exact fractional geometry claim is credible for box position and dimensions. It is not a WYSIWYG text claim.

For freeform text, the browser computes:

TypeScript
(size_pt / 7.5) * (1080 / 96)

That yields size_pt × 1.5 CSS pixels. But a 1080-pixel canvas representing 7.5 inches has 144 pixels per inch. A 20-point font should therefore occupy approximately:

20 / 72 inches × 144 pixels/inch = 40 pixels

The current browser preview uses 30 pixels. PPTX text is consequently about one-third larger relative to its box before glyph metrics are considered.

The browser inherits Inter, while the PPTX builder uses Arial. The PPTX text boxes use fixed font sizes and fixed heights with word wrapping but no explicit autofit or shrink policy.

The first failures will be:

different line breaks;

final lines clipped below a fixed text box;

headings wrapping in PPTX but not in the browser;

bullet rows becoming too short after font substitution;

Google Slides import applying another substitution/layout pass.

python-pptx exposes TextFrame.auto_size and fit_text() mechanisms, including fitting against font metrics, but these need an explicit product policy rather than being applied opportunistically. 
python-pptx
+2
python-pptx
+2

Mature handling pattern:

Use the same constrained font family in browser and PPTX.

Correct the point-to-canvas conversion.

Add a per-box policy: error, shrink_to_min, manual_breaks, or flatten.

Measure using the actual target font.

Store resolved line breaks and font size in the render plan when determinism matters.

Render the PPTX through LibreOffice and compare it to the browser reference with a visual-difference threshold.

Extract final PPTX text and verify required runs and qualifiers survived.

For especially complex visual groups, support an explicit flattened-image mode; do not silently rasterize everything and lose editability.

Font embedding can reduce substitutions when the font’s license permits embedding, but it should not replace target-render verification. 
Microsoft Support
+1

Also validate target-specific values during edit. For example, FreeformElement.color currently accepts an arbitrary string; invalid CSS may be ignored by the browser while the PPTX hex parser fails during export.

12. P2 — The editor is coherent in normal canvas mode, but overloaded when source mode is open

The freeform screenshot has a recognizable editor hierarchy: slide rail, canvas, contextual toolbar, inspector. The source screenshot crosses the usability threshold: source pane, slide rail, canvas, and inspector compete simultaneously, leaving the actual slide too small to judge.

A clearer mode architecture would be:

Design | Claims | Source | Present

Design should contain only the rail, canvas, and context-sensitive inspector.

Claims should center on the selected slide or selected text run, with a claim table, evidence drawer, qualifiers, and approval history. Chat can be a secondary assistant inside this mode rather than half of the primary screen.

Source should be a dedicated full-height editor with schema completion, changed-line indicators, validation messages linked to YAML paths, and an accepted-versus-proposed diff. It should not be a fourth persistent column.

Present should remove all editor chrome and use the exact revision being reviewed.

The layout gallery should initially show the few layouts compatible with the current content, with “All layouts” expanding the rest. Move-left/right operations belong naturally in the slide rail or keyboard shortcuts; the primary header should prioritize document status, undo/redo, mode, collaboration state, and export.

Designer-quality gaps beyond undo/redo include:

multiselect, group/ungroup, lock, and layers;

z-order, align, distribute, snapping, guides, safe areas, and keyboard nudging;

copy/paste, duplicate element, and paste style;

crop, focal point, mask, and asset replacement;

theme tokens and controlled typography;

visible text-overflow handling rather than advisory badges;

accessibility reading order, contrast checks, and alt-text review;

comments, revision history, conflict handling, and export preflight;

keyboard focus management and non-pointer editing paths.

Undo/redo and revision history should be implemented before adding substantially more formatting controls. Otherwise every new control multiplies irreversible write paths.

13. P2 — One-way typed-to-freeform conversion is acceptable, but only as an explicit detach operation

Freeform should not become the only layout model. Typed layouts provide semantic roles, predictable accessibility order, stronger overflow constraints, easier claim binding, and more reliable PPTX generation.

The one-way conversion becomes a trap only because a normal layout picker implies reversible transformation. Treat it as:

Detach from layout

The operation should:

show a confirmation;

record origin_layout, origin_revision, and semantic slot mappings;

create freeform elements with roles such as title, message, body[0], and visual;

remain undoable through revision history;

clearly indicate that future typed-layout changes will not automatically apply.

A useful hybrid is:

YAML
layout:
  mode: template
  template: split
  overrides:
    title:
      frame: [0.06, 0.07, 0.60, 0.12]
    visual:
      frame: [0.62, 0.30, 0.32, 0.50]

That permits local adjustment while retaining semantic slots. Full freeform is then the escape hatch for the minority of slides that genuinely need it.

A “Suggest typed layout” command can analyze a detached slide and propose a mapping, but it should be previewed and accepted as a new revision—not advertised as lossless reverse conversion.

14. P2 — Rejecting general bidirectional Markdown was the right decision; a constrained claim-safe outline mode remains possible

Ordinary Markdown cannot preserve claim status, visibility, source snapshots, qualifiers, freeform geometry, asset classification, animation data, or approval history. Making it canonical would weaken the exact properties that distinguish this compiler.

YAML is therefore the right canonical serialization. It is not, however, the ideal everyday authoring interface for most deck authors.

A constrained Markdown projection could safely support semantic content:

Markdown
<!-- slide:id=s03 revision=42 layout=statement -->

# {{claim:claim-problem}} Compliance review is difficult to inspect

- {{claim:claim-result}} Review time fell by 31%
- {{nonclaim:pilot-scope}} Internal 12-user pilot; not a production result

Safe round-trip rules would be:

slide and content-run IDs are stable;

geometry, theme, assets, and approval metadata remain in the sidecar/canonical model;

editing approved claim text creates a new candidate revision rather than silently changing the approved claim;

untagged substantive prose either creates a candidate claim or fails validation;

unknown or deleted IDs fail closed;

only semantic title/message/body/notes content participates;

freeform layout is read-only or explicitly unsupported in outline mode.

That is not general Markdown synchronization. It is a claim-aware outline editor rendered as Markdown. The current one-way Marp export should remain one-way.

15. Required proof before reconsidering release

The existing positive and negative tests demonstrate useful plumbing, but they do not close the central boundary. The next proof bundle should include at least these executable cases:

visual.items: ["production-ready"] is rejected or claim-bound in both React and PPTX.

A newly added slide cannot persist substantive text with no content-run claim binding.

A qualifier in body item five cannot disappear from a statement PPTX.

A qualifier in a stale freeform element cannot satisfy a typed-layout slide.

deck.public.yaml cannot change its target to private or public_and_private.

A public publish export fails with candidate claims; a draft export is visibly watermarked.

Every rendered textual field—including footer, caption, callout, visual item, and missing-asset text—is covered by the same content-run validator.

An unrelated nearby negation does not qualify a forbidden assertion.

Unknown or private claim source references fail a public build.

Clearing an asset makes its previous public URL inaccessible.

Two edits against the same base revision produce one success and one 409, not a lost update.

The final PPTX text-run inventory matches the render plan, including all mandatory non-claims and visible qualifiers.

Browser and LibreOffice-rendered PPTX stay inside an established visual-difference threshold on typography stress fixtures.

Malformed, oversized, mislabeled, and resource-exhausting asset uploads fail before persistent writes.

The compiler thesis and much of the UI are worth retaining. What needs rethinking is the canonical content model: today the system validates selected slide fields and metadata, not every statement that the renderers can place before an audience.

VERDICT: RETHINK
