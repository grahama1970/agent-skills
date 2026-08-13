# webgpt: agentic-evals design for pitchdeck (2026-08-13)

Source: /ask -> Tau DAG -> webgpt, given both repos (grahama1970/sparta private,
grahama1970/sparta-public public), the immutable goal, the honest current state,
the agentic-evals v2 contract + anti-slop rules, and the named open holes.
Sentinel: <<<WEBGPT_DONE:20260813T141513Z:2a1e5ba5>>>

## POSITION

Adopt this fixture as the replacement acceptance contract. For an `audience=public`
deliverable, **`grahama1970/sparta-public` at one resolved commit is the sole source
authority**. The private repository is only a drift oracle and a source for
individually approved promotions. It must never be an implicit fallback, even when
its text is richer or an asset has identical bytes. For an internal/private deck,
`grahama1970/sparta` becomes a separately declared authority.

The existing green suite may continue to report `HOUSE_NON_ANOMALOUS`, but it is not
entitled to report a validated positive "looks like a Graham pitchdeck" result until
the art-register mutant is rejected and a fresh, unspent confirmatory holdout passes.

## FINDINGS_FROM_SOURCE

**The packet's public-source snapshot is stale.** Current `sparta-public` at
`a7241754f6954a8cdbe3cbac79a1b536023d1c76` now carries essentially the full product,
demonstration, workflow, status, responsible-use, and collaboration narrative. Its
public-specific changes are an opening repository-boundary notice and removal of
links into private documentation and issues. Therefore "use the richer README" is an
unsafe source-selection rule; source authority must be declared before sectioning or
claim extraction.

Claim boundaries a source-specific eval must preserve (not merely the nouns):
- F-36 is fictional and synthetic.
- Relevance is not support; adjacency is never proof.
- Candidate visibility is not compliance credit.
- Models navigate and explain; authorized people decide.
- Embry OS is planned, is not flight-control software, grants no decision authority.
- `Implemented`, `Demonstrated`, `In integration` are different statuses.
- `canonical-active` does not mean expert-approved/implemented/compliance-credited.
- Mutable counts require population, date, and source artifact.
- Current route is prepared-host evaluation, not verified clone-and-run/turnkey.
- Local-first does not establish export-control compliance, authorization,
  accreditation, certification, or risk acceptance.

