---
name: best-practices-delivery-proof
description: >
  Delivery-proof discipline for agents driving external effects: browser
  submits, pane messages, file writes, pushes, API calls. Use when an agent is
  about to claim something was sent, submitted, delivered, landed, or running;
  when a transport reports success but the destination shows nothing; when an
  agent is retrying the same failing operation; or when the human says the
  agent is lying, skimming, or thrashing. Encodes the 2026-08-18 session in
  which five browser submits failed and the agent twice reported delivery that
  had not happened — every rule below is paid for by a specific receipt from
  that session.
triggers:
  - delivery proof
  - did it actually send
  - read-back verification
  - transport says success
  - waiting for acceptance
  - agent is lying about delivery
  - stop thrashing
  - read the skill first
  - proof boundary
provides:
  - delivery-claim-receipt-contract
  - self-status-is-not-delivery-rule
  - bounded-escalation-ladder
  - stale-artifact-shadowing-guard
  - self-kill-footgun-procedures
  - human-named-target-authority-rule
composes:
  - ask
  - surf
  - debugger
  - agentic-evals
complies:
  - best-practices-skills
taxonomy:
  - validation
  - resilience
  - browser
  - orchestration
disciplines:
  - engineering-standards
  - agentic-orchestration
---

# best-practices-delivery-proof

## Why this skill exists

On 2026-08-18 an agent spent over an hour failing to deliver one prompt to one
human-named browser tab. Five submits failed the same way. The agent twice told
the human the prompt was "submitted and generating" while the destination tab
held nothing. The human had to say "I'm looking at the browser tab now" to
force a read-back the agent should have done first. Every failure was
pre-answered by a contract the agent had been told to read and had only
grepped. None of the rules below are aspirations; each one names the exact
receipt that paid for it.

## Rule 1 — A delivery claim requires a receipt from the DESTINATION

A statement that something was sent, submitted, delivered, posted, or landed is
a claim about the destination, so only the destination can prove it. The
transport's opinion of itself is never sufficient, however official it looks.

| Claim | The only acceptable receipt |
| --- | --- |
| "prompt submitted to a browser tab" | message count grew in that tab, read from its DOM; or the transport host log's acceptance signature (for ChatGPT: `stopVisible=true composerChars=0`) |
| "message delivered to a pane" | the pane's own readback shows the text (`herdr pane read`) |
| "file written" | independent read of the file content |
| "pushed to main" | `git log origin/main..HEAD` is empty after fetch |
| "answer is generating" | the destination's own heartbeat/stream state, re-read this turn — not a cached read, not the phase at submit time |

Things that are NOT delivery proof, each observed lying on 2026-08-18:

- a live process whose argv contains the prompt (the process was wedged at
  `waiting_for_acceptance` for 12 minutes)
- `submitted: true` / exit code 0 from the wrapper (written before acceptance)
- a `.submitted.md` file (records intent, not effect)
- a heartbeat you have not read (the artifact said `waiting_for_acceptance`
  the whole time; the agent said "generating" without opening it)
- a stale meta/receipt at a shared output path (see Rule 4)

## Rule 2 — Read the owning contract in full before acting

When a skill owns the workflow, Read its entire SKILL.md before the first
command — not Grep, not head, not memory of a previous session. `skills/ask`
says it in its own first section: "read this whole file before acting."

The 2026-08-18 cost of skipping this: the agent drove raw `surf` under `/ask`
(forbidden at the contract's line 1481), missed that a human-named tab requires
`browser-oracle bind` + `--handler-project` + `--browser-tab-lifecycle
reuse-bound` (documented, three places), rebuilt the contract's own
receipts-first symptom table by trial and error, and rediscovered a failure
class ("text typed but left unsent in the composer") the contract already
documented with its lesson: delivery is verified after the fact, never
predicted.

When the human explicitly says to read a skill, that is an instruction with no
skim interpretation.

## Rule 3 — Escalate on evidence; never repeat a failed operation unchanged

The ladder, each rung entered only with the previous rung's receipt in hand:

1. **Documented layer.** Drive the owning skill with the documented flags.
   One attempt.
2. **Receipts.** On failure, read the artifacts the contract names
   (heartbeat, node receipt, host log, lane diagnostics) before any theory.
   The failure is usually named there verbatim.
3. **Isolate one variable.** A controlled experiment, not a retry: the
   2026-08-18 split was a one-line ping through the same transport to the same
   tab — it failed identically, proving the tab, not the payload.
4. **Alternate transport, with authorization.** Only a transport already
   proven against this destination (a 20-character DOM probe, read back), and
   only with the human's word when it leaves the owning skill's contract.
5. **Stop.** A defined give-up point stated in advance: what will be tried,
   how many times, and what happens after. Open-ended retrying is thrashing.

Submitting the same prompt to the same tab a third time with no new evidence is
not persistence; it is the spiral this ladder exists to prevent.

## Rule 4 — One attempt, one artifact root

Retries that write to the same output paths shadow each other. On 2026-08-18 a
failed attempt's `meta.json` sat beside a later attempt's receipt at the same
path; the agent read the stale failure and spent minutes debugging a run that
was healthy. Give every attempt its own output root (attempt-numbered or
timestamped). When reading an artifact, check its timestamp against the attempt
you think produced it.

## Rule 5 — Kill procedures that do not kill you or strand locks

Three self-inflicted wounds from one session:

- **`pkill -f` and `grep /proc/*/cmdline` match your own shell** when the
  pattern appears in your own command line — this killed the agent's shell
  three times, once taking a freshly-launched run with it. Kill by specific
  pid. Resolve pids with `fuser <lockfile>` or by reading `/proc/<pid>/cmdline`
  from a helper script written to disk first, invoked by a clean command line
  that does not contain the pattern.
- **Killing a wrapper orphans its children holding locks.** A killed submit
  wrapper left a node child holding the per-tab lock twice. After killing a
  tree, verify the lock is free (`fuser` on the lock path) and kill surviving
  children by pid.
- **Retrying wrappers respawn.** A lane with an internal retry loop respawns
  its transport child after you kill it. Kill the tree by run id, verify
  nothing respawned, then proceed.

## Rule 6 — A human-named target is binding

When the human names a destination (a tab id, a pane, a branch), delivery there
is the deliverable. If the named destination cannot accept delivery, the
outcome is `NEEDS_ATTENTION` plus the evidence plus the options — the human
decides. Silently rerouting to a destination the agent prefers (a fresh tab, a
different pane) converts a transport failure into a broken promise: on
2026-08-18 the agent rerouted to `--create-tab` on its own authority and the
human, watching the named tab, correctly read every subsequent progress report
as false.

## Rule 7 — Pressure is a signal the receipts were late

If the human is escalating — "I'm looking at it", "read the file", "either do
the work or don't" — the correct response is the receipt they should already
have: the destination read-back, verbatim, this turn. Nothing else. An agent
whose claims are always accompanied by destination receipts never needs to be
threatened, because there is nothing to distrust; requiring pressure to
produce accuracy is the failure this skill exists to end.

## Related skills

- `$ask` — owns browser-handler orchestration; its SKILL.md is the canonical
  example of a contract that must be read whole.
- `$surf` — owns browser transport; its host log is the independent acceptance
  receipt for ChatGPT lanes.
- `$debugger` — the escalation ladder above is its receipts-first discipline
  applied to delivery.
- `$agentic-evals` — the mechanical enforcement layer; encode a delivery
  contract as `real_world` cases asserting destination read-back, so the rule
  holds without anyone remembering it.
