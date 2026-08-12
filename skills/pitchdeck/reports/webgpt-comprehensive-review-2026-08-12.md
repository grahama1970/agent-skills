POSITION

The immutable goal is still not met.

The current system has advanced from a weak palette anomaly filter to a substantially better supervised deck-production pipeline:

claim-bound PPTX compilation is credible;

the emitted Sparta deck satisfies useful archetype and structural checks;

the gate catches gross layout, typography, visual-area, card-grid, and deck-arc mutations;

the artifact and render chain is materially harder to spoof;

the browser now approximates the canonical document rather than re-deriving a foreign layout.

But the remaining gaps map directly onto the immutable goal:

“Looks like a Graham pitchdeck” is not validated. The blinded set became development data, and the one content-register mutation the current channels cannot see still passes.

The image-source policy is not actually closed. Several intake and generation routes bypass reference lineage or can adopt arbitrary outputs.

The human-edit boundary is unsafe. Post-approval edits structurally validate but do not preserve assertion, asset, narrative, and release authorization.

The human-review UI is not release-ready. It exposes document-mode actions that are legacy-only, inaccessible, inert, or failing at runtime.

The north-star eval does not exercise the human-review/edit/export loop. Its final status explicitly remains HOUSE_NON_ANOMALOUS, not a validated positive style classification.

The honest current label is:

Supervised README + approved outline + approved assets → claim-faithful, structurally house-shaped PPTX, with an editable but not yet release-safe review UI.

Not:

A validated cold README-to-Graham-deck compiler.

“All seven slices were worked” is accurate only as a progress statement. Their own issue receipts still describe major portions as incomplete: Qdrant index contents are not digest-bound; structural distance and several archetype geometries remain; leave-one-deck-out folds still leak cross-deck duplicate clusters; the art-register channel is not implemented; cold/no-network CI is incomplete; and the confirmatory blind has not happened.

RANKED_NEXT_5
1. Make post-approval editing transactional, claim-safe, and export-gated

This is the highest-leverage action because a single human edit can currently invalidate the entire proof chain after all thirteen stages have passed.

document-edit presently:

modifies the canonical document directly;

checks only that the resulting JSON satisfies the DeckDocument schema;

accepts text changes without calling assertion authorization;

accepts asset swaps when the asset ID merely exists;

writes the document before UI reprojection succeeds;

has no base-document digest or compare-and-swap protection in the command itself;

does not regenerate the build manifest, PPTX, publish verification, style gates, or visual approval.

This is more decisive than a confirmatory holdout. A validated classifier attached to an unsafe editor still produces unsafe final decks.

The UI reliability defects belong in the same P0 because the UI is the human review boundary, not a sidecar.

2. Close #1331 and enforce immutable design-source lineage at every asset entry

The image policy is currently a documented convention with several bypasses, not an invariant.

The approved-asset registry remains open and explicitly P0.

Until it closes, the compiler cannot reliably distinguish:

README-extracted source imagery;

a crop derived from that imagery;

a reference-conditioned derivative;

an arbitrary uploaded image;

a generated candidate from an unrelated run;

an evidentiary screenshot;

a merely decorative image;

an SVG containing model-invented text.

This is more fundamental than confirmatory gate scoring because it controls what the gate is asked to certify.

3. Close #1383: add a channel that can detect art-register substitution

The development holdout demonstrated one concrete false-pass class:

Drawn/source-native imagery replaced with glossy teal 3D stock art, with text, boxes, geometry, and palette held constant.

It passed every existing channel. That is not a hypothetical edge case; it is the measured missing dimension.

A confirmatory run before closing this would knowingly test a classifier with a demonstrated blind spot. Worse, the current acceptance bar permits one off-house false pass, so the confirmatory run could “pass” while reproducing the known defect.

4. Run a genuinely confirmatory holdout

This becomes the next step only after actions 1–3 are frozen.

The existing holdout cannot be reused. It was consulted through six rounds of renderer changes, population reweighting, threshold changes, tolerance introduction, and embedding-floor adjustment. The project correctly admits that its blind is spent.

Fresh mutant seeds are necessary but insufficient. A true confirmation needs:

fresh off-house mutants;

