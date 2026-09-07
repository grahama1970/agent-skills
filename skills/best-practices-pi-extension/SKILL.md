---
name: best-practices-pi-extension
description: >
  Best practices for building, reviewing, and shipping Pi TypeScript extensions and extension packages. Use when authoring Pi extensions, custom tools, lifecycle hooks, intercom bridges, status guards, provider adapters, TUI components, package manifests, or retained extension evals.
triggers:
  - pi extension best practices
  - build a pi extension
  - review pi extension
  - custom pi tool
  - pi lifecycle hook
  - extension package
  - intercom extension
  - status guard extension
provides:
  - pi-extension-review
  - extension-validation-contract
  - typed-collaboration-boundary
  - retained-extension-eval-pattern
composes:
  - agentic-evals
  - shame
  - triage-error
  - ops-herdr
  - pi-intercom
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - validation
  - developer-tooling
  - resilience
disciplines:
  - developer-tooling
  - evaluation-quality
  - agentic-orchestration
---

# Pi Extension Best Practices

Use this when creating or reviewing a Pi extension or Pi package. Start from the
Pi docs (`docs/extensions.md`) and existing extension code; do not invent APIs.

## Non-negotiables

1. **Typed boundary first.** Validate every tool argument, lifecycle payload,
   provider payload, inter-extension event, receipt, and cross-session message at
   the boundary before use. TypeBox is the tool schema; Pydantic or an equivalent
   executable schema is the receipt/collaboration gate. Raw dict/string poking is
   not validation.
2. **Shame-compatible status.** If an extension reports completion, render from
   validated data, not model prose. For mutating or guard-forced flows, emit a
   valid `pi.agent_status.v1` with a first-class `answer`, `verified[]`, and
   local proof files whose text contains each command/result pair.
3. **Bidirectional means peer-gated.** Do not close a collaboration loop from the
   sender side. Ask with a typed JSON packet, validate the typed answer against
   the original question (`question_id`, allowed answers, response schema), and
   keep the peer acceptance receipt.
4. **Use the owner bridge for terminal discovery.** Intercom session lists are
   not the whole terminal universe. If Herdr panes are in scope, discover and
   route through `$ops-herdr`/the Herdr bridge, including Herdr-only terminals.
5. **Route failures through `$triage-error`.** A bare timeout, `NEEDS_ATTENTION`,
   rejected payload, or push denial is not enough. Use a catalog code, or mint a
   deterministic `*_unclassified_<8hex>` code when the catalog has no match.
6. **Retained `$agentic-evals` before done.** Every enforcement feature needs a
   retained eval fixture, at least one adversarial/negative case, a real path,
   read-back of the report, and a scoped commit/push or explicit external
   blocker.

## Extension implementation rules

- Put auto-discovered extensions in `~/.pi/agent/extensions/` or `.pi/extensions/`;
  package extensions declare `pi.extensions` in `package.json`.
- Runtime dependencies required by installed packages belong in `dependencies`,
  not only `devDependencies`.
- Start long-lived sockets, file watchers, or processes from `session_start` or
  the command/tool that needs them; clean them up in `session_shutdown`.
- Use `ctx.mode`/`ctx.hasUI` before TUI-only UI. JSON and print modes cannot
  depend on interactive prompts.
- Custom tools throw to signal failure. Returning `{ details: { error: true } }`
  is not an error unless the contract explicitly says so.
- Truncate large outputs and tell the model where the full output is stored.
- File-mutating custom tools use Pi's file mutation queue; queue the whole
  read-modify-write window on the resolved absolute path.
- If `prepareArguments()` supports old calls, keep the public schema strict and
  convert legacy input before validation.
- Tool prompt guidelines must name the tool; they are appended flat to the global
  guideline list.

## Collaboration packet pattern

Use small closed-world JSON packets for extension-to-agent collaboration:

```json
{
  "schema": "lazy_report_shame.collab_question.v1",
  "question_id": "unique-goal-id",
  "triage": {"code": "component_unclassified_deadbeef", "layer": "extension", "cause": "why this is being asked"},
  "question": "Is this SUFFICIENT or NEEDS_FIX?",
  "required_response_schema": "lazy_report_shame.collab_answer.v1",
  "allowed_answers": ["SUFFICIENT", "NEEDS_FIX"]
}
```

The answer must validate independently and against the question. A valid answer
with the wrong `question_id`, widened `allowed_answers`, or different schema is
invalid data, not dissent.

## Review checklist

- Does the extension use documented Pi APIs and sourceInfo/provenance fields
  instead of inferring from names or paths?
- Are all cross-boundary payloads validated before action and before persistence?
- Are errors surfaced as typed data with deterministic repair hints?
- Does the eval exercise the real extension path, not just a self-authored helper?
- Are proof boundaries explicit: what was live, what was fixture-backed, and what
  remains unproven?
