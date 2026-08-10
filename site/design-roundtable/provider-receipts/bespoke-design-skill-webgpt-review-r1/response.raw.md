Verdict

NEEDS_ATTENTION.

best-practices-bespoke-design is strong as a design and evidence standard but is not yet complete as an operational contract for live collaborative work. Commit 087303adf4 appears to repair the most dangerous immediate gap—G0–G20 enforcement and artifact-hash validation—but the skill still lacks a machine-readable lifecycle that distinguishes design work, corpus production, reviewer transport, reviewer evidence, checker maintenance, and final acceptance.

The current grahama.co state must remain exactly what the local checker reports:

Overall: NOT_TESTED

G11: NOT_TESTED

Fresh usable raters for the current corpus: 0

Craft render: PASS

No PASS, READY, or closure is established by this review.

The accessible default-branch snapshot does not contain local commit 087303adf4; it still exhibits the pre-repair drift in which the skill names G15–G20 while the validator and schema require only G0–G14. That corroborates the failure mode described in the bundle, but the bundle is authoritative for the newer local state.

What To Keep

The traceable transformation model.
Keep:

brand and audience truth → personality → narrative premise → visual grammar → responsive component system → rendered proof

This is the skill’s strongest contribution. It prevents visual novelty from becoming detached from product truth.

The separation of analysis, direction, and audit modes.
ANALYZE, DIRECT, and AUDIT are useful boundaries. The problem was not those modes; it was the absence of a second, orthogonal operating-state model for live work.

Evidence ledger, territory separation, and human territory selection.
Requiring three materially different territories, preserving rejected alternatives, and selecting by fit rather than prettiness should remain mandatory. These steps make later distinctiveness tests meaningful.

Browser-first and rendered-proof requirements.
Keep the requirement that flat mockups cannot prove responsive composition, interaction, focus, motion, reflow, or implementation fidelity.

Section/component/page-state crops as primary evidence.
The new prohibition on whole-site screenshots as primary review evidence is correct. The grahama.co corpus—147 crops across 5 viewports and 10 sections with 0 capture failures—is materially better evidence than a single tall page image.

The adversarial tests.
Keep logo-off recognition, competitor swap, motif semantics, cross-screen family, reference leakage, and template-residue review. These test structure rather than merely asking whether a page “looks bespoke.” The underlying acceptance procedures are sound.

Fail-closed status semantics.
Keep PASS, FAIL, NOT_TESTED, and BLOCKED, along with the rule that READY requires every required gate to be PASS. Missing proof must never be softened into partial success.

G0–G20 and precedence rules.
Keep craft integrity, type fidelity, material fidelity, reviewer/applier separation, world persistence, and asset provenance. Also keep the rule that open type/material contradictions outrank polish nits and that distinctiveness must be rerun after amendments.

Reviewer/applier role separation.
The reviewer should identify ordered amendments and must not apply its own findings. This is a valuable anti-self-certification control.

Exact revisions, hashes, raw outputs, and replayable aggregation.
These are essential. The repair that rejects stale corpus, source, implementation, and reviewer evidence is directionally correct.

Failure Modes

One document was doing four different jobs.
SKILL.md simultaneously acts as design philosophy, execution workflow, acceptance rubric, and collaboration protocol. The philosophy is clear; the live workflow is scattered across phases, gates, amendments, and stop conditions.

“One primary lane” was a rule without a state machine.
There was no required machine field naming the active lane, no entry condition, no permitted mutations, no exit predicate, and no invalidation behavior. Consequently, the agent could move between implementation, capture, transport debugging, checker repair, and reporting without an explicit transition.

G11 combined prerequisites with the design verdict.
At least five different questions were hidden behind distinctiveness_blind:

Is a current, usable corpus available?

Can that corpus reach reviewers?

Did enough fresh reviewers actually respond?

Were raw outputs preserved and parsed?

Did the design meet the thresholds?

A transport failure therefore looked like a design failure, while a prepared prompt or successful submission could feel like progress despite producing no usable design evidence.

NOT_TESTED was correct but operationally under-specified.
The same label could mean:

no corpus;

stale corpus;

