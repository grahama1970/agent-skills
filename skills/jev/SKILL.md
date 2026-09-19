---
name: jev
description: >
  Native typed decisions for Pi and Tau: choose skills and bounded tool-call
  candidates, classify intent/capability, rank Memory's ingest-code evidence,
  and preserve explicit abstention. Use when a small semantic decision would
  otherwise consume a generative-model turn. Pi has a TypeScript extension;
  Python exposes an importable API and registration decorator. Jev never owns
  retrieval, provider admission, execution, freshness, evidence authority or signoff.
triggers:
  - jev
  - typesafe
  - typed decision
  - pi skill routing
  - rank code recall
  - reduce harness tokens
provides:
  - typed-judgment
  - pi-context-and-skill-selection
  - python-tool-registration
  - bounded-tool-proposals
  - memory-candidate-reranking
  - model-capability-classification
composes:
  - memory
  - ingest-code
  - monitor-skills
  - tau
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
runtime_self_improvement: basic
disciplines:
  - engineering-standards
  - evaluation-quality
---

# Jev — small decisions, fewer unnecessary model turns

**Human orientation:** [README.md](README.md). **Immutable target:**
[immutable_goal.json](immutable_goal.json), explained in [IMMUTABLE_GOAL.md](IMMUTABLE_GOAL.md).
An implementation or passing fixture suite is not proof that the target is met.

## Ownership

| Owner | Responsibility |
|---|---|
| `ingest-code` | Extract/version the code projection; `ensure-current` checks target freshness. |
| Memory / graph-memory-operator | Retrieve scoped code, lessons, graph evidence and skill candidates; own intent/answerability and QRA state. |
| Jev | Semantic classification, candidate relevance and closed-set selection. |
| Pi extension | Assemble bounded context, narrow eligible skill metadata, preserve checkpoints and record usage. |
| `monitor-skills` | Catalog health/version evidence and drift monitoring, not live provider quotas. |
| Pi/Tau executor and provider adapters | Permissions, rate/capacity reservations, model admission, actual calls and completion evidence. |
| SPARTA | Domain-specific investigation/review presentation; not the sole Memory consumer. |

Two native implementations share the contract and conformance corpus. Pi never
spawns Python for a Jev call; Tau never needs Node for a Jev call.

## Runtime rules

1. Apply explicit user choices, deterministic rules, scope and policy first.
   Do not use Jev to run an already specified command, replace a local adequate
   classifier, or add a network hop to raw recall's fast path.
2. All hosted calls require explicit authorization and `public` or
   `approved_internal` classification. Scan the COMPLETE payload, including
   questions, criteria, candidate descriptions and argument values. Marker checks
   supplement authorization; they are not general DLP or compliance certification.
   Pi also requires the active provider/model in `memory.allowedModels` before
   sending retrieved source in model context; it rechecks after model changes.
3. `jev.decision.v1` binds the request, policy, question/candidate state and model.
   Validate answer types, submitted option domains, distributions and required
   questions. Missing/malformed data is `error`; doubt is `abstain`. A confident
   negative Noul is a negative judgment, never affirmative permission.
4. Keep unknown relevance candidates; remove only confident negatives, and never
   remove pinned requirements. Empty retrieval, all-irrelevant, uncertainty and
   dependency failure are different states. Preserve locators and source hashes.
5. A code hit is a repair candidate, not current-source or bug-localization proof.
   Before edits, use supported `code-node` / `ingest-code ensure-current` through
   the host. Stale or incomplete projection needs scoped investigation/refresh;
   do not overwrite canonical main from a repair worktree.
6. Tool decorators/registries only construct validated candidates. Bind arguments
   from known state or enumerated values. No generated shell, arbitrary arguments,
   automatic callbacks, DAG ownership, release decisions or QRA signoff.
7. Capability judgment is semantic. Model pricing, qualification, user pins,
   context fit, quota/cooldown and atomic capacity reservations are deterministic
   host duties. `choose_model` / `chooseModel` recommends from supplied snapshots;
   it does not reserve, switch or dispatch a model.
8. Memory ANSWER does not complete implementation work. Consume shared outcomes
   through `memory_disposition` / `memoryDisposition`. CLARIFY/DRAFT checkpoints
   stay human-owned; domain no-match is not a policy denial. Generic README/code
   drafting is not the QRA `/draft` workflow.
9. SDK retries are disabled; the host owns fallback. Deadlines/cancellation must
   not publish late results. Default Pi mode is off, then shadow, then a qualified
   active canary. Do not infer consent from the presence of an API key.

## Surfaces

| Surface | Entry point |
|---|---|
| Pi extension | `typescript/pi.ts`, project `.pi/jev.json` |
| TypeScript library | `typescript/runtime.ts`: `Jev`, `classify`, `select`, `rank` |
| Python library | `jev_runtime`: `Jev`, `classify`, `select`, `rank`, `tool` |
| Model/Memory reducers | `jev_runtime/routing.py`, `typescript/routing.ts` |
| Existing question CLI | `./run.sh tasks`, `gate`, `ask`; `jev.receipt.v1` retained |
| Shared instructions | `jev_runtime/contract.json` |
| Cross-language fixtures | `contracts/conformance.json` |

The Pi implementation currently ranks a bounded set of Memory and skill
candidates in one request. It reads `/intent` only in optional fast mode, reads
scoped `/recall`, never invokes `/draft/signoff`, and never independently
re-decides backend answerability. It does not automatically switch providers
or bypass Pi/Tau's execution path. Full terminal-response UI adapters and live
Tau wiring still require deployment-specific qualification.

## Installation and checks

```bash
# Prepare dependencies explicitly; normal runner calls do not resolve/download.
uv sync --extra live --extra test
npm install

./run.sh tasks
./run.sh gate --state '{"note":"synthetic"}'
./run.sh ask --preset goal_drift --state @state.json --allow-egress

./sanity.sh                 # offline contract suites; no implicit live call
./sanity.sh --live          # explicitly authorizes one synthetic SDK probe
npm run typecheck
```

The CLI's `--allow-egress` authorizes its complete payload as approved internal
material; restricted markers still block. Libraries require an explicit `Policy`.
No command reads credentials from shell startup files. The live SDK supports
`JEV_API_KEY` or `TYPESAFE_API_KEY`; dependency/setup and missing-key failures
must not be reported as successful judgments.

## Measurement and proof boundaries

Use matched tasks and include a deterministic-cleanup baseline. Measure main
model tokens/cache/cost, Jev usage, total elapsed time, required evidence retention,
correct skill/tool selection and independently verified task success. Character
counts are not token measurements. `0.98` is an initial acceptance bar, not proven
98% accuracy. Do not turn offline contract fixtures into a live efficacy claim.

Pi writes decision and usage metadata as session entries outside model context.
It does not POST telemetry to Memory on the hot path. An owning monitor may ingest
those receipts through supported Memory APIs; no direct ArangoDB/Qdrant access.
