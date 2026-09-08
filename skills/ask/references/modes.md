# Ask: Mode Selection In Depth

One-shot vs roundtable vs compete examples, model/execution-binding rules,
and reasoning/effort selection. Read before choosing or arguing a mode, and
before passing any model selector beyond the quickstart table.

### One-shot vs roundtable vs compete — good and bad examples

Pick the mode from what the DELIVERABLE is, not from how many seats you want.

**one-shot** — the deliverable is N independent answers, side by side.
No consensus, no judge, no quorum: 1/3 answers is a usable result. Full
contract in `$best-practices-one-shot`.

Human says: *"/ask webgpt, webclaude and oc-deepseek: how would you paginate
this API?"* — a question to several seats where the human reads each answer.

```bash
# GOOD: several perspectives on a question; you will read each answer yourself.
./run.sh one-shot "How would you paginate this API?" \
  --handler webgpt --handler webclaude --handler oc-deepseek
```

Converts to N fully independent single-call DAGs (no shared node at all —
one seat's failure cannot reach another lane even in principle):

```text
[handler-webgpt] -> human      [handler-webclaude] -> human      [handler-oc-deepseek] -> human
```

- BAD: using one-shot and then summarizing the answers into a "consensus"
  yourself — that is a roundtable without its equal-packet and quorum
  guarantees. Use roundtable.
- BAD: using one-shot to "pick the best answer" — that is a competition
  without isolation or an independent judge. Use compete.
- BAD: treating a one-shot with 0 answers as a pass because every lane named
  a blocker. It exits 3 NOT_READY; honesty is not readiness.

**roundtable** — the deliverable is one deliberated position built over an
identical packet, with quorum (three answering seats) and per-seat status.

Human says: *"/ask webgpt, webclaude and gpt-5.5 to discuss whether ask
should adopt lane-local retries and give me a recommendation"* — one
position is wanted, built from equal-context deliberation.

```bash
# GOOD: a decision that benefits from cross-model deliberation and synthesis.
./run.sh tau-dag "Should ask adopt lane-local retries? Argue and conclude." \
  --repo local/agent-skills --target retry-policy \
  --immutable-goal "A defensible recommendation with dissent recorded" \
  --dag-template roundtable --topology concurrent \
  --handler webgpt --handler webclaude --handler gpt-5.5-high --execute --json
```

Converts to concurrent handler nodes settling through a virtual join-gate
(tau join contract, policy all_terminal) so a failed lane degrades
lane-local, then one join that synthesizes with per-seat status:

```text
[handler-webgpt]----\
[handler-webclaude]--->[join-gate]-->[join]-->human
[handler-gpt-5-5-high]/
```

- BAD: tailoring any seat's packet ("you are the security expert, others are
  not told...") — equal context is the contract; a tailored packet is a
  violation the evals catch.
- BAD: reporting a 2-seat result as a panel. Below quorum the run must be
  refused, not summarized.
- BAD: declaring consensus while one seat is dead. Consensus over a dead
  seat is a violation; the dead seat's failure_code must be surfaced.

**compete** — the deliverable is a winner chosen by an INDEPENDENT judge from
ISOLATED candidates, with receipts. Candidates never see each other.

Human says: *"/ask webgpt, webclaude and oc-deepseek to each implement the
parser fix, then have Codex-opus-5 pick a winner with a rationale"* — the
human wants ONE implementation chosen on evidence, not a discussion.

```bash
# GOOD: multiple plausible implementations; local verification will follow.
./run.sh compete "Implement the parser fix. Return APPROACH/CHANGES/RISKS/PROOF_COMMANDS." \
  --repo local/agent-skills --target parser-fix \
  --immutable-goal "A locally verifiable fix" \
  --handler webgpt --handler webclaude --handler oc-deepseek \
  --judge-handler Codex-opus-5-low \
  --criterion correctness --criterion minimality --execute --json
# Then ALWAYS: ./run.sh panel-audit <run-dir> --mode compete
#              ./run.sh judge-audit <run-dir> --run-winner-proof
```

Converts to isolated candidate nodes through the join-gate, then the judge
(verdict must end `WINNER: <competitor-node-id>`), then the join (topology
read back from a real compiled dag.json):

```text
[handler-webgpt]----\
[handler-webclaude]--->[join-gate]-->[judge]-->[join]-->human
[handler-oc-deepseek]/
```

- BAD: making a competitor seat the judge, or letting the judge's prose stand
  unaudited — judge-audit exists because a scorecard is a claim until checked.
- BAD: counting dispatched seats as candidates. One answer wearing a
  competition's artifacts is a single opinion; panel-audit fails it.
- BAD: sharing one candidate's output with another to "help them improve" —
  that contaminates the competition; restart or convert to a roundtable.

Before executing any multi-seat DAG, compile first (omit `--execute`), show
the human the ASCII chart the CLI prints, and run only on their confirmation.

### Model selection is not execution-mode selection

For model/API work the route is **Ask → Tau → SciLLM**. A workspace binding
must never silently replace that route with a CLI runner.

| Selector | Workspace binding | Declared execution route |
| --- | --- | --- |
| `claude-fable-low`, other `claude-*`, or `gpt-5.5-high` | Not supported | Tau-owned `scillm.chat` |
| `gpt-5.5-xhigh` | Not supported | Tau-owned `subagent-runner.codex_exec` advisory lane |
| `codex` | Required: `--handler-workspace codex=/absolute/path` | Explicit local `codex.exec` authoring lane |
| `webgpt` and other browser handlers | Not supported | Provider-specific Surf adapter |

`--handler-workspace` is **not** a generic way to give an API model filesystem
access. API chat does not execute local proof commands. Use an explicitly
supported Tau tool-execution workflow when that capability is required; do not
turn a model selector into a different provider/runner by attaching a path.

Compilation and workers validate `HandlerExecutionBinding` with strict Pydantic
fields. An incompatible binding returns `ask_handler_binding_invalid` before
DAG dispatch. Old contradictory command specifications are rejected at the
worker boundary as well. Missing required fields or extra binding fields are
validation errors, not a reason to try another model.

### Reasoning / Effort Selection

For Tau handler DAGs, choose reasoning effort as part of the non-browser
handler selector unless the runtime exposes a future explicit effort flag. The
current supported Ask handler grammar is:

```text
<exact-model-id>-<effort>
```

Current Ask/Tau handler suffixes are `low`, `medium`, `med`, `high`, and
`xhigh`. `med` normalizes to `medium`. `xhigh` is preserved as the requested
selector, but the current SciLLM adapter dispatches it as `high` and records the
downgrade. Do not use `max` as an Ask handler suffix unless a future local
`./run.sh tau-dag run --help` shows an explicit supported flag and the emitted
receipts prove the applied effort.

Use exact dynamic model ids from the provider/SciLLM catalog as the model part.
For Claude Fable, use a selector such as `claude-fable-low`, which resolves to
the SciLLM catalog model `claude-fable-5` with the requested effort recorded.
For Codex, use exact current Codex catalog ids with the effort suffix appended
when needed:

```bash
./run.sh tau-dag "Review this bundle" \
  --repo local/agent-skills \
  --target ask-review \
  --immutable-goal "Return a receipt-backed review with explicit blockers." \
  --handler Codex-opus-5-high \
  --execute --json

./run.sh tau-dag "Compare these repair options" \
  --repo local/agent-skills \
  --target ask-roundtable \
  --immutable-goal "Each seat returns a usable position or a blocker." \
  --dag-template roundtable \
  --handler Codex-sonnet-4-6-medium \
  --handler gpt-5.5-xhigh \
  --topology concurrent \
  --execute --json
```

Do not invent partial aliases such as `opus-5-high`, `sonnet-high`,
`Codex high`, or `webclaude-high`. `webclaude` is a browser chat tab and has no
Ask-controlled reasoning effort. If the human asks for "Codex Opus 5 max" and
the current Ask runtime has no supported `max` selector, fail closed unless the
human explicitly accepts the highest supported Ask selector
(`Codex-opus-5-xhigh`) and the report states that `xhigh` dispatches as `high`
in the current SciLLM adapter.

Every executed API/model lane must preserve the effort evidence in the emitted
Tau artifacts. Inspect the command spec and node receipt for:

- `requested_model`: the exact selector the caller requested, such as
  `Codex-opus-5-xhigh`
- `model`: the resolved model id dispatched to SciLLM, such as `Codex-opus-5`
- `requested_reasoning_effort`: the requested suffix, such as `xhigh`
- `reasoning_effort`: the effort actually dispatched, such as `high`
- `reasoning_downgrade_reason`: required when requested and dispatched effort
  differ

For non-Tau oracle synthesis (`./run.sh ask ... --oracle`), reasoning is chosen
with `--oracle-reasoning <low|medium|high|xhigh>` and defaults to `high`
(`xhigh` for deep review). This is a different path from Tau handler selection.

For executed roundtables and competitions with browser handlers, Ask defaults to
`--browser-tab-lifecycle auto`. Auto creates one Chrome window, creates one tab
per requested browser handler, binds temporary browser-oracle projects, runs
Tau, and closes only that Ask-created window. The project agent does not need to
pre-create tabs or pass `--handler-project` for normal web seats. Use
`--browser-tab-lifecycle fresh-keep` only when a human needs to inspect the tabs
after the run. Use `--browser-tab-lifecycle reuse-bound` only when the human
intentionally wants the same long-lived provider tabs to keep their conversation
context across the whole roundtable or competition; preflight every named tab
before submission and keep the same binding for every round.

