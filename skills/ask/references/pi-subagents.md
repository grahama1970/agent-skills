# Ask: Pi-Native Subagent Target

Read before routing an explicit `pi`/`subagent`/`local reviewer` target through
the native `subagent` tool.

## Pi-Native Subagent Target

Inside Pi, `$ask` remains the front door. When the user explicitly names a
Pi-local target such as `pi`, `subagent`, `pi-subagent`, `local reviewer`, or
`local coder`, route the request through the native `subagent` tool instead of
Tau, Surf, Herdr, or SciLLM. This is the only approved substitution of a
subagent for `$ask`, because the user selected the Pi-native target type.

Required behavior for Pi-native subagent targets:

1. Call `subagent({ action: "list", capabilities: true })` before launching.
   Use only executable, non-disabled agents from that live registry. An
   external-CLI profile additionally requires `runner.available === true`;
   do not substitute one for a requested Pi-native agent.
2. Choose the named agent when the user names one. If they only name a role,
   use the closest live Pi agent role and state the mapping.
3. Use a direct `{ agent, task, async: true }` call for one child. For a team
   or sequence, use exactly one top-level `{ workflowScript, async: true }`
   call; launch its children with `runs.run` / `runs.all`. Await every result;
   `runs.all` returns an ordered array, not a key map. Do not manually simulate
   Tau, roundtable, compete, or creator-reviewer receipts.
4. Keep browser/model Ask traffic on the existing Ask/Tau paths. Never route
   `$ask webgpt`, `$ask webkimi`, `$ask tau-dag`, `$ask roundtable`, or
   `$ask compete` through Pi subagents.
5. Report the child run id/output as reviewer or worker evidence only. Local
   task closure still requires deterministic proof from the parent session.

The shell CLI `./run.sh` cannot call Pi host tools. This route applies when the
skill is invoked inside Pi through `$ask` or `/skill:ask` context. Non-Pi CLI
callers must use the documented `./run.sh` Ask/Tau commands.

### Copyable Pi prompts

```text
$ask pi reviewer inspect skills/battle/src/battle_skill/orchestrator.py. Read-only. Cite file:line evidence; do not run a Battle.

$ask use Pi-native subagents as two read-only scouts for Battle. One traces CLI-to-Judge wiring; the other checks saved code against manifest hashes. Run concurrently, return each report, then propose one repair plan. Do not edit or launch a campaign.

$ask pi worker apply only the approved documentation correction in skills/ask/docs/PI_NATIVE_SUBAGENTS.md. One writer on primary main; no worktrees. Read back the change and run the named check before reporting.
```

Read [Pi-native examples and evals](docs/PI_NATIVE_SUBAGENTS.md) for actual
host-tool calls, per-child model/reasoning selection, output handling, follow-up
controls, and proof boundaries. Honor an explicit model with the native
`model: "<provider>/<model>:<reasoning>"` syntax, on each `runs.all` item when
models differ. Discover allowed models with `subagent({ action: "models",
agent: "<agent>" })`. Do not use Tau's `model-high` syntax or dispatch-level
`thinking` (that field configures the watchdog). Verify the child's resolved
`steps[].model`, `steps[].thinking`, and `attemptedModels` in its status
artifacts. Unsupported choices or strict-selection mismatches fail acceptance;
a requested value is not proof of the model/reasoning actually used.
Use `output` on each child when its report must survive the run; return the
runtime's `outputReference` or `artifactPaths`, not an invented filename.
Keep one writer per checkout. For agent-skills, use primary `main` with
`worktree: false`; parallelism is for read-only work, not concurrent writers.
Fresh context is not a filesystem sandbox. Target execution still obeys the
owning skill's authorization and Docker requirements.

If the native tool is absent, report `PI_SUBAGENTS_UNAVAILABLE`. If the named
agent is absent or disabled, report `PI_SUBAGENT_NOT_EXECUTABLE` and name it.
Do not answer on the missing child's behalf or silently switch to Tau, a
browser, an external CLI, or foreground execution. For a launch failure,
preserve the exact failure and run artifacts; retry only the same protocol
after diagnosing the cause. Async runs notify Pi on completion; do not poll in
a sleep loop or use `bg_wait` merely to wait in an interactive chat.

The retained suite is `fixtures/agentic_eval_pi_subagents.json`. It exercises
real Pi model/tool traffic and independently checks child artifacts. Its
negative cases must reject missing execution evidence, unavailable native
tools, and unavailable named agents. See the linked guide for the command.