no transport preflight;

attachment not received;

no fresh raters;

insufficient usable raters;

raw output missing;

aggregation not run;

thresholds not evaluated.

The status vocabulary is sound, but every non-PASS state needs a stable reason code and a deterministic next action.

Freshness was not transitive enough.
Old favorable output remained psychologically available after the implementation or corpus changed. Evidence freshness must be represented as one common identity carried by every downstream artifact, not inferred from filenames and timestamps.

The whole-page prohibition existed as prose before it existed as an invariant.
A determined or confused agent could still generate a full-page screenshot, call it “review evidence,” and move forward. The checker must reject the artifact based on structured capture_scope and review_role, not on a reviewer noticing the mistake.

Transport acknowledgement was allowed to resemble reviewer evidence.
These are different receipts:

prompt/packet prepared;

transport invoked;

attachment delivered and visible;

reviewer returned output;

output parsed;

output deemed usable.

Only the last two can contribute to rater counts, and all six need separate records where applicable.

Activity could masquerade as progress.
Writing a failure report, updating project knowledge, preparing prompts, generating screenshots, invoking browser automation, or repairing checker code may be useful work. None advances a gate unless it produces and validates the artifact required by a defined state transition.

The live collaboration ledger was too prose-oriented.
A prose ledger helps with narrative history but makes the human perform joins across paths, hashes, commands, gate names, and reviewer counts. It should be generated from structured run state.

The one-lane rule risked becoming anti-collaborative.
An agent should be allowed to notice an issue outside the active lane. It should not be allowed to mutate that other lane. The missing mechanism was a queued_findings collection: observe now, schedule later, do not silently switch lanes.

Checker repair could contaminate acceptance work.
Without a separately declared checker-repair lane, modifying validation code can become indistinguishable from repairing the design or “making the receipt pass.” A checker amendment needs its own fixtures, versioning, and proof before current evidence is reevaluated.

The receipt schema risks silent semantic mutation.
Expanding a schema from G0–G14 to G0–G20 while retaining the same bespoke-design-receipt.v1 identity would make historical and current receipts appear equivalent when they are not. The next incompatible shape should be v2.

Skill Amendments
1. Add an operational state machine immediately after ## Modes

Add wording substantially equivalent to:

For live implementation, audit, or amend work, create a validated run-state artifact before the first mutation. Exactly one primary_lane may be active:

implementation

corpus_capture

rater_submission

checker_repair

final_receipt_generation

Every lane must declare its required entry artifacts, permitted mutations, exit predicate, artifacts invalidated by mutation, and permitted next lanes. An observation outside the active lane may be written to queued_findings, but it must not trigger an undeclared mutation or silent lane switch.

A lane is complete only when its exit predicate is deterministically validated. Merely performing work in the lane does not complete it.

Recommended lane semantics:

Lane	Entry condition	Permitted effect	Exit condition
implementation	Selected direction and protected invariants frozen	Site source changes	Exact implementation binding recorded; required local checks pass
corpus_capture	Implementation binding frozen	Screenshot/crop artifacts only	Current manifest validates, required coverage exists, capture failures are zero
rater_submission	Current corpus and protocol hashes frozen	Transport records, raw reviewer outputs, parsed records, aggregate	Required fresh usable records exist or a named external blocker is recorded
checker_repair	A checker/schema defect is identified separately from a gate failure	Checker, schema, fixture, and test changes only	Fixtures and regression tests pass; no site or reviewer evidence was rewritten
final_receipt_generation	All required evidence is current	Receipt assembly and validation only	Immutable receipt validates and hashes replay

A source mutation during corpus_capture, rater_submission, or final_receipt_generation must force a transition back to implementation and invalidate downstream evidence.

2. Define progress, not merely activity

Add:

A run advances only through a validated transition from one named state to another on the current evidence set. Every progress claim must name:

prior state;

new state;

validating command;

newly validated artifact;

evidence-set identity.

When no validated transition occurred, report STATE_UNCHANGED, even if useful activity occurred.

The following must be explicitly classified as activity only:

writing a review or failure report;

updating PROJECT_KNOWLEDGE.md or memory;

