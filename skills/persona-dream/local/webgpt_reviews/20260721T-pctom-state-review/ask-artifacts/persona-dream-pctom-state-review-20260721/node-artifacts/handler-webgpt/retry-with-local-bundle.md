Use the attached local bundle as the source of truth.
Do not rely on bare private GitHub URLs or local paths not present in the attachment.
Answer the original request using the attached bundle and state any remaining access gaps.

Original request:
# WebGPT Review Request: Persona Dream PCTOM-R State

Date: 2026-07-21
Repository: /tmp/persona-dream-pctom-next-main-T7LEYn
Project: skills/persona-dream
Review lane: WebGPT via /ask tau-dag handler=webgpt handler-project=webgpt=tau

## Objective

Review the current state of Persona Dream against the active research goal:

> Meet Persona Dream's research goals through the PCTOM-R text-first prospective
> Theory-of-Mind reliability lane: provenance-bound recall residue,
> deterministic hidden-state social episodes, valid ToM distributions, sealed
> prediction commitments, deterministic scoring, non-destructive belief
> revision, and fail-closed reliability checks, without treating provider/video
> work as the current critical path.

The human does not care about vague GitHub commit status. Assess concrete
research evidence and next steps.

## Current Local Project Evidence

- Active goal file:
  `skills/persona-dream/GOAL.md`
- Project state file:
  `skills/persona-dream/PROJECT_KNOWLEDGE.md`
- Research namespace:
  `skills/persona-dream/research/prospective-tom/`
- Protocol:
  `skills/persona-dream/research/prospective-tom/contracts/prospective_tom_protocol.v1.md`
- Schemas present:
  `social_episode`, `tom_belief_distribution`, `counterfactual_intervention`,
  `tom_prediction_commitment`, `tom_outcome_reveal`, `tom_scoring_receipt`,
  `tom_belief_revision`, `reliability_trial`, plus bundle/action/reliability
  schemas.
- Scripts present include corpus build/check, belief distribution checks,
  prediction commitment checks, reveal/score, action selection, live Tau
  condition comparison/action selection, strict inference, service retry proof,
  live Memory revision recall, fault surface, causal replay, heldout condition
  benefit, statistical confidence, and intervention diagnostics.

## Concrete Evidence Snapshot

1. Gate 0 / provenance:
   - Gate 0 exists as `run_live_pctom_gate0.py`.
   - Recent evidence claims include accepted-source recall lineage and exact
     reread behavior, but the reviewer should check whether this is sufficient
     for prospective trial causal attribution.

2. Live strict-inference balanced slice:
   - Receipt:
     `/tmp/persona-dream-live-tau-strict-inference-timeout120-v17-20260721T1527Z/live_tau_strict_inference_prompt_replication_receipt.v1.json`
   - Status:
     `PASS_LIVE_TAU_PCTOM_STRICT_INFERENCE_PROMPT_REPLICATION`
   - SHA:
     `sha256:27e7469cea92f3546ae6a2df3377548a3f6b61cf813cc7d02d1e79bcc38e5f0d`
   - Counts:
     `mocked:false`, `live:true`, 16/16 Tau calls, 16 action decisions, four
     planning rows, four scenario families, zero blocked cases, zero Memory/
     provider/canonical/identity/source-memory writes.
   - Limitation:
     `planning_benefit_with_confidence:false`, one `LOSS`, three `UNCHANGED`,
     `mean_cd_minus_baseline:0.1375`.

3. Gate 7 action-linked revision:
   - Receipt:
     `/tmp/persona-dream-live-tau-action-linked-revision-strict120-v17-20260721T1545Z/live_tau_action_linked_revision_receipt.v1.json`
   - Status:
     `PASS_LIVE_TAU_PCTOM_ACTION_LINKED_REVISION`
   - Counts:
     16/16 `PASS_TOM_BELIEF_REVISION`, prior and posterior revisions for every
     M/R/D/CD condition, zero Memory/provider/canonical/identity/source writes.

4. Deterministic revision recall:
   - Receipt:
     `/tmp/persona-dream-live-tau-revision-recall-strict120-v17-20260721T1546Z/live_tau_revision_recall_receipt.v1.json`
   - Status:
     `PASS_LIVE_TAU_PCTOM_REVISION_RECALL`
   - Counts:
     16 revision documents, 16 local recall hits, prior/posterior distinction
     preserved, synthetic/literal boundary preserved, zero write violations.

