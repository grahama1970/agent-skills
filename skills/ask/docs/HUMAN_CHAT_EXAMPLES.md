# `$ask` Human Chat Examples

These examples describe how a human can invoke `$ask` from chat. The skill
accepts natural phrasing, then maps it to memory recall, oracle synthesis,
persona consultation, argue, roundtable review, parallel review, CAE gap review,
or deep review.

## Defaults

- Use memory first for ordinary knowledge questions.
- Use oracle mode for high-value analytical, strategic, ambiguous, or review-heavy questions.
- Use `gpt-5.5` with `high` reasoning for normal oracle paths, and `xhigh` for deep-review unless unavailable or overridden.
- Use `subagent-runner` for personas, peers, roundtables, parallel review, and deep review.
- Use three `/scillm` calls for argue: two parallel advocates, then one sequential judge.
- Use CAE gap review only for compliance/cybersecurity evidence-case gap analysis.
- Treat memory recall as context, not evidence.
- Use `--scope sparta` for SPARTA, NIST-to-SPARTA, and space-cybersecurity questions.
- Treat empty answers, refusal-style non-answers, missing personas, or missing domain grounding as failed E2E behavior.
- Do not use oracle mode for bulk loops, nightly ingestion, or large batches.

## Memory Questions

```text
$ask what do we know about the release checklist?
$ask what did we decide about provider fallback behavior?
$ask show raw memory hits for timeout handling
$ask is memory healthy?
$ask doctor
$ask status for recent runs
```

Expected route:

```bash
./run.sh ask "what do we know about the release checklist?"
./run.sh doctor --json
./run.sh status --runs --json
```

## High-Reasoning Oracle

```text
$ask What is the state of Python packaging in 2026?
$ask oracle should we use subagent-runner here?
$ask oracle with a 10 minute timeout on this architecture decision
$ask Should subagent-runner replace direct scillm for focused oracle calls?
```

Expected route:

```bash
./run.sh ask "Should subagent-runner replace direct scillm for focused oracle calls?" \
  --oracle \
  --oracle-backend subagent-runner \
  --oracle-model gpt-5.5 \
  --oracle-reasoning high
```

## Provider/Model Shorthand

```text
$ask oc kimi explain this design tradeoff
$ask oc-qwen compare these options
$ask chutes kimi explain this design tradeoff
$ask chutes-kimi explain this design tradeoff
```

Expected route:

```bash
./run.sh ask "explain this design tradeoff" \
  --oracle \
  --oracle-backend scillm \
  --oracle-model opencode-go/kimi-k2.6
```

`oc` and `opencode` use the live scillm OpenCode Go discovery endpoint and
choose the best currently supported model for the requested family, such as
Kimi, DeepSeek, GLM, MiMo/Mini, MiniMax, or Qwen. `chutes` uses scillm's
configured Chutes aliases, such as `text-kimi`, while still accepting exact
catalog-style model IDs when scillm supports them.

## Persona Oracle

```text
$ask Brandon what is the best way to review this API boundary?
$ask Brandon persona about whether this retry design fails closed
$ask Architect persona about whether this plugin interface is too coupled
$ask Brandon ask Margaret where are we weak?
```

Expected route:

```bash
./run.sh ask "whether this retry design fails closed" \
  --oracle \
  --oracle-backend subagent-runner \
  --oracle-persona Brandon \
  --oracle-model gpt-5.5 \
  --oracle-reasoning high
```

Peer prompt:

```bash
./run.sh ask "where are we weak?" \
  --oracle \
  --oracle-backend subagent-runner \
  --oracle-persona Brandon \
  --oracle-peer Margaret \
  --oracle-iterations 2
```

## Cross-Model Oracle

```text
$ask oracle with GPT-5.5 architect and DeepSeek V4 critic for this design
$ask Brandon use DeepSeek V4 as a critic on this API boundary
```

Expected route:

```bash
./run.sh ask "Review this design" \
  --oracle \
  --oracle-backend subagent-runner \
  --oracle-model gpt-5.5 \
  --oracle-persona "GPT-5.5 architect" \
  --oracle-peer "DeepSeek V4 critic" \
  --oracle-peer-model opencode-go/deepseek-v4-pro \
  --oracle-iterations 3
```

## Roundtable

