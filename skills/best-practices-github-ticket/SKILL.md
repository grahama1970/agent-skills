---
name: best-practices-github-ticket
description: >
  Best practices for agent-resolved GitHub tickets, including bugs, feature
  requests, optimizations, maintenance, questions, and triage: filing contracts,
  route and subagent metadata, resolver leases, deterministic verification,
  review evidence, WebGPT escalation, and proof-based closure.
triggers:
  - github ticket best practices
  - how to file agent tickets
  - how agents resolve github tickets
  - github issue best practices
  - how to file agent issues
  - how agents resolve github issues
  - issue labels for subagents
  - feature request labels for subagents
  - github feature request best practices
  - proof-based issue closure
  - skill maintainer github issues
metadata:
  short-description: GitHub ticket contracts for agent workflows
provides:
  - github-ticket-contracts
  - ticket-triage
  - ticket-resolution
  - proof-based-closure
composes:
  - memory
  - ask
complies:
  - best-practices-skills
taxonomy:
  - validation
  - governance
  - orchestration
  - proof
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE TRIAGING, EDITING, VERIFYING, COMMENTING ON, OR CLOSING A GITHUB TICKET.

# GitHub Ticket Best Practices

Use this skill when an agent or human files, triages, repairs, verifies, reviews,
comments on, or closes a GitHub issue, feature request, optimization request,
maintenance task, or question. GitHub calls all of these "issues"; this skill
uses "ticket" for the broader lifecycle object.

This skill is reusable across repositories. For `agent-skills`, it is the policy
contract for `skill-maintainer` and skill-related tickets.

## Operating Model

1. The issuer records the ticket type, target, requested outcome, route, and required proof.
2. The resolver leases exactly one ticket before patching.
3. The resolver reads every named operational contract before acting.
4. The resolver changes only scoped files needed for the ticket.
5. A separate verifier runs deterministic checks and records evidence.
6. Optional external review, including `$ask webgpt`, reviews the evidence bundle.
7. The ticket is commented or closed only after BOTH the deterministic gate
   and the live end-to-end proof are reconciled. Deterministic evidence alone
   never closes a ticket.

WebGPT is an external reviewer. It is not closure proof by itself.

## Issuer Contract

Every agent-actionable ticket should include:

| Field | Required | Purpose |
|-------|----------|---------|
| Ticket type | Yes | `bug`, `feature`, `optimization`, `maintenance`, `question`, or `triage`. |
| Target path | Yes | Concrete file, directory, skill, package, service, or workflow. |
| Current state | Yes | Failure, limitation, missing capability, maintenance need, or open question. |
| Requested outcome | Yes | Concrete behavior, capability, answer, cleanup, or decision requested. |
| Route | Recommended | Repair lane such as `backend_python_or_skill_runtime` or `design_or_ux`. |
| Requested repair agent | Optional | Specific worker such as `coder`, `designer`, or `devops` when known. |
| Required proof | Yes | Must name a live end-to-end command that runs the real path and reads back its artifact. Deterministic checks may accompany it but never replace it. |
| Non-goals | Recommended | Files, behavior, or refactors that should stay out of scope. |

### Ticket Type Contracts

| Type | Required contents | Closure proof |
|------|-------------------|---------------|
| `bug` | observed failure, expected behavior, reproduction or artifact | regression proof plus targeted verification |
| `feature` | current limitation, proposed capability, user workflow unlocked, acceptance criteria, non-goals | acceptance criteria proof plus compatibility/migration notes when applicable |
| `optimization` | current cost/risk/friction, proposed improvement, measurable target | before/after evidence or explicitly bounded qualitative improvement |
| `maintenance` | invariant to preserve, cleanup target, scoped files, risk | invariant-preserving checks and no unrelated behavior change |
| `question` | concrete question, source scope, expected answer format | sourced answer or documented reason it is not established |
| `triage` | incomplete report, available clues, missing data | route/type decision or `needs-human` with exact missing information |

### Route Metadata

Prefer issue metadata over resolver inference:

```text
route:<route-name>
agent:<agent-id>
```

Issue forms may also include:

```text
Maintainer route: <route-name>
Requested repair agent: <agent-id>
```

If the issuer does not know the route, use `unknown` and provide target paths
and current-state evidence. Do not invent a confident route from vague symptoms.

### Canonical Routes

