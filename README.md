# Agent Skills

![agent-skills header](docs/assets/agent-skills-header.webp)

**Agent Skills** is a playground and toolbox for agent work: reusable
capabilities, bounded workers, persona contracts, scheduler jobs, and lifecycle
hooks. It is where patterns are tried, hardened, reused, and sometimes retired.
If you are building with agents, start here. If you are deploying inside this
ecosystem, this repo is the source of truth; project-local copies are consumers.

If you have ever written a browser automation script, then written another one
three months later because you could not find the first, this repo is for you.
Agent Skills is contract-first: every durable capability has a `SKILL.md`
contract, a stable entrypoint, and a proof surface. The goal is reusable,
bounded, documented agent work instead of orphaned scripts.

> **Public repo, private runtime note:** the code, prompts, contracts, and
> documentation are public, but some operational paths expect private/local
> infrastructure: memory services, browser bindings, model gateways, media
> storage, credentials, or project-specific agent homes. Treat this repo as a
> working blueprint and research playground, not a finished turnkey SDK. Many
> patterns are reusable as-is, but not every command is expected to run in a
> fresh external clone without adapting the environment.

## Start Here

```bash
# Find skill contracts
find skills -maxdepth 2 -name SKILL.md | sort

# Find agent contracts
find agents -maxdepth 2 \( -name AGENTS.md -o -name persona.yaml \) | sort

# Read the persona registry guide
sed -n '1,160p' personas/README.md

# Inspect the latest maintainer triage report
sed -n '1,180p' reports/agent-maintainer/latest.md
```

**Pro tip:** `README.md` files are human guides; `SKILL.md` files are operational
contracts. If someone names a skill, read its `SKILL.md` first. That file is the
source of truth for how the capability behaves.

Local deployment is for configured agent environments:

```bash
# Deploy skills and hooks to local agent homes
./deploy.sh

# Preview what would change
./deploy.sh --check
```

## Developer Compass

| If you want to... | Start here | What to expect |
|---|---|---|
| Solve a specific task | `skills/` | Browser automation, memory recall, video analysis, code review, model calls, and other modular capabilities |
| Understand agent behavior | `agents/` | Bounded worker contracts, reviewer roles, stop conditions, receipts, and scheduler definitions |
| Study persona and memory patterns | `personas/` | Persona registry records, memory probes, and voice-readiness evidence |
| Borrow guardrails | `hooks/` | Memory-first behavior, quality gates, and completion discipline |
| Find maintenance work | `reports/agent-maintainer/` | Report-only triage surfaces; warnings are leads, not proof of broken behavior |

## Choosing The Right Surface

| I want to... | Go to | Because |
|---|---|---|
| Invoke an existing capability | `skills/<name>/run.sh` and `skills/<name>/SKILL.md` | Skills own executable behavior, routing rules, artifacts, and proof language |
| Learn how a capability works | `skills/<name>/README.md` | Skill READMEs are operator-facing guides |
| Repair or extend a capability | `skills/<name>/SKILL.md`, scripts, tests, `sanity.sh` | Contract changes need focused implementation and proof |
| Delegate bounded work | `agents/<name>/AGENTS.md` plus `persona.yaml` | Agents define ownership, denied scope, allowed skills, receipts, and stop conditions |
| Inspect persona availability | `personas/registry.yaml` and `personas/README.md` | Personas are registry records, not generated corpora |
| Enforce session behavior | `hooks/` | Hooks inject memory, block unsafe exits, and enforce evidence discipline |
| Make maintenance decisions | `reports/agent-maintainer/latest.md` | Reports are decision surfaces, not dashboards |

## Current Inventory

Latest sweep: `msh-20260628-084135`

| Inventory | Count |
|---|---:|
| Skills | 330 |
| With `run.sh` | 285 |
| With `sanity.sh` | 278 |
| Agent directories | 72 |
| With `AGENTS.md` | 69 |
| With `persona.yaml` | 47 |
| With `services.yaml` | 6 |

Health check: 171 healthy, 158 warnings, 1 critical. These are triage numbers,
not quality scores. See the report before making maintenance decisions.

Reports live at:

```text
reports/agent-maintainer/latest.md
reports/agent-maintainer/latest.json
reports/agent-maintainer/latest.html
reports/agent-maintainer/runs/<run_id>/
```

## Repository Map