preparing a prompt or rater packet;

invoking reviewer transport;

receiving a generic browser-automation completion marker;

generating screenshots before the manifest validates;

generating full-page or whole-site navigation screenshots;

changing checker code before its fixtures pass;

paraphrasing reviewer output;

rerunning a command that leaves the state unchanged.

3. Add one canonical evidence-set identity

Define:

evidence_set_id =
  sha256(canonical_json({
    source_revision,
    implementation_bundle_sha256,
    visual_world_contract_sha256,
    corpus_manifest_sha256,
    rater_protocol_sha256,
    threshold_configuration_sha256
  }))

Every corpus, transport receipt, rater attempt, raw output, parsed output, aggregate, gate result, and final receipt must carry this exact identity.

Required invalidation rules:

Source, implementation, or direction-contract change invalidates corpus and everything downstream.

Corpus hash change invalidates transport receipts, rater records, aggregates, and final receipts.

Prompt/protocol or threshold change invalidates affected rater records and aggregates.

Checker change invalidates the validation result, not necessarily the underlying raw artifacts; those artifacts must be revalidated.

Internally valid but old evidence is excluded as STALE_EVIDENCE; the current gate becomes NOT_TESTED.

A claimed-current artifact whose bytes do not match its recorded digest is FAIL with ARTIFACT_DIGEST_MISMATCH.

4. Make the crop rule machine-enforceable

Add to Phase 8:

Every screenshot artifact must declare capture_scope and review_role.

Allowed primary review scopes are:

section

subsection

component

page_state

full_page and whole_site captures may only use review_role: navigation_debug. They cannot satisfy G6, G7, G8, G11, G12, G15, G16, or G17 and cannot be included in a blind-rater packet.

A contact sheet is usable only when each panel maps to a unique manifest crop_id, section or state identifier, viewport, source screenshot, crop rectangle, and artifact digest.

A checker encountering review_role: primary with capture_scope: full_page|whole_site should return FAIL, not a warning.

5. Separate transport proof from reviewer proof

Add to Phase 9:

Rater packet preparation, transport, reviewer output, parsing, and usability are separate states. A transport success signal is not a reviewer response. A reviewer response is not usable unless it is preserved raw, bound to the current evidence set and packet, parseable against the required response contract, and complete enough for deterministic aggregation.

Unusable attempts must remain preserved and receive an exclusion reason. They must not increment usable_rater_count.

A transport receipt should prove, at minimum:

packet ID;

evidence-set ID;

assigned crop IDs or contact-sheet ID;

attachment expected;

attachment seen;

visible panel count where applicable;

transport/provider lane;

submission time;

raw transport response artifact;

result: DELIVERED, NOT_DELIVERED, WRONG_ATTACHMENT, BLOCKED, or UNKNOWN.

6. Split G11 into mandatory child states

Keep top-level G11; do not renumber G12–G20. Make the following children mandatory:

Child state	PASS semantics	Other semantics
corpus_current	Manifest, source binding, implementation binding, crop records, files, and hashes validate; required coverage exists; zero capture failures; no prohibited primary full-page evidence	NOT_TESTED when no current corpus; FAIL for malformed/missing/mismatched declared evidence; BLOCKED only for a named capture dependency
rater_transport_ready	Verified transport capacity exists for the required rater count, bound to the exact packet/evidence set	NOT_TESTED before preflight; FAIL when transport claims delivery but attachment is absent or wrong; BLOCKED when an external transport service prevents submission
fresh_rater_set_complete	Current, independent, usable rater count meets the preregistered minimum	NOT_TESTED while count is below minimum and further submission is possible; FAIL when completion is claimed with invalid, duplicate, stale, or protocol-violating records; BLOCKED when submissions cannot continue
raw_outputs_preserved	Every completed reviewer attempt has immutable raw output; every transport attempt has its raw transport record; all digests match	NOT_TESTED before attempts; FAIL for missing, edited, overwritten, or reconstructed output
aggregate_reconciled	A deterministic replay from usable parsed records exactly matches attempted, excluded, usable, and answer counts	NOT_TESTED until sufficient records exist; FAIL for any mismatch or hand-authored unsupported count
logo_off_passed	Current valid aggregate meets the preregistered logo-off thresholds	NOT_TESTED without a valid aggregate; FAIL when current valid evidence misses threshold
competitor_swap_passed	Current valid aggregate meets the preregistered competitor-swap threshold, including the required independent structural conflict channels	NOT_TESTED without a valid aggregate; FAIL when current valid evidence misses threshold
cross_screen_family_passed	Current valid aggregate meets grouping and non-color-invariant thresholds	NOT_TESTED without a valid aggregate; FAIL when current valid evidence misses threshold
reference_leakage_passed	Current review finds no prohibited distinctive combination copied from the frozen reference corpus	NOT_TESTED without a current review; FAIL when leakage is established
thresholds_met	Derived automatically as all four outcome children passing	Must never be authored independently