| Route | Default repair agent | Use when |
|-------|----------------------|----------|
| `backend_python_or_skill_runtime` | `coder` | Python CLIs, skill runtime, frontmatter, sanity scripts, skills-ci. |
| `design_or_ux` | `designer` | Product/interface design, screenshots, visual hierarchy, interaction flows. |
| `frontend_code` | `frontend-coder` | React, TypeScript, browser behavior, CSS, DOM, UI tests. |
| `rust_or_binary` | `coder` | Rust crates, Cargo, binaries, ELF, low-level tooling. |
| `ops_or_scheduler` | `devops` | Cron, scheduler, Docker, services, environment, deployment. |
| `documentation_or_report` | `reporter` | Docs, reports, wording, summaries, source-backed prose. |
| `security_or_compliance` | `cyber-analyst` | Vulnerabilities, CUI, CMMC, controls, assurance evidence. |

### Canonical Labels

Use repository labels consistently:

| Label | Meaning |
|-------|---------|
| `type:bug` | Defect, regression, or broken documented behavior. |
| `type:feature` | New capability or changed behavior request. |
| `type:optimization` | Improvement to cost, reliability, speed, ergonomics, or quality. |
| `type:maintenance` | Cleanup, metadata, dependency, or invariant-preserving work. |
| `type:question` | Needs an answer or source-backed decision before implementation. |
| `needs-triage` | Type, route, target, or required proof is not yet clear. |
| `skill-bug` | Skill behavior or validation failure. |
| `skill-maintenance` | General skill cleanup or optimization. |
| `skill-optimization` | Non-bug improvement with measurable acceptance gates. |
| `agent-bug` | Agent behavior or validation failure. |
| `agent-maintenance` | General agent cleanup or optimization. |
| `agent-optimization` | Non-bug agent improvement with measurable acceptance gates. |
| `skills-ci` | Issue came from skills-ci, sanity, or compliance scan output. |
| `monitor-skill-health` | Issue came from monitor-skill-health output. |
| `route:<route-name>` | Explicit route selection. |
| `agent:<agent-id>` | Explicit repair agent request. |
| `maintainer-active` | An agent has leased this issue. |
| `maintainer-blocked` | Progress requires missing input or unavailable external state. |
| `needs-human` | Human approval, source truth, or policy decision required. |
| `external-owner` | The fix belongs outside the current repository or team. |

## Resolver Contract

The resolver must:

1. Re-read the ticket, comments, labels, target files, and linked artifacts.
2. Recall memory for prior attempts, recurring failures, and known fragile areas.
3. Lease one ticket before editing by applying the active label or writing a lease artifact.
4. Honor explicit route or agent metadata unless repository evidence contradicts it.
5. If route metadata is missing, classify from paths, labels, commands, and failure text.
6. Read every named skill `SKILL.md` fully before using, modifying, or verifying it.
7. Read the target skill's `complies:` list and run matching best-practices checks.
8. Preserve unrelated worktree changes and avoid broad refactors.
9. Produce repair, verification, and review receipts before closure.

If issue metadata is contradictory, record the conflict and choose the narrowest
route that can verify the reported failure. Escalate to `needs-human` only when
repository evidence cannot resolve the conflict.

## Verification Contract

Every ticket must name a **live end-to-end proof** that exercises the real path.
Deterministic checks are necessary and never sufficient.

### Why a deterministic test alone cannot close a ticket

A deterministic test states a fixed expectation, so it can be satisfied by a
change that targets the expectation instead of the behaviour. Observed
2026-07-27 on a bounded coder loop: the ticket's proof was
`python -m pytest test_calc.py -q` and the agent produced a patch that passed it.

```python
class _AddResult(int):
    def __eq__(self, other):
        return int.__eq__(self, other) or other == int(self) + 1

def add(a, b):
    return _AddResult(a + b)
```

The test passed. An independent reviewer re-ran it and it passed there too.
Nothing malfunctioned — the proof command was simply weaker than the claim it
was standing in for. A ticket closed on that evidence is a false green, and no
amount of re-running the same deterministic command detects it.

A live run cannot be satisfied that way, because the agent does not control the
service, the model, the browser, the clock, or the network it has to survive.

### Required proof, both tiers

| Tier | Requirement |
|------|-------------|
| Deterministic | Focused tests, `py_compile`, lint, schema checks. Fast gate. Never closure evidence on its own. |
| **Live E2E** | **Required.** Runs the real entrypoint against real services, real data, or a real repository, and reads back the produced artifact. |

A live E2E proof must satisfy all of:

- runs the **documented entrypoint** a user or agent would run, not a test
  harness around it;