at least one second generated deck;

fresh positive Graham material not used during runs 1–6;

no known-deck exception tables;

no code, calibration, model, or threshold changes after scoring begins.

If no fresh Graham deck exists outside the five development decks, you do not have a deck-level confirmatory positive set. Fresh slide crops from those same decks are not an equivalent substitute because their deck identity and design families have already influenced the gate.

5. Make the north-star a clean-checkout, no-network, internally consistent eval

The current north-star still depends on absolute workstation and temporary scratchpad paths for:

approved outline;

deck context;

publication approvals;

house template;

source tree.

Its coverage stage allows up to two public claims to be missing while the fixture claims coverage is 11/11. Its agentic fixture says “11 stages” while the current shell pipeline contains thirteen. It also retains a supposedly “cold” positive case pointing at a pre-existing /mnt/storage12tb document.

That needs to become a self-contained proof, not a workstation ritual.

This slice should also close the remaining calibration debts:

digest the actual Qdrant index contents or remove that channel from the verdict;

make duplicate clusters incapable of crossing LODO folds;

remove development-deck-specific allowances;

complete the committed unseen-README cold refusal fixture;

enforce no-network artifact mode.

Imagery rule: remaining enforcement holes

The design correction is directionally right, but “reference required, no exceptions” is not yet true in code.

Direct bypasses

Legacy image-variations remains a text-to-image generator. It uses hand-written style axes and Codex/image generation with no reference image. That is an exact violation of the new rule.

asset-alternates --select can adopt any local file. It does not require the selected file to be a candidate named in a reference-bound receipt. It simply copies the bytes over the target and edits the manifest.

The “reference” may be arbitrary or derivative. It defaults to the asset’s current file. After one generated derivative is adopted, the next generation can use that derivative as its authority. This permits reference laundering and gradual drift away from the README original.

asset-add and UI drag/drop accept arbitrary imagery. Alt text and basic manifest registration are not source lineage, rights approval, visible-text approval, or design-source provenance. The UI asset-drop route is still the legacy bundle intake.

--example still competes textually with the reference. The implementation appends filename-derived “in the spirit of” language to the prompt. That directly contradicts the claim that no style suffix competes with the shown reference.

--figure bypasses the reference requirement. Deterministic figures should indeed have a different contract, but that means the invariant should be typed as:

No unreferenced generative illustration.

Data-derived charts and diagrams should require a claim-bound data/spec provenance chain, not a fictitious image reference.

Backend capability is asserted, not proved. Passing --reference does not prove a backend consumed those bytes. The receipt needs the reference hash, request payload digest, backend/model digest, and returned output hash.

Model-generated words are not controlled by “no text” prompting. Raster outputs need a human visible-text attestation bound to the output hash. OCR can be an advisory detector but not publication proof. An unknown result must refuse.

The Claude SVG path is insufficiently constrained. It extracts the first <svg>…</svg> region from model output and rasterizes it. It needs SVG sanitization, external-reference refusal, deterministic <text> inspection, font handling, source-reference receipt binding, and explicit human fidelity approval.

Hand crops have no semantic provenance. A crop can hide an error, timestamp, status label, caveat, or surrounding context. Every crop needs:

source asset hash;

crop rectangle;

resize/interpolation operation;

output hash;

source README reference;

visible-text manifest;

approved role;

human approval.

The README is a valid source of visual evidence and product identity. It is not automatically a sufficient source of house composition. A raw screenshot still needs house-accurate framing, hierarchy, and archetype treatment. The current formulation should not be used to waive those design checks.

AUDIT_OF_RUNS_1-5

The trail is development, not confirmation. Correctly documenting every change does not preserve blindness.

