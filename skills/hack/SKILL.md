---
name: hack
description: >
  Containerized hardening validation and authorized security auditing tools.
  All operations run in isolated Docker containers for safety.
allowed-tools:
  - run_command
  - read_file
triggers:
  - hack
  - scan
  - audit
  - security check
  - red team
  - blue team
metadata:
  short-description: Containerized hardening validation and security auditing
  requires: docker
provides:
  - security-scan
  - docker-isolation
composes:
  - memory
  - skills-broadcast
  - scheduler
  - task-monitor
  - code-runner

taxonomy:
  - security
  - corruption
  - stealth
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Hack Skill

**Containerized hardening validation and authorized security auditing tools.**

All security operations run in **isolated Docker containers** - no tools execute on the host system. This ensures:

- Isolation from host filesystem and network
- Reproducible scanning environment
- No risk of tool vulnerabilities affecting host
- Safe execution of bounded proof probes for patching and hardening authorized systems

## Prerequisites

- **Docker Engine** must be installed and running
- The security container image will be built automatically on first use

## Commands

### Network Scanning

```bash
# Basic port scan
./run.sh scan 192.168.1.1

# Service detection scan
./run.sh scan 192.168.1.1 --scan-type service

# Vulnerability scripts
./run.sh scan 192.168.1.1 --scan-type vuln --ports 22,80,443

# Save results
./run.sh scan 192.168.1.1 --output scan_results.txt
```

### Static Application Security Testing (SAST)

```bash
# Full audit (Semgrep + Bandit)
./run.sh audit /path/to/code

# Semgrep only
./run.sh audit /path/to/code --tool semgrep

# Bandit only (Python)
./run.sh audit /path/to/code --tool bandit

# Filter by severity
./run.sh audit /path/to/code --severity high

# Use threat profile for deeper audit
./run.sh audit /path/to/code --profile state-actor
```

### Hybrid Correlation

The skill automatically correlates **DAST** (Nuclei/Nmap) findings with **SAST** (Semgrep/Bandit) origins via `correlation.py`. When both tools verify a vulnerability class (e.g., SQL Injection), the confidence is boosted to **VERIFIED** in the reports.

### Software Composition Analysis (SCA)

```bash
# Check Python dependencies for vulnerabilities
./run.sh sca /path/to/project

# Use safety instead of pip-audit
./run.sh sca /path/to/project --tool safety
```

### Check Available Tools

```bash
./run.sh tools
```

### Full Containerized Session Audit

```bash
# Generate a session Dockerfile, clone the target in Docker, launch it, scan it, and report
./run.sh session-audit https://github.com/SasanLabs/VulnerableApp.git

# Keep the target compose stack running for manual follow-up
./run.sh session-audit https://github.com/SasanLabs/VulnerableApp.git --keep-running

# Opt into bounded exploit proof probes for remediation after scans
./run.sh session-audit https://github.com/SasanLabs/VulnerableApp.git --probe-exploits

# Evolutionary greybox hardening campaign using feedback-guided strategy mutation
./run.sh evolve-campaign http://127.0.0.1:18789 \
  --last-plan session-*/reports/HACK_REPORT.md \
  --scanner-findings session-*/reports/semgrep.json \
  --dogpile-report openclaw-hardening-dogpile.md \
  --duration-minutes 60 \
  --max-generations 4 \
  --max-attempts 1000 \
  --population-size 16 \
  --seed 1234

# Advanced red/blue hardening arena
./run.sh battle /path/to/codebase --rounds 100
```

`session-audit` is the end-to-end `$hack` workflow. It creates
`/mnt/storage12tb/artifacts/agent-skills/hack/session-*`, writes a per-session
scanner `Dockerfile` and `docker-compose.yml`, installs required scanner tools
including `semgrep`, `nmap`, and `nuclei`, clones the authorized target through
that scanner container, resolves a target launch plan, launches the target
Docker compose stack, runs SAST/DAST from containers, writes
`reports/HACK_REPORT.md`, and emits a distilled `reports/memory-payload.json`
with artifact pointers.

Target launch is discovery-driven. `$hack` first uses the requested compose
file. If that is missing, it searches for common compose filenames while
skipping large/internal trees such as `.git`, `node_modules`, `dist`, and build
artifacts. If no compose file exists but a root `Dockerfile` exists, `$hack`
writes `target-launch/docker-compose.generated.yml`, infers the service port
from Dockerfile/README/env/package metadata, and records the decision in
`reports/target-launch-plan.json`. For OpenClaw-style gateway repos, this lets
`$hack` discover the gateway compose/port before DAST and proof-probe planning.