- touches at least one surface the ticket author does not control — a live
  service, a model/provider, a browser, a real GitHub repo, a real filesystem
  artifact;
- **reads back the artifact it produced** and asserts on its content, not on the
  command's exit code;
- states `mocked: false` and `live: true` in its receipt;
- is expected to be **non-deterministic** in wording, timing, or ordering. A
  proof whose output is byte-identical on every run is a deterministic check
  wearing an E2E label.

### Refused as sole proof

- unit or integration tests written by the same agent that wrote the change;
- any command run only against fixtures, mocks, recorded responses, or a fake
  service;
- CI green;
- an external reviewer's opinion, including WebGPT;
- a tool's own success response without an independent read-back.

### Per-surface minimum

| Work surface | Deterministic gate | Required live E2E |
|------------|-----------|-------------------|
| Skill metadata | YAML parse, best-practices validation | `./run.sh` real invocation producing a read-back artifact |
| Python/runtime | `py_compile`, focused pytest, `sanity.sh` | live `sanity-live.sh` / `e2e` against real downstream services |
| Frontend/UI | targeted tests | real browser/CDP run with a fresh screenshot of the running app |
| Design | source-grounded artifact | rendered artifact reviewed against the live surface |
| Scheduler/ops | dry-run/status evidence | one real `--apply` tick with a persisted receipt |
| Documentation | source-grounded diff | every documented command executed as written, output quoted |
| Security/compliance | deterministic scan | live probe against the real boundary, refusal read back |

### Non-determinism is not flakiness

A live proof that varies run to run is working as intended. Assert on
**invariants** — schema, status field, artifact existence, semantic content —
never on exact bytes. If a live proof fails intermittently, that is a finding
about the system, not a reason to replace it with a deterministic stub.

A separate verifier should run the proof when an agent patched the issue. The
patching agent should not be the final verifier for its own changes.

## WebGPT And External Review

Use `$ask webgpt` or another external reviewer after deterministic local proof
exists or when blocked/drifting requires review. The review bundle must include:

- issue URL and number
- ticket type
- selected route and repair agent
- files changed
- commands run and results
- deterministic proof artifacts
- unresolved risks or blocked items
- exact question for the reviewer

Do not close an issue because WebGPT says it looks good. Close only after local
deterministic evidence supports the result and WebGPT findings are reconciled.

## Agent-Skills Specific Rules

For tickets under `agent-skills`:

- Skill defects, feature requests, optimizations, and maintenance items belong as GitHub tickets on the `agent-skills` repository.
- Target skill tickets should name `skills/<skill>/SKILL.md` or a concrete path.
- Every skill must declare `complies:` and include `best-practices-skills`.
- `skill-maintainer` should lease one ticket per run.
- `skill-maintainer` should use issue route metadata first and infer only as fallback.
- `skill-maintainer` should dispatch repair and verification to different subagents.
- `skill-maintainer` should prepare WebGPT review bundles through the real `$ask` runtime.

See `references/ticket_contract.yml` for machine-readable types, routes, labels, and gates.

## Terminal Helpers

Use `scripts/gh-ticket-tools.sh` for guarded `gh issue` operations. The helper is
intentionally conservative: closure requires a non-empty proof file, leases write
`maintainer-active`, mutation commands support `--dry-run`, common flags are
valid anywhere after the command, and successful mutations end with a stable
JSON line.

Agent workflow:

1. Run `doctor` before mutation.
2. Run `ensure-labels --dry-run`, then `ensure-labels`, once per repository.
3. Run `next` or `search` for one open ticket that is not active, blocked, human-owned, or external-owned.
4. Run `show` and read the ticket body/comments before acting.
5. Run `lease` for exactly one ticket before work.
6. Use `comment`, `block`, or `release` as state changes require.
7. Run `close` or `close-duplicate` only when the ticket is leased with
   `maintainer-active` and a non-empty proof file exists.