Run	Change	Audit
1	Initial blinded result: 0/5 real decks passed; 1/8 mutants false-passed	Valid discovery result. It established that the gate was unusable as calibrated.
2	Scan master-level chrome; use LibreOffice provenance end-to-end	Legitimate measurement-category fixes. The scanner omitted a real presentation surface, and calibration/scoring used different rendering instruments. These are instrumentation errors. They still consume the holdout and require a new confirmatory set afterward.
3	Reweight floors from duplicate-cluster representatives to pages	Crosses into estimator tuning. “The judged unit is a page” does not justify giving repeated pages repeated votes. The prior duplicate analysis established that pages are correlated. Changing the statistical population after seeing false rejects is a modeling decision, not merely fixing a broken sensor.
4	Move pixel floors to corpus minima	Definite semantic change and threshold relaxation. This demotes ink and palette from positive style evidence to anomaly floors. That is defensible only if reported exactly that way. It cannot also support HOUSE_POSITIVE_MATCH. The observation that stricter floors cannot admit sparse pages while catching register swaps proves the channels are insufficient; it does not prove minima are a positive-style threshold.
5	Allow the worst real deck’s conformance failure rate, 7.5%	Direct holdout fitting. The tolerance is calculated from the same decks being evaluated. This is not a frozen corpus law. It encodes the development holdout’s worst result into acceptance and should not survive into confirmation.

The report accurately records the progression, including the switch to minima and the worst-deck allowance.

Two additional changes deserve the same scrutiny:

Nearest-cluster palette is a defensible model improvement, but because it was selected after inspecting holdout failures, it is development tuning and must be frozen before confirmation.

Embedding 0.395 → 0.39 based on ReqML page 49 scoring 0.39496 is post-hoc threshold tuning. A renderer-jitter margin is legitimate only when estimated from a preregistered repeated-render experiment, with the margin frozen before evaluating labeled pages. The current calibration source explicitly names the failing ReqML measurement as the reason for the new value.

What the confirmatory protocol must pin

Before any confirmatory image is scored, commit and digest:

source commit and clean tree;

every gate implementation;

corpus roster;

duplicate-cluster assignments;

archetype assignments;

all thresholds and tolerances;

aggregation and waiver formulas;

model name and weights digest;

Qdrant collection content digest, not merely collection name;

renderer, rasterizer, fonts, DPI, dimensions, and color profile;

text-mask algorithm;

expected page counts;

missing/error behavior;

mutant generator code and seed list;

positive and negative sampling protocol;

exact pass bar;

label-sealing mechanism;

report generator.

Renderer jitter must be estimated beforehand using repeated renders of an unlabeled calibration subset. It cannot be inferred from a confirmatory failure.

The protocol must state:

Any implementation, threshold, tolerance, corpus, or model change after scoring invalidates the run. The revised system requires a new untouched holdout.

No “bug-fix rerun” of the same confirmatory set may unlock the phrase.

EDIT_CONTRACT

The minimum safe contract is not “Pydantic accepted the edited document.” It is a typed edit transaction with authorization state.

1. Every edit is an operation against a specific approved revision

Required input:

edit_id
actor_id
base_document_sha256
base_revision
slide_id
element_id / slide operation
operation_type
old_value_digest
proposed_value

A stale base digest must return a typed conflict. It must not partially apply or silently overwrite another edit.

2. Classify the edit before applying it
Geometry or typography edit

Examples: move, resize, alignment, font size, bold.

Required gates:

document schema;

protected-zone geometry;

clipping/overflow;

archetype structure;

visual-assertion relationships;

render parity;

visual approval invalidation.

It need not invalidate the narrative outline when no meaning changes, but it must invalidate the previous build manifest, render receipt, house-gate receipt, and visual approval.

Text edit

The existing atom’s approval does not authorize replacement text.

The edit must run through authorize_atom:

verbatim/truncation/inflection: mechanically verify against the bound claim;

aggregation/generalization: create a candidate and require named human approval;

nonclaim/chrome: require a role-scoped typed authorization;

qualifier: preserve claim association, placement, and minimum legibility;

title/purpose changes that alter slide intent: invalidate outline approval.

Until authorized, the document is EDITED_PENDING_CONTENT_APPROVAL and cannot produce a publishable export.

Asset swap

The new asset must pass:

approved registry;

source/design-reference lineage;

content hash;

visibility;

rights;

allowed target;

approved role;

visible-text manifest;

generated/derived/source classification;

evidentiary versus decorative status;

required VisualAssertion bindings.

“Asset ID exists in doc.assets” is not enough.

Add/delete/reorder slide

These affect narrative coverage and deck meaning. They must invalidate:

outline approval;

claim coverage receipt;