Also expose two derived dimensions:

JSON
{
  "evidence_pipeline_status": "PASS|FAIL|NOT_TESTED|BLOCKED",
  "design_outcome_status": "PASS|FAIL|NOT_TESTED"
}

This is essential to prevent a transport outage from being reported as evidence that the design itself failed.

Parent G11.status should derive as follows:

FAIL when a current valid outcome misses a threshold or when proof integrity fails.

BLOCKED when an external evidence-pipeline blocker prevents testing and no current outcome exists.

NOT_TESTED when required current evidence has not yet been produced.

PASS only when every mandatory child passes.

7. Add an explicit forbidden-progress clause

The skill should explicitly forbid:

counting packet preparation as rater progress;

counting transport invocation as delivery;

counting delivery as reviewer completion;

counting malformed, incomplete, duplicate, or stale output as usable;

retaining only parsed summaries while discarding raw responses;

using old favorable outputs after any evidence-set input changes;

using unmanifested crops or full-page captures as primary evidence;

manually entering aggregate counts that cannot be replayed;

changing checker criteria merely to accept existing artifacts;

rewriting evidence during checker repair;

manually editing the generated current-status artifact;

claiming a gate improved because a failure report became more detailed;

claiming the project is closer to READY without naming a validated state transition;

pushing or deploying the local render without explicit human authorization.

Checker/Artifact Changes

Version the receipt contract.
Introduce bespoke-design-receipt.v2 and a new schema $id. Do not silently continue expanding v1. Historical v1 receipts may remain inspectable, but they must not establish current READY under the G0–G20 contract.

Create a separate live-run schema.
Add:

schemas/bespoke-design-run-state.schema.json

The mutable run-state artifact and immutable final receipt should be different files with different responsibilities.

Extend screenshot artifact records.

Minimum fields:

JSON
{
  "artifact_id": "crop-work-phone-390-001",
  "kind": "screenshot_crop",
  "review_role": "primary",
  "capture_scope": "section",
  "section_id": "#work",
  "page_state": "default",
  "viewport_id": "phone-390",
  "source_screenshot_id": "page-home-phone-390",
  "crop_rect": {"x": 0, "y": 2150, "width": 390, "height": 910},
  "path": "...",
  "sha256": "...",
  "evidence_set_id": "..."
}

Create a structured rater-attempt record.

Minimum fields:

JSON
{
  "attempt_id": "g11-rater-01-attempt-01",
  "rater_slot": "rater-01",
  "packet_id": "...",
  "evidence_set_id": "...",
  "transport_status": "DELIVERED",
  "transport_receipt_artifact_id": "...",
  "raw_output_artifact_id": "...",
  "raw_output_sha256": "...",
  "parse_status": "PASS",
  "usable": true,
  "exclusion_reason": null,
  "completed_at": "..."
}

Unusable records remain in the array with usable: false and a stable exclusion code.

Make aggregates generated artifacts.
The aggregate must contain:

preregistered required rater count;

attempted count;

completed count;

usable count;

excluded count by reason;

raw and parsed artifact IDs;

per-question counts;

threshold configuration and hash;

deterministic replay command;

aggregate SHA-256.

The checker must recompute the aggregate and reject discrepancies.

Add stable reason codes.
Do not rely on free-text needs. Suggested codes include:

