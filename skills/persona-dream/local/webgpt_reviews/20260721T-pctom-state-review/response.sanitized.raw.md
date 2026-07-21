Operational assessment

The PCTOM-R research program is on track as an experimental reliability and causal-evaluation platform, but the main scientific efficacy claim is not currently supported.

The supplied evidence supports that Persona Dream can run prospective ToM conditions, seal and score outputs, select actions, preserve revisions, recall them from Memory, and fail closed under several fault classes. It does not show that counterfactual dreaming improves either calibrated ToM prediction or planning. On the reported planning outcomes, CD is tied, worse than the strongest baseline, or associated with the only observed harm.

The strongest scientifically defensible conclusion today is:

The current PCTOM-R implementation can test the hypothesis under substantial provenance and reliability controls, but the tested CD treatment has not demonstrated benefit and may be ineffective or harmful under the current corpus, belief-to-action policy, or utility function.

1. Source-derived PCTOM-R step model

Provenance-bound episode formation.
A trial should begin with an immutable chain from recall query to retrieved raw source, normalized social residue, episode identity, and treatment assignment. Current memory research emphasizes incremental write–manage–read behavior rather than static recall, while long-term-memory security work argues that provenance, versioning, retention policy, and rollback must be established at storage time rather than added at retrieval time. 
arXiv
+2
arXiv
+2

Partner-specific prospective state.
The agent should predict a particular partner’s future beliefs, intentions, or actions before observing the outcome. This is more demanding than answering static story questions: recent ToM criticism distinguishes literal prediction from functional ToM, where predictions must rationally change subsequent behavior and adapt to a partner across interaction history. 
arXiv
+2
arXiv
+2

Sealed prediction commitment.
Each condition must commit a full probability distribution, uncertainty state, source lineage and admissible information set before reveal. The commitment should be immutable and hash-bound; after outcome reveal, no regeneration or silent repair can count as the original prediction.

Controlled counterfactual intervention.
M, R, D and CD must represent explicit, versioned interventions rather than prompt labels. Counterfactual dreaming should alter a declared causal variable—such as anticipated partner policy, hidden information or future branch—not merely produce more text. Causal Agent Replay supports intervention-based attribution rather than correlational inspection, while planning research indicates that explicit future trajectories and value propagation are needed to distinguish planning from locally plausible reasoning. 
arXiv
+1

Outcome reveal and proper scoring.
Reveal must occur only after commitment. Predictions should be evaluated with deterministic proper scores such as log loss or Brier score, plus calibration slope/intercept and uncertainty coverage. Accuracy alone is insufficient because PCTOM-R claims calibrated prospective belief.

Belief-to-action translation.
The same committed beliefs must drive a predeclared action policy and utility function. This is the functional-ToM step: a better mental-state model must result in a better action where the scenario offers an action-relevant distinction. Strong literal ToM without rational behavioral adaptation does not establish functional ToM. 
arXiv
+1

Non-destructive revision and incremental recall.
After scoring, the agent may create a versioned revision, but it must preserve the original commitment and literal/synthetic distinction. Later trials should test whether revisions are selectively retrieved and appropriately used across multiple interactions, matching the incremental, test-time-learning and selective-forgetting competencies emphasized in memory-agent evaluation. 
arXiv
+1

Reliability surface and causal localization.
Repeat the complete trial across random seeds, semantically equivalent perturbations and controlled fault intensities. ReliabilityBench formalizes this as R(k,ϵ,λ), with repeated-execution consistency, semantic perturbation and fault intensity; its fault set includes timeouts, rate limits, partial responses and schema drift. MAS-FIRE further shows that semantic and coordination faults can propagate without runtime exceptions, and that topology affects recovery. Causal replay should then localize whether failure came from recall, treatment construction, prediction, action selection, scoring, revision or persistence. 
arXiv
+2
arXiv
+2

2. Compact status classification
Classification	Current PCTOM-R state
IMPLEMENTED	Typed protocol and artifact schemas; M/R/D/CD condition execution; prediction commitments; outcome reveal and deterministic scoring machinery; action selection; belief revision; local and live Memory revision recall; causal replay artifact generation; fault-injection trials; service-boundary idempotency and duplicate-submission suppression.
PARTIALLY_PROVEN	End-to-end prospective sealing; complete provenance from recall query through dream branch and prediction; calibration across held-out partners; live retry/resume through the actual Tau execution path; Memory security beyond exact reread; causal attribution of planning failure; generalization beyond four scenario families.
MISSING	Evidence that CD improves predictive score or calibration; evidence that CD reduces planning regret against the strongest baseline; proof that the action policy is sensitive to genuinely better beliefs; a powered, preregistered, family-held-out effect estimate; naturalistic multi-turn partner adaptation; a full R(k,ϵ,λ) surface.
ASPIRATIONAL	General prospective ToM improvement across models and partner types; robust long-horizon adaptation; secure and selectively forgetting long-term memory; automatic causal localization across arbitrary Tau failures; multimodal dreaming that adds scientific value beyond the text-first protocol.
3. Assessment of the current evidence chain
What is strongly supported

According to the supplied bundle, the project has meaningful operational evidence for:

