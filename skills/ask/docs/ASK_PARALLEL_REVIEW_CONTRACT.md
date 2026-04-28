# /ask Parallel Review Contract

## Purpose

`/ask parallel-review` is a bounded reviewer-fanout protocol for code, diff,
plan, artifact, or architecture review. It gives `/ask` Pi-subagents-style
independent judgment without turning `/ask` into a generic subagent runtime.

The lane exists for one job:

```text
resolve target -> run read-only reviewer roles -> synthesize -> verify -> emit artifacts
```

The first real adapter is deliberately just `/scillm` composition:

```text
3 reviewer JSON calls in bounded async parallel
  -> 1 judge/synthesis JSON call after all reviewers finish
  -> deterministic verifier
```

It must not become an implementation worker DAG, migration runner, or replacement
for `/code-runner` or Pi-native subagents.

## Command Shape

Targeted review requires an explicit target:

```bash
./run.sh ask "review this diff for correctness, tests, and maintainability" \
  --parallel-review \
  --review-target git:diff \
  --parallel-review-personas Brandon,Margaret,Jennifer \
  --parallel-reviewers 3 \
  --parallel-review-runner scillm \
  --review-dag hybrid
```

This runs Brandon, Margaret, and Jennifer as three independent reviewer prompts,
then runs one judge/synthesis prompt that picks the strongest review and emits a
hybrid synthesis.

## Concrete DAG Example

The DAG is intentionally small and review-specific. It is not a general workflow
engine.

User request:

```text
Create 3 parallel reviews with Brandon, Margaret, and Jennifer, then judge which
review is best and create a meaningful hybrid synthesis.
```

Normalized command:

```bash
./run.sh ask "review this runtime change" \
  --parallel-review \
  --review-target git:diff \
  --parallel-review-personas Brandon,Margaret,Jennifer \
  --parallel-reviewers 3 \
  --parallel-review-runner scillm \
  --review-dag hybrid
```

Execution DAG:

```yaml
schema_version: ask.parallel_review.v1
nodes:
  - id: target_bundle
    type: target_bundle
    depends_on: []
    writes:
      - parallel_review/target_bundle.md

  - id: Brandon
    type: scillm_call
    depends_on: [target_bundle]
    role: reviewer
    parallel_group: reviewers
    writes:
      - parallel_review/reviewer_outputs/Brandon.json

  - id: Margaret
    type: scillm_call
    depends_on: [target_bundle]
    role: reviewer
    parallel_group: reviewers
    writes:
      - parallel_review/reviewer_outputs/Margaret.json

  - id: Jennifer
    type: scillm_call
    depends_on: [target_bundle]
    role: reviewer
    parallel_group: reviewers
    writes:
      - parallel_review/reviewer_outputs/Jennifer.json

  - id: judge
    type: scillm_call
    depends_on: [Brandon, Margaret, Jennifer]
    role: judge
    writes:
      - parallel_review/judge.json

  - id: synthesis
    type: deterministic_render
    depends_on: [judge]
    writes:
      - parallel_review/synthesis.md
      - parallel_review/verdict.json

  - id: verifier
    type: deterministic_verifier
    depends_on: [synthesis]
    writes:
      - parallel_review/verifier.log
```

Operationally, this is four `/scillm` calls:

```text
call 1: Brandon reviewer     \
call 2: Margaret reviewer     > bounded async parallel
call 3: Jennifer reviewer    /
call 4: judge/synthesis      after calls 1-3 complete
```

The reviewer calls use `/scillm`'s documented non-QRA batch pattern:
`asyncio.create_task` plus `asyncio.as_completed`, bounded to a small concurrency
limit. The judge call is sequential because it depends on all reviewer outputs.

## Example Prompt Payloads

Reviewer prompt shape:

```text
Review target in read-only mode.

Question:
review this runtime change

Target:
git:diff

Reviewer role:
- name: Brandon
- role: reviewer
- focus: ["reviewer"]
- prompt: Review as Brandon. Apply the reviewer role if specified. Stay evidence-bound.

Target bundle:
<contents of parallel_review/target_bundle.md>

Return exactly one JSON object matching:
{
  "reviewer": "role/name",
  "verdict": "SAFE | SAFE_WITH_CONDITIONS | NOT_SAFE | INSUFFICIENT_EVIDENCE",
  "summary": "specific review summary",
  "files_inspected": [],
  "evidence": [],
  "findings": [
    {
      "severity": "high | medium | low",
      "title": "finding title",
      "evidence": "specific evidence",
      "impact": "why it matters",
      "fix": "exact fix",
      "verification": "test/check"
    }
  ],
  "test_gaps": [],
  "read_only_claim": true,
  "confidence": "low | medium | high"
}

Rules:
- Do not edit files.
- Memory can guide context but is not evidence.
- Findings require evidence from the target bundle.
- If evidence is insufficient, use verdict INSUFFICIENT_EVIDENCE.
```