```text
$ask Brandon, Margaret, and Jennifer personas to roundtable about the topic: Should this service use retries or queues?
$ask roundtable with Brandon:failure_mode, Margaret:evidence_auditor, Jennifer:complexity_minimizer on this architecture
$ask Brandon, Margaret, and Jennifer to debate the relevance of formal methods in large-scale aerospace projects in 2026
$ask Brandon, Margaret, and Jennifer personas to roundtable about the topic: What is the state of cybersecurity in 2026?
```

Expected route:

```bash
./run.sh ask "Should this service use retries or queues?" \
  --oracle \
  --oracle-backend subagent-runner \
  --roundtable \
  --roundtable-personas "Brandon:failure_mode,Margaret:evidence_auditor,Jennifer:complexity_minimizer" \
  --roundtable-rounds 2
```

Use `--roundtable-persist full` only when the full transcript matters. The
default is summary persistence to avoid memory pollution.

Roundtable is a sequential protocol: each persona sees prior claims, reacts
under a protocol role, and the moderator synthesizes. It is not the same as
parallel review.

## Parallel Review

```text
$ask run 3 parallel adversarial reviewers on this implementation
$ask launch 5 parallel reviewers for correctness, tests, security, maintainability, and UX
$ask run N parallel reviews on the current diff
$ask run parallel reviewers with fresh context and memory summary only
```

Expected route:

```bash
./run.sh ask "this implementation" \
  --oracle \
  --oracle-backend subagent-runner \
  --parallel-review \
  --parallel-reviewers 3 \
  --parallel-review-focus correctness,tests,maintainability \
  --review-context fresh \
  --inherit-memory summary
```

If focus labels are not explicit, `/ask` chooses reviewer angles from
`docs/reviewers/*.md`, always including evidence and failure-mode coverage.

## Argue

```text
$ask argue whether we should ship this change
$ask debate whether retries or queues are safer here
$ask make the case for and against this implementation plan
```

Expected route:

```bash
./run.sh ask "we should ship this change" \
  --argue
```

Forced binary decisions must be explicit:

```bash
./run.sh ask "we should ship this change" \
  --argue \
  --decision-required \
  --tie-breaker more-reversible
```

Argue returns `FOR`, `AGAINST`, `NO_CLEAR_WINNER`, or
`INSUFFICIENT_EVIDENCE`. It does not edit files or invoke `/code-runner`.

## CAE Gap Review

```text
$ask cae gap review AC-2 MFA evidence for the production tenant
$ask run cae gap review on audit logging evidence for the SOC platform
$ask ask cae reviewers to review incident response evidence for IR-4
```

Expected route:

```bash
./run.sh ask "AC-2 MFA evidence for the production tenant" \
  --cae-gap-review \
  --cae-reviewers "Brandon:cae_policy_evidence,Margaret:cae_technical_enforcement,Jennifer:cae_control_mapping" \
  --cae-judge "CAE Gap Judge" \
  --cae-max-rounds 3
```

CAE reviewers are persona plus prompt-role preset pairs. The default personas
are Brandon, Margaret, and Jennifer; the bounded prompt roles are policy
evidence, technical enforcement, and control mapping. The judge reroutes only
one unresolved missing evidence item per round, then stops. The output is not a
compliance approval, certification, attestation, audit opinion, or assurance
outcome.

## Parallel Review Then Roundtable

```text
$ask review then roundtable with Brandon, Margaret, Jennifer on this architecture
$ask run parallel reviewers first, then have Brandon and Margaret debate unresolved issues
```

Expected route:

```bash
./run.sh ask "Review this architecture" \
  --oracle \
  --oracle-backend subagent-runner \
  --parallel-review \
  --parallel-reviewers 3 \
  --roundtable \
  --roundtable-personas "Brandon:failure_mode,Margaret:evidence_auditor,Jennifer:complexity_minimizer"
```

## Deep Review

```text
$ask deep review this implementation --deep-review-target src/ask/ask.py
$ask is this safe to proceed? --deep-review-target "current branch vs main"
$ask comprehensive review of this plan --deep-review-target docs/IMPLEMENTATION_PLAN.md
```

Expected route:

```bash
./run.sh ask "deep review this implementation" \
  --deep-review \
  --deep-review-target src/ask/ask.py \
  --deep-reviewers 5 \
  --deep-review-focus boundaries,fail-closed,tests,auditability \
  --oracle-backend subagent-runner \
  --oracle-model gpt-5.5 \
  --oracle-reasoning xhigh
```

Deep review emits:

