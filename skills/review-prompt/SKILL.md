---
name: review-prompt
description: >
  Deterministic prompt contract review and optimization loop.
  Sends prompt bundles, source files, validators, and consumer code to N models
  via /scillm, merges findings, applies bounded fixes, and keeps only rounds
  that improve executable gates. Self-improvement loops must be coded, not
  agent-directed.
allowed-tools: Bash, Read
triggers:
  - review prompt
  - optimize prompt
  - prompt review
  - improve prompt template
  - multi-model prompt review
  - prompt optimization
  - review-prompt with webgpt
  - webgpt prompt review
  - prompt review over 2 rounds
  - webgpt prompt contract review
metadata:
  short-description: Multi-model prompt review loop via /scillm batch
provides:
  - prompt-review
  - prompt-contract-review
  - deterministic-prompt-improvement
composes: [scillm, prompt-lab, best-practices-self-improvement-loop, ask, project-knowledge, surf]

taxonomy:
  - prompt-engineering
  - llm
disciplines:
  - evaluation-quality
  - model-ops
---

## Standard Review Iteration Parameters

This `review-*` skill follows the shared contract in
`skills/.system/review-iteration-contract.md`.

Canonical parameters:

- `--max-rounds N`
- `--output-dir PATH`
- `--ask-gate`
- `--ask-model MODEL` (default `gpt-5.5`)
- `--ask-reasoning LEVEL` (default `high`)
- `--ask-timeout SECONDS`
- `--ask-focus LABELS`

When `--max-rounds > 1` is supplied, the skill must behave as a bounded
gate-producing controller or fail closed if that mode is not implemented. The
canonical gate artifact is `review_result.json` with verdict
`PASS`, `NEEDS_CHANGES`, `BLOCKED`, or `INSUFFICIENT_EVIDENCE`.

# review-prompt — Deterministic Prompt Review Loop

Concurrent multi-model review of prompt contracts with deterministic scoring.
Same autoresearch pattern as `/code-runner`, but the loop must be coded. The
agent invokes the loop; the agent is not the loop.

## Relationship To Plan Iterate

`$review-prompt` is the domain loop for prompt-contract improvement. It owns the
coded preflight, model review, bounded patching, deterministic scoring,
validator/smoke gates, and keep/revert decisions.

`$plan-iterate` is the parent phase controller when prompt work is part of a
larger evidence-gated phase. In that case `$plan-iterate` records the
`$review-prompt` terminal audit, validator logs, smoke output, reviewer
artifacts, blockers, and acceptance decision. It should not replace the coded
prompt loop with an agent-directed retry sequence.

When `$review-prompt` runs inside `$plan-iterate`, record it as a read-only
`domain_review_loops[]` entry. That entry must include the reviewer persona,
immutable prompt-contract goal, context artifact, relevant `best-practices-*`
skills such as `best-practices-prompt`,
`best-practices-self-improvement-loop`, `best-practices-scillm`, or
`best-practices-security`, loop state/events/aggregate artifacts, and a
prompt-fixture/gate-to-finding matrix. Each round also records exactly three
project-agent-owned plan artifacts: implementation/patch, validation/evidence,
and review/escalation.

When `$review-prompt` participates in a `$plan-iterate` phase, its primary
deliverable is a complete prompt-contract audit bundle for the phase-level
`$scillm` aggregation gate. `$review-prompt` does not decide whether the phase
continues or completes. If the current phase does not change a prompt contract,
or if required prompt evidence is missing, write a fail-closed skip/blocker
artifact instead of running a wording-only review.

Minimum aggregation input for prompt phases:

```text
review-prompt/
  context.md
  prompt-templates/
  rendered-fixtures/
  expected-responses/
  validators-and-smoke.md
  consumer-or-schema.md
  audit.json
  aggregate_verdict.json
  PROMPT_REVIEW_ITERATE_MATRIX.md
```

Minimum fail-closed skip artifact for non-prompt phases:

```json
{
  "state": "skipped_fail_closed",
  "skill": "review-prompt",
  "reason": "No prompt contract changed in this phase.",
  "missing_contract_fields": [],
  "verdict": "not_applicable_verified"
}
```

The `$scillm` gate consumes this artifact alongside other applicable review
bundles and decides `PASS`, `NEEDS_CHANGES`, `BLOCKED`, or
`INSUFFICIENT_EVIDENCE`. `not_applicable_verified` is non-blocking only when
the phase evidence proves no prompt contract changed. Missing or uncertain
prompt applicability, or missing expected-response evidence for a
prompt-changing phase, remains fail-closed and must map to `BLOCKED` or
`INSUFFICIENT_EVIDENCE`.