```text
agent-skills/
  skills/                  reusable capabilities with SKILL.md contracts
  agents/                  bounded workers, reviewers, monitors, maintainers
  personas/                persona registry, schemas, and guide
  hooks/                   lifecycle gates and prompt hooks
  scripts/                 repo maintenance, checks, and queue runners
  reports/agent-maintainer latest repo sweep for human decisions
  deploy.sh                broadcast skills and hooks to local agent homes
  workers-registry.json    generated worker registry
```

## Skills

`skills/` holds 330 capabilities. Each durable skill is a directory with a
contract, entrypoint, and proof surface:

```text
skills/<name>/
  SKILL.md            the contract; read this first
  README.md           human guide when you need context
  run.sh              the stable entrypoint
  sanity.sh           cheap local proof
  scripts/            implementation details
  references/         schemas, examples, templates
```

**Do not write a parallel utility** for browser automation, LLM calls, memory
recall, report writing, GitHub tickets, code review, video analysis, or
scheduled monitoring until you have checked the skill list and maintainer
report. Reuse first.

Typical invocation:

```bash
cd skills/surf
./run.sh tab.list --json
```

## Agents

`agents/` holds 72 bounded workers. Unlike skills, agents are not broadcast; they
are referenced by project-agent/OpenCode configuration and maintainer routing.

A good agent has a narrow boundary:

- what it owns
- what it **does not** own
- which skills it may call
- what artifacts prove a turn
- when it must stop or ask for help

Normal shape:

```text
agents/<name>/
  AGENTS.md
  persona.yaml
  services.yaml       only for scheduled jobs
```

Missing `persona.yaml` is a normalization candidate, not proof the worker is
broken.

## Personas

`personas/` is the roster and contract layer for persona work, not a storage dump
for generated character assets.

```text
personas/
  README.md
  registry.yaml
  schemas/persona-registry.schema.json
```

The registry points to source directories, memory probes, and voice-readiness
receipts. Runtime memory lives in `$memory`; generated media and voice artifacts
live under their own storage or skill job paths.

## Hooks

Hooks run around agent lifecycle events. They keep behavior honest:

- **memory first**: no shortcuts that skip context
- **no destructive shell**: safety rails on commands
- **no fake green exits**: if it failed, say so
- **evidence required**: vague completion claims without proof are blocked

Deploy:

```bash
./deploy.sh --hooks
```

Important paths:

```text
hooks/memory-first.sh
hooks/quality-gate.sh
hooks/task-complete-gate.sh
hooks/prompts/
```

## Maintainer Loop

Two roles, one issue at a time:

| Role | Owns | Does not own |
|---|---|---|
| `agent-maintainer` | Scheduled report-only sweeps; latest reports; candidate next actions | Automatic deprecation, deletion, repair, or issue closure |
| `skill-maintainer` | One GitHub issue lease at a time; repair routing; verifier/review/WebGPT evidence bundle; proof-based issue disposition | Broad untracked cleanup, multi-issue repair, closure from WebGPT alone |

Run the report-only sweep:

```bash
mkdir -p reports/agent-maintainer
skills/monitor-skill-health/run.sh audit \
  --no-memory \
  --no-deep-review \
  --repo-report \
  --json > reports/agent-maintainer/last_run.json
```

The scheduled job is registered in `agents/agent-maintainer/services.yaml` but
**disabled by default**. Enable it only when the scheduler environment is ready
and you want the cron active.

## Adding Things

**Add a skill** when the capability is reusable and needs a contract, entrypoint,
and proof. **Add an agent** when a bounded role, receipts, and stop conditions
matter.

One-off scripts, product features, broad cleanup, and standalone prompts belong
elsewhere unless they fit an existing skill or agent contract.

### New Skills

- Put the operating contract in `SKILL.md`
- Use `run.sh` as the stable entrypoint
- Add `sanity.sh` for cheap local proof
- **Reuse existing skills before adding infrastructure**
- Keep generated outputs and heavy artifacts out of the skill directory unless
  the contract explicitly says otherwise

### New Agents

- Define the owner boundary in `AGENTS.md`
- Encode the role in `persona.yaml`
- Add `services.yaml` only for scheduled jobs
- **Avoid agents that own detection, mutation, queueing, and closure all at once**

## Proof And Non-Claims

The maintainer sweep was local and deterministic: no mocks, no live calls, and
no exercise of runtime behavior.

| What was checked | What was not |
|---|---|
| 330 skills via `monitor-skill-health audit` | Semantic correctness of each skill |
| Shallow `agents/` metadata inventory | Runtime behavior of each agent |
| | Live scheduler daemon registration |
| | Live GitHub issue mutation |

Rerun the sweep after substantial changes. Use
`reports/agent-maintainer/latest.md` before final maintenance decisions.
