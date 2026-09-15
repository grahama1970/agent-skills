**Model-origin advisory review—not human-authored rationale.** I reviewed `INLINE_1`. Its corpus verification claims are supplied evidence; I have not independently inspected the underlying transcripts, commits, receipts, or executable Pydantic definitions.

## 1. Verdict: suitable for observational mining, not yet for automatic success/failure supervision

**Proceed with the mining pilot, but block automatic training export under the current label rules.** The design can produce useful records of integration, evaluation, user feedback, and observable behavior. It does not yet establish that a successful artifact came from a correct reasoning process—or that an unsuccessful integration decision identifies incorrect reasoning.

The distinction is central to the research. **ProcessBench** evaluates expert-annotated error locations, not merely final-answer correctness. The associated PRM development study finds that correct answers can accompany flawed processes and that outcome-oriented evaluation can overstate process-verification quality. Your corresponding failure would be promoting “this patch landed” into “the preceding reasoning was good.” citeturn517330view0turn517330view1

**Retain the boundaries already adopted:** satisfaction separate from correctness; unverified by default; taxonomy entries treated as priors; deterministic aggregation; model-origin provenance; and historical durations excluded from live telemetry. Those are sound design choices. The problems are in promotion and attribution, not the overall direction.

Separate four supervision targets:

| Target | What can support it | What cannot establish it |
|---|---|---|
| Artifact acceptance | Attributable contribution incorporated into an identified repository state | Timestamp proximity or shared filenames |
| Task correctness | Requirement-scoped, trustworthy evaluation of the exact artifact | Acceptance, satisfaction, or a `real_world` fixture tag |
| Step validity | An adjudicated decision given its available history, observations, and constraints | The eventual episode outcome |
| Preference | Comparable alternatives under a stated preference dimension | A correction appearing after an answer |

**The highest-risk sentence in the bundle is “usable for solver SFT on landed traces.”** Replace it with: *landed artifacts are candidates for task-specific training eligibility checks*. A validated final artifact might support final-answer/code SFT without validating every intermediate step. Conversely, training on an entire successful transcript can teach its abandoned errors, unsupported claims, and unnecessary actions.

Also define “reasoning trace” as **observable transcript content**, with channel and completeness metadata—not verified access to the model’s actual internal reasoning. Empirical work shows that visible reasoning can omit factors influencing an answer. That limits causal claims drawn from prose alone. citeturn899889view5

## 2. Label-validity holes and concrete fixes

### The ±15-minute git join is candidate retrieval, not attribution

The proposed window can miss delayed commits and assign another worker’s contemporaneous change to the trace. “Last activity” is particularly unstable when sessions contain reviews, resumed work, or unrelated later turns.

**Recommended fix:** time proximity may generate candidates, but never qualify them. Record the task/attempt identifier, repository identity, worktree, base commit/tree, trace-produced patch or output digest, and the eventual integration relationship. Require content-level evidence that the contribution survived into the target state.

For squash, rebase, or cherry-pick histories, use patch equivalence as supporting evidence, then inspect the actual retained changes. Git’s stable patch IDs ignore whitespace, so they are not byte-exact artifact identity or sufficient authorship proof. citeturn899889view2

Keep at least three attribution states: `confirmed`, `ambiguous`, and `unsupported`. Preserve competing candidates rather than choosing whichever is nearest in time. **Shared paths plus nearby timestamps must remain unverified.**

### The analysis unit needs task episodes and contribution boundaries

A session is not necessarily one task; a turn is not necessarily one attempt. A single commit can combine several agents’ work, while one task can span several sessions and commits.

Your browser-review corpus makes this especially important: a review can influence a later patch without having authored it. Copying that review into a CLI session can also create two records of the same underlying contribution.

**Recommended fix:** introduce `task_id`, `episode_id`, `attempt_id`, `parent_attempt_ids`, and explicit roles such as `author`, `reviewer`, `research_assistant`, and `human_intervention`. Attribute outcomes to artifacts and episodes first. Connect individual steps through separately adjudicated contribution assertions.