This skill follows `/best-practices-self-improvement-loop`: every improve cycle
must perform deterministic preflight, try an ordered strategy, measure against a
configured gate, keep/revert deterministically, write artifacts after every
iteration, and halt with an audit trail when exhausted.

## Contract Boundary

`/review-prompt` reviews prompt contracts, not just prompt wording.

A complete prompt contract bundle can include:

- active system/user prompt templates
- complete review payloads
- valid and invalid examples
- JSON Schema, Pydantic models, or semantic validators
- source files that assemble or consume the prompt
- runtime adapters that consume the prompt output
- tests, fixtures, and smoke commands
- prior review artifacts such as `$ask` `review.md` / `review.json`

Do not claim a prompt is improved because a reviewer says it is clearer. It is
improved only when executable gates pass and the weighted finding score does not
regress.

For `$plan-iterate` aggregation, expected response evidence is mandatory for at
least one concrete fixture. If the expected response, validator/smoke command,
or consumer/schema is missing, halt with `missing_expected_response`,
`missing_validator`, or `missing_consumer_schema`; do not send the prompt to
reviewers as prose only.

## How It Works

```
1. Preflight inputs and configured gates deterministically.
2. Read prompt bundle, validators, source files, consumer code, and tests.
3. Try the next ordered improvement strategy.
4. Send the bundle to N models concurrently via `/scillm`.
5. Parse findings into `critical`, `major`, and `minor`.
6. Apply only bounded fixes allowed by the current strategy. Inside
   `$plan-iterate`, apply fixes only to candidate artifacts/temp workspace
   and never mutate production as a `domain_review_loops[]` reviewer entry. If
   the human authorizes production mutation, record it as a separate
   project-agent patch iteration or implementation-worker artifact whose output
   is validated by the parent controller.
7. Run validators, fixture checks, and configured smoke checks.
8. Score the round from model findings plus deterministic gate failures.
9. Keep only if score improves and no required gate regresses; otherwise revert.
10. Write all request, response, score, diff, gate, and keep/revert artifacts.
11. Run `$ask` deep review as the final gate when required by scope or `--ask-gate`.
12. Optionally run WebGPT through the real `$ask` WebGPT route as an external
    final gate when `--webgpt-gate` is supplied.
13. Stop on gate pass, score 0, max rounds, blocked preflight, exhausted
    strategies, `$ask` blocker, or WebGPT blocker.
```

## Deterministic Loop Requirements

The loop must exist in code. Do not rely on an agent to remember the sequence.

Required coded stages:

1. **Preflight**
   - verify template paths exist
   - verify source and consumer files exist
   - verify configured models are reachable or halt
   - verify output directory is writable
   - verify validator/smoke commands exist when required
   - verify user-configured gates are explicit

2. **Strategy list**
   Strategies must be ordered before the first model call. Default strategy order:
   - `baseline_review`: review current bundle without changes
   - `evidence_discipline`: separate target evidence from technique evidence
   - `schema_tightening`: add or tighten JSON Schema / semantic validators
   - `example_alignment`: fix valid/invalid examples to avoid unsupported specificity
   - `consumer_contract`: align prompt output with actual runtime adapter/consumer
   - `safety_filters`: add fail-closed safety, forbidden-output, and false-positive gates
   - `artifact_audit`: add artifact path, run metadata, and reproduction requirements

3. **Measure**
   Every round writes:
   - model request payloads
   - raw model responses
   - parsed findings
   - merged findings
   - applied patch or proposed diff
   - validator output
   - smoke output
   - weighted score
   - keep/revert decision

4. **Gate**
   Gates are configured inputs, not model inventions. Default gates:
   - `max_critical = 0`
   - `max_major = 0` for release candidates, otherwise explicit
   - prompt output example parses as JSON when applicable
   - closed vocabulary checks pass when applicable
   - schema or semantic validator passes when configured
   - consumer compatibility smoke passes when configured
   - no required safety or fail-closed gate regresses

5. **Keep/revert**
   Keep a round only when:
   - weighted score improves over the current best
   - all required deterministic gates pass or improve
   - no consumer compatibility check regresses
   - no safety check regresses

   Revert otherwise. Write the rejected diff and reason.

6. **Halt**
   When the loop cannot pass, write a terminal audit artifact with:
   - `status: "halted"`
   - best round id and score
   - gate thresholds
   - all attempted strategies
   - remaining blockers
   - required non-prompt work, if any
   - artifact paths for every round