Judge prompt shape:

```text
Judge the parallel reviewer outputs and produce a hybrid review.

Question:
review this runtime change

Target:
git:diff

DAG mode:
hybrid

Reviewer outputs:
<Brandon.json>
<Margaret.json>
<Jennifer.json>

Return JSON only. Pick the best single reviewer by evidence quality, then create
a hybrid summary that keeps only evidence-supported findings. Do not add claims
not present in the reviewer outputs.
```

Judge output shape:

```json
{
  "judge": "review-judge",
  "best_reviewer": "Brandon",
  "best_review_reason": "Most specific evidence and best failure-path coverage.",
  "hybrid_summary": "Combined synthesis using only evidence-supported claims.",
  "verdict": "SAFE_WITH_CONDITIONS",
  "evidence": ["parallel_review/reviewer_outputs/Brandon.json"],
  "findings": [],
  "test_gaps": [],
  "read_only_claim": true
}
```

## Additional DAG Shapes

These are review DAG patterns, not arbitrary workflows. Nodes are limited to
target bundling, `/scillm` JSON calls, deterministic rendering, deterministic
verification, and optional `/code-runner` handoff artifact creation.

### Pattern A: Independent Reviewers, Then Judge

Use when the human asks for named reviewers and a best-review judgment.

```text
target_bundle
  ├─ Brandon reviewer
  ├─ Margaret reviewer
  └─ Jennifer reviewer
       ↓
judge_best_review
       ↓
synthesis
       ↓
verifier
```

Call order:

```text
parallel: Brandon, Margaret, Jennifer
sequential: judge_best_review -> synthesis -> verifier
```

### Pattern B: Target Reconstruction, Then Specialist Reviewers

Use when the target is complex and reviewers should share a neutral target
summary before specializing.

```yaml
nodes:
  - id: target_bundle
    type: target_bundle
    depends_on: []

  - id: target_reconstruction
    type: scillm_call
    depends_on: [target_bundle]
    prompt_role: "reconstruct the target and intended invariants"

  - id: correctness
    type: scillm_call
    depends_on: [target_reconstruction]
    parallel_group: specialists

  - id: tests
    type: scillm_call
    depends_on: [target_reconstruction]
    parallel_group: specialists

  - id: maintainability
    type: scillm_call
    depends_on: [target_reconstruction]
    parallel_group: specialists

  - id: judge
    type: scillm_call
    depends_on: [correctness, tests, maintainability]

  - id: verifier
    type: deterministic_verifier
    depends_on: [judge]
```

Call order:

```text
sequential: target_bundle -> target_reconstruction
parallel: correctness, tests, maintainability
sequential: judge -> verifier
```

### Pattern C: Evidence Audit Gate Before Safety Judgment

Use when review quality depends on whether the supplied evidence is sufficient.

```text
target_bundle
  ↓
evidence_auditor
  ├─ if insufficient: verifier -> NEEDS_ATTENTION
  └─ if sufficient:
       ├─ failure_mode reviewer
       ├─ security_data_risk reviewer
       └─ test_proof reviewer
            ↓
       judge_hybrid_synthesis
            ↓
       verifier
```

Call order:

```text
sequential: target_bundle -> evidence_auditor
conditional barrier: stop if evidence is insufficient
parallel: failure_mode, security_data_risk, test_proof
sequential: judge_hybrid_synthesis -> verifier
```

### Pattern D: Review, Challenge, Final Judge

Use when the human wants a meaningful hybrid synthesis rather than a vote.

```yaml
nodes:
  - id: target_bundle
    type: target_bundle
    depends_on: []

  - id: reviewer_wave
    type: parallel_group
    depends_on: [target_bundle]
    children: [Brandon, Margaret, Jennifer]

  - id: challenger
    type: scillm_call
    depends_on: [reviewer_wave]
    prompt_role: "find contradictions, weak evidence, and unsupported safe claims"

  - id: judge
    type: scillm_call
    depends_on: [reviewer_wave, challenger]
    prompt_role: "choose best review and synthesize a hybrid verdict"

  - id: verifier
    type: deterministic_verifier
    depends_on: [judge]
```

Call order:

```text
parallel: Brandon, Margaret, Jennifer
sequential: challenger -> judge -> verifier
```

### Pattern E: Review Then /code-runner Handoff