Do not equate “appeared in the successful episode” with “caused success.” Recent trajectory-attribution research explicitly separates target behavior, attributed source components, and intervening chains; that is a useful structural precedent, not proof that automated causal attribution is solved. citeturn517330academia28

### `rejected`, `reverted`, and `landed` are not mutually exclusive correctness classes

The bundle correctly acknowledges that rejection is not wrongness, but the proposed labels still invite that interpretation. Closed tickets may be duplicates, out of scope, superseded, or completed elsewhere. Reverts can reflect compatibility, scheduling, or product decisions rather than a faulty original solution.

**Recommended fix:** represent dated events and reasons instead of one terminal verdict:

`integrated → evaluation_passed → reverted`, each with its own evidence and scope.

Keep `decision_reason`, `correctness_assessment`, `policy_assessment`, and `observed_at` separate. Partial reverts require hunk/artifact-level attribution rather than declaring the entire episode wrong.

“No observed revert” must include an observation horizon. Recent traces have less opportunity to accumulate negative evidence. Store `observed_through` and censoring status; do not count immature observations as durable successes.

The nightly job must therefore revisit **existing affected outcomes**, not only new transcripts.

### `landed_and_proven` needs a substantially stronger receipt contract

A fixture *containing* a `real_world` case does not establish that the case ran, exercised the relevant behavior, used trustworthy assertions, or tested the artifact that landed.

**Recommended fix:** qualify evidence using the exact tested tree—including relevant dirty/untracked content—plus evaluator version, environment digest, executed case IDs, skipped cases, assertions, requirement mappings, and results. Separate evaluator ownership from artifact authorship. Preserve the already-adopted prohibition on self-authored tests being sufficient proof.

For a repair, require a relevant fail-before/pass-after check when applicable, plus protected regression checks. For a new feature, require independently specified acceptance behavior rather than forcing an artificial fail-before condition.

Prefer a scoped name such as `acceptance_checks_passed` over `proven`. A receipt should identify **what was tested**, not imply global correctness.

### Matching by repository and blocker type is insufficient

Those controls help, but leave initial state, model/harness version, available tools, permission constraints, budget, prior attempts, human assistance, and task complexity uncontrolled.

**Recommended fix:** capture pre-attempt context and compare closely matched task states where possible. Keep later corrections and extra evidence visible as treatment differences rather than pretending the attempts received equal information.

Do not automatically “control for” total tool calls or elapsed time when estimating a behavioral effect: those may be consequences of the behavior you are studying. Report associations first; reserve causal language for stronger intervention or replay evidence.

Finally, your mixed 200-trace sample cannot provide an unweighted corpus-wide success rate. The random cohort and outcome-selected paired cohort serve different purposes. Retain sampling strata and inclusion probabilities; publish their results separately.

### Git-based eligibility creates a coding-only selection bias

Research, review, clarification, safe refusal, and permission-respecting stops may succeed without producing commits.

**Recommended fix:** keep the shared `/intent` vocabulary, but add a mining-specific `task_kind` and `outcome_evidence_kind`. Use `not_applicable` for git attribution outside artifact-producing work. Do not silently teach that “no commit” means low-quality work.

## 3. Feature taxonomy: useful audit hypotheses, but not yet process supervision

The main gap is **step-local semantic validity**, not a shortage of workflow slogans.

PRMBench examines missing prerequisites, contradictions, domain misuse, circularity, misleading confidence, and consistency across multiple valid solutions. Those are substantially different from counting recognizable workflow habits. citeturn557205view0turn557205view8

More directly relevant, **ToolPRMBench, published in ACL Findings 2026**, constructs cases containing an interaction history, a preferred action, a plausible incorrect alternative, and tool metadata. It combines local deviations with full-rollout failures. That is a stronger template for this corpus than assigning an entire trace a favorable or unfavorable behavioral identity. citeturn734806view0

**Add measurements in these areas:**