## Usage

```bash
# Review a prompt template with its source files
./run.sh review \
  --template prompts/code_runner_system_v2.txt \
  --source code-runner/prompt_assembly.py \
  --source code-runner/evidence.py \
  --context "Bounded code-fixing executor, not a full agent"

# Custom models (default: codex, gemini, deepseek)
./run.sh review \
  --template prompts/my_prompt.txt \
  --models gpt-5.3-codex text-gemini text \
  --max-rounds 4

# Dry run — show what would be sent without calling LLM
./run.sh review --template prompts/my_prompt.txt --dry-run

# Review a full prompt contract bundle with validators and consumer code
./run.sh review \
  --template prompts/evolution/seed_research/user.txt \
  --source prompts/evolution/seed_research/system.txt \
  --source prompts/review/evolution_seed_research_payload.txt \
  --source evolutionary_campaign.py \
  --source tests/test_evolutionary_campaign.py \
  --context "Lane-aware /hack evolutionary greybox seed research contract" \
  --validator "python scripts/validate_seed_strategy_set.py fixtures/seed_strategy_valid.json" \
  --smoke "python -m pytest tests/test_evolutionary_campaign.py -k seed_strategy" \
  --ask-gate \
  --ask-model gpt-5.5 \
  --ask-reasoning high \
  --webgpt-gate \
  --webgpt-tab-id 837343233 \
  --max-rounds 2
```

### WebGPT tab binding (CLI parity)

Prefer **zero-flag** invocation from a registered working directory. `/ask` and `/surf` compose `$browser-oracle` automatically.

| Flag | When to use |
|------|-------------|
| *(none)* | cwd has walk-up registry + binding — preferred |
| `--browser-oracle-from <dir>` | Override walk-up root (monorepo subdir) |
| `--webgpt-project <name>` | Explicit project; skips yaml walk-up |
| `--webgpt-tab-id <id>` | One-off override; skips walk-up |
| `--webgpt-url <url>` | Resolve by conversation URL; skips walk-up |

Setup: `$browser-oracle register` + `bind` + `doctor --from <dir>`. See `$browser-oracle` and `$ask` SKILL.md **WebGPT tab binding** sections.

## Options

| Option | Description |
|--------|-------------|
| `--template` / `-t` | Prompt template file to review (required) |
| `--source` / `-s` | Source files that use the template (repeatable) |
| `--context` / `-c` | One-line description of what the prompt does |
| `--models` / `-m` | Models to use (default: gpt-5.3-codex, text-gemini, text) |
| `--max-rounds` | Max review rounds (default: 3) |
| `--dry-run` | Show prompt without calling LLM |
| `--output` / `-o` | Write final reviewed template to file |
| `--payload` | Concrete rendered input payload or fixture used to exercise the prompt |
| `--expected-response` | Expected response JSON/artifact for at least one concrete fixture |
| `--consumer-schema` | Consumer code, JSON Schema, Pydantic model, or adapter contract that ingests the response |
| `--persona` | Optional reviewer role/persona label for final `$ask`/WebGPT adjudication |
| `--validator` | Deterministic validation command; may repeat |
| `--smoke` | Consumer compatibility or runtime smoke command; may repeat |
| `--gate` | Gate override such as `max_critical=0`; may repeat |
| `--strategy` | Strategy override; may repeat, otherwise use default order |
| `--artifact-root` | Directory for round artifacts and terminal audit |
| `--ask-gate` | Run `$ask --deep-review` as the final readiness/debug gate |
| `--ask-model` | `$ask` oracle model for the final gate (default: `gpt-5.5`) |
| `--ask-reasoning` | `$ask` oracle reasoning effort for the final gate (default: `high`) |
| `--webgpt-gate` | Run WebGPT through the real `$ask` WebGPT route as an external final gate |
| `--browser-oracle-from` | Walk-up root when cwd lacks registry (monorepo subdirs) |
| `--webgpt-project` | Explicit project binding; skips yaml walk-up |
| `--webgpt-tab-id` | Exact ChatGPT tab id; skips walk-up (override) |
| `--webgpt-url` | Conversation URL; skips walk-up |
| `--webgpt-timeout` | WebGPT gate timeout seconds (default: 900) |

## Scoring

Deterministic — count findings, don't ask the LLM if it's good:

| Severity | Weight | Example |
|----------|--------|---------|
| critical | 3 | Prompt injection vulnerability, missing safety block |
| major | 2 | Ambiguous format spec, contradictory rules |
| minor | 1 | Redundant instruction, unclear wording |