deck structural/arc receipt;

visual approval.

3. Commit atomically

The current implementation writes deck.document.json before projection. If projection or the second write fails, the supposedly rejected edit has already changed the canonical document.

Required sequence:

Load current files and verify base digest.

Apply to an in-memory copy.

Run authorization and validation.

Write document, UI payload, edit receipt, and state marker to temporary files.

fsync.

Atomically rename all outputs or roll back all outputs.

Return the new revision and digests.

4. Export must consume the edited revision

Publication export must refuse unless:

no pending content, asset, or narrative approval exists;

build manifest was regenerated from the edited document;

PPTX was regenerated;

verify-publish passed;

asset and visual assertions passed;

render receipt matches;

house gates passed;

a new human visual approval covers the exact final render.

A human should be free to edit. They should not be able to accidentally deliver a deck under stale approvals.

UI contract: release-blocking versus deferrable

The interaction findings are not polish. They expose that the claimed review surface is only partially integrated.

Release-blocking

Any HTTP 500 on a core review/edit/save/export action. Expected failures must become typed UI states, not server crashes or console errors.

Current missing-context 409s. A 409 is acceptable only for a real revision conflict with a visible “reload and retry” recovery. A 409 because a document-mode screen invoked a legacy bundle endpoint is a blocker.

Enabled inert controls. Add, duplicate, move, delete, undo, asset attach, layout, notes, footer, bullet, and export controls must either work in document mode or be hidden/disabled with a reason.

EditToolbar always calls legacy /api/deck-op and /api/undo.

Inspector exposes layout, transition, reveal, visual position, footer, notes, and bullet operations that document-edit does not implement.

The asset-swap control is not actually reachable. In FloatingToolbar, the asset selector is nested inside the isText branch while also requiring isAsset, an impossible condition. The reported round trip therefore proves the backend command, not the human toolbar path. The same toolbar exposes entrance and delete operations unsupported by document-edit.

Keyboard-inaccessible core editing. Freeform element selection is a clickable <div> without tabIndex, keyboard handlers, or a semantic role. react-rnd drag and resize are mouse-only. There is no equivalent numeric x/y/w/h inspector. This directly explains at least part of the keyboard-unreachable report.

Missing data-qs-action on an interactive QID. The declared contract is agent-drivability. It must apply to inputs, selects, sliders, custom role-buttons, and drag handles—not only the Button primitive. The current primitive enforces the contract only for Button.

Unidentified console errors and inert actions. Every discovery finding must map to an exact QID, action, expected effect, and disposition. “Could be a test artifact” is not closure evidence.

Non-atomic saves. A UI that can report failure after changing the canonical file is not release-safe.

Deferrable only with capability gating

Voice recording, model-assisted chat, alternate generation, or other optional network features may be deferred if their controls are absent or disabled when unavailable and no console error is emitted.

Direct keyboard dragging may be deferred if complete numeric frame editing is keyboard accessible.

Presenter animation controls may be deferred if the core review, text edit, asset swap, and PPTX export path works.

A deliberate CAS 409 is acceptable when it shows a conflict dialog and preserves all data.

With the current unknown 500s, nine console errors, legacy document-mode calls, inaccessible element selection, and enabled inert controls, the human-review surface is release-blocking.

The browser issue itself remains open and acknowledges missing diagram/icon rendering and browser-versus-LibreOffice parity.

DELETE_LIST
Delete now

Delete image_variations.py and the image-variations CLI command. It directly violates the reference-required design rule.

Delete asset-alternates --example. Filename-derived stylistic suggestions compete with the actual reference.

Move --figure out of asset-alternates. Create a separate deterministic, claim-bound figure command. It is not an alternate-image-generation exception.

Delete unsupported backend choices from the public interface. Do not advertise Flux or Ollama in a reference-required command when the implementation refuses them for lack of reference input.

Delete the universal HOUSE_VISUAL_DENSITY median-as-minimum rule. It is not an invariant and has already false-rejected legitimate sparse real slides.

Delete the worst-development-deck conformance allowance from the positive classifier. That is fitted tolerance, not house design law.

Delete or hide all legacy bundle-only editing controls in document mode. Do not leave enabled buttons that are known to return 409 or 422.