- **Action validity and evidence use:** tool suitability, argument correctness, prerequisites, target identity, source authority/freshness, and whether subsequent claims follow from observations.
- **State and constraint preservation:** maintaining the requested goal, distinguishing test from production, honoring permissions, recognizing unavailable tools, and preserving previously established invariants.
- **Error evolution and recovery:** first supported error, propagation through dependent steps, detection, correction, and whether the corrected state was verified. Do not mark every step after an initial error incorrect; research on reflective PRMs explicitly addresses error cessation and valid recovery. citeturn517330view2
- **Diagnostic value and uncertainty:** whether a probe distinguishes competing explanations; whether new evidence changes the approach; whether confidence exceeds evidence; whether abstention or escalation is appropriate.

Planning, tool unavailability, recovery, and safe refusal also appear as distinct evaluation families in the 2026 Plan-RewardBench work. Your taxonomy currently underrepresents these legitimate alternatives to uninterrupted execution. citeturn734806view5

### Treatment of the ten existing features

| Existing feature | Recommended treatment |
|---|---|
| `read-receipt-first` | Keep conditionally. Measure whether relevant, sufficiently current evidence was consulted **before the dependent decision**, not whether reading happened first in every task. |
| `verified-read-back` | Keep, but bind it to the correct artifact/object, version, expected property, observation, and verifier. “Read something afterward” is insufficient. |
| `re-ran-previously-working-path` | Keep as regression-check coverage when applicable. It is neither necessary nor sufficient for every task. |
| `root-cause-not-symptom` | Too strong as a cheap-model binary. Prefer `supported_failure_mechanism`, with evidence, alternatives considered, and unresolved attribution. |
| `escalated-after-two-focused-failures` | The fixed threshold is likely local-policy noise. Measure escalation appropriateness under the actual budget, permissions, and escalation policy. |
| `retry-same-input` | Keep only as a raw observation. Identical arguments can be legitimate polling, flaky-test reruns, or verification after external state changes. |
| `stopped-mid-goal-for-status` | Distinguish voluntary premature termination from a requested update, handoff, context limit, timeout, or permission boundary. A status message is not necessarily a stop. |
| `routed-around-blocker` | Split authorized equivalent fallback from bypassing a required constraint. The current feature can punish resilience and reward stubbornness. |
| `patched-from-error-string` | Likely noisy as written. Some errors fully identify a mechanical fix. Measure whether the evidence was sufficient for the change, not where diagnosis began. |
| `claimed-unverified` | Keep as a claim-evidence relation. Distinguish missing visible support, incomplete logs, invalid evidence, and actually contradicted claims. |

**The exact digest rule contains a direct contradiction:** running the same read command before and after a write may be your desired read-back behavior, yet “identical digest twice” classifies it as retry failure. Rename the mechanical output to `repeated_call_signature`; leave its appropriateness to a separate contextual assessment.

For each feature, retain `present`, `absent`, `unknown`, and `not_applicable`. Otherwise, missing instrumentation will masquerade as bad behavior or good behavior.

## 4. Schema, graph, and scoring-architecture risks

The supplied “Pydantic schemas” are field sketches, not executable definitions. The following are contract requirements and conditional implementation risks—not claims that particular validators are already broken.

### Strengthen the storage contract

| Area | Required delta |
|---|---|
| Trace identity | Separate stable logical identity from immutable source revision. Record source session/event identifiers, boundaries, parser version, and content hashes. Do not derive identity solely from a mutable path, summary, or growing session-file hash. |
| Analysis-unit references | Explicitly reference the request, answer, response, reasoning/tool spans, context snapshot, and branch/continuation relationships. `turn_index` alone is inadequate across re-parsing and branched sessions. |
| Tool calls | Add call/result IDs, tool/schema version, working context, observation references, and missingness. Distinguish successful invocation from successful task effect. Unknown duration is not zero. |
| Feature observations | Replace loose `features{}` plus a parallel provenance map with typed observations containing definition version, value, scope, evidence references, coverage, scorer run, and adjudication state. |
| Outcome evidence | Store versioned assertions with attribution strength, artifact bindings, evidence authority, observation horizon, and explicit unresolved alternatives. |
| Feedback | Separate speech act, satisfaction, task continuity, and targeted answer IDs. A frustrated correction can occupy several categories simultaneously. |
| Origin and eligibility | Add per-component authorship/source provenance, privacy status, permitted training uses, and deny-by-default export eligibility. Tags are not authorization controls. |
| Derived text | Record summary method, source revisions, information cutoff, and whether outcomes were visible during generation. |