no_current_corpus
full_page_primary_evidence_forbidden
corpus_hash_mismatch
transport_not_preflighted
attachment_not_seen
wrong_attachment
fresh_blind_raters_not_run_for_current_segmented_corpus
insufficient_fresh_usable_raters
stale_rater_record
raw_output_missing
aggregate_mismatch
distinctiveness_threshold_missed
checker_validation_stale
human_authorization_required

Propagate invalidation automatically.
design_world_check.py should output:

JSON
{
  "source_state": "...",
  "evidence_set_id": "...",
  "invalidated_artifact_ids": [],
  "invalidated_reason": null
}

Stale records may be listed for audit history but must never enter current counts.

Add negative fixtures for the actual failures.

Required fixtures should cover:

valid current corpus with zero raters;

a stale rater bound to an old corpus;

successful transport response with attachment unseen;

an unusable rater whose raw output is preserved;

a missing raw output;

an aggregate count mismatch;

a valid aggregate that fails competitor swap;

a full-page artifact marked as primary;

a source change that invalidates corpus and all downstream records;

checker repair that passes fixtures but leaves current G11 NOT_TESTED.

Keep checker repair from manufacturing evidence.
A checker/schema change may alter validation logic only through a versioned contract and passing fixtures. It must not rewrite source artifacts, rater records, or gate statuses.

Human-Visible UX

Yes. The skill should require one machine-generated status artifact and one generated human rendering:

site/design-roundtable/bespoke-design-run-state.latest.json
site/design-roundtable/bespoke-design-run-state.latest.md

The JSON is authoritative. The Markdown is regenerated from it and must not be edited manually.

Minimum schema:

JSON
{
  "schema": "bespoke-design-run-state.v1",
  "run_id": "grahama-20260810-g11",
  "project": "grahama.co",
  "mode": "AUDIT",

  "primary_lane": "rater_submission",
  "allowed_next_lanes": [
    "rater_submission",
    "checker_repair"
  ],

  "phase": {
    "id": "P9",
    "name": "adversarial_distinctiveness"
  },
  "gate_focus": "G11",

  "evidence_binding": {
    "source_revision": "...",
    "implementation_revision": "...",
    "working_tree_state": "clean",
    "visual_world_contract_sha256": "...",
    "corpus_manifest_path": "site/design-roundtable/rendered-screens/responsive-section-corpus-20260810T030534Z/manifest.json",
    "corpus_sha256": "5edd2f32f1ffa69c368b79e310d66dc992141e1cb780997630bf61eb8fd17f0d",
    "rater_protocol_sha256": "...",
    "threshold_configuration_sha256": "...",
    "evidence_set_id": "..."
  },

  "current_artifact": {
    "kind": "section_corpus",
    "path": "site/design-roundtable/rendered-screens/responsive-section-corpus-20260810T030534Z/manifest.json",
    "sha256": "5edd2f32f1ffa69c368b79e310d66dc992141e1cb780997630bf61eb8fd17f0d"
  },

  "counts": {
    "viewports": 5,
    "sections": 10,
    "crops": 147,
    "capture_failures": 0,
    "rater_slots_required": 5,
    "rater_attempts": 0,
    "fresh_usable_raters": 0,
    "raw_outputs_preserved": 0
  },

  "status": {
    "overall": "NOT_TESTED",
    "gate": "G11",
    "gate_status": "NOT_TESTED",
    "evidence_pipeline_status": "NOT_TESTED",
    "design_outcome_status": "NOT_TESTED",
    "reason_code": "fresh_blind_raters_not_run_for_current_segmented_corpus",
    "subgates": {}
  },

  "blocker": null,

  "last_command": {
    "argv": [
      "skills/monitor-website/run.sh",
      "design-world-check",
      "--json"
    ],
    "exit_code": 0,
    "result_status": "NOT_TESTED",
    "receipt_path": "site/design-roundtable/design-world-check.latest.json"
  },

  "next_action": {
    "type": "human_transport",
    "input_artifact": "current hash-bound G11 rater packet",
    "expected_artifact": "raw rater output plus transport receipt",
    "success_predicate": "attachment_seen=true, evidence_set_id matches, response parses, usable count increases"
  },

  "stop_condition": {
    "scope": "lane",
    "condition": "five fresh usable current raters exist, or a named external transport blocker is recorded",
    "met": false
  },

  "authorization": {
    "production_deploy_allowed": false,
    "authorization_ref": null
  },

  "queued_findings": [],
  "updated_at": "..."
}