Exploit proof for remediation is opt-in. With `--probe-exploits`, `$hack` uses
`/code-runner` only to generate and DoD-verify bounded local proof probes under
the session `attack-workspace`; `$hack` then executes those probes inside the
generated scanner Docker container and writes proof artifacts under
`session-*/attacks`. The purpose is to validate exploitable weaknesses so the
authorized target can be patched, prioritized, and hardened. Reports must state
this boundary explicitly: `/code-runner` generates probe code, `$hack` executes
probes in Docker, and every successful proof must produce a hardening task or
patch plan. Raw proof and replay details stay in artifacts; `HACK_REPORT.md`
leads with the executive remediation result and artifact paths.

`evolve-campaign` is the adaptive exploit-discovery and hardening mode. Its
first population is the former `chaos-campaign` idea: broad uncommon
combinations that are expected to mostly fail. Those failures are useful
negative evidence for scoring, pruning, mutation, Dogpile reseeding, and the
next campaign plan.

The evolve lifecycle follows this loop:

1. Report findings, crashes, auth anomalies, SAST leads, DAST leads, and proof
   artifacts from the previous plan.
2. Feed that distilled evidence into `/dogpile` with a concrete prompt that
   asks for new high-level and low-level hardening approaches.
3. Convert the last plan, `/dogpile` synthesis, and scanner findings into a
   campaign genome.
4. Run randomized uncommon combinations in Docker: protocol/auth flows,
   WebSocket handshakes, OpenAI-compatible HTTP routes, plugin/hook/session
   routes, forwarded-header variants, path/body/header/parser mutations, and
   bounded crash/slow-response checks.
5. Promote anomalies into focused proof probes and blue-team patch tasks.
6. Repeat by feeding promoted anomalies into the next `/dogpile` query and
   campaign seed.

The hidden `chaos-campaign` CLI remains only as a compatibility entrypoint for
generation-zero broad exploration. It is not a third top-level `/hack` mode.
The three top-level `/hack` modes are:

1. `session-audit` — scanner/proof/report workflow for an authorized repo or
   target.
2. `evolve-campaign` — broad uncommon-combination exploration plus scoring,
   pruning, mutation, reproducibility gates, Dogpile reseeding, proof
   promotion, and patch/hardening hypotheses.
3. `battle` — advanced red/blue live hardening arena delegated to sibling
   `/battle`, where red attacks a running repo/system and blue patches or
   hardens under scoring.

Evolution artifacts are written under `evolve-campaign-*`: `preflight.json`,
`baseline.json`, `auth-sessions.json`, `strategies.seed.json`,
`loop-contract.json`, `attempts.jsonl`, `anomalies.jsonl`,
`generation-*.json`, `promotion-tasks/`, `summary.json`,
`HACK_EVOLVE_REPORT.md`, `next-dogpile-seed.json`, and Docker execution logs
for live runs. Thousands of failed attempts are normal; one deterministic
anomaly is enough to drive the next focused proof and patch cycle.

The Docker contents are plan-driven. By default `$hack` writes
`scanner/plan.json` with the base image, apt packages, pip packages, Nuclei
version, Semgrep config, and scan lanes. Default scanner package versions are
pinned so repeated runs do not depend on pip resolver drift. A different
strategy may provide a JSON plan file or additive packages:

```bash
./run.sh session-audit https://github.com/SasanLabs/VulnerableApp.git \
  --plan-file ./hack-docker-plan.json \
  --apt-package masscan \
  --pip-package detect-secrets
```

If a scanner attempt fails because required tooling is missing, the deterministic
self-improvement loop should produce a revised plan that changes
`scanner/plan.json` and therefore changes the generated Dockerfile before the
next attempt.

`evolve-campaign` uses the Docker-contained safety boundary and a feedback loop
inspired by the arXiv greybox fuzzing papers:

1. Build a route/payload/header genome from prior reports, dogpile synthesis,
   scanner findings, and built-in hardening genes.
2. Execute bounded probes against local/private authorized targets only.
3. Score attempts with cheap greybox signals: HTTP status, WebSocket upgrade,
   reset/error class, timing, disclosure tokens, sensitive-route success, and
   source lineage.
4. Select high-scoring parent genes and mutate one axis at a time while keeping
   lineage metadata.
5. Promote deterministic anomalies into focused proof-probe objectives and
   blue-team patch hypotheses.

