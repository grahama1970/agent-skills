---
name: best-practices-competition
description: >
  Best practices for leading Ask compete and bakeoff workflows. Use when a
  user asks for competing models, isolated candidate implementations,
  winner selection, feature harvesting, approach comparison, model bakeoffs,
  or a creator competition where $ask should route browser and API handlers
  through Tau and the project agent must judge results against local evidence.
triggers:
  - competition best practices
  - lead a competition
  - Ask compete
  - model competition
  - implementation bakeoff
  - competing models
  - isolated candidates
  - winner selection
  - feature harvesting
  - compare candidate implementations
provides:
  - competition-leadership-protocol
  - isolated-candidate-contract
  - winner-selection-gate
  - feature-harvesting-contract
  - winner-revision-request-pattern
composes:
  - ask
  - best-practices-tau-dag
  - brave-search
  - github-search
  - dogpile
complies:
  - best-practices-skills
  - best-practices-tau-dag
taxonomy:
  - orchestration
  - competition
  - review
  - validation
---

# Best Practices: Competition

Use this skill to run a competition that produces usable engineering signal:
isolated candidates, identical task packets, explicit judging criteria, local
verification, and a bounded revision request for the selected winner.

A competition is not a roundtable. Competitors do not deliberate with one
another, and the project agent does not share participant information between
candidate lanes or rounds. The project agent judges the work against the
codebase, skill contracts, and deterministic evidence.

## Core Rule

Compete candidates are claims until checked.

The project agent owns the competition contract, candidate isolation, artifact
collection, feature verification, scorecard, winner decision, and final
revision request. `$ask` owns the runtime entrypoint and should compile the
competition into Tau-owned candidate nodes and a join node. `$tau`, `$surf`,
`$browser-oracle`, and `$scillm` own transport and provider execution.

Browser-backed handlers and API-backed handlers are peers. Do not privilege or
discard a candidate merely because it arrived through a different transport.

The project agent may coach each participant between its own iterations with
the project agent's review of that participant's output, local deterministic
findings, and external research from `$brave-search`, `$github-search`, or
`$dogpile`. That help must stay lane-local unless it is shared public evidence
added to a fresh common task packet for every candidate. Never leak another
candidate's approach, code, score, feature ideas, or failure analysis.

## Use This When

- The user asks for a competition, compete run, bakeoff, isolated candidates, a
  winner, or "best of several implementations."
- The task has multiple plausible implementation paths and comparison will
  improve the final patch.
- The candidates may mix browser seats such as `webgpt`, `webclaude`,
  `webkimi`, or `webgemini` with `$scillm` model seats.
- The project agent can locally inspect candidate output and verify reusable
  features before promoting them.

## Do Not Use This When

| Request shape | Better route |
| --- | --- |
| Shared deliberation or synthesis | `$ask` roundtable with `$best-practices-roundtable` |
| One answer from one handler | `$ask` single handler |
| Creator then pass/fail reviewer | `$ask tau-dag --topology sequential` |
| A deterministic repair is already obvious | Apply and test the repair directly |
| The judge cannot inspect the target repo or artifact | Stop with `NEEDS_ATTENTION` |
| The user needs a human policy decision | Ask the human directly |

## Source-Derived Step Model

1. **Define the competition contract.**
   State the objective, immutable goal or acceptance bar, target repo/path,
   allowed files, candidate count, judging criteria, output schema, and proof
   boundary.

2. **Freeze the shared task packet.**
   Every candidate receives the same task, context, constraints, and expected
   output. Do not tailor hidden context to favor one handler.

3. **Choose isolated candidates.**
   Use at least two handlers. Mix browser and API handlers when useful. Treat
   `webclaude` as a strong default candidate for hard work; when available in
   `$ask`, prefer `Opus 5 High` for that browser seat.

4. **Compile through `$ask compete`.**
   Use `$ask` as the front door. The competition should become a Tau DAG with
   concurrent candidate nodes and a join node.

5. **Preserve all receipts.**
   Read `request.json`, `dag.json`, command specs, candidate receipts,
   candidate responses, scorecard, and winner revision request. Missing,
   blocked, stale-tab, or rate-limited candidates must be visible in the
   scorecard.

6. **Normalize candidate outputs.**
   Extract concrete changes, proposed files, test commands, risk notes, and
   `VERIFIED_FEATURE:` claims. Do not let prose style or confidence decide the
   winner.

7. **Review each candidate iteration.**
   For each participant, inspect only that participant's artifacts plus the
   original task packet, local repo state, and tool-backed research. Use
   `$brave-search`, `$github-search`, or `$dogpile` to unblock the participant
   when research can answer a concrete implementation question. Send feedback
   back only to that same lane.

8. **Verify reusable features locally.**
   A candidate feature is promotable only after the project agent checks it
   against repository state, skill contracts, and the narrow deterministic proof
   command. Unchecked features stay out of the winner request.

9. **Score with evidence.**
   Score criteria such as correctness, minimality, maintainability, contract
   fit, proof quality, and failure handling. Tie every score to artifacts or
   local checks.