For deterministic steps, next_action must instead contain exact shell argv, expected output path, and success predicate. For browser or human transport, it must name the exact input artifact, expected raw output, and proof required.

The generated Markdown should fit on one screen and lead with:

LANE: rater_submission
PHASE/GATE: P9 / G11
CORPUS: PASS — 147 crops, 5 viewports, 10 sections, 0 failures
RATERS: NOT_TESTED — 0 / 5 fresh usable
DESIGN OUTCOME: NOT_TESTED
REASON: fresh_blind_raters_not_run_for_current_segmented_corpus
BLOCKER: none
LAST COMMAND: skills/monitor-website/run.sh design-world-check --json
NEXT: submit the current hash-bound packet and preserve one raw response
STOP WHEN: 5 current usable raters exist or transport is formally BLOCKED
DEPLOYMENT: forbidden without explicit human authorization

Crucially, NOT_TESTED must not automatically imply a blocker. In the present case, the evidence says the fresh rating work has not been run; it does not yet establish that it cannot be run.

Next Executable Slice

Implement only the G11 composite-state evaluator and its status output. Do not change the grahama.co design, capture another corpus, submit raters, edit thresholds, assemble a final receipt, or deploy.

Patch scope:

skills/monitor-website/scripts/design_world_check.py
skills/monitor-website/tests/test_design_world_check_g11_subgates.py
skills/monitor-website/tests/fixtures/g11/

The change should replace a flat distinctiveness_blind status with:

current evidence-set binding;

mandatory G11 child states;

separate evidence_pipeline_status and design_outcome_status;

stable reason_code;

exact counts;

deterministic next_action;

parent status derived from children.

For the current grahama.co state, the expected result is:

corpus_current: PASS
fresh_rater_set_complete: NOT_TESTED
fresh usable raters: 0 / 5
design_outcome_status: NOT_TESTED
G11: NOT_TESTED
overall: NOT_TESTED
reason_code: fresh_blind_raters_not_run_for_current_segmented_corpus

Proof command:

Bash
python3 -m py_compile \
  skills/monitor-website/scripts/design_world_check.py

python3 -m pytest \
  skills/monitor-website/tests/test_design_world_check_g11_subgates.py \
  -q

skills/monitor-website/run.sh design-world-check --json \
  | tee site/design-roundtable/design-world-check.latest.json

python3 - <<'PY'
import json
from pathlib import Path

path = Path("site/design-roundtable/design-world-check.latest.json")
result = json.loads(path.read_text(encoding="utf-8"))

g11 = result["gates"]["distinctiveness_blind"]
subgates = g11["subgates"]

assert result["status"] == "NOT_TESTED"
assert g11["status"] == "NOT_TESTED"
assert g11["design_outcome_status"] == "NOT_TESTED"

assert subgates["corpus_current"]["status"] == "PASS"
assert (
    subgates["corpus_current"]["corpus_sha256"]
    == "5edd2f32f1ffa69c368b79e310d66dc992141e1cb780997630bf61eb8fd17f0d"
)

fresh = subgates["fresh_rater_set_complete"]
assert fresh["status"] == "NOT_TESTED"
assert fresh["usable"] == 0
assert fresh["required"] == 5

assert (
    g11["reason_code"]
    == "fresh_blind_raters_not_run_for_current_segmented_corpus"
)
assert g11["next_action"]["lane"] == "rater_submission"

print("PASS: G11 operational state is decomposed, current, and non-overclaiming")
PY

python3 scripts/check_mock_evidence_claims.py

This is the smallest repair that changes the process from “G11 is not done” to an actionable, non-spiraling state machine without pretending that any new design evidence exists.

<<<WEBGPT_DONE:20260810T120755Z:96797a91>>>