Use `--dry-run` to write deterministic synthetic artifacts without sending
network probes.

`battle` is `/hack`'s advanced third mode. It delegates execution to the sibling
`/battle` skill rather than duplicating the red/blue game loop. Use it when the
goal is an adversarial live hardening arena, not a normal repo-to-report audit:

```bash
./run.sh battle /path/to/codebase --rounds 100
./run.sh battle /path/to/codebase --overnight
./run.sh battle --docker-image nginx:latest --rounds 100
```

Battle artifacts are owned by `/battle`: red and blue team memory directories,
round episodes, checkpoints, scores, and battle reports. `/hack` treats battle
as the third top-level mode because red uses `/hack`-style attack/proof
capabilities while blue records patches, broken defenses, and hardening lessons.

### Isolated Hardening Proof Execution

```bash
# Run a bounded proof probe in an isolated container
./run.sh exploit --target 192.168.1.50 --env python --payload exploit.py

# Interactive shell in isolated environment
./run.sh exploit --target 192.168.1.50 --env kali --interactive

# Novel Iterative Hardening Proofs (Chaos Mode)
# Enforces mandatory research phase and iterative feedback loop with bounded probes
./run.sh exploit --target 192.168.1.50 --chaos --max-retries 5
```

### Threat Profiles

Use `--profile` to adjust scanning intensity and stealth:

| Profile           | Strategy       | Nmap Timing | Use Case                |
| ----------------- | -------------- | ----------- | ----------------------- |
| `script-kiddie`   | Loud & Fast    | `-T4`       | Quick baseline          |
| `hobbyist`        | Standard       | `-T3`       | General audit (Default) |
| `organized-crime` | Stealthy       | `-T2`       | Stealth testing         |
| `state-actor`     | Expert Stealth | `-T1`       | Depth & evasiveness     |

Example:

```bash
./run.sh scan 10.0.0.5 --profile state-actor
```

### Knowledge Base & Research

```bash
# Fetch exploits from Exploit-DB
./run.sh learn --source exploit-db

# Search GitHub for CVE PoCs
./run.sh learn --source github --query "CVE-2024-1234"

# Deep research via dogpile
./run.sh research "buffer overflow mitigation techniques"

# Update exploit feeds (CVE monitoring)
./run.sh update-exploits --source github
```

### Dogpile Scan Request Validation

Dogpile can hand Hack a bounded scan-request packet for future execution
planning:

```bash
./run.sh validate-scan-request fixtures/hack-scan-request/valid.json \
  --expected-target fixture-target@sha256:fixture \
  --receipt-out /tmp/hack-scan-request-validation.json
```

This command only validates the `dogpile.hack_scan_request.v1` data contract and
writes `hack.scan_request_validation_receipt.v1`. It does not invoke Docker,
subprocess scanners, network probes, target launch, exploit execution, patching,
or Battle scoring. A valid request is research design input only; it is not
target authorization and cannot be executed until the authorization-manifest,
Compose-policy, sterile-environment, and independent-proof-authority gates exist.

### Target Authorization Manifest

Execution-capable Hack commands require a `security.target_authorization.v1`
manifest before Docker, clone, scanner, network probe, proof-probe, or target
runtime setup can start:

```bash
./run.sh authorization-preflight \
  --authorization-manifest fixtures/authorization/valid-local.json \
  --target fixture-target@sha256:fixture \
  --action session-audit \
  --receipt-out /tmp/hack-authorization-preflight.json
```

The manifest records project/operator scope, target identity, allowed URLs,
CIDRs, ports, actions, probe classes, runtime modes, resource budgets, and
denied behavior. It is not a legal opinion and does not prove Docker isolation,
source truth, exploitability, patch effectiveness, or Battle readiness.

### Proof Authority Boundary

Hack probe output is split into observation and validation authorities:

```bash
./run.sh prove-proof-authority \
  --fixture fixtures/proof-authority \
  --out /tmp/hack-proof-authority
```

`hack.probe_observation.v1` records what a bounded Hack probe observed. It
binds target identity, authorization-manifest hash, runtime hash, scan/probe
hashes, executor identity, exit code, signal type, and sanitized evidence
artifacts. It always sets `exploit_confirmed=false`.

`hack.proof_validation_receipt.v1` is the only Hack-side receipt that can set a
session status to `CONFIRMED`, and only when an independent validator binds the
exact observation artifact hash, target/auth/runtime/probe/scan hashes, replay
spec hash, replay receipt hash, and validator identity. The validator identity
must differ from the Hack executor. In Battle workflows this validator is the
Battle Judge.

