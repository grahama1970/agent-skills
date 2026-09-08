# Ask: Talk To Another Agent's Session (Herdr)

Read before `./run.sh herdr list|who|send`.

## Talk To Another Agent's Session (Herdr)

Agents working in different Herdr sessions reach each other by name. Three
verbs, no ids to look up first:

```bash
cd skills/ask
./run.sh herdr list                 # every session you can talk to
./run.sh herdr who memory           # what does this name resolve to?
./run.sh herdr send memory "Please fix graph-memory-operator#105"
```

`NAME` is whatever you already know — a project directory (`memory`), a GitHub
repo (`graph-memory-operator`), or an exact pane id (`w11:p13`). The first two
disagree on this machine: `~/workspace/experiments/memory` *is*
`grahama1970/graph-memory-operator`. Both spellings resolve to the same panes,
so you never have to remember which name a project answers to.

**Ambiguity is refused, never guessed.** Names are not unique — `memory`
currently matches 5 live panes and `agent-skills` 44. `send` stops and prints
the candidates plus a ready-to-paste command:

```
'memory' matches 5 live panes:
  w11:p13 [codex/idle]    /home/graham/workspace/experiments/memory
  w7E:pK  [Codex/idle]   /home/graham/workspace/experiments/memory
  w88:p1  [opencode/idle] /home/graham/workspace/experiments/memory
Pick one by pane id:
  ./run.sh herdr send w11:p13 "<message>"
```

When names collide, `send` runs `$interview` and asks which session, listing
**session, model, and directory** for every candidate — the three facts that
tell identical names apart. Answer the question and the message is delivered;
no second command needed.

Exit codes let a caller branch without parsing prose: `0` delivered, `2`
ambiguous, `1` nothing addressable matched. `--json` returns the candidates
instead of interviewing, so a machine caller drives its own disambiguation;
`--no-interview` fails closed on ambiguity.

Two panes are never chosen for you:

- **Dead panes.** No agent attached, or Herdr reports `blocked`/`unknown` —
  that is monitor-herdr's rule, reused here, and it means a human or a wedged
  agent owns the pane.
- **Busy panes.** An agent mid-task is excluded so a message cannot interrupt
  running work by accident. Pass `--busy` when interrupting is the intent.

Delivery goes through `herdr pane run`, the same transport `$monitor-herdr`
uses. A success receipt proves the prompt was *submitted*, not that the other
agent understood or acted on it — treat it as delivery proof only.

**`submitted: true` is herdr reporting on itself.** During development it
returned exit 0 for a pane whose content never showed the message, so confirm
delivery independently with `herdr pane read <pane_id>` when it matters.
`scripts/herdr_e2e_probe.sh` does exactly that and is wired into the agentic
evals as `herdr-live-delivery-readback-e2e`.

**Bidirectional round-trip** is proven separately by
`scripts/herdr_roundtrip_probe.sh` (eval case
`herdr-bidirectional-roundtrip-e2e`): it sends a nonce challenge and waits for
the agent's *reply*, requiring two or more occurrences — one for the echoed
prompt, one for the answer. Counting is harness-agnostic; reply markers are not
(codex renders `›` for input and `•` for output, other harnesses differ).
Round-trip needs a harness that echoes and answers in the pane, so it is
expected to work with pi/codex/Codex-style TUIs and to skip elsewhere.

**Some panes report `idle` but are dead.** A blank readback is not about which
agent is running — it is about whether anything is still drawing to the
terminal. A live `opencode` pane spawns a separate TUI child
(`~/.cache/opencode/tui/tui-*`) that renders the screen; the panes that read
back as 0 bytes have the `opencode` process alive with **no TUI child**, so the
screen is genuinely empty and nothing can receive input. Herdr reports both
states as `agent_status: idle`, so status alone cannot tell them apart.

The rule that follows: **a pane whose screen cannot be read is not proven
addressable.** Both probes check readability before sending, which is also what
prevents a message being stranded in a wedged session — the failure mode that
produced `submitted: true` with nothing delivered.

### Never interrupt a pane mid-task

`send` refuses a pane that is still working, and `agent_status` cannot decide
that: Herdr reports `idle` between the turns of an active task, and its pane
record exposes no idle-age field (only agent, status, cwd, and ids). On
2026-08-09 eight probe messages landed in a pane running a ticket-closure job
for exactly that reason.

The signal that works is the screen itself. `is_quiescent()` samples the pane
twice a few seconds apart and treats any change as work in flight — an agent
mid-task redraws, a settled one does not. An unreadable pane counts as busy,
never as free. Pass `--interrupt` when interrupting is the intent.

A composer heuristic was tried and removed: matching the last `>`/`›` line
reads a harness's transcript of the previously submitted prompt as if it were
live input, and flags greyed placeholder hints like `Implement {feature}` as
real text. Delivery is verified after the fact instead of predicted before it.

Two conditions the probes report honestly rather than as `/ask` failures: a
target that received the message but is **out of provider credits** (skip, not
fail), and a `pane run` that types text which the harness leaves **unsent in
the composer** — observed once on a Codex pane, where `submitted: true`
was reported for a message still sitting at the prompt.

