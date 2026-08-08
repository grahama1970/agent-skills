---
name: project-drift
description: >
  Conservative project knowledge drift auditor. Use when a human or hook asks to
  check whether recent Codex/Claude transcript evidence contradicts, stale-dates,
  resolves, or materially changes curated PROJECT_KNOWLEDGE.md claims.
triggers:
  - project drift
  - check project knowledge drift
  - detect stale project knowledge
  - scan transcript for drift
  - drift candidates
  - compare transcript to project knowledge
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
provides:
  - project-knowledge-drift-report
  - drift-candidate-generation
  - transcript-cleaning
  - drift-prompt-payload
composes:
  - project-knowledge
  - memory
  - scillm
  - agentic-evals
taxonomy:
  - knowledge-management
  - validation
  - drift-detection
disciplines:
  - evaluation-quality
  - observability-operations
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE RUNNING OR PATCHING THIS SKILL.

# /project-drift

Conservative auditor for detecting when recent session evidence may contradict or stale-date curated project knowledge.

## Purpose

`/project-drift` does **not** update `PROJECT_KNOWLEDGE.md` and does **not** write authoritative memory.

It produces a review artifact:

```text
recent transcript/tool evidence
  + current PROJECT_KNOWLEDGE.md claims
  -> cleaned evidence
  -> drift prompt payload
  -> drift_report.json candidates
```

`/project-knowledge` remains the authority that writes `PROJECT_KNOWLEDGE.md` and syncs chunks into `/memory` / ArangoDB.

`/memory` remains the authority for searchable durable recall. This skill may
read current `PROJECT_KNOWLEDGE.md` claims and produce candidate artifacts, but
it must not write memory or bypass `/project-knowledge` sync.

## What Counts As Drift

A drift candidate must satisfy all three conditions:

1. A specific `project_knowledge` claim is affected.
2. Recent evidence is concrete: verifier result, successful command, artifact, commit, file change, or explicit human statement.
3. Future agents would behave differently if the claim were updated.

Valid drift kinds:

| Kind | Meaning |
|------|---------|
| `contradiction` | Project knowledge says X; evidence shows not-X. |
| `stale_status` | Project knowledge status is now stale, such as broken -> fixed or fixed -> broken. |
| `workflow_drift` | Documented workflow A appears replaced by verified workflow B. |
| `contract_drift` | Path, schema, artifact, command, or gate contract changed. |
| `resolved_open_question` | An open question now has evidence-backed resolution. |
| `new_blocking_question` | Recent evidence exposes a new blocker. |
| `missing_high_impact_knowledge` | A missing fact would change future execution. Rare; candidate-only. |

Reject routine additions. This is not a session summarizer.

## Commands

```bash
# Scan a transcript and write artifacts under .project-drift/latest
./run.sh scan --transcript /path/to/transcript.jsonl

# Build artifacts only; do not call any LLM endpoint
./run.sh scan --transcript /path/to/transcript.jsonl --no-execute

# Use explicit project root and output directory
./run.sh scan --project-root /path/to/repo --transcript /path/to/transcript.jsonl --out-dir /tmp/drift

# Clean a transcript into compact observations
./run.sh clean-transcript --transcript /path/to/transcript.jsonl --out cleaned.json

# Build prompt payload from cleaned evidence and PROJECT_KNOWLEDGE.md
./run.sh build-prompt --cleaned cleaned.json --out prompt_payload.json

# Validate a drift report against the schema
./run.sh validate-report drift_report.json

# Print JSON schema
./run.sh schema

# List likely transcript files for current project/user
./run.sh list-transcripts
```

## Outputs

`scan` writes:

```text
.project-drift/latest/
  cleaned_transcript.json
  project_knowledge_claims.json
  prompt_payload.json
  drift_report.json        # only if --execute succeeds
  scan_summary.json
```

## Hook Usage

Run at boundaries, not after every tool call.

Recommended triggers:

- Codex/Claude `Stop`
- `/checkpoint` completed
- `/orchestrate` stage completed
- verifier/report artifact completed

Do **not** block execution for candidate-only additions. Block only when a report returns `verdict=block` and cites a specific stale/contradicted claim that affects current execution.

## LLM Execution

By default, `scan` builds the prompt payload and writes it to disk. To call an OpenAI-compatible endpoint, pass `--execute` and set:

```bash
export PROJECT_DRIFT_LLM_BASE_URL="http://127.0.0.1:4001"   # scillm/OpenAI-compatible endpoint
export PROJECT_DRIFT_LLM_API_KEY="..."                      # optional
```

The skill does not import provider SDKs. It sends an OpenAI-compatible
`/v1/chat/completions` request when requested and tags the call with
`x-caller-skill: project-drift`.

## Codex Transcript Support

Current Codex JSONL stores most useful records under top-level `payload`
objects, including `response_item` records with `function_call` and
`function_call_output` payloads. `scan` must produce nonzero observations for a
real session containing user messages, assistant messages, or tool calls. A
zero-observation scan is a parser failure unless the transcript is genuinely
empty after the selected `--since` / `--tail` window.

## Common Mistakes

### WRONG: Auto-update project knowledge from a hook

```text
Stop hook -> project_drift -> PROJECT_KNOWLEDGE.md updated
```

### RIGHT: Produce a candidate artifact

```text
Stop hook -> project_drift -> drift_report.json -> human/agent review -> project_knowledge update
```

### WRONG: Treat successful tool calls as durable knowledge

A successful `ls`, `grep`, `Read`, or `cat` is usually routine evidence.

### RIGHT: Require evidence plus future impact

A verifier pass, changed artifact contract, resolved open question, or explicit human decision can justify a candidate.

## Safety Boundary

- No direct ArangoDB access.
- No authoritative memory writes.
- No `PROJECT_KNOWLEDGE.md` edits.
- JSON drift report only.
- `/project-knowledge` performs accepted updates.
- `/project-knowledge` path/project precedence is respected through
  `--knowledge-file`, `PROJECT_KNOWLEDGE_PATH`, and `PROJECT_KNOWLEDGE_PROJECT`.