Score = sum(severity × weight) + deterministic gate penalties. Lower is better.
0 means no model findings and no gate failures.

Default gate penalties:

| Gate Failure | Weight | Example |
|--------------|--------|---------|
| validator failure | 6 | JSON Schema rejects valid example |
| consumer smoke failure | 6 | Prompt output cannot be consumed by runtime |
| safety regression | 6 | Raw exploit strings or unsafe outputs introduced |
| missing artifact proof | 3 | Round lacks request/response/score artifacts |
| unsupported specificity | 3 | Example invents route, symbol, file, or dependency |

Model findings cannot override deterministic gates. A round with fewer findings
but a failed required validator is not an improvement.

## Prompt Contract Review Checks

For schema-bearing or security-sensitive prompts, review must check:

- output schema exists and is executable, or the blocker is reported
- examples parse and pass validators
- closed vocabularies are complete and unique
- each recommended item has admissible evidence
- technique evidence is not treated as target evidence
- source paths are not treated as inspected facts unless inspected
- runtime consumer can ingest the prompt output
- fail-closed behavior is specified for malformed, empty, partial, stale, and failed outputs
- forbidden outputs and prompt-injection boundaries are explicit
- generated artifacts are sufficient for audit and reproduction

For prompts that generate security, compliance, memory, deployment, or monitoring
artifacts, a `SAFE` or `ready` outcome requires deterministic proof, not reviewer
confidence.

## Ask Final Gate

`/review-prompt` composes `$ask` as an artifact-bearing readiness gate, not as a
replacement for the coded loop.

Use `/scillm` for cheap concurrent inner-loop reviewer calls. Use the real
`$ask` runtime for final high-reasoning review when any of these are true:

- the prompt controls release, readiness, security, compliance, memory, deployment, or monitoring artifacts
- the user passes `--ask-gate`
- deterministic gates still fail after the configured maximum rounds
- the remaining blocker needs a high-reasoning verdict over the complete artifact bundle

Required `$ask` invocation shape:

```bash
../ask/run.sh ask "Deep review this prompt contract bundle for readiness." \
  --deep-review \
  --deep-review-target artifacts/review-prompt/<run_id>/final/ask-review-bundle.json \
  --deep-review-focus schema,evidence-discipline,consumer-contract,safety,auditability \
  --oracle-model gpt-5.5 \
  --oracle-reasoning high \
  --ask-id review-prompt-<run_id>-ask-gate \
  --json
```

The final `/review-prompt` audit must link the `$ask` artifact set:

- `<ask_id>.request.json`
- `<ask_id>.status.json`
- `<ask_id>.events.jsonl`
- `review.md`
- `review.json`

`$ask` verdict handling is fail-closed:

- `NOT_SAFE` blocks readiness.
- `INSUFFICIENT_EVIDENCE` blocks readiness until the missing evidence is added.
- `SAFE_WITH_CONDITIONS` blocks readiness unless every condition maps to a passing deterministic gate or explicit human-accepted residual risk.
- `SAFE` is admissible only when deterministic `/review-prompt` gates also pass.

Do not run `$ask` on every inner round by default. Inner rounds need cheap
parallel breadth; `$ask` is the expensive final/debug gate with persistent proof.

## WebGPT Final Gate

`/review-prompt` can run WebGPT as an external final gate via `$ask` when WebGPT
has demonstrated better judgment than Codex/scillm for the prompt class under
review.

Use WebGPT for:

- prompt contracts with high judgment burden
- prompt specs that previously produced dashboard theater, vague diagrams, or
  performative artifacts
- final adjudication where WebGPT has already outperformed local/API routes

Do not replace the coded loop with WebGPT. The deterministic validators, fixture
checks, consumer smoke tests, and keep/revert logic still decide whether a prompt
candidate can be kept. WebGPT is a fail-closed external gate: if it returns
`NOT_SAFE`, `INSUFFICIENT_EVIDENCE`, `SAFE_WITH_CONDITIONS`, malformed output,
or no verdict, readiness is blocked unless a human explicitly accepts the
residual risk.

Required command shape:

```bash
./run.sh review \
  --template prompts/my_prompt.txt \
  --payload fixtures/expected_input.json \
  --expected-response fixtures/expected_response.json \
  --consumer-schema schemas/my_prompt_response.schema.json \
  --context "Prompt purpose and consumer contract" \
  --persona "consumer/reviewer role" \
  --validator "python validate_expected_response.py" \
  --webgpt-gate \
  --webgpt-tab-id 837343233
```