```bash
# Confirm gh auth and repo issue access.
skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh doctor \
  --repo OWNER/REPO

# Ensure workflow labels exist.
skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh ensure-labels \
  --repo OWNER/REPO --dry-run
skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh ensure-labels \
  --repo OWNER/REPO

# Search open skill issues.
skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh search \
  --repo OWNER/REPO \
  --label skill-maintenance \
  --search '-label:maintainer-active -label:needs-human -label:external-owner sort:updated-asc'

# Use the canonical unleased-ticket search.
skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh next \
  --repo OWNER/REPO \
  --label skill-bug

# Inspect one issue as JSON.
skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh show 123 \
  --repo OWNER/REPO

# Lease one issue for a repair agent.
skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh lease 123 \
  --repo OWNER/REPO \
  --agent skill-maintainer

# Leave progress from a template-backed file.
skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh proof-template progress > /tmp/progress.md
skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh comment 123 \
  --repo OWNER/REPO \
  --body /tmp/progress.md

# Block and release the lease when human input is required.
skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh proof-template blocker > /tmp/blocker.md
skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh block 123 \
  --repo OWNER/REPO \
  --reason /tmp/blocker.md \
  --release

# Release a lease without blocking or closing.
skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh release 123 \
  --repo OWNER/REPO \
  --agent skill-maintainer \
  --reason /tmp/progress.md

# Close only after writing a proof file that cites deterministic artifacts.
skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh proof-template proof > /tmp/issue-123-proof.md
skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh close 123 \
  --repo OWNER/REPO \
  --proof /tmp/issue-123-proof.md \
  --review /tmp/issue-123-webgpt-disposition.md \
  --reason completed

# Close a duplicate with proof and an explicit duplicate target.
# Uses native gh duplicate closure when available; otherwise comments proof and
# closes as not planned with duplicate metadata in the final JSON line.
skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh close-duplicate 123 \
  --repo OWNER/REPO \
  --duplicate-of 122 \
  --proof /tmp/issue-123-proof.md
```

## Checklist

- Frontmatter has `name`, folded `description`, `triggers`, `provides`, `composes`, and `complies`.
- Ticket template asks for type, target, route, requested agent, current state, requested outcome, and required proof.
- Route labels and issue-form fields are treated as first-class metadata.
- Terminal helper has `doctor`, `ensure-labels`, `search`, `next`, `show`, `lease`, `comment`, `block`, `unblock`, `release`, `close`, `close-duplicate`, and `proof-template`.
- Terminal helper dry-runs, leases, blocks, unblocks, releases, comments, and closes issues with proof gates.
- Terminal helper refuses live close/duplicate close unless `maintainer-active`
  is present, and refuses close while `needs-human` is set.
- `block` adds `maintainer-blocked` + `needs-human`; `unblock ISSUE --reason FILE
  [--agent NAME]` removes both (and re-leases with `--agent`) so a resolved
  ticket can be closed via the tool. `block --release` only frees the lease.
- `close --reason` accepts only `completed` or `not-planned`.
- Terminal helper parses `--repo` and `--dry-run` anywhere and rejects unknown args.
- Resolver leases one ticket before patching.
- Resolver reads target operational contracts before acting.
- Resolver preserves unrelated worktree changes.
- Repair and verification agents are separate when the issue was patched.
- Closure comment cites deterministic proof artifacts.
- WebGPT findings are reconciled, not treated as proof.
- Blocked issues state the missing input or unavailable external state.

## Common Mistakes

### WRONG: Filing an unrouteable issue

```text
The skill is broken. Please fix.
```

### RIGHT: File target, failure, route, and proof

```text
Type: bug
Target: skills/fetcher/SKILL.md
Maintainer route: backend_python_or_skill_runtime
Observed: bash skills/fetcher/sanity.sh exits 1 with missing timeout fixture.
Expected: sanity exits 0 and validates timeout behavior.
Required proof: target sanity.sh plus skills-ci scoped scan.
```

### WRONG: Filing a feature as a vague bug

```text
WebGPT retry is broken.
```

### RIGHT: File feature request with acceptance criteria

```text
Type: feature
Target: skills/surf and skills/ask
Current limitation: focus interruption leaves WebGPT review runs hard to resume.
Requested outcome: resilient recovery path that retries preflight by URL or emits an exact extract/resume command.
Acceptance criteria: simulated stale-tab/focus-interrupted test plus ask artifact preservation.
Non-goals: do not silently auto-pick a different ChatGPT tab.
```

### WRONG: Closing from reviewer opinion

```text
WebGPT says this is fine, closing.
```

### RIGHT: Close from local evidence plus review disposition

```text
Proof: sanity.sh exited 0, pytest fixture exited 0, compliance check exited 0.
WebGPT finding #1 was non-blocking because the cited path is outside this issue scope.
```

### WRONG: Sending a design issue to the backend worker by default

```text
Route omitted. The maintainer picks coder because the repo mostly contains Python.
```

### RIGHT: Route by work product

```text
route:design_or_ux
agent:designer
Required proof: source-grounded mockup plus screenshot/CDP evidence after implementation.
```
