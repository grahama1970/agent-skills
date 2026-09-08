# Ask: Live Evals, Handoffs, Panel Audits, Seat Roster, Rate-Limit Substitution

Read when validating a finished panel, choosing seats, or handling a
rate-limited/unavailable provider seat.

### Live evals: the contract is honesty, not a fixed answer

```bash
skills/ask/run.sh live-seat-probe claude-opus-4-8-high
skills/ask/run.sh live-seat-probe claude-fable-low     # exercises self-recovery
skills/ask/run.sh live-seat-probe webgemini
```

Deterministic tests over local functions proved nothing about whether `/ask`
works: every real defect this session came from a live run, and none from a
test. These cases call real providers, so they are non-deterministic by design.

A live provider may answer, rate limit, or stall, and none of that is under our
control. Asserting a fixed answer would go red whenever a provider is merely
busy, and everyone would learn to ignore it. So the contract is:

> a seat either answers with real content, or names why it did not.

Both outcomes pass. Three things fail, whatever the provider was doing:

| violation | why it matters |
| --- | --- |
| `PASS` with zero response bytes | a green run that produced nothing |
| a non-PASS status with no `failure_code` | a dead end nobody can act on |
| a **generic** `failure_code` where a specific cause is knowable | `browser_handler_timeout` hiding an attachment-shape rejection (#1531) |
| a different model answered, unrecorded | a reply that looks fine and silently came from elsewhere |

Ask composes `/triage-error`: `browser-recovery-packet.json` carries a canonical
`triage: {code, cause, next_command}` from the shared catalog, and a failed
webgpt lane writes `node-artifacts/handler-*/preflight-doctor.json` — so a
browser-lane bug is diagnosed from the run dir, unambiguously, not from
`/tmp/surf-host.log`.

The third caught a real bug minutes after the rate-limit fallback was added:
the receipt read `claude-fable-low PASS` while `claude-opus-4-8` had written the
answer. The substitution is now recorded in the node receipt:

```json
"rate_limit_fallback": {
  "from": "claude-fable-low", "to": "claude-opus-4-8-high",
  "reason": "provider_rate_limited"
}
```

A timeout is a named outcome, not a violation — that is exactly the
non-determinism these accept.

### Where did this run hand off to?

```bash
skills/ask/run.sh handoff            # most recent run
skills/ask/run.sh handoff <run-dir>  # a specific run
skills/ask/run.sh handoff --json
```

Every node emits a `tau.agent_handoff.v1` payload naming its result, its
evidence and the next agent. Those used to be printed to stdout and lost, so
after a run there was no way to answer where it handed off or what it carried --
the one seam in Ask with no artifact, and the seam whose entire purpose is
telling the next agent what happened. They are now written as `handoff.json`
beside each node receipt, and this reads the chain back in order.

A run with no handoff artifacts says so, rather than printing nothing: it
either predates this or no node completed.

### Auditing a panel against the best-practices contracts

```bash
skills/ask/run.sh panel-audit <run-dir> --mode roundtable
skills/ask/run.sh panel-audit <run-dir> --mode compete
```

`best-practices-roundtable` and `best-practices-competition` state rules that
decide whether a panel's output means anything. They lived only in prose, so
"this run complied" was an assertion nobody could check. This reads a finished
run directory and answers from artifacts:

| check | rule |
| --- | --- |
| `equal_context` | every seat received the same task body |
| `seat_status` | every seat accounted for from its own artifacts |
| `no_silent_consensus` | no agreement claimed over a seat that never answered |
| `isolation` | no candidate was shown a rival's response |
| `roundtable_quorum` | three seats **answered**, or the run reports the shortfall |
| `competition_outcome` | two candidates **answered**, and no winner without evidence |

`roundtable_quorum` runs in `--mode roundtable`, `competition_outcome` in
`--mode compete`; the first four checks run in both.

Equal context is measured on the task body, not raw bytes: `Handler:`,
`Model:`, `Seat:`, `node_id:` and `Browser model preference:` are per-seat
addressing and may differ. Everything else that differs is a tailored packet.

Both floors count seats that **answered**, never seats dispatched. A run that
dispatched two seats and received one is a single opinion; the live run on
2026-08-16 did exactly that while its scorecard read `candidates: 2`, and
stayed honest only because it also reported `NEEDS_ATTENTION`.

The floors differ because the modes differ. A competition at two candidates is
a real head-to-head. A roundtable at two has no majority to hold and no dissent
to attribute, so it collapses to one opinion as soon as a seat drops — hence
three, and hence seating five so three can still answer. The numbers live in
`ROUNDTABLE_MIN_ANSWERING` / `COMPETITION_MIN_ANSWERING` in
`src/ask/panel_compliance.py`; `prove-workflow` imports them rather than
restating them.

### webclaude is testing-only

A claude.ai web call is billed the same as an OAuth call, so there is no reason
to spend a browser seat, a window, and Chrome contention on it. Use the local
Claude lane. `webclaude` exists to test the browser path itself; for that
testing, `claude-opus-5` is the model to use.

When `webclaude` is requested and unavailable it is the ONE named seat that
auto-substitutes, to **`claude-opus-5-high`** (then `claude-opus-4-8-high`,
then `claude-fable-low`), because
preferring the local lane is the policy rather than a workaround. Every other
named browser seat blocks with its failure code instead of quietly answering as
something else.

The takeover happens at BOTH selection and submit time. The availability probe
can only see an account banner if some existing claude.ai tab is showing one; a
fresh tab shows nothing until the submit is attempted, so a selection-only
fallback fires or does not depending on which tabs happen to be open.

Proven live 2026-08-16: claude.ai reported "You're out of usage credits" and the
run answered from `handler-claude-opus-5-high`, status DEGRADED, substitution
recorded.

### The preferred seat roster

Five browser providers plus the local Claude lane:

```
webgpt  webgrok  webkimi  webdeepseek  webgemini  claude-fable-low
```

with **`claude-opus-4-8-high`** as the fallback when Fable is rate limited.

Spread matters because providers rate-limit independently. Measured 2026-08-16:
`browser-availability` reported webgpt `limited: true` on both its tabs while
webgpt was, at that moment, the only browser seat that worked at all. A panel
drawn from one or two providers is one rate limit away from no panel.

`claude-fable-low` is the local Fable 5 lane at low reasoning effort; it needs
no browser, no tab, and no Chrome contention, and it carries a real reasoning
selector. Both ids resolve through the SciLLM route table:

```
claude-fable-low      -> claude-fable-5   effort=low
claude-opus-4-8-high  -> claude-opus-4-8  effort=high
```

**`webclaude` is not in the roster.** It is a claude.ai chat tab: no tools, no
repo access, no Ask-controlled reasoning effort, and one more seat competing for
the same Chrome. It stays reachable by explicit name and is always ordered last.
Live-web questions still lead with a browser seat, since a chat tab with search
is better at those than a local model without one.

The roster lives in `PREFERRED_PANEL_ROSTER` and is eval-gated, including a case
that fails if a roster seat has no launch URL.

### When a web seat is rate limited

Rate limits and unavailability are reported explicitly — `browser-availability`
names the provider, and `browser-provider-selection.json` records
`removed_handlers` with a `failure_code`. A limited provider is **removed** from
the roundtable, competition, or MVP rather than retried into a timeout.

The seat is then refilled by that provider's **local same-family equivalent**,
not by another copy of whatever is left:

| removed seat | local family |
| --- | --- |
| `webkimi` | `kimi` |
| `webdeepseek` | `deepseek` |
| `webgemini` | `qwen` |
| `webgrok` | `glm` |
| `webgpt` | `qwen` |

Family-for-family preserves the diversity a panel exists for; collapsing every
removed seat onto one model produces a panel that agrees with itself.

Build selection inside a family is capability-driven:

- **text question → `flash`.** Reaching for `pro` by default spends the capable
  build on work that never needed it.
- **multi-modal question → `pro`**, selected by asserting `image`/`pdf` input
  support against the live catalog. A multi-modal question can never land on a
  text-only build; if no configured model supports the input, the substitution
  returns nothing instead of answering blind.

Model ids come from the live OpenCode Go catalog, so preference lists may name
a build that does not exist yet — `opencode-go/kimi-k3` sits ahead of `k2.6` and
is simply skipped until scillm reports it. That is how a newer model is
preferred without inventing a working name.

### Prefer the local Claude lane over webclaude

Handler preference for Claude work, in order:

1. **`claude-fable-low`** — local Fable 5 at low reasoning effort. Preferred
   outright.
2. **`claude-opus-4-8`** — when Fable is rate limited.
3. **`webclaude`** — last resort only.

`webclaude` is a claude.ai chat tab: no tools, no repo access, no Ask-controlled
reasoning effort, and one more seat competing for the same Chrome. The local
lane answers the same questions with effort control and no browser at all.
Live-web questions still put a browser seat first, since that is what a chat tab
is actually better at.

This ordering lives in `WEBCLAUDE_PREFERRED_SUBSTITUTES` and is eval-gated.
Before it, the fallback list filtered to browser names only, so every Codex
fallback was forced onto a chat tab by construction.

