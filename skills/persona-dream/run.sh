#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=(uv run --project "${SCRIPT_DIR}" python)

usage() {
  cat <<'EOF'
Usage: ./run.sh <command> [options]

Commands:
  read                 Print PROJECT_KNOWLEDGE.md before running pipeline phases
  test-suite           Run the deterministic pytest contract suite (CI guard; no paid/live calls)
  check-tau-routing-boundary  Static check: only /tau may reach /scillm (fails on un-sanctioned direct scillm calls)
  generate             Create a persona dream packet
  research-bakeoff     Run opt-in story/contact-sheet/A-V research bakeoff modes
  contact-sheet        Build/amend/retrieve visual reference sheets, memory records, and Qdrant index
  pipeline-phase02-recall  Re-run Phase 2 live recall and refresh Phase 1+2 sections of the 8892 report
  phase-05-sync-contact-sheet-sidecars  Write prompt links + probed-dimension sidecars (no PNG duplication)
  phase-05-contact-sheet-gate  Validate/write Phase 5 contact-sheet gate (accepted 4:3 sizes + sidecars)
  regenerate                 Regenerate contact sheets or panels from recreate bundles
  validate-gate              Validate pipeline gates by ID, list, or 'all'. Resolved blockers auto-detected.
  pipeline-loop-status       Report the active serial while-loop and first blocker
  pipeline-loop-run          Run a fail-closed serial while-loop controller pass
  validate-pipeline-loop-run Validate a serial while-loop controller receipt
  validate-run-root          Report the first blocker from dream_packet to one-scene Kling packet
  multiscene-live-smoke      Generate real scene-scoped contact sheets and panels without Kling
  validate-multiscene-live-smoke Validate multi-scene live smoke receipts and image hashes
  write-multiscene-live-report Write an HTML report from a multi-scene live smoke receipt
  validate-dream-packet      Validate dream packet shape, residue, frame prompts, and contact sheet
  write-dream-packet-work-order  Write dream packet generation/repair work order
  validate-dream-packet-work-order Validate dream packet generation/repair work order
  validate-panel-repair-gate Validate final panel repair/provider eligibility gate
  validate-panel-source      Validate panel source provenance, hash, and final-panel eligibility
  validate-provider-media-url Probe a public media URL and verify sha256
  write-provider-media-publication-work-order  Write authorization-gated public media work order
  validate-provider-media-publication-work-order Validate public media publication work order
  stage-provider-media-local-asset  Copy locked media to the proposed repo path without publishing
  validate-provider-media-local-staging Validate local provider-media staging receipt
  validate-provider-media-publication-preflight Validate local readiness for authorized public media publication
  write-provider-media-publication-authorization-template Write a draft approval packet that is not an authorization receipt
  validate-provider-media-publication-authorization Validate explicit authorization before public media publication
  validate-provider-media-public-handoff Validate work order + staged bytes + public URL probe agreement
  validate-pipeline-evidence-bundle Validate run-root, loop, public handoff, and Panel 01 report evidence
  apply-provider-media-public-probe  Patch panel repair gate only after a PASS public media probe
  write-panel-comparison-status  Write source-derived status JSON for Panel 01 comparison report
  validate-panel-comparison-report Validate Panel 01 comparison report assets and claim boundary
  validate-story-contract    Validate story contract schema, accepted status, and semantic basics
  write-story-contract-work-order  Write story review/regeneration work order
  validate-story-contract-work-order Validate story review/regeneration work order
  validate-visual-review     Validate visual review receipt evidence and eight-check coverage
  validate-storyboard-panel  Validate storyboard panel receipt image, timing, and continuity links
  write-storyboard-panel-work-order  Write storyboard panel generation/review work order
  validate-storyboard-panel-work-order Validate storyboard panel generation/review work order
  write-panel-source         Derive panel_source_receipt.json from a panel repair gate receipt
  write-panel-repair-work-order  Write one-panel repair-gate handoff request
  validate-panel-repair-work-order  Validate one-panel repair-gate handoff request
  write-one-scene-kling-review-packet  Install blocked one-scene Kling packet + local media lock
  convert-accepted-storyboard-to-kling  Convert accepted storyboard packet into fail-closed Kling dry-run artifacts
  validate-kling-scene-packet  Validate a fail-closed Kling dry-run scene packet
  check-kling-scene-packet-dry-run-gate  Convert then validate accepted storyboard as local dry-run Tau gate
  check-respawn-plan   Compare revision lineage and write a local respawn plan
  check-stale-write-fence  Prove stale/partial staged artifacts cannot promote to accepted
  check-global-progress-rollup  Derive local revision evidence progress from receipts
  check-dynamic-respawn-events  Classify user/project-agent change events into respawn actions
  check-creator-reviewer-respawn-loop  Prove creator/reviewer loops honor respawn and stale-write gates
  check-persona-dream-run-state  Prove local run-state consistency across revision, queue, Tau, progress, and provider gates
  write-run-state-from-run-root  Project a real run root into dream_run_state.v1 and global_progress_sources.v1
  check-run-root-state  Validate run-root projection fixtures or one real run root
  select-video-provider  Score and select a dry-run video provider from a scene contract
  check-video-provider-selection  Prove video provider routing stays dry-run and fail-closed
  refresh-video-provider-registry  Refresh Brave/fal provider discovery evidence without provider calls
  check-video-provider-registry-refresh  Prove provider refresh parsing stays dry-run and fail-closed
  write-video-provider-packet  Write a provider-specific dry-run video packet from a scorecard
  check-video-provider-packet-routing  Prove provider packet routing stays dry-run and fail-closed
  check-fal-api-preflight  Check FAL auth and non-generation API/docs access without submitting jobs
  check-fal-api-preflight-fixtures  Prove FAL auth discovery preflight stays fail-closed
  check-pipeline-robustness  Aggregate offline autonomous, lineage, fail-closed, and provider-boundary checks
  check-live-memory-recall  Exercise live Memory /recall through static dream generation and write a fail-closed receipt
  run-live-pctom-gate0  Exercise live Memory recall and derive a PCTOM-R Gate 0 lineage case
  run-live-tau-gate2-4  Exercise live Tau text reasoning through PCTOM-R Gate 2-4 validators
  run-live-tau-score-revision  Score live Tau PCTOM-R commitments and validate Gate 7 revision
  run-live-tau-reliability-bridge  Validate controlled Gate 8/9 fault containment over live Tau PCTOM artifacts
  run-condition-comparison  Run deterministic M/R/D/CD PCTOM-R condition comparison instrumentation
  run-live-tau-condition-comparison  Run live Tau-authored M/R/D/CD PCTOM-R condition comparison
  run-live-tau-condition-reliability-bridge  Validate Gate 8/9 fault containment over live Tau condition artifacts
  run-live-tau-condition-action-selection  Score Gate 6 actions over live Tau condition artifacts
  run-live-tau-action-linked-revision  Link Gate 6 action decisions to Gate 7 belief revisions
  run-live-tau-revision-recall  Check deterministic recall over action-linked revisions
  run-heldout-condition-benefit  Run frozen held-out M/R/D/CD scoring plus Gate 6 action decisions
  run-live-memory-revision-recall  Persist action-linked revisions and recall them through live Memory
  run-live-memory-revision-delayed-recall  Re-read persisted revision Memory records from a fresh no-write process
  run-live-memory-restart-delayed-recall  Restart Memory, then re-run delayed revision recall
  run-live-memory-aged-retention-recall  Re-run delayed Memory recall only after a minimum elapsed source age
  check-social-episode-independent-replay  Recompute social episode policy/label invariants without generator imports
  run-sealed-test-statistical-confidence  Run 64-episode sealed-test CD-vs-baseline bootstrap confidence
  analyze-sealed-test-planning-gap  Explain why sealed-test prediction benefit did not become planning benefit
  run-live-fault-injection-surface  Exercise broader PCTOM-R fault containment over live Memory and receipt boundaries
  run-live-tau-sealed-test-replication  Run bounded live Tau-authored sealed-test replication plus Gate 6 actions
  run-live-tau-full64-statistical-confidence  Compute confidence intervals over accepted full64 live Tau artifacts
  run-live-tau-full64-repeated-run-summary  Aggregate repeated full64 live Tau sealed-test replications
  check-pctom-calibration-abstention  Audit calibration/risk-coverage fields over full64 live Tau artifacts
  check-pctom-unsupported-evidence-abstention  Exercise unsupported-evidence abstention through Gate 2 and Gate 5
  check-pctom-objective-evidence  Bind the active PCTOM-R objective to success and coverage receipts
  run-live-tau-full64-planning-diagnostic  Diagnose why full64 planning-regret benefit is not confidence-bound
  run-live-tau-full64-action-policy-sensitivity  Explain sparse full64 planning deltas through action switches
  run-live-tau-trust-commit-replication  Rerun focused live Tau M/R/D/CD trust-commitment planning cases
  run-live-tau-trust-commit-repeated-seed-summary  Aggregate repeated focused trust-commitment live Tau planning receipts
  run-live-tau-planning-non-generalization-audit  Hash-bind planning receipts and explain sparse/non-general planning benefit
  run-live-tau-distributional-planning-intervention  Run a broader distributional planning intervention over full64 live Tau artifacts
  run-live-tau-confidence-gated-planning-intervention  Run a confidence-gated epistemic action intervention over full64 live Tau artifacts
  run-live-tau-balanced-planning-replication  Run live Tau planning over a balanced four-family slice
  run-live-tau-balanced-planning-diagnostic  Diagnose mixed GAIN/LOSS rows in a balanced live Tau aggregate
  run-live-tau-balanced-threshold-intervention  Run action-threshold ablations over a balanced live Tau aggregate
  run-live-tau-cooperation-threshold-rule  Replay a pre-outcome cooperation threshold rule on held-out live Tau rows
  run-live-tau-cooperation-exposure-slice  Run held-out live Tau variants 23-24 for cooperation-rule exposure
  check-cooperation-exposure-instrument  Build and check deterministic held-out cooperation-exposure episodes
  check-cooperation-contrast-instrument  Build and check deterministic held-out cooperation contrast episodes
  check-cooperation-unsafe-offer-pressure-instrument  Build and check deterministic unsafe-offer-pressure episodes
  run-live-tau-cooperation-instrument-slice  Run deterministic cooperation-exposure instrument through live Tau
  run-live-tau-cooperation-contrast-slice  Run deterministic cooperation-contrast instrument through live Tau
  run-live-tau-cooperation-exposure-contrast-slice  Run deterministic cooperation exposure/contrast instrument through live Tau
  run-live-tau-cooperation-unsafe-offer-pressure-slice  Run unsafe-offer-pressure instrument through live Tau
  diagnose-cooperation-unsafe-offer-no-exposure  Diagnose live unsafe-offer-pressure no-exposure artifacts
  check-cooperation-class-separated-exposure  Audit class-separated cooperation exposure from a live Tau slice
  check-cooperation-visible-pressure-rule-reliability  Audit visible-pressure rule reliability over live Tau replays
  build-cooperation-visible-pressure-reliability-surface  Build Gate 8 surface from visible-pressure reliability evidence
  build-cooperation-visible-pressure-causal-replay  Build Gate 9 replay from visible-pressure reliability surface
  analyze-cooperation-visible-pressure-planning-benefit  Analyze slice-local planning benefit over visible-pressure evidence
  diagnose-cooperation-policy  Diagnose cooperation-threshold policy effects over live instrument artifacts
  accept-cooperation-no-intervention-policy  Accept no-intervention for observed cooperation regression slice
  check-cooperation-feature-split-prerequisites  Audit whether cooperation evidence can support a replacement feature split
  run-live-tau-strict-inference-prompt-replication  Run live Tau planning with strict non-template inference prompts
  run-pctom-causal-identifiability-gate  Recompute fixed-policy oracle/anti-oracle sensitivity and fail-closed lineage
  run-live-tau-prompt-timeout-diagnostic  Diagnose Tau/scillm prompt timeout boundaries
  run-live-tau-sealed-test-retry-proof  Prove retry/idempotence over live Tau sealed-test artifacts
  run-live-tau-sealed-test-runsh-orchestration-retry-proof  Exercise sealed-test retry proof through run.sh dispatch
  run-live-tau-sealed-test-queue-worker-retry-proof  Exercise sealed-test retry proof through a bounded queue worker
  run-live-tau-sealed-test-service-retry-proof  Exercise sealed-test retry proof through a local HTTP service
  run-live-tau-full64-memory-fault-surface  Exercise live Memory faults over full64 live Tau artifacts
  check-live-gate2-4-boundary-negatives  Mutate live-originated Gate 2-4 artifacts and require fail-closed receipts
  check-live-gate5-7-boundary-negatives  Mutate live-originated Gate 5-7 artifacts and require fail-closed receipts
  run-social-simulator-service-proof  Serve deterministic social episodes over HTTP and inject service faults
  check-live-stage-hash-lineage-audit  Recompute PCTOM-R Gate 2-7 hashes and artifact lineage
  check-autonomous-no-human-judgment-surface  Audit PCTOM-R receipts for no human/LLM judgment
  check-pctom-goal-coverage  Check active PCTOM-R goal clauses against receipt evidence
  check-pctom-success-criteria  Audit PCTOM-R success criteria and scope gaps
  check-prospective-tom-protocol  Validate PCTOM-R Gate 0 fixture lineage through a sealed prediction
  build-pctom-external-proof-archive  Copy GOAL.md-cited /tmp receipts into the durable in-repo archive
  verify-pctom-external-proof-archive  Re-read the durable proof archive and confirm every digest still matches
  build-social-episode-corpus  Build deterministic PCTOM-R Gate 1 social episodes
  check-social-episode-corpus  Validate deterministic PCTOM-R Gate 1 social episodes
  check-tom-belief-distributions  Validate PCTOM-R Gate 2 ToM distribution invariants
  check-counterfactual-branches  Validate PCTOM-R Gate 3 counterfactual branch invariants
  check-tom-prediction-commitments  Validate PCTOM-R Gate 4 sealed prediction commitments
  reveal-and-score-tom-trial  Reveal and score PCTOM-R Gate 5 sealed predictions
  run-tom-action-selection-trial  Validate PCTOM-R Gate 6 action selection and planning regret
  check-tom-belief-revision  Validate PCTOM-R Gate 7 non-destructive belief revision
  run-reliability-surface  Validate PCTOM-R Gate 8 repeated, perturbed, and fault-injected reliability surface
  run-causal-replay  Validate PCTOM-R Gate 9 causal replay and failure localization
  check-pipeline-contract  Validate the canonical Phase 01-16 pipeline contract
  write-phase10-reproducibility-receipt  Prove Phase 10 committed artifacts are canonically reproducible
  repair-semantic-mix-revision Create, Memory-verify, and activate a new explicit-human-idea revision
  bootstrap-phase11-payload-binding Create the active-revision Standard payload binding without provider calls
  capture-phase11-provider-source-snapshot Capture official current fal schema and pricing evidence without generation
  capture-phase11-public-media-evidence Probe the seven exact request assets and write technical transition evidence
  reconcile-phase11-upstream-validation Replace the historical 12/15 false-green summary with an explicit deferred boundary
  compile-phase11-canonical-live-request  Compile the ACTIVE_CONSISTENT zero-call Phase 11 request bundle
  validate-phase11-canonical-live-request Independently validate and optionally persist the Phase 11 boundary
  write-phase11-approval-receipts  Write five receipts only from an explicit human authorization packet
  phase11-fal-canary-preflight  Prove the zero-call submit/resume/download adapter preflight
  phase11-fal-canary-execute  Execute the exactly-once canary only after all five approvals validate
  tailscale-funnel-publication-canary  Plan or run authorized Funnel publish/probe/teardown with zero provider calls
  validate-local-media-lock  Validate local media hash and localhost serving for a run root
  review-clipboard-bridge    Serve clipboard + regenerate bridge for pipeline review UI (:8893)
  storyboard-fixture   Build the Horus/Embry storyboard-first Kling dry-run fixture
  backend-readiness    Record backend readiness for keyframe/I2V/assembly lanes
  chutes-generate      Call a Chutes /generate endpoint with retry receipts
  lore-canary          Sample Horus lore chunks and run no-write extraction canary

Examples:
  ./run.sh read
  ./run.sh generate --persona embry
  ./run.sh generate --persona embry --fixture scripts/fixtures/sample_residue.json --output-dir /tmp/persona-dream-smoke
  ./run.sh research-bakeoff smoke
  ./run.sh research-bakeoff contact-sheet --dry-run
  ./run.sh contact-sheet build --asset-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/research/bakeoff/<ref-run> --index-qdrant --write-memory
  ./run.sh storyboard-fixture --out-dir /mnt/storage12tb/skills/persona-dream/outputs/horus-embry-storyboard-first-fixture
  ./run.sh research-bakeoff elevenlabs
  ./run.sh backend-readiness --output-dir /tmp/persona-dream-smoke
  ./run.sh chutes-generate --prompt "a high quality photo of a sunrise" --output-dir /tmp/persona-dream-smoke
  ./run.sh lore-canary --output-dir /tmp/persona-dream-lore-canary --max-calls 3
  ./run.sh validate-gate --gate all --table
  ./run.sh pipeline-loop-status /mnt/storage12tb/skills/persona-dream/outputs/<run-id> --direction backward --json
  ./run.sh pipeline-loop-run /mnt/storage12tb/skills/persona-dream/outputs/<run-id> --direction backward --output /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/pipeline_loop_run.json --json
  ./run.sh validate-pipeline-loop-run /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/pipeline_loop_run.json --json
  ./run.sh validate-run-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id> --json
  ./run.sh multiscene-live-smoke --run-root /tmp/persona-dream-multiscene-live --scene-count 2 --max-workers 2 --auth codex-oauth --json
  ./run.sh validate-multiscene-live-smoke /tmp/persona-dream-multiscene-live/receipts/multiscene_live_smoke_receipt.json --json
  ./run.sh write-multiscene-live-report --receipt /tmp/persona-dream-multiscene-live/receipts/multiscene_live_smoke_receipt.json --validation /tmp/persona-dream-multiscene-live/receipts/multiscene_live_smoke_validation.json --output reports/multiscene-live-smoke/report.html --json
  ./run.sh validate-dream-packet /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/dream_packet.json --run-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id> --json
  ./run.sh write-dream-packet-work-order --run-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id> --output /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/dream_packet_work_order.json --json
  ./run.sh validate-dream-packet-work-order /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/dream_packet_work_order.json --json
  ./run.sh validate-panel-repair-gate /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/panel_repair_gate_receipt.json --require-provider-eligible
  ./run.sh validate-panel-source /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/panel_source_receipt.json --run-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id> --json
  ./run.sh validate-provider-media-url --url https://.../panel_01.png --expected-sha256 sha256:... --output /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/provider_media_url_probe_receipt.json --json
  ./run.sh write-provider-media-publication-work-order --run-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id> --panel-id panel_01 --panel-repair-gate-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/panel_repair_gate_receipt.json --provider-media-probe-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/provider_media_url_probe_receipt.json --output /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_publication_request.json --json
  ./run.sh validate-provider-media-publication-work-order /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_publication_request.json --json
  ./run.sh stage-provider-media-local-asset --work-order /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_publication_request.json --output /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_local_staging_receipt.json --json
  ./run.sh validate-provider-media-local-staging /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_local_staging_receipt.json --json
  ./run.sh validate-provider-media-publication-preflight --work-order /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_publication_request.json --local-staging-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_local_staging_receipt.json --json
  ./run.sh write-provider-media-publication-authorization-template --preflight-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/provider_media_publication_preflight.json --output /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/provider_media_publication_authorization_template.json --json
  ./run.sh validate-provider-media-publication-authorization --preflight-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/provider_media_publication_preflight.json --json
  ./run.sh validate-provider-media-public-handoff --work-order /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_publication_request.json --local-staging-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_local_staging_receipt.json --public-probe-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/final_provider_eligibility_work_orders/panel_01_run_<ts>/provider_media_url_probe_receipt.json --json
  ./run.sh validate-pipeline-evidence-bundle --run-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id> --pipeline-loop-run-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/pipeline_loop_run.json --publication-work-order /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_publication_request.json --local-staging-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_local_staging_receipt.json --public-probe-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/final_provider_eligibility_work_orders/panel_01_run_<ts>/provider_media_url_probe_receipt.json --publication-preflight-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/provider_media_publication_preflight.json --publication-authorization-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/provider_media_publication_authorization.json --panel-report reports/panel-comparison/report.html --json
  ./run.sh apply-provider-media-public-probe --panel-repair-gate-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/final_provider_eligibility_work_orders/panel_01_run_<ts>/panel_repair_gate_receipt.json --provider-media-probe-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/final_provider_eligibility_work_orders/panel_01_run_<ts>/provider_media_url_probe_receipt.json --output /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/final_provider_eligibility_work_orders/panel_01_run_<ts>/panel_repair_gate_receipt.public_media_applied.json --json
  ./run.sh write-panel-comparison-status --run-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id> --panel-repair-gate-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/final_provider_eligibility_work_orders/panel_01_run_<ts>/panel_repair_gate_receipt.json --local-staging-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_local_staging_receipt.json --public-probe-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/final_provider_eligibility_work_orders/panel_01_run_<ts>/provider_media_url_probe_receipt.json --publication-work-order /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_publication_request.json --provider-media-publication-preflight-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/provider_media_publication_preflight.json --provider-media-publication-authorization-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/provider_media_publication_authorization.json --provider-media-publication-authorization-template /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/provider_media_publication_authorization_template.json --pipeline-loop-run-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/pipeline_loop_run.json --pipeline-evidence-bundle-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/pipeline_evidence_bundle_validation.json --output reports/panel-comparison/status.json --json
  ./run.sh validate-panel-comparison-report reports/panel-comparison/report.html --json
  ./run.sh validate-story-contract /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/story_contract.json --run-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id> --json
  ./run.sh write-story-contract-work-order --run-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id> --story-contract /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/story_contract.json --output /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/story_contract_work_order.json --json
  ./run.sh validate-story-contract-work-order /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/story_contract_work_order.json --json
  ./run.sh validate-visual-review /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/visual_review_receipt.json --run-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id> --json
  ./run.sh validate-storyboard-panel /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/storyboard_panel_receipt.json --run-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id> --json
  ./run.sh write-panel-source /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/panel_repair_gate_receipt.json --output /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/receipts/panel_source_receipt.json --json
  ./run.sh write-panel-repair-work-order --run-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id> --panel-id panel_01 --panel-repair-gate-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/panel_repair_gate_receipt.json --output /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/final_provider_eligibility_work_orders/panel_01_request.json --json
  ./run.sh validate-panel-repair-work-order /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/final_provider_eligibility_work_orders/panel_01_request.json --json
  ./run.sh write-one-scene-kling-review-packet --run-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id> --panel-source-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/final_provider_eligibility_work_orders/panel_01_run_*/panel_source_receipt.json --panel-repair-gate-receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/storyboard/panel_repair_gate/final_provider_eligibility_work_orders/panel_01_run_*/panel_repair_gate_receipt.json --json
  ./run.sh convert-accepted-storyboard-to-kling --storyboard-packet /mnt/storage12tb/persona-dream/phase07_tau_runs/<run-id>/work/storyboard_packet.json --output-root /mnt/storage12tb/persona-dream/phase07_tau_runs/<run-id>/work/phase08_kling_scene_packet --json
  ./run.sh validate-kling-scene-packet /mnt/storage12tb/persona-dream/phase07_tau_runs/<run-id>/work/phase08_kling_scene_packet/kling_scene_packet.json --receipt-out /tmp/kling_scene_packet_validation_receipt.json --json
  ./run.sh check-kling-scene-packet-dry-run-gate --storyboard-packet /mnt/storage12tb/persona-dream/phase07_tau_runs/<run-id>/work/storyboard_packet.json --output-root /mnt/storage12tb/persona-dream/phase07_tau_runs/<run-id>/work/phase08_kling_scene_packet --receipt-out /tmp/kling_scene_packet_dry_run_gate_receipt.json --json
  ./run.sh check-respawn-plan --fixtures-root tests/fixtures/respawn --receipt-out /tmp/persona-dream-respawn/check_receipt.json --json
  ./run.sh check-stale-write-fence --fixtures-root tests/fixtures/stale-write-fence --receipt-out /tmp/persona-dream-stale-write-fence/check_receipt.json --json
  ./run.sh check-global-progress-rollup --fixtures-root tests/fixtures/global-progress-rollup --receipt-out /tmp/persona-dream-global-progress/check_receipt.json --json
  ./run.sh check-dynamic-respawn-events --fixtures-root tests/fixtures/dynamic-respawn-events --receipt-out /tmp/persona-dream-dynamic-respawn/check_receipt.json --json
  ./run.sh check-creator-reviewer-respawn-loop --fixtures-root tests/fixtures/creator-reviewer-respawn-loop --receipt-out /tmp/persona-dream-creator-reviewer-loop/check_receipt.json --json
  ./run.sh check-persona-dream-run-state --fixtures-root tests/fixtures/run-state --receipt-out /tmp/persona-dream-run-state/check_receipt.json --json
  ./run.sh write-run-state-from-run-root --run-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id> --output /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/dream_run_state.v1.json --progress-source-out /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/global_progress_sources.v1.json --json
  ./run.sh check-run-root-state --fixtures-root tests/fixtures/run-root-state --receipt-out /tmp/persona-dream-run-root-state/check_receipt.json --json
  ./run.sh select-video-provider --scene-contract /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/video_scene_contract.v1.json --output /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/video_provider_scorecard.v1.json --json
  ./run.sh check-video-provider-selection --fixtures-root tests/fixtures/video-provider-selection --receipt-out /tmp/persona-dream-video-provider-selection/check_receipt.json --json
  ./run.sh refresh-video-provider-registry --live-brave-search --receipt-out /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/provider_registry_refresh_receipt.v1.json --json
  ./run.sh check-video-provider-registry-refresh --fixtures-root tests/fixtures/video-provider-registry-refresh --receipt-out /tmp/persona-dream-video-provider-refresh/check_receipt.json --json
  ./run.sh write-video-provider-packet --scene-contract /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/video_scene_contract.v1.json --scorecard /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/video_provider_scorecard.v1.json --media-lock /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/media_lock_manifest.v1.json --output-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/video_provider_packet --json
  ./run.sh check-video-provider-packet-routing --fixtures-root tests/fixtures/video-provider-packet-routing --receipt-out /tmp/persona-dream-video-provider-packet-routing/check_receipt.json --json
  ./run.sh check-fal-api-preflight --live --receipt-out /tmp/persona-dream-fal-api-preflight/live_receipt.json --json
  ./run.sh check-fal-api-preflight-fixtures --fixtures-root tests/fixtures/fal-api-preflight --receipt-out /tmp/persona-dream-fal-api-preflight/check_receipt.json --json
  ./run.sh check-pipeline-robustness --output-root /tmp/persona-dream-robustness --json
  ./run.sh check-pipeline-contract --json
  ./run.sh write-phase10-reproducibility-receipt --json
  ./run.sh tailscale-funnel-publication-canary --asset reports/pipeline-complete/phase_07_storyboard_live_tau/generated_storyboard_frames/sb_001_start_frame.png --output-root /tmp/persona-dream-funnel-canary --json
  ./run.sh validate-local-media-lock /mnt/storage12tb/skills/persona-dream/outputs/<run-id> --serve --json
  ./run.sh validate-gate --gate voice-clone
  ./run.sh validate-gate --gate phase-05,phase-06
EOF
}