5. Live Memory revision recall:
   - Receipt:
     `/tmp/persona-dream-live-memory-revision-recall-strict120-v17-20260721T1547Z/live_memory_revision_recall_receipt.v1.json`
   - Status:
     `PASS_PCTOM_LIVE_MEMORY_REVISION_RECALL`
   - Counts:
     16 noncanonical PCTOM-R revision docs upserted and exact-reread, 16
     semantic mirrors exact-reread, four `/recall` condition queries, 16 recall
     hits, zero canonical/identity/source-memory/provider/Tau writes.

6. Live fault-injection surface:
   - Receipt:
     `/tmp/persona-dream-live-fault-injection-surface-strict120-v17-20260721T1548Z/live_fault_injection_surface_receipt.v1.json`
   - Status:
     `PASS_PCTOM_LIVE_FAULT_INJECTION_SURFACE`
   - SHA:
     `sha256:aa0bf2389ff88f299ccfaf77f3b017e40e4159d851fc7928aca379cb49ded84f`
   - Counts:
     eight required fault families, eight trials, one causal replay artifact,
     three live Memory fault probes, zero `CONTINUED_WITH_UNKNOWN_STATE`, zero
     side-effect violations, zero Memory/provider/Tau/canonical/identity/
     source writes.
   - Limitation:
     Does not prove service-boundary retry machinery or live Tau sealed-test
     execution.

7. Full64 service-boundary retry proof:
   - Receipt:
     `/tmp/persona-dream-live-tau-sealed-test-service-retry-proof-fresh-20260721T155119Z/live_tau_sealed_test_service_retry_proof_receipt.v1.json`
   - Status:
     `PASS_LIVE_TAU_PCTOM_SERVICE_RETRY_PROOF`
   - SHA:
     `sha256:d92fd93008ec467b515b745083947459d875b33dfa87bd423a4bf64e7cf509ef`
   - Counts:
     `mocked:false`, `live:true`, live Tau-originated artifacts consumed without
     reexecuting Tau, 256 action decisions, 256 active predictions, five HTTP
     submissions, four unique service jobs, one duplicate submission detected
     and not promoted, two completed jobs, two blocked jobs, eight retry fault
     trials, zero `CONTINUED_WITH_UNKNOWN_STATE`, zero duplicate active/action
     promotions, zero side-effect violations, zero Memory/provider/canonical/
     identity/source-memory writes.
   - Limitation:
     This is a local HTTP process boundary over live-originated artifacts; it is
     not a permanently deployed orchestrator and not new live Tau execution.

8. Balanced planning reuse over strict120 roots:
   - Receipt:
     `/tmp/persona-dream-live-tau-balanced-planning-reuse-strict120-v17-limit1-20260721T1550Z/live_tau_balanced_planning_replication_receipt.v1.json`
   - Status:
     `PASS_LIVE_TAU_PCTOM_BALANCED_PLANNING_REPLICATION`
   - Counts:
     16 hash-bound live Tau case artifacts consumed, all four families
     represented, four action decisions per condition, zero writes.
   - Limitation:
     Negative/insufficient result: `planning_benefit_with_confidence:false`,
     CD planning regret mean `0.275`, strongest baseline D `0.1375`,
     CD-minus-D `0.1375`.

9. Planning intervention CI repair:
   - Files:
     `skills/persona-dream/research/prospective-tom/scripts/run_live_tau_distributional_planning_intervention.py`
     `skills/persona-dream/research/prospective-tom/scripts/run_live_tau_confidence_gated_planning_intervention.py`
     `skills/persona-dream/tests/test_pctom_planning_intervention_ci.py`
   - Proof:
     `uv run --project skills/persona-dream pytest skills/persona-dream/tests/test_pctom_planning_intervention_ci.py -q`
     returned `4 passed in 0.03s`; `python3 -m py_compile` over the two scripts
     and test emitted no errors.
   - Fresh receipts:
     `/tmp/persona-dream-live-tau-distributional-planning-intervention-ci-derived-20260721T155724Z/distributional_planning_intervention_receipt.v1.json`
     `/tmp/persona-dream-live-tau-confidence-gated-planning-intervention-ci-derived-20260721T155724Z/confidence_gated_planning_intervention_receipt.v1.json`
   - Result:
     planning benefit still not shown. Distributional ties all 64 planning rows
     with CI `[0.0,0.0]`; confidence-gated has 63 ties and one harm with CI
     upper `0.014062499999999997`.

10. Blocked fresh balanced live Tau variants 19-20:
    - Receipt:
      `/tmp/persona-dream-live-tau-balanced-planning-v19-20-20260721T155956Z/live_tau_balanced_planning_replication_receipt.v1.json`
    - Status:
      `BLOCKED_LIVE_TAU_PCTOM_BALANCED_PLANNING_REPLICATION`
    - SHA:
      `sha256:9f7fddbca26b1442e62c0c81e0beb7c3e695975ae52eeae88f81502721e4a585`
    - Counts:
      `mocked:false`, `live:true`, 32 live Tau attempts/calls, 0 Memory/
      provider/canonical/identity/source-memory writes.
    - Blocker:
      Failed closed because `sealedte-info-asym-19` R and D returned
      `scillm_http_status_502`, leaving 7/8 accepted planning rows and failing
      balanced family counts. Treat this as reliability/blocker evidence, not
      planning-benefit evidence.