running all four conditions through live Tau;

preserving prior and posterior revisions;

distinguishing synthetic from literal memory;

exact reread of local and live Memory artifacts;

avoiding canonical, identity and source-memory writes;

blocking unknown-state continuation;

suppressing duplicate service-job promotion;

producing replayable artifacts after faults;

failing closed when the balanced live run loses required cells to HTTP 502.

That is substantial progress. The project is no longer merely a schema proposal.

What is only partially supported

Prospective sealing is not yet publication-grade. The bundle reports commitments, reveals and strict inference, but Gate 0 still lacks one complete hash chain joining:

recall query
→ accepted raw source ID and content hash
→ normalized residue hash
→ condition assignment
→ dream/counterfactual branch hash
→ prediction commitment hash
→ sealed timestamp
→ outcome reveal hash
→ score
→ action decision
→ revision

Without that chain, leakage or accidental post-reveal reuse remains difficult to exclude conclusively.

Reliability is demonstrated in slices, not as one end-to-end system property. The local HTTP retry proof is good idempotency evidence, but it consumed existing live Tau artifacts and did not demonstrate the same retry/resume machinery recovering the two failed live R/D calls. The fault-injection surface also explicitly excludes service-boundary retry and fresh sealed live Tau execution.

Memory recall is proven more strongly than memory use. Exact reread and condition-specific retrieval are necessary, but the scientific question is whether the recalled revision changes a later prediction or action in the correct direction. Incremental memory benchmarks distinguish retrieval from test-time learning and appropriate behavioral adaptation. 
arXiv

What the negative planning results imply

The reported results do not merely lack significance:

CD was worse by 0.1375 regret on the strict balanced slice.

D was the strongest reported baseline.

The full64 distributional intervention produced all ties.

The confidence-gated intervention produced 63 ties and one harm.

Fresh variants 19–20 were incomplete because of 502s, so they add reliability evidence but no efficacy evidence.

This pattern suggests at least one of four possibilities:

CD does not improve the underlying ToM distribution.

CD improves beliefs, but the action policy cannot use the improvement.

The scenarios rarely contain cases where different beliefs imply different optimal actions.

The regret or utility function is too coarse or saturated to detect a change.

Running more CD trials before distinguishing these explanations would increase cost without resolving the causal bottleneck.

There is also a statistical independence risk: 64 rows distributed across only four scenario families do not automatically constitute 64 independent experimental units. The effect analysis should cluster or bootstrap at the episode/family level and include held-out families.

4. Which gate should come next?
Priority decision

Prioritize a different gate: planning identifiability and causal lineage.

Do not first build a broader retry service, and do not redesign the corpus to make CD produce a positive result.

The two HTTP 502 failures should eventually be resumed, but they are not the principal scientific blocker: multiple completed slices already show no CD planning benefit. Repairing those two cells may complete a table, but it cannot establish that the current experiment is capable of detecting a belief-driven planning benefit.

The next gate should answer:

If the action selector is given demonstrably better prospective beliefs, does it choose better actions under the current scenarios and utility function?

If the answer is no, further CD generation is uninterpretable as a planning experiment.

5. Prioritized next steps, artifacts and stop conditions
1. Close the PCTOM-R causal-identifiability gate

Use existing sealed strict120/full64 roots. Do not make new provider calls initially.

Create:

pctom_causal_identifiability_manifest.json
pctom_end_to_end_lineage_receipt.json
pctom_oracle_policy_sensitivity.jsonl
pctom_oracle_policy_sensitivity_receipt.json

For each selected episode:

reconstruct the complete lineage chain described above;

keep the action selector, action set and utility function fixed;

evaluate three belief inputs:

the actually committed distribution;

an oracle distribution aligned with the hidden outcome;

an anti-oracle distribution that assigns probability mass away from it;

run all three before exposing their comparative scores to the policy;

record action, expected utility and realized regret.

Pre-register these acceptance conditions:

lineage completeness = 100%
post-reveal inputs influencing commitment = 0
oracle-vs-observed mean regret CI upper bound < 0
anti-oracle-vs-oracle mean regret CI lower bound > 0
action-switch count > 0 on episodes whose Bayes-optimal action differs

Stop condition: if the lineage is incomplete, repair provenance and rerun no efficacy experiment. If oracle beliefs do not improve actions, stop CD experimentation and repair the action policy, utility model or scenario identifiability.

This directly follows planning research that separates future-aware decision policies from stepwise reasoning, and causal-replay research that tests causes by intervention rather than observation. 
arXiv
+1

2. Resume only the failed live Tau cells

Proceed only after the identifiability gate passes.

Create:

pctom_live_tau_exact_resume_manifest.json
pctom_live_tau_exact_resume_receipt.json
pctom_balanced_variants_19_20_completion_receipt.json

Resume only the two failed R/D calls using immutable:

trial_id
condition
scenario_family
prompt hash
source-lineage root
prediction-commitment target
model selector
output schema

Do not rerun seven accepted rows. A completed accepted receipt must suppress a provider call.

Stop condition: stop on request-hash drift, commitment-target drift, unknown execution state, duplicate active prediction, duplicate action promotion or exhausted retry budget. Record the run as blocked rather than silently regenerating the trial.