Reports and memory payloads use the closed status vocabulary
`NOT_ATTEMPTED`, `OBSERVED_UNCONFIRMED`, `CONFIRMED`, `REJECTED`, and
`VALIDATION_ERROR`. A file named `proof.*`, a zero exit code, or a Hack-authored
artifact is never sufficient to set `exploit_proven=true`.

## Architecture

```
+-------------------+     +------------------------+
|   Host System     |     |  Docker Container      |
|                   |     |  (hack-skill-security) |
| ./run.sh scan ... | --> |  nmap, semgrep, bandit |
|                   |     |  pip-audit, safety     |
| (No tools here)   |     |                        |
+-------------------+     +------------------------+
        |                          |
        +--- Results returned -----+
```

## Red Team / Blue Team Usage

### Red Team (Hardening Validation)

- `scan` - Discover open ports and services
- `audit` - Find vulnerabilities in target code
- `exploit` - Execute bounded proof probes in an isolated environment to confirm patch priority
- `learn --source github` - Find CVE proof techniques for authorized remediation
- `prove --negate` - Find counterexamples to security claims

### Threat Intelligence

- `update-exploits` - Monitor latest CVEs and exploit feeds
- `research` - Trigger mandatory research phase before exploits
- `chaos` - Generate novel/insane exploit ideas via Codex
- `task-monitor` - Dynamic progress tracking for all sessions

## Memory Integration

The hack skill is **deeply integrated** with the memory skill - the brain of the entire project.

### Automatic Memory Recall

All scanning and audit commands automatically query memory for relevant prior knowledge before execution:

- Previous scanning techniques that worked
- Known vulnerabilities and their mitigations
- Proof-probe patterns, patch plans, and defenses

```bash
# Scan with memory recall (enabled by default)
./run.sh scan 192.168.1.1

# Disable memory recall for faster scans
./run.sh scan 192.168.1.1 --no-recall
```

### Explicit Memory Commands

```bash
# Store security knowledge
./run.sh remember "Use nmap -sV for service detection" --title "nmap tips"
./run.sh remember "CVE-2024-1234 affects version 1.0-1.5" --tags "cve,critical"

# Recall knowledge
./run.sh recall "nmap scanning techniques"
./run.sh recall "buffer overflow exploits" --k 10
```

### Knowledge Flow

```
+----------------+     +---------------+     +------------------+
| hack skill     | --> | memory skill  | --> | Future Sessions  |
|                |     |               |     |                  |
| - scan results |     | - Store       |     | - recall before  |
| - audit finds  |     | - Embed       |     |   operations     |
| - exploits     |     | - Index       |     | - learn from     |
|                |     |               |     |   past attempts  |
+----------------+     +---------------+     +------------------+
```

## Leveraged Skills

The hack skill **delegates** to sibling skills rather than duplicating functionality:

### Core Integrations (Direct Commands)

| Skill          | Command               | Purpose                                                  |
| -------------- | --------------------- | -------------------------------------------------------- |
| `memory`       | (automatic)           | Recall prior proof, patch, and hardening lessons before every operation |
| `anvil`        | `hack harden`         | Thunderdome multi-agent red teaming                      |
| `ops-docker`   | `hack docker-cleanup` | Container pruning and management                         |
| `treesitter`   | `hack symbols`        | Parse code structure before auditing                     |
| `taxonomy`     | `hack classify`       | Tag findings with bridge tags (Loyalty, Fragility, etc.) |
| `task-monitor` | (automatic)           | Track long-running scan progress                         |

### Research Integrations (via `hack research`)

| Skill         | Usage                          |
| ------------- | ------------------------------ |
| `dogpile`     | Deep multi-source research     |
| `arxiv`       | Academic security papers       |
| `perplexity`  | Real-time threat intelligence  |
| `lean4-prove` | Formal security verification   |
| `learn`       | Knowledge extraction & storage |

### Skill Delegation Examples

```bash
# Red-team a codebase via anvil Thunderdome
./run.sh harden /path/to/code --issue "SQL injection in auth"

# Clean up Docker via ops-docker
./run.sh docker-cleanup --until 24h --execute

# Extract code symbols via treesitter before audit
./run.sh symbols /path/to/file.py --content

# Classify findings via taxonomy for graph storage
./run.sh classify "SQL injection vulnerability in login handler"
```

## Safety Notes