Use only when the human explicitly requests implementation after review.

```text
target_bundle
  ├─ correctness reviewer
  ├─ test_proof reviewer
  └─ maintainability reviewer
       ↓
judge_hybrid_synthesis
       ↓
verifier
       ↓
code_runner_handoff.md
```

This does not run `/code-runner` directly. It writes a bounded handoff artifact
with target files, findings, tests, non-goals, and risk notes. `/code-runner`
owns edits and test-driven repair in an isolated implementation lane.

## Bad DAG Examples That Must Not Work

These are intentional misuse examples. `/ask` should reject these with
`needs_attention` or a clear parameter error instead of trying to be helpful.

### Bad Example 1: Missing Target

```bash
./run.sh ask "have Brandon, Margaret, and Jennifer review this" \
  --parallel-review \
  --parallel-review-personas Brandon,Margaret,Jennifer
```

Why this fails:

```text
No --review-target was supplied.
/ask must not infer "this" as the whole repository, current worktree, or chat history.
Safe default: do_not_run_review.
```

Expected behavior:

```json
{
  "needs_attention": {
    "reason": "missing_parallel_review_target",
    "safe_default": "do_not_run_review",
    "resume_hint": "Run again with --review-target <git:diff|paths|artifact>."
  }
}
```

### Bad Example 2: Implementation Hidden Inside Review

```yaml
nodes:
  - id: Brandon
    type: scillm_call
    prompt: "Review the diff"

  - id: fix_the_code
    type: scillm_call
    depends_on: [Brandon]
    prompt: "Apply the fix directly to src/ask/ask.py"
```

Why this fails:

```text
/ask reviewer DAGs are read-only.
Source edits belong to /code-runner, with allowlists and DoD checks.
```

Correct replacement:

```text
parallel reviewers -> judge -> verifier -> code_runner_handoff.md
```

### Bad Example 3: Arbitrary Shell Node

```yaml
nodes:
  - id: reviewer
    type: scillm_call

  - id: run_shell
    type: shell
    command: "rm -rf .ask_artifacts/runs && pytest"
```

Why this fails:

```text
/ask DAG nodes are not shell execution nodes.
Allowed nodes are target_bundle, scillm_call, deterministic_render,
deterministic_verifier, and handoff artifact generation.
```

Correct replacement:

```text
Use /code-runner or a local validation task outside /ask review mode.
```

### Bad Example 4: Unbounded Model Fanout

```bash
./run.sh ask "review every file with 50 reviewers" \
  --parallel-review \
  --review-target git:diff \
  --parallel-reviewers 50
```

Why this fails:

```text
Fanout is bounded. Default is 3 reviewers, hard cap is 7.
Large batch work must use the correct /scillm batch policy or /orchestrate plan.
```

### Bad Example 5: Memory As Code Evidence

```text
Reviewer says: SAFE because memory says this pattern worked before.
```

Why this fails:

```text
Memory can guide focus, but code/diff/artifact findings require inspected target evidence.
SAFE or SAFE_WITH_CONDITIONS without target evidence fails verifier.
```

Deep review can reuse the same bounded fanout under the existing deep-review lane:

```bash
./run.sh ask "deep review the ask runtime layer" \
  --deep-review \
  --deep-review-target skills/ask/src/ask/run_state.py,skills/ask/src/ask/status.py \
  --reviewer-spec fail-closed \
  --reviewer-spec evidence-auditor \
  --reviewer-spec test-proof \
  --oracle-backend subagent-runner
```

Until a dedicated `--review-target` flag exists, deep review continues to use
`--deep-review-target`; normal parallel review must not infer repository scope
from vague prompts such as "review this" without a concrete path, diff, artifact,
PR, plan, or manifest.

## Safety Contract

Parallel review must satisfy these invariants:

1. **Target required.** Refuse or enter `needs_attention` if no concrete target is
   supplied. Do not guess the full repository.
2. **Read-only by default.** Reviewer roles may inspect, grep, run safe read-only
   commands, and write artifacts only. They must not edit source files.
3. **Fresh context per reviewer.** Each reviewer receives the same target bundle
   and policy, not the full parent chat transcript.
4. **Bounded fanout.** Default to 3 reviewers. Allow up to 7 only with explicit
   user choice.
5. **Protocol roles, not arbitrary agents.** Reviewers are named roles such as
   `correctness`, `test-proof`, `failure-mode`, `evidence-auditor`,
   `security-data-risk`, `complexity-minimizer`, or `maintainability`.
6. **Memory is context, not evidence.** Memory may guide reviewer focus, but
   file/diff/artifact inspection is required for findings.
