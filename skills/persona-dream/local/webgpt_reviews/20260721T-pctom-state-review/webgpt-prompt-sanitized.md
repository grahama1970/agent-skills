# WebGPT Review Request: Persona Dream PCTOM-R State

You are reviewing a local project state bundle. The browser cannot read private
filesystem paths, so this prompt contains the source facts directly. Treat every
receipt-status line as a local evidence claim supplied by the project agent, not
as proof you independently inspected the file. Your job is to assess whether the
research program is on track and identify the next cutting-edge research steps.

## Active Research Goal

Persona Dream's active goal is PCTOM-R: Prospective Counterfactual
Theory-of-Mind Reliability.

The goal is to show whether synthetic counterfactual dreaming improves an
agent's prospective, calibrated Theory-of-Mind predictions and planning
decisions while the pipeline remains provenance-bound, sealed before outcome
reveal, deterministically scored, non-destructively revised, and fail-closed
under memory, model, tool, schema, retry, and persistence faults.

The current critical path is text-first research evidence, not video/provider
generation, dashboard polish, or subjective dream-content quality.

## Implemented Project Shape

The project has a research namespace for prospective ToM. It contains:

- a prospective ToM protocol contract;
- schemas for social episodes, ToM belief distributions, counterfactual
  interventions, prediction commitments, outcome reveals, scoring receipts,
  belief revisions, reliability trials, action selections, causal replay, and
  reliability surfaces;
- scripts for social episode corpus build/check, distribution checks,
  prediction commitment checks, reveal and score, action selection, condition
  comparison, heldout condition benefit, reliability surface, causal replay,
  live Tau condition comparison/action selection, live Memory revision recall,
  live fault injection, full64 statistical confidence, strict inference,
  service-boundary retry proof, and planning-policy interventions.

## Current Evidence Snapshot

1. Gate 0 provenance exists as a live PCTOM gate script. Recent local evidence
   claims accepted-source recall lineage and exact reread behavior. The open
   question is whether it is strong enough for prospective causal attribution
   from recall query to accepted raw source id to normalized residue to dream
   branch to ToM prediction.

2. Live strict-inference balanced slice:
   - status: PASS_LIVE_TAU_PCTOM_STRICT_INFERENCE_PROMPT_REPLICATION
   - receipt SHA: sha256:27e7469cea92f3546ae6a2df3377548a3f6b61cf813cc7d02d1e79bcc38e5f0d
   - mocked: false
   - live: true
   - counts: 16 of 16 Tau calls, 16 action decisions, 4 planning rows, 4
     scenario families, 0 blocked cases, 0 Memory/provider/canonical/identity/
     source-memory writes
   - limitation: planning_benefit_with_confidence is false; oracle transitions
     were 1 LOSS and 3 UNCHANGED; mean CD-minus-baseline was 0.1375, so CD was
     worse on this slice.

3. Gate 7 action-linked belief revision:
   - status: PASS_LIVE_TAU_PCTOM_ACTION_LINKED_REVISION
   - counts: 16 of 16 belief revisions passed; prior and posterior revisions
     exist for all M/R/D/CD conditions; 0 Memory/provider/canonical/identity/
     source writes.

4. Deterministic local revision recall:
   - status: PASS_LIVE_TAU_PCTOM_REVISION_RECALL
   - counts: 16 revision documents, 16 local recall hits, prior/posterior
     distinction preserved, synthetic/literal boundary preserved, 0 write
     violations.

5. Live Memory revision recall:
   - status: PASS_PCTOM_LIVE_MEMORY_REVISION_RECALL
   - counts: 16 noncanonical PCTOM-R revision docs upserted and exact-reread,
     16 semantic mirrors exact-reread, 4 recall condition queries, 16 recall
     hits, 0 canonical/identity/source-memory/provider/Tau writes.

6. Live fault-injection surface:
   - status: PASS_PCTOM_LIVE_FAULT_INJECTION_SURFACE
   - receipt SHA: sha256:aa0bf2389ff88f299ccfaf77f3b017e40e4159d851fc7928aca379cb49ded84f
   - counts: 8 required fault families, 8 trials, 1 causal replay artifact, 3
     live Memory fault probes, 0 CONTINUED_WITH_UNKNOWN_STATE, 0 side-effect
     violations, 0 Memory/provider/Tau/canonical/identity/source writes.
   - limitation: this does not prove service-boundary retry machinery or live
     Tau sealed-test execution.

7. Full64 service-boundary retry proof:
   - status: PASS_LIVE_TAU_PCTOM_SERVICE_RETRY_PROOF
   - receipt SHA: sha256:d92fd93008ec467b515b745083947459d875b33dfa87bd423a4bf64e7cf509ef
   - mocked: false
   - live: true
   - consumed live Tau-originated artifacts without reexecuting Tau
   - counts: 256 action decisions, 256 active predictions, 5 HTTP submissions,
     4 unique service jobs, 1 duplicate submission detected and not promoted, 2
     completed jobs, 2 blocked jobs, 8 retry fault trials, 0
     CONTINUED_WITH_UNKNOWN_STATE, 0 duplicate active/action promotions, 0
     side-effect violations, 0 Memory/provider/canonical/identity/source-memory
     writes.
   - limitation: local HTTP process boundary only; not a permanent orchestrator
     and not new live Tau execution.