11. UX Lab housing:
    - URL:
      `http://127.0.0.1:3002/?project=persona-dream`
    - Last marker:
      `/home/graham/workspace/experiments/agent-skills-main/.codex/ui-verification/latest.json`
    - Limitation:
      This only proves a project wrapper/card is reachable. It does not prove
      the old `#dream` runtime or research pipeline UI.

## Brave Search Research Seeds

The local agent consulted Brave Search first as requested. Seed results:

- `Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers`
  arXiv/html `2603.07670v1`: memory mechanisms, causal annotations,
  counterfactual planning, multi-step debugging.
- `Position: Theory of Mind Benchmarks are Broken for Large Language Models`
  OpenReview: critiques static ToM benchmarks because they do not test
  adaptation to new partners.
- `Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions`
  arXiv/pdf `2507.05257`: incremental multi-turn memory evaluation.
- `LLMs achieve adult human performance on higher-order theory of mind tasks`
  PMC: explicitly notes that binary judgment success may not translate to
  reliable naturalistic dialogue/multi-agent prediction/action tasks.
- `Why Reasoning Fails to Plan: A Planning-Centric Analysis of Long-Horizon
  Decision Making in LLM Agents` arXiv/html `2601.22311v1`: explicit lookahead,
  counterfactual future trajectories, next-action commitment.
- `Survey on Evaluation of LLM-based Agents` arXiv/html `2503.16416v1`:
  reflection, memory use, belief update, counterfactual reasoning, decision
  adjustment.
- `Theory of Mind in Large Language Models: Assessment and Enhancement`
  arXiv/html `2505.00026v1`: passive benchmarks versus active agents.
- `ReliabilityBench: Evaluating LLM Agent Reliability Under Production-Like
  Stress Conditions` arXiv `2601.06112`: pass^k, semantic perturbation epsilon,
  fault intensity lambda, reliability surface R(k, epsilon, lambda), partial
  responses, schema drift, timeouts/rate limits.
- `MAS-FIRE` arXiv `2602.19843`: fault injection and reliability evaluation for
  LLM-based multi-agent systems.
- `tau-bench`: repeated tool-agent-user interaction benchmark and pass^k
  motivation.
- `Causal Agent Replay: Counterfactual Attribution for LLM-Agent Failures`
  arXiv `2606.08275`: counterfactual replay/localization of agent failures.
- `A Survey on the Security of Long-Term Memory in LLM Agents` arXiv
  `2604.16548`: long-term memory security and attack/failure surfaces.

## Browser Oracle State

- Persona Dream-specific Browser Oracle resolution returned
  `needs_attention/no_project_resolved`.
- Explicit project override works:
  `skills/browser-oracle/run.sh resolve --from skills/persona-dream --backend webgpt --project tau --json`
  resolved project `tau`, binding `/home/graham/.pi/webgpt-projects/tau.json`,
  tab id `837360427`.
- Browser Oracle doctor with the same override returned readiness `ready`.
- WebGPT conversation URL:
  `https://chatgpt.com/g/g-p-6a401806e7a08191a4ea6745a305f981-tau/c/6a5a1f08-edc8-83ea-8376-6dd6d7accd16`

## Review Questions

Please review the project state and answer with a source-grounded operational
assessment, not a generic roadmap.

1. Are Persona Dream's active PCTOM-R research goals being met by the current
   local evidence? Separate implemented behavior, partially proven behavior,
   aspirational behavior, and missing proof.
2. What is outstanding or brittle in the current implementation and evidence
   chain?
3. What are the next concrete steps that would keep this project cutting-edge
   research, given the external research seeds above?
4. Should the next engineering action prioritize retry/resume machinery for
   live Tau `scillm_http_status_502` failures, planning-policy/corpus design to
   produce measurable CD benefit, or a different gate?
5. What should explicitly not be done next?

Please include:

- A numbered source-derived step model.
- A table or bullets labeling `IMPLEMENTED`, `PARTIALLY_PROVEN`,
  `MISSING`, and `ASPIRATIONAL`.
- A prioritized next-step list with stop conditions and artifact names.
- A clear statement of whether current evidence supports the main scientific
  claim. Treat WebGPT as advisory only; do not claim proof without local
  receipts.

Browser failure class that triggered this retry packet: repo_access_blocked