3. Determine whether the corpus has treatment-sensitive decisions

If the policy passes oracle sensitivity but actual CD remains tied, test the scenario design rather than tuning CD prompts.

Create:

pctom_treatment_sensitivity_manifest.json
pctom_decision_margin_analysis.jsonl
pctom_treatment_sensitivity_receipt.json

For every scenario, compute:

whether two plausible partner-belief distributions imply different optimal actions;

the utility margin between those actions;

whether the hidden outcome can alter the ranking;

whether the scenario template leaks the optimal action;

whether the same partner appears over multiple turns;

whether the scenario belongs to a held-out partner/family split.

Stop condition: stop corpus scaling if most cases have one dominant action independent of belief state, zero utility margin, template leakage or no repeated-partner adaptation. Replace those cases before additional live inference.

Functional-ToM evaluation should test adaptation to partners, not only isolated literal predictions. 
arXiv

4. Run a preregistered held-out efficacy study

Create:

pctom_r_preregistration.json
pctom_partner_holdout_split.json
pctom_effect_estimates.json
pctom_effect_estimate_receipt.json

Use co-primary outcomes:

prediction:
  log score
  Brier score
  calibration slope/intercept

planning:
  realized action regret
  expected utility under committed belief

Compare CD first against the strongest observed baseline, currently D, rather than only against a weak baseline.

Analysis must:

pair conditions within episode;

cluster uncertainty by scenario family and partner;

report family-held-out effects;

report effect sizes and confidence intervals, not only a Boolean benefit field;

distinguish superiority, equivalence, harm and insufficient power;

preserve negative results.

Stop condition: if confidence remains too wide for the preregistered minimum effect, conclude INSUFFICIENT_POWER; do not reinterpret it as benefit. If CD is significantly worse, report the harm and move to causal ablation.

5. Decompose the CD treatment

Only after the first interpretable efficacy study.

Create:

pctom_cd_factorial_contract.json
pctom_cd_factorial_trials.jsonl
pctom_cd_factorial_effects.json

Separate at least:

memory recall present/absent
literal residue present/absent
counterfactual generation present/absent
future-trajectory evaluation present/absent
belief revision available/unavailable

The purpose is to identify which component changes prediction and action—not to search combinations until one wins.

Stop condition: reject any factorial cell that changes multiple undeclared variables, uses post-outcome information or modifies the scoring/action policy.

6. Build the full reliability surface after identifiability

Create:

pctom_reliability_surface_contract.json
pctom_reliability_trials.jsonl
pctom_reliability_surface_R_k_epsilon_lambda.json
pctom_reliability_surface_receipt.json

Vary:

k: repeated executions;

ϵ: paraphrase, distractor, partner-style and source-order perturbation;

λ: timeout, 502, rate limit, partial response, schema drift, stale receipt, duplicate submit, Memory unavailability, poisoned revision and rollback failure.

Use end-state and artifact equivalence, not textual answer similarity. Both ReliabilityBench and τ-bench motivate repeated-run reliability rather than single successful demonstrations; MAS-FIRE further supports process-level fault localization because silent semantic failures may propagate even when execution succeeds. 
arXiv
+2
arXiv
+2

Stop condition: any CONTINUED_WITH_UNKNOWN_STATE, duplicate promotion, canonical-memory contamination or unversioned revision blocks the surface.

6. What should explicitly not be done next

Do not:

generate video or provider-heavy dream media;

polish UX Lab dashboards;

evaluate subjective dream vividness or creativity;

scale provider calls before the action policy passes oracle sensitivity;

modify prompts or scenarios after seeing outcomes without a new versioned preregistration;

tune the corpus specifically to force a CD win;

count 64 rows as 64 independent scientific units when they derive from four families;

rerun already accepted cells while repairing the two 502 failures;

merge synthetic revisions into canonical, identity or source memory;

replace the current fail-closed behavior with permissive partial continuation;

build a permanent retry orchestrator before proving the current planning experiment is identifiable;

claim general ToM from story-style or binary prediction performance alone;

claim memory benefit from exact retrieval without showing correct downstream behavioral use.

7. Main scientific claim ruling

Current local evidence does not support the main claim that synthetic counterfactual dreaming improves prospective, calibrated ToM predictions and planning decisions.

It supports these narrower claims:

PCTOM-R has a substantial executable protocol and artifact surface.

Prospective condition runs, action selection, revisions and recall can be performed without destructive canonical writes.

Several fault families fail closed.

Duplicate service submissions can be detected and prevented from promotion.

The current CD planning treatment has not shown benefit on the supplied completed slices.

The existing negative results are scientifically useful. They narrow the problem from “can the pipeline run?” to “is the treatment causally effective, and can the policy measure that effectiveness?” The immediate research contribution should therefore be an identifiable, provenance-complete experiment—not another demonstration run.

This assessment is advisory. The cited papers ground the evaluation model and next gates; the supplied local receipts remain the sole proof source for Persona Dream’s actual executions.

<<<WEBGPT_DONE:20260721T163808Z:498f70b4>>>