8. Balanced planning reuse over strict120 roots:
   - status: PASS_LIVE_TAU_PCTOM_BALANCED_PLANNING_REPLICATION
   - counts: 16 hash-bound live Tau case artifacts consumed, all 4 families
     represented, 4 action decisions per condition, 0 writes
   - limitation: negative or insufficient planning result:
     planning_benefit_with_confidence false; CD planning regret mean 0.275;
     strongest baseline D 0.1375; CD-minus-D 0.1375.

9. Planning intervention CI repair:
   - files patched: distributional planning intervention runner, confidence
     gated planning intervention runner, planning intervention CI test
   - proof: focused pytest returned 4 passed in 0.03s; py_compile emitted no
     errors
   - fresh full64 intervention receipts still do not show planning benefit:
     distributional ties all 64 planning rows with CI [0.0, 0.0];
     confidence-gated has 63 ties and 1 harm with CI upper 0.014062499999999997.

10. Blocked fresh balanced live Tau variants 19-20:
    - status: BLOCKED_LIVE_TAU_PCTOM_BALANCED_PLANNING_REPLICATION
    - receipt SHA: sha256:9f7fddbca26b1442e62c0c81e0beb7c3e695975ae52eeae88f81502721e4a585
    - mocked: false
    - live: true
    - counts: 32 live Tau attempts/calls, 0 Memory/provider/canonical/identity/
      source-memory writes
    - blocker: two R/D condition calls for one information-asymmetry variant
      returned scillm_http_status_502. The runner failed closed with 7 of 8
      accepted planning rows and did not satisfy balanced family counts. This
      is reliability/blocker evidence, not planning-benefit evidence.

11. UX Lab housing:
    - local URL: a Persona Dream project card exists in a multi-project UX Lab
      wrapper
    - limitation: it proves wrapper/card visibility only, not legacy dream
      runtime or research-pipeline UI.

## External Research Seeds From Brave Search

- Memory for Autonomous LLM Agents, arXiv 2603.07670: memory mechanisms,
  causal annotations, counterfactual planning, multi-step debugging.
- Position: Theory of Mind Benchmarks are Broken for Large Language Models:
  critiques static ToM benchmarks for not testing adaptation to new partners.
- Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions,
  arXiv 2507.05257: incremental multi-turn memory evaluation.
- LLMs achieve adult human performance on higher-order ToM tasks: notes binary
  judgment success may not transfer to naturalistic dialogue, multi-agent
  prediction, or action tasks.
- Why Reasoning Fails to Plan, arXiv 2601.22311: explicit lookahead,
  counterfactual future trajectories, next-action commitment.
- Survey on Evaluation of LLM-based Agents, arXiv 2503.16416: reflection,
  memory use, belief update, counterfactual reasoning, decision adjustment.
- Theory of Mind in LLMs: Assessment and Enhancement, arXiv 2505.00026:
  passive benchmarks versus active agents.
- ReliabilityBench, arXiv 2601.06112: pass^k, semantic perturbation epsilon,
  fault intensity lambda, reliability surface R(k, epsilon, lambda), partial
  responses, schema drift, timeouts and rate limits.
- MAS-FIRE, arXiv 2602.19843: fault injection and reliability evaluation for
  LLM-based multi-agent systems.
- Tau-bench: repeated tool-agent-user interaction benchmark and pass^k
  motivation.
- Causal Agent Replay, arXiv 2606.08275: counterfactual replay/localization of
  agent failures.
- Security of Long-Term Memory in LLM Agents, arXiv 2604.16548: long-term
  memory security and attack/failure surfaces.

## Review Questions

Answer with a source-grounded operational assessment, not a generic roadmap.

1. Are Persona Dream's active PCTOM-R research goals being met by the current
   local evidence? Separate implemented behavior, partially proven behavior,
   missing proof, and aspirational behavior.
2. What is outstanding or brittle in the current implementation and evidence
   chain?
3. What next concrete steps would keep this project cutting-edge research,
   given the external research seeds above?
4. Should the next engineering action prioritize retry/resume machinery for the
   live Tau 502 failures, planning-policy/corpus design to produce measurable
   CD benefit, or a different gate?
5. What should explicitly not be done next?

Please include:

- a numbered source-derived step model;
- a compact status classification labeled IMPLEMENTED, PARTIALLY_PROVEN,
  MISSING, and ASPIRATIONAL;
- a prioritized next-step list with stop conditions and artifact names;
- a clear statement of whether the current local evidence supports the main
  scientific claim. Treat your review as advisory only; local receipts remain
  the proof source.