7. **Artifact-only writes.** Reviewer outputs, synthesis, verdict, status, and
   events are the only writes allowed.
8. **Verifier gate required.** Final synthesis is not accepted until the verifier
   checks target coverage, evidence, schema, verdict, and read-only status.
9. **No implementation unless explicit.** Fixes require a separate
   `/code-runner` handoff or an explicit future `--implement` lane with isolated
   worktree rules.

## Runner Adapter Interface

`/ask` owns the review contract. The runtime adapter only executes bounded roles.
For `scillm/api`, this means `POST /v1/chat/completions` with
`response_format: {"type": "json_object"}`, `Authorization`, and
`X-Caller-Skill: ask`. Non-QRA reviewer batches use `/scillm`'s documented
bounded `asyncio.create_task` + `asyncio.as_completed` pattern; `/ask` must not
invent a separate batching framework.

Minimum adapter input:

```json
{
  "ask_id": "ask-20260428T000000Z-review",
  "target": {
    "kind": "git_diff",
    "paths": ["skills/ask/src/ask/run_state.py"],
    "bundle_path": ".ask_artifacts/runs/<ask_id>/target_bundle.md"
  },
  "role": "test-proof",
  "policy": {
    "read_only": true,
    "fresh_context": true,
    "artifact_only_writes": true,
    "memory_as_evidence": false
  },
  "output_path": ".ask_artifacts/runs/<ask_id>/reviewer_outputs/test-proof.json"
}
```

Minimum adapter output:

```json
{
  "role": "test-proof",
  "status": "completed",
  "target_coverage": ["skills/ask/src/ask/run_state.py"],
  "findings": [
    {
      "severity": "high",
      "title": "Missing failure-path test",
      "evidence": "tests/test_run_state_protocol.py lacks ...",
      "impact": "Regression can pass silently",
      "fix": "Add ...",
      "verification": "pytest ..."
    }
  ],
  "limits": {
    "read_only": true,
    "edited_files": []
  }
}
```

Supported adapters may include:

```text
pi-subagents
subagent-runner
codex exec
claude code
gemini cli
opencode
scillm/api
dry-run-only
```

Adapter selection must be explicit or deterministic from availability. It must
not silently choose a paid or broad-context runner for normal questions.

## Artifact Layout

Parallel review uses the standard runtime run directory:

```text
.ask_artifacts/runs/<ask_id>/
  <ask_id>.request.json
  <ask_id>.status.json
  <ask_id>.events.jsonl
  target_bundle.md
  reviewer_plan.json
  reviewer_outputs/
    Brandon.json
    Margaret.json
    Jennifer.json
  judge.json
  synthesis.md
  verdict.json
  verifier.log
```

`request.json` records the normalized target, reviewer roles, runner adapter, and
policy. `status.json` is atomic and includes current reviewer progress.
`events.jsonl` is append-only and records `target_resolved`, `reviewer_started`,
`reviewer_finished`, `synthesis_started`, `verifier_finished`, and terminal
`finished`, `failed`, or `needs_attention` events.

## Verifier Rules

The verifier must reject the review when any required condition fails:

- missing target bundle
- target type unsupported or ambiguous
- reviewer count below requested minimum
- reviewer output malformed or missing role/status/findings
- `SAFE` or `SAFE_WITH_CONDITIONS` verdict lacks inspected evidence
- finding lacks evidence, impact, fix, or verification
- reviewer claims coverage for files not in the target bundle
- memory-only evidence is used for a code/diff/artifact finding
- unexpected source-file edits occurred
- synthesis ignores high-severity reviewer findings without rationale

Allowed verdicts:

```text
SAFE_TO_MERGE
SAFE_WITH_CONDITIONS
CHANGES_REQUESTED
NOT_SAFE
INSUFFICIENT_EVIDENCE
NEEDS_ATTENTION
```

## Handoff To /code-runner

Parallel review may produce a fix specification, but it does not apply patches.

Handoff artifact:

```text
.ask_artifacts/runs/<ask_id>/code_runner_handoff.md
```

The handoff must include:

- selected findings
- target files
- expected tests
- non-goals
- risk notes
- explicit statement that `/code-runner` owns implementation

No handoff is generated unless the user requests implementation or accepts the
review findings.

## Non-Goals

`/ask parallel-review` is not:

- a generic subagent orchestration framework
- a background worker scheduler
- a dependency updater
- a migration executor
- a hidden paid-model fanout path
- an automatic code modifier

The clean split remains:

```text
/ask: decide, review, argue, judge, verify, synthesize
pi-subagents: native Pi child-agent execution
/code-runner: bounded implementation and test-driven repair
```