```text
.ask_artifacts/deep-review/<timestamp>/review.md
.ask_artifacts/deep-review/<timestamp>/review.json
.ask_artifacts/deep-review/<run_id>/request.json
.ask_artifacts/deep-review/<run_id>/status.json
.ask_artifacts/deep-review/<run_id>/events.jsonl
```

Deep review is read-only at runtime. It records before/after git status and
fails verifier checks if unexpected non-artifact file changes appear.

Saved chains for deep review and parallel review live in `docs/chains/`.
Project agents should prefer those chain specs over inventing new ad hoc review
protocols.

## Domain-Specific Examples

These remain valid when the project has the relevant memory/persona data:

```text
$ask what do we know about SPARTA QRA validation?
$ask What is the state of space-based cybersecurity in 2026?
$ask Brandon what is the state of space-based cybersecurity in 2016?
$ask Brandon, Margaret, and Jennifer personas to roundtable about the topic: What is the state of cybersecurity in 2026?
$ask Brandon persona about how NIST AC-3 is related to SPARTA countermeasure CM0001
$ask parallel reviewers on this NIST-to-SPARTA traceability matrix
$ask oracle whether this evidence case is sufficient for CMMC Level 2 scoping
```

Expected SPARTA/space-cybersecurity routes:

```bash
./run.sh ask "What is the state of space-based cybersecurity in 2026?" \
  --scope sparta \
  --oracle \
  --oracle-backend scillm

./run.sh ask Brandon what is the state of space-based cybersecurity in 2016? \
  --scope sparta

./run.sh ask "What is the state of cybersecurity in 2026?" \
  --scope sparta \
  --roundtable \
  --roundtable-personas "Brandon:failure_mode,Margaret:evidence_auditor,Jennifer:complexity_minimizer" \
  --roundtable-rounds 1 \
  --oracle-backend subagent-runner
```

## SPARTA Preflight Examples

SPARTA, NIST-to-SPARTA, and space-cybersecurity prompts use the deterministic
`sparta_preflight` route before answer synthesis. The preflight step must rely on
structured `/extract-entities` and `/memory` grounding, then either hands grounded
controls to `/create-evidence-case` or pauses safely.

```text
$ask --scope sparta how does NIST AC-3 map to the mustard SPARTA countermeasure CM0001?
$ask --scope sparta can we claim the mustard SPARTA CM0001 evidence package is compliant?
```

Expected route:

- For a resolved extractor entity such as `CM0001` from the SPARTA corpus, route
  through `sparta_preflight` to `/create-evidence-case`; the evidence package
  remains `NEEDS_VERIFICATION`, not a final compliance determination.
- For an unresolved or fabricated `CM0001`/mustard reference, stop the evidence
  path with `needs_attention`; do not invent a control, relationship, crosswalk,
  or compliance status.

## Raw And JSON Output

```text
$ask show raw memory hits for timeout handling
$ask give me JSON for persona matches on API design
```

Expected route:

```bash
./run.sh ask "timeout handling" --raw
./run.sh ask "persona matches on API design" --json
```

Do not combine `--raw` with oracle, roundtable, parallel review, or deep review.

## Wrong And Right

```text
Wrong: $ask run oracle for these 100 questions
Right: Use normal memory ask or a batch-capable model lane; reserve oracle for high-value questions.

Wrong: $ask roundtable and persist everything by default
Right: $ask Brandon and Margaret to roundtable for 2 rounds on <topic>

Wrong: $ask safe to proceed?
Right: $ask safe to proceed? --deep-review-target "current branch vs main"

Wrong: $ask use DeepSeek somehow
Right: $ask oracle with GPT-5.5 and DeepSeek V4 using --oracle-peer-model opencode-go/deepseek-v4-pro
```

## Persona Review → Implement (agents API)

Full orchestration example with persona, `/review-code`, `/memory`, `/dogpile`
when blocked, and implementation via scillm **agents** (not chat completions).

```text
$ask Brandon $review-code the ask example module then implement the handoff fix; consult $memory and $dogpile when blocked
```

Expected route:

```bash
cd skills/ask
./examples/run-example.sh "Brandon: review-code then implement sample_target" dry-run
# or
./run.sh ask "Brandon \$review-code the module then implement the fix" \
  --orchestrate --agent-worker implementation --dry-run --json
```

See `examples/README.md` for prerequisites (memory, scillm agents registry, implementation worker).

When stuck on a runtime error during implementation, the workflow expects **`/debugger`**
before guessing at patches: set breakpoints, run the repro, inspect paused variable state,
then patch. See `examples/run-debugger-stuck.sh` and `examples/README.md`.