There are two concrete Pydantic implementation traps to test. A field literally named `_key` is treated as a private attribute rather than a normal validated field; use an ordinary Python field with an `_key` serialization alias. Also, `model_construct()` bypasses validation, so it must not become a performance shortcut on the write/export boundary. citeturn373989view6turn373989view7

Use strict validation, forbidden extras, bounded enums, finite numeric values, and cross-field invariants. Pydantic otherwise permits useful but potentially inappropriate coercions. None of these settings can establish that an external receipt is genuine or refers to the tested artifact; that requires independent resolution and verification. citeturn899889view1

### Make graph assertions more precise

`trace→repo`, `trace→model`, and `trace→tool` are useful descriptive relationships. They should not imply authorship, causality, or correctness.

For the consequential relationships, introduce evidence-bearing assertion nodes or equivalently rich typed edges:

- `attempt → contributed_to → artifact_revision`
- `outcome_assertion → supported_by → evaluation_receipt`
- `feature_observation → evidenced_by → source_span`
- `feedback_event → targets → answer`
- `revised_answer → responds_to → feedback_event`

Keep `corrected_by` as an observational relationship until a separate pair-construction gate establishes a valid preference example. A human correction, model rewrite, and later assistant answer are different node types.

Every consequential edge should carry relation type, assertion origin, evidence, revision, and status. Prevent dangling endpoints and unvalidated relation/type combinations. **Trust must not propagate merely because a path exists in the graph.**

Use append-only assertion revisions with a current projection. An upsert that replaces yesterday’s `landed` with today’s `reverted` destroys the information needed to reconstruct earlier exports. Publish graph/vector updates through a versioned commit boundary or outbox so incomplete synchronization cannot expose stale eligibility.

### Quote verification is not judgment verification

Move literal quote checks into deterministic code. Paying a stronger model to determine whether a substring occurs is unnecessary and introduces avoidable variability.

More importantly, an exact quote does not establish that it supports the assigned feature. “I found the root cause” is an exact quote, not root-cause evidence.

Absence claims need a different evidence contract: **a quote cannot prove that no read-back occurred**. Require an inspected range, completeness/coverage status, and applicable search scope. Truncated or budget-exhausted inspection must produce `unknown`, not `absent`.

The stronger reducer can assess contextual support, but “stronger model, low effort” is not a calibrated adjudicator. Use independent human reference labels for error estimation and audit negative/omitted findings as well as child-reported positives.

At the initial 200-trace scale, auditing 10% means roughly 20 traces. Even with **zero errors in 20 independent gold-audited decisions**, the exact one-sided 95% upper bound on the error rate is about **13.9%**, calculated as \(1-0.05^{1/20}\). Model-on-model agreement provides less assurance than that calculation assumes.

Finally, give scoring children redacted, read-only, outcome-blind source views with restricted navigation. Historical transcript instructions must remain data. Exhausted budgets, malformed output, and unread context are processing failures—not reasoning-quality labels.

## 5. Silent contamination risks and guards

### Related examples leaking across splits

One task may recur as a CLI trace, browser review, correction, commit discussion, retrieved memory, and revised attempt. Random row splitting would allow nearly identical evidence and answers into both training and evaluation.

**Guard:** form split groups from task/issue lineage, shared prefixes, copied reviews, artifact ancestry, and exact/near-duplicate content. Split before retrieval-assisted annotation or augmentation. ToolPRMBench likewise keeps examples derived from the same instruction on one side of its train/test split. citeturn557205view7

Do **not** compute split groups from every graph edge: shared model/tool/repository hubs could connect almost the entire corpus. Use designated lineage and duplication relationships.

Maintain a later untouched temporal holdout and, where feasible, repository/model-family holdouts. If a newly discovered duplicate connects existing splits, invalidate affected evaluation records.

### Outcome information entering the input

A summary saying “successfully fixed,” an outcome edge, a commit message, a later review, or a `landed` tag can reveal the answer to the training target.

