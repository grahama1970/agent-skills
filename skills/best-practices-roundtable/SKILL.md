---
name: best-practices-roundtable
description: >
  Best practices for leading multi-model Ask roundtables and Tau-DAG
  deliberation panels. Use when a user asks for a roundtable, model panel,
  mixed web/API collaborator discussion, multi-round critique, attributed
  dissent synthesis, or guidance on turning several model perspectives into
  executable next steps through $ask.
triggers:
  - roundtable best practices
  - lead a roundtable
  - model panel
  - multi-model discussion
  - Ask roundtable
  - Tau DAG roundtable
  - browser and API model panel
  - attributed dissent
  - roundtable synthesis
provides:
  - roundtable-leadership-protocol
  - equal-context-panel-contract
  - roundtable-synthesis-gate
  - dissent-preservation-pattern
  - executable-slice-manifest-pattern
composes:
  - ask
  - best-practices-tau-dag
  - brave-search
  - dogpile
complies:
  - best-practices-skills
  - best-practices-tau-dag
taxonomy:
  - orchestration
  - review
  - deliberation
  - validation
disciplines:
  - engineering-standards
  - agentic-orchestration
---

# Best Practices: Roundtable

Use this skill to lead a roundtable that is actually useful: equal context,
independent perspectives, attributed disagreement, bounded iteration, and a
result that can become work.

A roundtable is a deliberation panel. It is not a compete run, not a linear
creator-reviewer pipeline, and not a way to turn model agreement into proof.

## Core Rule

Lead the room. Do not merely collect replies.

The project agent owns the shared packet, seat selection, round prompts,
between-round research, synthesis, dissent handling, and conversion into
executable slices. `$ask` owns the runtime and should compile the request into a
Tau DAG. `$tau`, `$surf`, `$browser-oracle`, and `$scillm` own transport and
provider execution below that boundary.

Browser-backed handlers and API-backed handlers are peers in the panel. Their
transport differs, but the roundtable contract does not.

## Use This When

- The user asks for a roundtable, panel, council, collaborator discussion, or
  multiple model perspectives.
- The question benefits from disagreement, cross-checking, design critique,
  architecture tradeoffs, or implementation strategy.
- The requested handlers may mix browser seats such as `webgpt`, `webclaude`,
  `webkimi`, or `webgemini` with `$scillm` model seats such as
  `gpt-5.5-high` or `chutes deepseek-ai/DeepSeek-V3.2-TEE`.
- The output should become a plan, decision record, patch strategy, review
  rubric, or executable slice manifest.

## Do Not Use This When

| Request shape | Better route |
| --- | --- |
| One factual answer or one model response | `$ask` single handler |
| Independent implementations and winner selection | `$ask compete` or an approach bakeoff |
| Creator then pass/fail reviewer | `$ask tau-dag --topology sequential` |
| The next deterministic command is obvious | Run the command first |
| A missing human decision controls scope | Ask the human directly |
| The goal is already proven locally | Report the proof instead of convening models |

## Source-Derived Step Model

1. **Classify the workflow.**
   State whether this is a roundtable, compete run, creator-reviewer pipeline,
   or explicit DAG. A roundtable uses concurrent seats with equal context.

2. **Write the shared packet.**
   Include objective, immutable goal or acceptance bar, target files or
   artifacts, constraints, current evidence, known failures, exact questions,
   and proof boundaries. Every seat receives the same packet.

3. **Select seats and transport.**
   Name handlers explicitly. Use browser handlers for browser-only reviewers
   and API model names for `$scillm` seats. Do not give one seat privileged
   hidden context because its transport is easier.

4. **Compile through `$ask`.**
   Use `$ask` as the front door so the request becomes a Tau DAG. For current
   web/API roundtables, use `./run.sh tau-dag ... --topology concurrent`.

5. **Read receipts before interpreting answers.**
   Inspect `dag.json`, command specs, node receipts, response files, and join
   artifacts. A missing seat, stale tab, rate limit, provider failure, or
   missing response makes that seat `NEEDS_ATTENTION`; it does not become silent
   consensus.

6. **Synthesize with attribution.**
   Attribute each material claim to the seat that made it. Keep disagreements
   visible. Separate recommendations from evidence and separate model claims
   from local proof.