COMMAND="${1:-help}"
shift || true

case "$COMMAND" in
  read)
    knowledge_path="${SCRIPT_DIR}/PROJECT_KNOWLEDGE.md"
    if [[ ! -f "${knowledge_path}" ]]; then
      echo "Missing project knowledge: ${knowledge_path}" >&2
      exit 1
    fi
    exec sed -n '1,$p' "${knowledge_path}"
    ;;
  generate)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/persona_dream.py" generate "$@"
    ;;
  research-bakeoff)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/research_bakeoff.py" "$@"
    ;;
  contact-sheet)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/contact_sheet.py" "$@"
    ;;
  pipeline-phase02-recall)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/run_phase_02_memory_recall.py" "$@"
    ;;
  phase-05-sync-contact-sheet-sidecars)
    exec python3 "${SCRIPT_DIR}/scripts/sync_contact_sheet_sidecars.py" "$@"
    ;;
  phase-05-contact-sheet-gate)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_phase_05_contact_sheet_gate.py" "$@"
    ;;
  regenerate)
    exec python3 "${SCRIPT_DIR}/scripts/regenerate_asset.py" "$@"
    ;;
  validate-gate)
    exec python3 "${SCRIPT_DIR}/scripts/validate_gate.py" "$@"
    ;;
  pipeline-loop-status)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/pipeline_loop_status.py" "$@"
    ;;
  pipeline-loop-run)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/pipeline_loop_run.py" "$@"
    ;;
  validate-pipeline-loop-run)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_pipeline_loop_run.py" "$@"
    ;;
  validate-run-root)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_run_root_pipeline.py" "$@"
    ;;
  multiscene-live-smoke)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/run_multiscene_live_smoke.py" "$@"
    ;;
  validate-multiscene-live-smoke)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_multiscene_live_smoke.py" "$@"
    ;;
  write-multiscene-live-report)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_multiscene_live_report.py" "$@"
    ;;
  validate-dream-packet)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_dream_packet.py" "$@"
    ;;
  write-dream-packet-work-order)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_dream_packet_work_order.py" "$@"
    ;;
  validate-dream-packet-work-order)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_dream_packet_work_order.py" "$@"
    ;;
  validate-panel-repair-gate)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" "$@"
    ;;
  validate-panel-source)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_source_receipt.py" "$@"
    ;;
  validate-provider-media-url)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_provider_media_url.py" "$@"
    ;;
  write-provider-media-publication-work-order)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_provider_media_publication_work_order.py" "$@"
    ;;
  validate-provider-media-publication-work-order)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_provider_media_publication_work_order.py" "$@"
    ;;
  stage-provider-media-local-asset)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/stage_provider_media_local_asset.py" "$@"
    ;;
  validate-provider-media-local-staging)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_provider_media_local_staging.py" "$@"
    ;;
  validate-provider-media-publication-preflight)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_provider_media_publication_preflight.py" "$@"
    ;;
  write-provider-media-publication-authorization-template)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_provider_media_publication_authorization_template.py" "$@"
    ;;
  validate-provider-media-publication-authorization)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_provider_media_publication_authorization.py" "$@"
    ;;
  validate-provider-media-public-handoff)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_provider_media_public_handoff.py" "$@"
    ;;
  validate-pipeline-evidence-bundle)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_pipeline_evidence_bundle.py" "$@"
    ;;
  apply-provider-media-public-probe)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/apply_provider_media_public_probe.py" "$@"
    ;;
  write-panel-comparison-status)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_panel_comparison_status.py" "$@"
    ;;
  validate-panel-comparison-report)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_comparison_report.py" "$@"
    ;;
  validate-story-contract)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_story_contract.py" "$@"
    ;;
  write-story-contract-work-order)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_story_contract_work_order.py" "$@"
    ;;
  validate-story-contract-work-order)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_story_contract_work_order.py" "$@"
    ;;
  validate-visual-review)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_visual_review_receipt.py" "$@"
    ;;
  validate-storyboard-panel)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_storyboard_panel_receipt.py" "$@"
    ;;
  write-storyboard-panel-work-order)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_storyboard_panel_work_order.py" "$@"
    ;;
  validate-storyboard-panel-work-order)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_storyboard_panel_work_order.py" "$@"
    ;;
  write-panel-source)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_panel_source_receipt.py" "$@"
    ;;
  write-panel-repair-work-order)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_panel_repair_work_order.py" "$@"
    ;;
  validate-panel-repair-work-order)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_work_order.py" "$@"
    ;;
  write-one-scene-kling-review-packet)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_one_scene_kling_review_packet.py" "$@"
    ;;
  convert-accepted-storyboard-to-kling)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/convert_accepted_storyboard_to_kling.py" "$@"
    ;;
  validate-kling-scene-packet)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_kling_scene_packet.py" "$@"
    ;;
  check-kling-scene-packet-dry-run-gate)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_kling_scene_packet_dry_run_gate.py" "$@"
    ;;
  check-respawn-plan)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_persona_dream_respawn_plan.py" "$@"
    ;;
  check-stale-write-fence)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_persona_dream_stale_write_fence.py" "$@"
    ;;
  check-global-progress-rollup)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_persona_dream_global_progress_rollup.py" "$@"
    ;;
  check-dynamic-respawn-events)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_persona_dream_dynamic_respawn_events.py" "$@"
    ;;
  check-creator-reviewer-respawn-loop)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_persona_dream_creator_reviewer_respawn_loop.py" "$@"
    ;;
  check-persona-dream-run-state)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_persona_dream_run_state.py" "$@"
    ;;
  write-run-state-from-run-root)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_persona_dream_run_state_from_run_root.py" "$@"
    ;;
  check-run-root-state)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_persona_dream_run_root_state.py" "$@"
    ;;
  select-video-provider)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/select_video_provider.py" "$@"
    ;;
  check-video-provider-selection)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_video_provider_selection.py" "$@"
    ;;
  refresh-video-provider-registry)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/refresh_video_provider_registry.py" "$@"
    ;;
  check-video-provider-registry-refresh)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_video_provider_registry_refresh.py" "$@"
    ;;
  write-video-provider-packet)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_video_provider_packet.py" "$@"
    ;;
  check-video-provider-packet-routing)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_video_provider_packet_routing.py" "$@"
    ;;
  check-fal-api-preflight)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_fal_api_preflight.py" "$@"
    ;;
  check-fal-api-preflight-fixtures)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_fal_api_preflight_fixtures.py" "$@"
    ;;
  check-pipeline-robustness)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_pipeline_robustness.py" "$@"
    ;;
  check-live-memory-recall)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_live_memory_recall.py" "$@"
    ;;
  run-live-pctom-gate0)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_pctom_gate0.py" "$@"
    ;;
  run-live-tau-gate2-4)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_gate2_4.py" "$@"
    ;;
  run-live-tau-score-revision)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_score_revision.py" "$@"
    ;;
  run-live-tau-reliability-bridge)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_reliability_bridge.py" "$@"
    ;;
  run-condition-comparison)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_condition_comparison.py" "$@"
    ;;
  run-live-tau-condition-comparison)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_condition_comparison.py" "$@"
    ;;
  run-live-tau-condition-reliability-bridge)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_condition_reliability_bridge.py" "$@"
    ;;
  run-live-tau-condition-action-selection)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_condition_action_selection.py" "$@"
    ;;
  run-live-tau-action-linked-revision)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_action_linked_revision.py" "$@"
    ;;
  run-live-tau-revision-recall)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_revision_recall.py" "$@"
    ;;
  run-heldout-condition-benefit)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_heldout_condition_benefit.py" "$@"
    ;;
  run-live-memory-revision-recall)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_memory_revision_recall.py" "$@"
    ;;
  run-live-memory-revision-delayed-recall)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_memory_revision_delayed_recall.py" "$@"
    ;;
  run-live-memory-restart-delayed-recall)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_memory_restart_delayed_recall.py" "$@"
    ;;
  run-live-memory-aged-retention-recall)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_memory_aged_retention_recall.py" "$@"
    ;;
  check-social-episode-independent-replay)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_social_episode_independent_replay.py" "$@"
    ;;
  run-sealed-test-statistical-confidence)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_sealed_test_statistical_confidence.py" "$@"
    ;;
  analyze-sealed-test-planning-gap)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/analyze_sealed_test_planning_gap.py" "$@"
    ;;
  run-live-fault-injection-surface)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_fault_injection_surface.py" "$@"
    ;;
  run-live-tau-sealed-test-replication)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_sealed_test_replication.py" "$@"
    ;;
  run-live-tau-full64-statistical-confidence)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_full64_statistical_confidence.py" "$@"
    ;;
  run-live-tau-full64-repeated-run-summary)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_full64_repeated_run_summary.py" "$@"
    ;;
  run-live-tau-full64-planning-diagnostic)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_full64_planning_diagnostic.py" "$@"
    ;;
  run-live-tau-full64-action-policy-sensitivity)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_full64_action_policy_sensitivity.py" "$@"
    ;;
  run-live-tau-trust-commit-replication)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_trust_commit_replication.py" "$@"
    ;;
  run-live-tau-trust-commit-repeated-seed-summary)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_trust_commit_repeated_seed_summary.py" "$@"
    ;;
  run-live-tau-planning-non-generalization-audit)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_planning_non_generalization_audit.py" "$@"
    ;;
  run-live-tau-distributional-planning-intervention)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_distributional_planning_intervention.py" "$@"
    ;;
  run-live-tau-confidence-gated-planning-intervention)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_confidence_gated_planning_intervention.py" "$@"
    ;;
  run-live-tau-balanced-planning-replication)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_balanced_planning_replication.py" "$@"
    ;;
  run-live-tau-balanced-planning-diagnostic)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_balanced_planning_diagnostic.py" "$@"
    ;;
  run-live-tau-balanced-threshold-intervention)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_balanced_threshold_intervention.py" "$@"
    ;;
  run-live-tau-cooperation-threshold-rule)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_cooperation_threshold_rule.py" "$@"
    ;;
  run-live-tau-cooperation-exposure-slice)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_cooperation_exposure_slice.py" "$@"
    ;;
  check-cooperation-exposure-instrument)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_cooperation_exposure_instrument.py" "$@"
    ;;
  check-cooperation-contrast-instrument)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_cooperation_contrast_instrument.py" "$@"
    ;;
  check-cooperation-unsafe-offer-pressure-instrument)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_cooperation_unsafe_offer_pressure_instrument.py" "$@"
    ;;
  run-live-tau-cooperation-instrument-slice)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_cooperation_instrument_slice.py" "$@"
    ;;
  run-live-tau-cooperation-contrast-slice)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_cooperation_contrast_slice.py" "$@"
    ;;
  run-live-tau-cooperation-exposure-contrast-slice)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_cooperation_exposure_contrast_slice.py" "$@"
    ;;
  run-live-tau-cooperation-unsafe-offer-pressure-slice)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_cooperation_unsafe_offer_pressure_slice.py" "$@"
    ;;
  diagnose-cooperation-unsafe-offer-no-exposure)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/diagnose_cooperation_unsafe_offer_no_exposure.py" "$@"
    ;;
  check-cooperation-class-separated-exposure)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_cooperation_class_separated_exposure.py" "$@"
    ;;
  check-cooperation-visible-pressure-rule-reliability)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_cooperation_visible_pressure_rule_reliability.py" "$@"
    ;;
  build-cooperation-visible-pressure-reliability-surface)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/build_cooperation_visible_pressure_reliability_surface.py" "$@"
    ;;
  build-cooperation-visible-pressure-causal-replay)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/build_cooperation_visible_pressure_causal_replay.py" "$@"
    ;;
  analyze-cooperation-visible-pressure-planning-benefit)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/analyze_cooperation_visible_pressure_planning_benefit.py" "$@"
    ;;
  diagnose-cooperation-policy)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/diagnose_cooperation_policy.py" "$@"
    ;;
  accept-cooperation-no-intervention-policy)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/accept_cooperation_no_intervention_policy.py" "$@"
    ;;
  check-cooperation-feature-split-prerequisites)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_cooperation_feature_split_prerequisites.py" "$@"
    ;;
  run-live-tau-strict-inference-prompt-replication)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_strict_inference_prompt_replication.py" "$@"
    ;;
  run-pctom-causal-identifiability-gate)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_pctom_causal_identifiability_gate.py" "$@"
    ;;
  run-live-tau-prompt-timeout-diagnostic)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_prompt_timeout_diagnostic.py" "$@"
    ;;
  run-live-tau-sealed-test-retry-proof)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_sealed_test_retry_proof.py" "$@"
    ;;
  run-live-tau-sealed-test-runsh-orchestration-retry-proof)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_sealed_test_runsh_orchestration_retry_proof.py" "$@"
    ;;
  run-live-tau-sealed-test-queue-worker-retry-proof)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_sealed_test_queue_worker_retry_proof.py" "$@"
    ;;
  run-live-tau-sealed-test-service-retry-proof)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_sealed_test_service_retry_proof.py" "$@"
    ;;
  run-live-tau-full64-memory-fault-surface)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_live_tau_full64_memory_fault_surface.py" "$@"
    ;;
  check-live-gate2-4-boundary-negatives)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_live_gate2_4_boundary_negatives.py" "$@"
    ;;
  check-live-gate5-7-boundary-negatives)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_live_gate5_7_boundary_negatives.py" "$@"
    ;;
  run-social-simulator-service-proof)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_social_simulator_service_proof.py" "$@"
    ;;
  check-live-stage-hash-lineage-audit)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_live_stage_hash_lineage_audit.py" "$@"
    ;;
  check-autonomous-no-human-judgment-surface)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_autonomous_no_human_judgment_surface.py" "$@"
    ;;
  check-pctom-goal-coverage)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_pctom_goal_coverage.py" "$@"
    ;;
  check-pctom-success-criteria)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_pctom_success_criteria.py" "$@"
    ;;
  check-pctom-calibration-abstention)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_pctom_calibration_abstention.py" "$@"
    ;;
  check-pctom-unsupported-evidence-abstention)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_pctom_unsupported_evidence_abstention.py" "$@"
    ;;
  check-pctom-objective-evidence)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_pctom_objective_evidence.py" "$@"
    ;;
  check-prospective-tom-protocol)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_prospective_tom_protocol.py" "$@"
    ;;
  build-pctom-external-proof-archive)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/build_pctom_external_proof_archive.py" "$@"
    ;;
  verify-pctom-external-proof-archive)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/build_pctom_external_proof_archive.py" --verify "$@"
    ;;
  build-social-episode-corpus)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/build_social_episode_corpus.py" "$@"
    ;;
  check-social-episode-corpus)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_social_episode_corpus.py" "$@"
    ;;
  check-tom-belief-distributions)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_tom_belief_distributions.py" "$@"
    ;;
  check-counterfactual-branches)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_counterfactual_branches.py" "$@"
    ;;
  check-tom-prediction-commitments)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_tom_prediction_commitments.py" "$@"
    ;;
  reveal-and-score-tom-trial)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/reveal_and_score_trial.py" "$@"
    ;;
  run-tom-action-selection-trial)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_action_selection_trial.py" "$@"
    ;;
  check-tom-belief-revision)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/check_tom_belief_revision.py" "$@"
    ;;
  run-reliability-surface)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_reliability_surface.py" "$@"
    ;;
  run-causal-replay)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/research/prospective-tom/scripts/run_causal_replay.py" "$@"
    ;;
  check-pipeline-contract)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_persona_dream_pipeline_contract.py" "$@"
    ;;
  write-phase10-reproducibility-receipt)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_phase10_reproducibility_receipt.py" "$@"
    ;;
  repair-semantic-mix-revision)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/repair_semantic_mix_revision.py" "$@"
    ;;
  bootstrap-phase11-payload-binding)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/bootstrap_phase11_payload_binding.py" "$@"
    ;;
  write-dream-observation-packet)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_dream_observation_packet.py" "$@"
    ;;
  check-dream-observation-packet)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_dream_observation_packet.py" "$@"
    ;;
  check-tau-routing-boundary)
    # Enforce operator rule "only /tau may reach /scillm": deterministic static
    # scan of skills/persona-dream + skills/watch for direct scillm proxy calls.
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/../../scripts/check_tau_routing_boundary.py" "$@"
    ;;
  write-phase11-media-requirement-manifest)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_phase11_media_requirement_manifest.py" "$@"
    ;;
  write-phase11-dry-run-bundle)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_phase11_dry_run_bundle.py" "$@"
    ;;
  capture-phase11-provider-source-snapshot)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/capture_phase11_provider_source_snapshot.py" "$@"
    ;;
  capture-phase11-public-media-evidence)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/capture_phase11_public_media_evidence.py" "$@"
    ;;
  reconcile-phase11-upstream-validation)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/reconcile_phase11_upstream_validation.py" "$@"
    ;;
  compile-phase11-canonical-live-request)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/compile_phase11_canonical_live_request.py" "$@"
    ;;
  validate-phase11-canonical-live-request)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_phase11_canonical_live_request.py" "$@"
    ;;
  write-phase11-approval-receipts)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_phase11_approval_receipts.py" "$@"
    ;;
  phase11-fal-canary-preflight)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/phase11_fal_canary_adapter.py" --preflight "$@"
    ;;
  phase11-fal-canary-execute)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/phase11_fal_canary_adapter.py" --execute "$@"
    ;;
  write-cognitive-loop-dry-run)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/write_cognitive_loop_dry_run.py" "$@"
    ;;
  tailscale-funnel-publication-canary)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/tailscale_funnel_publication_canary.py" "$@"
    ;;
  validate-local-media-lock)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_local_media_lock.py" "$@"
    ;;
  review-clipboard-bridge)
    exec python3 "${SCRIPT_DIR}/scripts/pipeline_review_clipboard_bridge.py" "$@"
    ;;
  storyboard-fixture)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/storyboard_first_fixture.py" "$@"
    ;;
  backend-readiness)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/persona_dream.py" backend-readiness "$@"
    ;;
  chutes-generate)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/persona_dream.py" chutes-generate "$@"
    ;;
  lore-canary)
    exec "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/run_lore_extraction_canary.py" "$@"
    ;;
  test-suite)
    # Deterministic contract suite. Runs offline (no paid/live provider calls);
    # any test that needs a live route must sit behind an opt-in marker, not here.
    exec "${PYTHON[@]}" -m pytest "${SCRIPT_DIR}/tests" -q "$@"
    ;;
  help|--help|-h)
    usage
    ;;
  *)
    echo "Unknown command: ${COMMAND}" >&2
    usage >&2
    exit 2
    ;;
esac