1. **Authorized Hardening Only** - Only use against systems you have permission to test, patch, or harden
2. **Isolated Execution** - All tools run in Docker containers
3. **Network Isolation** - SAST audits run with `--network=none`
4. **Read-Only Mounts** - Target directories mounted read-only
5. **Remediation Purpose** - Bounded proof probes exist to validate and prioritize fixes, not to enable misuse

## Example Workflows

### Vulnerability Assessment

```bash
# 1. Scan network
./run.sh scan 192.168.1.0/24 --scan-type basic

# 2. Audit discovered services
./run.sh audit /path/to/webapp --severity medium

# 3. Check dependencies
./run.sh sca /path/to/webapp
```

### Hardening Proof Validation

```bash
# 1. Research the vulnerability
./run.sh learn --source github --query "CVE-2024-XXXX"

# 2. Test bounded proof probe in isolation
./run.sh exploit --target test-vm --env python --payload poc.py

# 3. Verify fix with formal methods
./run.sh prove --claim "buffer overflow impossible after patch"
# 3. Verify fix with formal methods
./run.sh prove --claim "buffer overflow impossible after patch"
```

## Deterministic Self-Improving Plan Loop Contract

`skills/hack/self_improve_loop.py` defines the pure data contract for a bounded
self-improving `/hack` loop. Importing that module must never invoke Docker,
external network calls, `/plan`, `/dogpile`, `/memory`, `/project-knowledge`, or
`/orchestrate`; callers are responsible for executing any returned specification.

### Loop decisions

The loop evaluates a caller-supplied `LoopConfig` and ordered `AttemptRecord`
values with `decide_next_action(config, attempts)`. Outcomes are deterministic:

- `success` — the latest attempt succeeded and the loop stops successfully.
- `same_plan_retry_for_transient` — a transient infrastructure failure may retry
  the same plan only while inside `max_transient_retries_per_plan`. This retry
  budget is separate from the plan-revision budget.
- `regenerate_plan_for_strategy_failure` — strategy or security failures require
  a new plan revision rather than replaying the same plan.
- `stop_max_retries` — bounded strategy/security plan revisions are exhausted.
- `stop_unsafe_scope` — authorization or scope safety is not confirmed.
- `stop_ambiguous` — scope or evidence is too ambiguous to continue safely.
- `stop_infra_unreachable` — required infrastructure preflight is unreachable or
  transient infrastructure retries are exhausted.

For strategy and security failures, the next plan revision context must include
all of: `prior_failure_evidence`, `previous_plan_id`, `learning_delta`,
`dogpile_context`, `memory_context`, and an explicit non-empty
`strategy_change`. Failure evidence is represented as artifact paths only.

### Docker launch contract

`build_docker_launch_spec(...)` is a pure builder. It returns the per-session
Dockerfile content, `docker-compose.yml` content, environment, mounts, network
policy, and evidence paths without writing files or running Docker. Session
artifacts must live under:

```text
/mnt/storage12tb/artifacts/agent-skills/hack/session-*
```

The generated launch contract includes:

- a per-session `Dockerfile` path;
- a per-session `docker-compose.yml` path;
- explicit environment variables such as session id, plan id, evidence dir, and
  network policy;
- declared target mounts, normally read-only, plus a read-write evidence mount;
- an explicit network policy (`none`, `bridge`, or `host`);
- stdout, stderr, exit-code, findings, and plan evidence artifact pointers.

Callers may materialize and run this spec only after confirming authorization,
scope, and infrastructure. Do not run Docker at import time.

### Research, memory, and project knowledge

`build_research_requirement(...)` creates a pure `/dogpile` research request for
plan regeneration. It must cover Brave/web search, GitHub repositories, GitHub
issues, GitHub code, ArXiv papers, feeds/advisories, and — when configured —
books/sites. The requested synthesis must feed findings into the next plan and
map them to prior failure evidence, the learning delta, and the required strategy
change.

`build_memory_record(...)` and `build_project_knowledge_update(...)` return
persistence payloads only. They store distilled lessons, summaries, facts, next
steps, and artifact pointers. Raw logs, packet captures, scanner output, and
exploit output must not be embedded directly; store them as files under the
session artifact directory and reference the paths.

### Generic `/test-lab` reachability

A generic `/test-lab` is optional by default. Require it only when preflight
configuration explicitly marks it required and reachable. If the loop is
configured to require `/test-lab` but preflight cannot prove it reachable, stop
with `stop_infra_unreachable` rather than assuming availability.