**Public-source deictic conflict (needs the source owner's decision).** The opening
says the public repo is README+screenshots while implementation lives privately;
later prose defines "Implemented" as existing "in this repository", describes
"repository-local" surfaces, and names `explorer/`, `src/sparta/`, `scripts/`,
`tests/`. A public build must either receive a named attestation rewriting the
referent to the private workspace, or refuse with
`REFUSE_SOURCE_CONTRADICTION_REQUIRES_ATTESTATION`.

**Visual inventory at the pinned public commit:** eight WebP figures plus one SVG
helmet mark — six dense dark-interface captures, one cinematic conceptual Embry OS
illustration, one multibranch response-flow diagram. Screenshots are text-heavy and
become unreviewable as decorative thumbnails; the Embry image is explicitly
conceptual, and the response flow is a conceptual contract view, not implementation
evidence.

That mixed inventory changes the art-register test: "glossy or cinematic" cannot be
globally forbidden because the README itself contains an authorized cinematic
illustration. The mutant must prove the gate distinguishes (1) an exact source asset
or approved derivative, (2) an unauthorized same-palette substitute, (3) a source
asset used with the wrong evidentiary status, (4) an otherwise authorized visual in
the wrong slide role.

Private availability is not public approval. The private publication manifest makes
the human boundary explicit: visual files require human inspection because automated
scanners cannot reliably detect visible browser chrome, tabs, hostnames, real
customer names, or similar disclosures. A private-image promotion receipt must bind a
named human visual review, exact blob SHA, audience, permitted role, use count,
expiry, and approval scope.

**Deterministic image-use policy:** public deck must represent all eight curated
public WebPs at least once; default per parent image at most two total uses and at
most one principal use (crops count against parent); assertion+art/process/product-
tour slides exactly one principal visual; section dividers zero principal visuals
(product mark only); cover/bullets/close zero or one, archetype-conditioned; at most
two supporting visuals per slide and a supporting visual may not dominate the
principal; helmet mark only in designated mark slots; exceptions require a human
`image-use-exception` receipt bound to audience, blob, slide IDs, allowed counts.

## CASE_SET

The proposed `sparta_v2.py` is a thin fixture adapter that must invoke production
compiler/validator/renderer/document-edit/React/export entry points rather than
reimplementing them. Every successful subcommand must emit an evidence receipt with
source SHA, input/output digests, artifact paths, and invoked entry points; the
harness must independently recompute at least one bound digest. Printing expected
strings without artifacts must fail adapter self-tests.

The machine-readable fixture is committed alongside this report as
`fixtures/sparta_agentic_evals_v2.design.json` (20 cases: 7 positive, 3 negative,
10 adversarial).

## ADVERSARIAL_RATIONALE (highlights)

- Matrix cases exit 0 only when EVERY internal mutant is independently refused —
  preventing a false green where one early rejection masks untested mutations.
- `mixed_public_readme_private_asset_root_refused` uses a screenshot whose blob is
  shared by both repos but resolved from the private root: identical bytes must not
  override the source boundary.
- `private_readme_claim_lineage_leak_refused` injects private lineage into visible
  text, links, notes, alt text and package relationships — the boundary scan must
  inspect the entire PPTX package, not just rendered slide text.
- `art_register_substitution_refused` preserves palette, geometry, typography and
  layout so the anomaly channels stay green; only source/register-aware positive
  validation can reject it — and it must reject because the asset is not the declared
  source and not in the approved slide-role register, NOT merely because it is
  cinematic (that protects the legitimate Embry OS conceptual image).
- `page_clone_mutant_refused` varies authorized text, crops and page numbers so exact
  duplicate detection is insufficient; deck-architecture diversity must fail.
- `confirmatory_unspent_style_holdout_live` uses two separately sealed partitions
  keyed by trial index, verifies they were unspent, and freezes the mutant generator.

## DOES_NOT_PROVE

Even with all twenty cases green, the fixture must not claim: that README product
claims are independently true; that any private asset is publication-safe because a
receipt validates mechanically; that the deck/repos are free of ITAR/CUI/classified/
proprietary/customer/third-party licensing concerns; that automated inspection
replaces the required human visual review; that a simulated browser reviewer made a
sound substantive judgment; that Sparta Explorer is production-ready/accredited/
certified/secure/deployable; that HOUSE_NON_ANOMALOUS equals a positive Graham-style
classifier; that 5-real/8-mutant confirmation establishes universal generalization;
that the classifier remains blind after partitions are opened; that arbitrary unseen
READMEs can be authored without approved art; that all editable PowerPoint features
survive every external PowerPoint/LibreOffice version.

## CI_SPLIT

**Every commit (13 cheap/deterministic, trials: 2):** public_source_specific_claims_
and_hedges, public_repository_deixis_conflict_requires_attestation, mixed_public_
readme_private_asset_root_refused, private_readme_claim_lineage_leak_refused,
private_only_screenshot_leak_refused, private_asset_scoped_promotion_positive_control,
responsible_use_and_repository_boundary_removal_refused, stale_section_plan_claim_
ledger_and_asset_ledger_refused, occurrence_scoped_duplicate_text_refused, public_
image_provenance_roles_budgets_and_semantics, image_budget_principal_cardinality_and_
evidence_status_mutants, post_approval_edit_bypass_refused, cold_authoring_without_
approved_art_refused. (Protected runner: several need the pinned private repo; cached
checkouts, fixed SHAs, deterministic mutations, no model seats.)

**Nightly (6 expensive/live, trials: 2):** public_source_end_to_end_live, declared_
source_selection_and_drift_live, art_register_substitution_refused, page_clone_mutant_
refused, human_review_edit_reapprove_export_live, render_receipt_tamper_matrix. The
nightly style corpus may be spent/reusable but its status must be REGRESSION, never
CONFIRMATORY.

**One-shot release gate (1, two sealed partitions):** confirmatory_unspent_style_
holdout_live — deliberately NOT nightly; running it repeatedly spends the blind and
recreates the current overstatement. After partitions open, archive digests/results,
relabel as spent regression material, and prepare new sealed partitions.

## UNCERTAINTIES (webgpt's own)

`skills/pitchdeck/evals/sparta_v2.py`, its subcommands and refusal strings are an
IMPLEMENTATION CONTRACT, not a claim those paths exist. The adapter must map them
onto the actual compiler, 13-stage evaluator, document-edit CLI, React app, renderer
and publication verifier. The reviewer inspected the public eight-image contact sheet
and the private repo's asset paths/blobs/captions/publication manifest, but did not
receive one authenticated contact sheet of all private images — this is not
pixel-level publication clearance for the private inventory.

## BLOCKERS (expect intentional red until these close)

1. A source/register-aware positive style channel must reject art-register
   substitution while accepting the source-bound Embry OS conceptual image.
2. Document mutations must invalidate BOTH outline and rendered-appearance approvals,
   and export must enforce their current document digest.
3. The React review/edit/export loop must be exercised through the actual browser and
   document-edit path.
4. The public README's repository-deixis conflict needs correction or named
   attestation (SOURCE OWNER DECISION).
5. Two new sealed confirmatory partitions must be prepared before
   HOUSE_STYLE_VALIDATION_STATUS=CONFIRMED can be emitted.

Until then the honest top-level status remains HOUSE_NON_ANOMALOUS, with
public/private source-boundary and human-edit closure still open.