Delete the stale materialized-cold-deck-clean agentic-eval case. A pre-existing absolute-path artifact is neither cold nor self-contained.

Delete absolute /tmp/claude…/scratchpad dependencies from the north-star. Approved context and approvals belong in a digest-bound fixture.

Remove the generic /project-state --quick result from pitchdeck readiness evidence. It collected zero pitchdeck tests and described the 385-skill repository. Fix skill-root detection in /project-state; do not treat this report as a pitchdeck signal.

Demote after #1383 proves a replacement

Remove the text-confounded Jina/Qdrant channel from the release verdict. Keep it as a semantic render diagnostic only. This also removes a live service and mutable index from the release-critical path.

Keep ink and palette minima only as anomaly diagnostics. They cannot contribute positive “looks like Graham” evidence merely because they are calibrated.

Keep blind-attribution and authorship language out of the release status until confirmation.

EXECUTABLE_SLICES
Slice 1 — Post-approval edit transaction and document-mode UI closure
Capability

One atomic edit service for the canonical document, with typed authorization state, CAS revision control, rollback, capability discovery, and export invalidation.

Local proof
Bash
cd skills/pitchdeck

python -m pytest -q \
  tests/test_document_edit_authorization.py \
  tests/test_document_edit_atomicity.py \
  tests/test_document_edit_revision_conflicts.py \
  tests/test_document_mode_capabilities.py

./scripts/prove_review_edit_export_chain.sh

cd ui
pnpm test:interactions -- \
  --base-url http://127.0.0.1:3006 \
  --mode document \
  --output ../reports/document-ui-interactions.json
Acceptance

Unauthorized text replacement causes zero file changes.

Legal truncation passes and emits a new authorized atom.

Generalization remains pending until named approval.

Geometry edits invalidate render/style/visual approvals but not content approval.

Slide add/delete/reorder invalidates outline approval.

Unregistered or role-incompatible asset swaps refuse.

A simulated projection failure leaves both document and UI payload byte-identical.

Stale revision produces a typed 409 conflict with a reload path.

Export refuses while any approval or manifest is stale.

Zero HTTP 500s.

Zero unhandled console errors.

Zero missing data-qs-action findings.

Zero enabled inert core controls.

Every core control is keyboard reachable.

Asset swap is exercised through the actual visible toolbar, not direct API calls.

Slice 2 — Approved asset registry and immutable reference lineage
Capability

Every source image, crop, derivative, upload, SVG, screenshot, and generated alternate carries a closed provenance and approval record.

Local proof
Bash
cd skills/pitchdeck

python -m pytest -q \
  tests/test_asset_registry.py \
  tests/test_asset_reference_lineage.py \
  tests/test_crop_provenance.py \
  tests/test_asset_visible_text.py \
  tests/test_svg_asset_safety.py \
  tests/test_asset_adoption_receipts.py

./scripts/prove_asset_registry_reference_lineage.sh
Acceptance

image-variations no longer exists.

An arbitrary --select /tmp/file.png is refused unless the hash appears in a reference-bound candidate receipt.

The immutable README-origin reference asset ID and hash are recorded.

A derivative cannot become its own design authority without explicit human promotion.

UI uploads enter PENDING_ASSET_APPROVAL, not immediately publishable state.

Every crop records source hash, rectangle, transform, and output hash.

Cropping away a mandatory status or qualifier is refused.

Raster visible-text status unknown refuses publication.

SVG <text>, scripts, remote references, unsafe fonts, and undeclared embedded data are refused.

The actual backend request receipt proves which reference bytes were supplied.

Asset rights, visibility, role, target, and named approval are required.

Data-derived figures use a separate claim/data-bound contract.

Slice 3 — Art-register discrimination channel
Capability

A pinned, text-masked visual channel that detects image-content/register substitutions after text, chrome, and layout are held constant.

Local proof
Bash
cd skills/pitchdeck

./run.sh benchmark-house-channel \
  --channel masked-spatial \
  --cases fixtures/house-gate/art-register-development.v1.json \
  --calibration fixtures/house-gate/calibration.v1.json \
  --output reports/masked-spatial-ablation.json