**Guard:** define separate views for retrospective analysis, decision-time step scoring, and outcome verification. For a step scorer, enforce the information cutoff at that step. For an artifact verifier, allow the evidence its deployment contract genuinely provides.

“Computable from the trace” is insufficient when the trace contains later self-reports or copied evaluator feedback. Exclude such leakage according to the intended task, not through an indiscriminate ban on all evaluation evidence.

### Scorer imitation mistaken for correctness learning

A verifier trained on one model’s judgments may learn that model’s stylistic preferences or familiar failure narratives. A stronger reducer agreeing with it does not establish independence.

**Guard:** retain judge identity, rubric/prompt version, generator identity, and adjudication source. Label synthetic judgments as synthetic. Evaluate against blinded human labels and externally checked outcomes, with disagreement and abstention reported separately.

This may still produce useful **judge distillation** data. It must not be described as independently validated correctness supervision.

### Passing traces containing reward hacks

A passing artifact can result from weakened assertions, changed expectations, bypassed checks, or evaluation-sensitive modifications. This is not hypothetical as a training mechanism: Countdown-Code’s 2026 experiments found that a small fraction of reward-hacking examples in distillation SFT could seed behavior that resurfaced during subsequent RL. The reported 1% finding is specific to that experimental setting, not a universal threshold. citeturn734806view3

**Guard:** inspect changes to evaluation-relevant components, preserve protected checks, verify requirement-to-assertion bindings, and evaluate the exact artifact with an independent oracle where available. Flagging test edits should trigger review, not automatically condemn legitimate test maintenance.

Keep suspicious passing traces in a separately governed diagnostic corpus, not positive solver demonstrations.

### Workflow and prose shortcuts becoming the reward

A model could learn to emit “verified,” escalate on the second failure, or perform redundant reads because those correlate with positive labels.

**Guard:** build matched challenge cases: confident wrong versus tentative correct; concise correct versus ritual-heavy wrong; legitimate repeated calls versus unproductive retries; safe refusal versus unsafe apparent completion.

Recent PRM robustness work reports reward improvements disconnected from correctness, while 2026 rubric-RL research distinguishes evaluator failures from omissions in the rubric itself. A stronger judge does not fix an underspecified objective. citeturn734806view4turn517330academia30

### Authorship, privacy, and training-loss contamination

A `user` message may contain pasted browser-model prose. Human approval of that prose does not make it human-authored.

**Guard:** preserve transport role separately from authorship and derivation. Keep every mined derivative outside the QRA human-authored rationale route. Apply privacy and permitted-use gates **before external scoring**, not only before memory writes; cover quotes, summaries, vectors, and exports.

For solver SFT, use target-aware loss masks. Failed attempts can be context for learning a valid repair, but blindly applying assistant-token loss across the whole transcript also teaches the failed actions. For critique training, the flawed response belongs in the input—not accidentally in the desired-output target.

## 6. Correction-derived preference pairs: usable after reconstruction and validation

**Do not implement `rejected = agent answer; chosen = user correction` as the default.** Most corrections are instructions, evidence, or partial diagnoses—not interchangeable assistant completions.

For example, “You edited the wrong repository; inspect the other checkout” is useful feedback but not a preferred answer to the original engineering request. Training it as the chosen completion teaches a role mismatch.

Current interaction-learning research supports using follow-ups, but through more careful mechanisms. RLHI constructs user-guided rewrites, while the 2026 *Aligning Language Models from User Interactions* work derives hindsight-conditioned learning signals. Neither establishes that raw user follow-ups are automatically preferred assistant answers. citeturn899889view4turn734806view1

**Recommended eligibility conditions:**

1. **Target resolution:** establish which answer or step the correction addresses. Do not assume adjacency, especially across interrupted or branched sessions.
2. **Comparable outputs:** both candidates must be valid output objects for the same decision—two assistant answers, patches, or tool actions—not an answer versus a request to revise it.
3. **Context accounting:** distinguish an original-prompt improvement from a repair that uses newly supplied facts, permissions, files, or changed requirements.
4. **Independent preference basis:** validate the preferred candidate for the stated dimension: correctness, instruction-following, safety, or personal style. Record ties, trade-offs, and unknowns.
5. **Preserved derivation:** store the original feedback, reconstruction method, generator, verification evidence, and split lineage.

