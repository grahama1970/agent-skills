---
name: best-practices-security
description: >
  General application, service, plugin, and agent security hardening baseline.
  Use before /hack, /security-scan, /code-runner probe generation, or security
  review. Grounded in OWASP ASVS, OWASP Cheat Sheet Series, Node.js security
  guidance, and agent/plugin trust-boundary lessons.
triggers:
  - best practices security
  - security best practices
  - hardening checklist
  - secure coding checklist
  - appsec baseline
  - security baseline
  - hardening validation
metadata:
  short-description: Security hardening baseline for scans, probes, and reviews
provides:
  - security-hardening-baseline
  - secure-code-review-checklist
  - proof-probe-constraints
composes:
  - memory
  - best-practices-prompt
  - best-practices-agent
  - best-practices-skills
  - dogpile
  - hack
  - security-scan
  - agentic-evals
taxonomy:
  - security
  - resilience
  - precision
  - corruption
disciplines:
  - engineering-standards
  - compliance-security
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Security Best Practices

Use this skill to define what "secure enough to proceed" means before running
`/hack`, `/security-scan`, `/code-runner` proof probes, or a manual code review.
The goal is authorized hardening: find exploitable weaknesses, validate them in
bounded local containers, and produce patch/regression-test plans.

## Seed Sources

Use these as canonical external baselines when `/dogpile` needs fresh context:

| Source | Use |
|---|---|
| `https://github.com/OWASP/ASVS` | Verification requirements and measurable control language |
| `https://github.com/OWASP/CheatSheetSeries` | Topic-specific defensive implementation guidance |
| `https://cheatsheetseries.owasp.org/cheatsheets/Nodejs_Security_Cheat_Sheet.html` | Node.js runtime and service hardening |
| `https://github.com/agamm/claude-code-owasp` | Skill-shaped OWASP reference; use as inspiration, not copied text |
| `https://owasp.org/www-project-top-10-for-large-language-model-applications/` | LLM/tool-call security boundaries |
| `https://genai.owasp.org/` | Agentic application risks and controls |

Do not paste large sections from these sources into reports. Extract project
specific checks and cite the source URL.

## Required Pipeline Placement

Run this skill after codebase understanding and before research/probing:

1. Read launch/config docs, security docs, and runtime manifests.
2. Extract symbols for auth, input, command, plugin, network, and storage paths.
3. Recall memory using concrete paths and symbol names.
4. Apply the checklist sections below.
5. Write a `/dogpile` prompt grounded in paths, symbols, configs, and memory.
6. Generate `/code-runner` proof probes only for bounded local validation.

## Baseline Review Categories

Every hardening plan must cover each category or explicitly mark it not
applicable with a reason.

| Category | Check |
|---|---|
| Auth/session | Tokens have sufficient entropy, are scoped, expire/rotate, and fail closed |
| Authorization | Every action checks caller role, device/session scope, and target ownership |
| Input handling | Untrusted input has length/type/schema constraints before reaching sinks |
| Command execution | Shell execution is avoided; allowlists and argv arrays are enforced |
| Plugin/runtime boundary | Plugins have explicit capabilities, deny-by-default permissions, and audit trails |
| Trusted proxy | Proxy headers are trusted only from configured proxy paths and cannot bypass auth |
| WebSocket/API control plane | Handshake auth, origin rules, replay limits, and rate limits are enforced |
| Secrets/config | Secret refs resolve from allowed roots; secrets never appear in logs or prompts |
| Filesystem paths | Includes/uploads/templates resolve under explicit roots and reject traversal |
| SSRF/network | Server-side fetches restrict schemes, hosts, redirects, and private ranges |
| Serialization | No unsafe deserialization or prototype pollution path accepts user data |
| Dependencies | Lockfiles, provenance, update policy, and vulnerable transitive packages are reviewed |
| Containers | Non-root user, dropped capabilities, read-only mounts where possible, no broad host mounts |
| Logging/audit | Security decisions record actor, action, target, result, and correlation ID |
| Error handling | Errors hide internals from users and fail closed for auth/security decisions |

## Agent And Plugin Addendum

For agent systems, MCP/plugin hosts, or tool-calling runtimes, also check:

- Tool calls are least-privilege and scoped per session/user.
- Generated code or probe code runs in a sandbox/container with explicit mounts.
- LLM output is treated as untrusted before reaching shell, SQL, filesystem, DOM, or tools.
- Memory/RAG content is separated by trust level and cannot silently override system rules.
- Inter-agent messages authenticate sender, target, and intended action.
- Human approval is required for destructive, external-effect, or credential-affecting actions.
- Kill switches, timeouts, and cost/request budgets exist for autonomous loops.

## Bounded Proof-Probe Rules

`/code-runner` may generate probe code only when all rules pass:

1. The target is local or otherwise explicitly authorized.
2. The probe has one named vulnerability hypothesis tied to a source path/symbol.
3. The probe is non-destructive and does not create persistence or exfiltrate secrets.
4. The probe runs through `/hack` Docker, not directly on the host.
5. The probe accepts explicit target/proof paths and writes proof only under the session artifact directory.
6. The probe exits success only on deterministic proof; otherwise it exits nonzero.
7. The report stores raw proof as an artifact and shows only a safe summary.
8. A successful proof creates a remediation task or patch plan plus a regression check.

## Security Review Prompt Requirements

When writing `/dogpile`, `/ask`, or `/code-runner` prompts for this domain:

- Include concrete source paths, symbols, ports, config files, and memory lessons.
- State the target runtime, e.g. `Node.js gateway on 127.0.0.1:18789`.
- Ask for controls mapped to the listed source paths, not generic advice.
- Include rejection criteria that discard sources not mapped to the codebase.
- Require output sections for attack surface, controls, bounded probes, and patch plan.
- Do not ask for weaponized payloads or internet-target instructions.

## Output Contract For Reports

Security reports must answer these questions first:

- Is the target launched and reachable?
- Which security surfaces were reviewed?
- Which best-practice categories passed, failed, or were not applicable?
- Were bounded proof probes generated?
- Did `/hack` execute any proof probe in Docker?
- Was a weakness proven?
- What patch or hardening task follows?
- Which artifacts contain raw logs/proof?

## OpenClaw-Relevant Focus Areas

For OpenClaw-style gateway/plugin systems, prioritize:

- gateway token resolution and secret-ref handling;
- pairing/device-token scope and rotation;
- trusted proxy header authorization;
- WebSocket handshake and origin/auth behavior;
- plugin SDK permissions and command registration;
- node-host command allowlists and child-process execution;
- local/LAN bind modes and gateway port exposure;
- workspace/config include roots and path traversal;
- agent tool-call and memory/RAG trust boundaries.

## Dogpile Seed Query

Use a query like this after paths/symbols are known:

```text
OWASP ASVS Node.js gateway WebSocket bearer token device pairing trusted proxy
plugin sandbox command execution allowlist secret refs hardening checklist GitHub
examples mapped to: <source paths and symbol names>
```

## Decision Rule

If a scanner finds no parsed candidate, do not conclude the target is safe.
Revise the plan: improve launch discovery, expand symbol/document ingestion,
run `/dogpile` with code-grounded questions, then rerun bounded validation.
