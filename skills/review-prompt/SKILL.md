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
metadata:
  short-description: Multi-model prompt review loop via /scillm batch
provides:
  - prompt-review
  - prompt-contract-review
  - deterministic-prompt-improvement
composes: [scillm, prompt-lab, best-practices-self-improvement-loop, ask]

taxonomy:
  - prompt-engineering
  - llm
---

# review-prompt — Deterministic Prompt Review Loop

Concurrent multi-model review of prompt contracts with deterministic scoring.
Same autoresearch pattern as `/code-runner`, but the loop must be coded. The
agent invokes the loop; the agent is not the loop.

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

## How It Works

```
1. Preflight inputs and configured gates deterministically.
2. Read prompt bundle, validators, source files, consumer code, and tests.
3. Try the next ordered improvement strategy.
4. Send the bundle to N models concurrently via `/scillm`.
5. Parse findings into `critical`, `major`, and `minor`.
6. Apply only bounded fixes allowed by the current strategy.
7. Run validators, fixture checks, and configured smoke checks.
8. Score the round from model findings plus deterministic gate failures.
9. Keep only if score improves and no required gate regresses; otherwise revert.
10. Write all request, response, score, diff, gate, and keep/revert artifacts.
11. Run `$ask` deep review as the final gate when required by scope or `--ask-gate`.
12. Stop on gate pass, score 0, max rounds, blocked preflight, exhausted strategies, or `$ask` blocker.
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
  --max-rounds 2
```

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
| `--validator` | Deterministic validation command; may repeat |
| `--smoke` | Consumer compatibility or runtime smoke command; may repeat |
| `--gate` | Gate override such as `max_critical=0`; may repeat |
| `--strategy` | Strategy override; may repeat, otherwise use default order |
| `--artifact-root` | Directory for round artifacts and terminal audit |
| `--ask-gate` | Run `$ask --deep-review` as the final readiness/debug gate |
| `--ask-model` | `$ask` oracle model for the final gate (default: `gpt-5.5`) |
| `--ask-reasoning` | `$ask` oracle reasoning effort for the final gate (default: `high`) |

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
```

Write artifacts after every iteration, before deciding whether to continue.

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