When feedback supplies missing information, create a **feedback-conditioned repair example**. Do not retrospectively mark the original answer wrong for lacking unavailable information. Hindsight-distilled targets can still be useful, but should be explicitly identified as privileged-information supervision rather than fair same-context comparisons.

A raw correction is directly usable as a chosen answer only in the narrow case where it actually supplies a complete, valid alternative response under unchanged conditions. Most records will require reconstruction.

For step-level pairs, borrow the same-history comparison structure from tool-use PRM research, but allow several valid actions. Different from the observed successful action is not equivalent to wrong. citeturn557205view7

## 7. Ranked next five implementation steps—and what not to build yet

### 1. Patch label promotion and export eligibility first

Introduce separate acceptance, correctness, process, preference, and integrity assertions. Default `eligible_for` to empty. Preserve the current labels as observational classifications, not training permissions.

**Acceptance gate:** deterministic counterexamples reject timestamp-only attribution, `landed`-only solver export, skipped `real_world` cases, mismatched evaluation trees, closure-as-incorrectness, and automatic raw-correction preference pairs.

This is the first patch because it prevents every later component from confidently exporting the wrong target.

### 2. Build the 200-record evidence and lineage slice

Implement canonical task/attempt boundaries, source-span hashing, typed event references, artifact attribution, feedback targeting, and append-only outcome revisions. Include delayed/squashed commits, concurrent workers, copied reviews, truncated logs, and non-code tasks.

**Acceptance gate:** repeated ingestion preserves logical identity; changed source revisions are detected; ambiguous joins remain ambiguous; later outcome changes preserve earlier assertions and identify affected exports.

Resolve the cron/summary contradiction here: a no-model nightly pass may generate a deterministic, sanitized retrieval description from factual fields or excerpts. Record that method explicitly; do not silently introduce model summarization.

### 3. Create a blinded human reference set before judging model accuracy

Retain the proposed 100 random records plus 100 matched records—**50 pairs**—but keep the sampling arms distinct. Human-review every pilot outcome assertion proposed for supervision. Independently double-review a stratified subset and adjudicate disagreements.

Use structured decisions and evidence selection; this does not require importing mined prose into the human-rationale workflow.

**Acceptance gate:** report attribution precision, eligibility precision, unresolved cases, agreement, and coverage by source/task type. Do not resolve disagreements by defaulting to the stronger model.

### 4. Run the fanout/reducer pilot as measurement validation

Implement contextual repeated-call features, claim-evidence relations, step validity, and recovery annotations. Use deterministic span checks, outcome-blind scorer views, and explicit abstention.

**Acceptance gate:** publish per-feature precision/recall, missingness, support counts, and human-reference disagreement. Include simple baselines using length, source, and task category to expose confounding.

The feature-outcome table should report exploratory associations with clustered uncertainty—not claim that 200 records confirm or refute all ten priors. For reward-hack detection specifically, TRACE’s 2026 results suggest testing matched contrastive review as well as isolated classification. citeturn734806view2

### 5. Build versioned, target-specific exports and an untouched evaluation suite

Produce separate candidate datasets for artifact SFT, step verification, critiques, and feedback-conditioned repair. Each export should have source/label revisions, eligibility reasons, lineage split assignments, origin restrictions, and hashes.

**Acceptance gate:** deny cross-split retrieval; reject stale or unsupported labels; preserve model-origin provenance; pass the leakage and shortcut challenge cases; and reproduce the export exactly from its manifest.

Only then enable unattended ingestion/scoring at larger scale, with refreshes for changed historical outcomes. Keep automatic training promotion disabled until its audited error characteristics justify a policy.

**Do not build yet:** a universal scalar “reasoning quality” reward; automatic correction-to-DPO conversion; bulk solver SFT over landed sessions; causal root-cause edges inferred from prose; pooled model leaderboards; or a reward-optimization loop using these features.

**The first milestone should establish that the system measures the labels it claims to measure—not that recognizable good-looking behavior predicts getting a commit merged.**