10. **Pick a winner or fail closed.**
   Pick a winner only when one candidate has a clear evidence-backed advantage.
   If candidates are tied, incomplete, blocked, unverifiable, or all wrong,
   report `NEEDS_ATTENTION` instead of fabricating a winner.

11. **Send one bounded winner revision request.**
    Ask the winning candidate to keep its own implementation as the base and add
    only locally verified features harvested from other candidates. The
    revision request is a next step, not proof that the revision happened.

12. **Verify the final implementation locally.**
    Competition output can guide the patch, but closure requires local
    deterministic evidence appropriate to the task.

## Competition Packet

Every substantial competition prompt should include:

```text
Objective:
Immutable goal or acceptance bar:
Target repo/path:
Allowed files or boundaries:
Shared context:
Candidate handlers:
Judging criteria:
Expected candidate output:
Forbidden claims:
Proof boundary:
```

Ask every candidate for:

- `APPROACH`: concise strategy.
- `CHANGES`: specific files, functions, commands, or artifacts.
- `VERIFIED_FEATURE`: only features that the project agent can check locally.
- `RISKS`: failure modes, omitted cases, and assumptions.
- `PROOF_COMMANDS`: exact commands the project agent should run.
- `BLOCKERS`: only missing input, credentials, or external state.

## Iteration And Research Rules

The project agent may run iterative competitions, but isolation still applies.

Allowed lane-local help:

- ask a participant to repair its own failed proof gate;
- give a participant the project agent's review of that participant's output;
- provide deterministic local errors from that participant's attempted patch;
- run `$brave-search web`, `$github-search`, or `$dogpile` for a concrete
  blocker and provide the retrieved public evidence to that participant;
- update all participants with a fresh common task packet when the same public
  evidence should apply to everyone.

Forbidden cross-lane leakage:

- another participant's code, approach, prompt, score, or review;
- "candidate B solved this by..." hints;
- merged feature lists before winner selection;
- using one participant as an uncredited reviewer of another participant;
- sharing failure analysis from one lane with another lane unless the human
  explicitly converts the competition into a roundtable.

If cross-lane leakage happens, mark the competition contaminated and restart
from a fresh shared packet or convert it to a roundtable with human approval.

## Scoring Contract

The project agent's scorecard must include:

- candidate status: responded, blocked, stale tab, timed out, rate-limited, or
  not run;
- artifact paths for every candidate;
- feature claims accepted, rejected, or unchecked;
- local checks run by the project agent;
- criterion scores with evidence;
- winner, tie, or `NEEDS_ATTENTION`;
- bounded winner revision request, if a winner exists.

Do not score a candidate higher for sounding confident. Score only what can be
reconciled with the task packet, codebase, skill contracts, and proof artifacts.

## Ask Integration

Use `$ask` for execution. Do not replace competitions with informal subagents or
manual browser prompts.

Compile-only example:

```bash
cd skills/ask
./run.sh compete "Implement the focused patch. Return concrete reusable features as VERIFIED_FEATURE lines only when locally checkable." \
  --repo local/agent-skills \
  --target ask-competition-example \
  --handler webgpt \
  --handler webclaude \
  --handler gpt-5.5-high \
  --handler-project webgpt=tau \
  --criterion skill-contract \
  --criterion deterministic-proof \
  --json
```

Add `--execute` only when live browser/provider calls are authorized and the
required browser-oracle bindings or provider credentials are available.

## Fail-Closed Rules

| Condition | Behavior |
| --- | --- |
| Fewer than two candidates | Request another handler or emit `NEEDS_ATTENTION` |
| Candidate sees another candidate's output or score | Restart; isolation was broken |
| Missing candidate receipt | Mark that candidate `NEEDS_ATTENTION` |
| Candidate feature is not locally checkable | Do not promote it |
| All candidates fail the same gate | Stop the family and report systemic failure |
| No clear evidence-backed winner | Report tie or `NEEDS_ATTENTION` |
| Winner revision request exists | Treat it as a request packet, not final proof |

## Common Failure Modes

| Failure mode | Required correction |
| --- | --- |
| Roundtable disguised as competition | Re-run as isolated `$ask compete` |
| Consensus substituted for judging | Use roundtable, or verify features locally |
| Cross-lane coaching | Restart or convert to roundtable with human approval |
| Tool help omitted for a research blocker | Use `$brave-search`, `$github-search`, or `$dogpile` lane-locally |
| Feature harvesting without proof | Remove unchecked features from the winner request |
| Winner picked from style | Score against criteria and artifacts |
| Over-broad final revision | Bound the request to verified features only |
| Ignored losing candidate insight | Preserve rejected and accepted feature reasons |
| Browser/API transport hidden | Mark per-candidate transport status explicitly |

## Closure Boundary

A competition can close its selection phase when it has:

- a frozen shared packet;
- isolated candidate receipts;
- a scorecard with local checks;
- explicit accepted/rejected/unchecked feature claims;
- a winner, tie, or `NEEDS_ATTENTION`;
- a bounded winner revision request when a winner exists.

It cannot close the user's implementation goal by itself. Final closure requires
the selected implementation to be applied and locally proven.