Artifacts are written under `artifacts/review-prompt/<run_id>/final/webgpt/`
plus `final/webgpt-artifacts.json`. The WebGPT request is sent through the real
`$ask` runtime with `--oracle-backend webgpt`, so proof must include `$ask`
request/status/events artifacts, controlled tab id, raw/clean response,
sentinel metadata, and no page-chrome contamination.

### WebGPT Reviewer Loop Shorthand

When the user says a short prompt such as:

```text
per current changes and project knowledge, $review-prompt with webgpt over 2 rounds
```

expand it into a bounded prompt-contract reviewer/project-agent loop:

1. Use `$project-knowledge` to recover the prompt purpose, consumer contract,
   known prompt failures, required schemas, and previous review findings.
2. Build a complete prompt contract bundle before any WebGPT call. The bundle
   must include the full prompt templates, concrete rendered fixture, input
   payload, expected response, validators/smoke commands, consumer code/schema,
   invalid examples or rejection criteria, current diff, and non-goals.
3. If required expected output or validator evidence is missing, stop with
   `missing_expected_response` or the specific missing gate. Do not ask WebGPT
   to judge prompt wording alone.
4. Run the real `$ask`/WebGPT route on the complete bundle and preserve
   request/status/events/review artifacts plus controlled-tab metadata when
   `$surf` is used.
5. The project agent applies or adapts valid prompt/schema/test changes, then
   runs the deterministic validators and consumer smoke checks.
6. Build the round-2 bundle with round-1 findings, what changed since round 1,
   rejected findings with rationale, fresh expected-output/validator evidence,
   and remaining open questions.
7. Run exactly one more WebGPT review round unless round 1 blocks on a human
   product or acceptance decision.
8. Final status includes changed files, deterministic gate output, WebGPT/ask
   artifact paths, unresolved risks, and whether human decision is required.

Preferred human prompt:

```text
per current changes and project knowledge, $review-prompt with webgpt over 2 rounds
```

Scoped variant:

```text
per current changes, $review-prompt with webgpt over 2 rounds for the Stage 12 QRA prompt contract
```

Do not make the human write the artifact checklist in a long prompt. The skill
owns the expansion, and the expected-response gate remains non-negotiable.

## Artifact Layout

Each run writes:

```text
artifacts/review-prompt/<run_id>/
  request.json
  preflight.json
  rounds/
    001-baseline_review/
      model-requests.jsonl
      model-responses.jsonl
      findings.json
      merged-findings.json
      patch.diff
      validator-output.json
      smoke-output.json
      score.json
      decision.json
    002-schema_tightening/
      ...
    final/
      reviewed-template.txt
      audit.json
      summary.md
      ask-review-bundle.json
      ask-artifacts.json
      webgpt-artifacts.json
      webgpt/
        request.md
        response.md
        response.meta.json
```

Write artifacts after every iteration, before deciding whether to continue.

When embedded in `$plan-iterate`, copy or reference the terminal audit and
per-round artifacts from the phase `domain-review-loops/` directory:

```text
domain-review-loops/<prompt-surface>/
  context.md
  state.json
  events.jsonl
  audit.json
  aggregate_verdict.json
  PROMPT_REVIEW_ITERATE_MATRIX.md
  rounds/
    001/
      implementation-plan.md
      validation-plan.md
      review-plan.md
      model-requests.jsonl
      model-responses.jsonl
      score.json
      decision.json
```

The implementation plan describes prompt/schema/test changes the project agent
will make or reject. The validation plan names fixtures, expected responses,
validators, and consumer smoke checks. The review plan names the next model,
`$ask`, WebGPT, `$dogpile`, or human escalation gate.

## Do Not Do This

- Do not run an agent-directed retry loop.
- Do not invent scoring thresholds.
- Do not keep a round because it "looks better".
- Do not treat lower model finding count as success when validators fail.
- Do not edit consumer code unless that file is explicitly in scope.
- Do not claim prompt readiness without artifacts and deterministic gates.

## Integration

| Skill | Role |
|-------|------|
| `/scillm` | LLM backend (concurrent model calls) |
| `/prompt-lab` | Template storage and ground truth |
| `/code-runner` | Consumer of reviewed prompts |
| `/best-practices-self-improvement-loop` | Required coded loop pattern |
| `/ask` | Required high-reasoning final/debug gate for high-stakes prompt contracts; optional for cheap inner rounds |
| `/surf` | Browser transport owned by `$ask` for WebGPT; do not call directly for normal prompt review |