./run.sh benchmark-house-channel \
  --channel dinov2-masked \
  --cases fixtures/house-gate/art-register-development.v1.json \
  --calibration fixtures/house-gate/calibration.v1.json \
  --output reports/dinov2-masked-ablation.json

python -m pytest -q tests/test_art_register_gate.py
Acceptance

art-register-swap is rejected.

Honest Sparta imagery remains accepted.

No real Graham development deck becomes a false reject.

Text masking is derived from PPTX text regions and is digest-bound.

Model identifier and weights digest are frozen.

The channel adds at least the preregistered balanced-accuracy improvement.

Thresholds are fixed before the confirmatory set is generated.

Gram-matrix work is not added unless both cheaper channels fail on the named register mutant.

Slice 4 — One-shot confirmatory “looks like Graham” evaluation
Capability

A preregistered, sealed, one-shot confirmation on fresh positive and negative material.

Local proof
Bash
cd skills/pitchdeck

./scripts/freeze_house_gate_protocol.py \
  --config fixtures/house-gate/confirmatory-protocol.v1.yaml \
  --output fixtures/house-gate/confirmatory-protocol.v1.lock.json

./scripts/run_house_gate_confirmatory.py \
  --protocol fixtures/house-gate/confirmatory-protocol.v1.lock.json \
  --sealed-cases /mnt/holdout/pitchdeck-confirmatory-2026-08 \
  --output reports/house-gate-confirmatory-2026-08.json

./scripts/verify_confirmatory_integrity.py \
  reports/house-gate-confirmatory-2026-08.json
Acceptance

At least one real Graham deck was never used in runs 1–6 or gate development.

At least one second generated deck was not used in threshold selection.

Mutant seeds and source assets are fresh.

All real held-out decks pass.

At least 90% of held-out real duplicate clusters pass.

No named hard mutant—art-register, mirror, ransom-note typography, card-grid, tiny visuals, or arc shuffle—passes.

Overall off-house false-pass rate stays within the preregistered bound.

Code, calibration, thresholds, model, index, renderer, fonts, and protocol digests match the frozen record.

No implementation or threshold change occurs between scoring and publication.

A failed integrity check makes the result inadmissible.

Failure does not trigger a rerun on the same sealed cases.

Only this receipt may unlock HOUSE_POSITIVE_MATCH or “looks like a Graham pitchdeck.”

Slice 5 — Self-contained cold and artifact north-star profiles
Capability

Two honest eval profiles:

deterministic artifact assembly from README + approved outline + approved assets;

unseen README cold-authoring behavior.

Local proof
Bash
cd skills/pitchdeck

env -i \
  PATH="$PATH" HOME="$HOME" \
  PITCHDECK_NO_NETWORK=1 \
  ./scripts/prove_north_star_clean.sh \
    --fixture tests/fixtures/e2e/sparta-artifact \
    --work-dir /tmp/pitchdeck-clean-artifact

env -i \
  PATH="$PATH" HOME="$HOME" \
  PITCHDECK_NO_NETWORK=1 \
  ./scripts/prove_north_star_clean.sh \
    --fixture tests/fixtures/e2e/unseen-readme-no-art \
    --expect NEEDS_APPROVED_ART \
    --work-dir /tmp/pitchdeck-clean-cold

python -m pytest -q \
  tests/test_north_star_contract.py \
  tests/test_no_network_artifact_mode.py \
  tests/test_duplicate_cluster_folds.py \
  tests/test_house_index_digest.py
Acceptance

Runs from a clean checkout.

No /tmp/claude…, prior output directory, or hidden scratchpad input.

No network access in artifact mode.

Every required fixture is committed or passed explicitly.

Public claim coverage is exactly 11/11; one missing claim fails.

Stage count in docs, script, and agentic fixture agrees.

No pre-existing approved document is used as a “cold” case.

Missing approved art produces NEEDS_APPROVED_ART.

A README containing approved source imagery can proceed without generated filler.

Qdrant index contents are digest-bound if the embedding channel remains.

Duplicate clusters cannot cross LODO folds.

The final artifact-mode receipt says only what it proves.

The UI edit-and-export transaction is part of the full immutable-goal eval, not an untested side surface.