7. **Research load-bearing claims between rounds.**
   Before launching another round, check claims that would change the decision.
   Prefer `$dogpile` when available; otherwise use `$brave-search web`. Feed the
   evidence brief back to every seat identically.

8. **Iterate only while it buys clarity.**
   Default cap: three rounds. Stop earlier if the panel converges with enough
   evidence to choose the next local action. If dissent survives the cap,
   report the split instead of smoothing it away.

9. **Convert advice into executable slices.**
   The close artifact should identify concrete slices with owner, target
   artifact or command, acceptance check, and proof boundary. A prose summary is
   not enough for implementation work.

10. **Verify locally before closure.**
    Model agreement is advisory evidence. Completion still requires local,
    deterministic proof appropriate to the task: tests, schema checks, endpoint
    responses, screenshots, database queries, or generated artifact validation.

## Prompt Contract

Every substantial roundtable prompt should include these fields:

```text
Objective:
Immutable goal or acceptance bar:
Target files/artifacts:
Current evidence:
Known failures or uncertainty:
Constraints:
Handlers:
Questions for every seat:
Expected response format:
Proof boundary:
```

Ask every seat for:

- `POSITION`: the seat's recommended direction.
- `EVIDENCE`: facts, files, commands, receipts, or external sources supporting
  the position.
- `RISKS`: likely failure modes and false-green traps.
- `QUESTIONS`: only blockers that require human or external input.
- `EXECUTABLE_SLICES`: owner, artifact or command, and acceptance check.

The prompt may invite seat-specific strengths, but it must not hide context
from any seat.

## Synthesis Contract

The roundtable leader's synthesis must include:

- seat status: responded, blocked, rate-limited, stale tab, timed out, or not
  run;
- common ground;
- attributed dissent;
- externally checked claims;
- claims still unverified;
- selected next slice or `NEEDS_ATTENTION`;
- exact local proof command or artifact expected next.

Do not write "the panel agrees" unless all successful seats actually converge
and every missing or blocked seat is named separately.

## Ask Integration

Use `$ask` for execution. Do not replace it with informal subagents or direct
browser typing.

Compile-only example:

```bash
cd skills/ask
./run.sh tau-dag "Roundtable webgpt, webclaude, webkimi, and chutes deepseek-ai/DeepSeek-V3.2-TEE concurrently on: <shared packet>" \
  --repo local/agent-skills \
  --target roundtable-example \
  --handler webgpt \
  --handler webclaude \
  --handler webkimi \
  --handler deepseek-ai/DeepSeek-V3.2-TEE \
  --topology concurrent \
  --json
```

Natural syntax is acceptable when `$ask` supports it:

```bash
cd skills/ask
./run.sh tau-dag "concurrently webgpt, webclaude, webkimi and chutes deepseek-ai/DeepSeek-V3.2-TEE <shared packet>" \
  --repo local/agent-skills \
  --target roundtable-example \
  --topology concurrent \
  --json
```

Add `--execute` only when live provider/browser calls are authorized and the
required browser-oracle bindings or provider credentials are available.

## Common Failure Modes

| Failure mode | Required correction |
| --- | --- |
| One-shot polling | Run another round only after synthesis and research, or close with slices |
| Sequential chain called a roundtable | Recompile as concurrent, or rename it a pipeline |
| Hidden context per seat | Rebuild a shared packet and restart the round |
| Browser/API transport failure buried in consensus | Mark the affected seat `NEEDS_ATTENTION` |
| Model consensus treated as proof | Run the deterministic proof gate locally |
| Vague "next steps" | Convert to executable slices with checks |
| Research side quest | Research only load-bearing claims that affect the next round or slice |
| No immutable goal | Ask the human or state the missing goal before dispatch |

## Closure Boundary

A roundtable can close its deliberation when it has:

- a shared prompt packet;
- per-seat receipt status;
- attributed synthesis;
- load-bearing claims checked or explicitly marked unchecked;
- executable slices or preserved dissent;
- a named local proof gate for the project agent.

It cannot close the user's implementation goal by itself. That requires the
project agent to apply the selected slice and produce deterministic evidence.
