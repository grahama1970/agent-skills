# Ask a Pi subagent or team

`$ask` is the front door; Nico's `pi-subagents` runs Pi-local children.
These are chat prompts inside Pi, not `./run.sh pi ...` shell commands.
Ask's Python CLI cannot invoke a tool owned by a running Pi host.

## One read-only reviewer

Paste into Pi:

```text
$ask pi reviewer inspect skills/battle/src/battle_skill/orchestrator.py.
Trace where Judge results enter scoring. Cite file:line evidence.
Do not edit files, run target code, or launch a Battle.
```

The parent first calls:

```js
subagent({ action: "list", capabilities: true })
```

If `reviewer` is executable and not disabled, dispatch:

```js
subagent({
  agent: "reviewer",
  task: "Read skills/battle/src/battle_skill/orchestrator.py and its Judge/scoring callers. Trace where Judge results enter scoring; cite file:line evidence. Read-only; no target execution or Battle launch.",
  async: true,
  context: "fresh",
  worktree: false,
  output: "judge-review.md"
})
```

Agent names come from discovery, not this example. If a name is unavailable,
stop with `PI_SUBAGENT_NOT_EXECUTABLE`; do not silently select another agent.
An external-CLI profile is not a Pi-native child, even if its executable exists.

## Choose each model and reasoning level

```text
$ask use Pi-native subagents. Use <provider>/<model-a>:low for the scout
and <provider>/<model-b>:high for the evidence reviewer. Read-only.
Do not substitute models or lower reasoning. Report what actually ran.
```

Replace the placeholders with exact IDs from Pi's live model registry:

```js
subagent({ action: "models", agent: "reviewer" })
```

Native Pi dispatch encodes reasoning in `model`, for example
`"<provider>/<model>:high"`. This is **not** Tau's `model-high` handler grammar.
The top-level `thinking` tool parameter is for watchdog configuration, not child
dispatch. Omitting the suffix lets the selected agent's defaults decide; a
reviewer can therefore run at high even when the parent uses low.

For a team, put `model` on each `runs.all` item:

```js
const results = await runs.all([
  { key: "scout", agent: "scout", model: "<provider>/<model-a>:low", task: "Trace the named caller. Read-only.", output: "scout.md" },
  { key: "review", agent: "reviewer", model: "<provider>/<model-b>:high", task: "Check the named evidence files. Read-only.", output: "review.md" }
]);
return results.map(result => result.artifactPaths);
```

This snippet belongs inside the one async `workflowScript` call below. A
workflow-level `model` supplies a default; explicit child models override it.
Use only reasoning levels supported by the selected provider/model. Read each
child's persisted `steps[].model`, `steps[].thinking`, and `attemptedModels`
from native status artifacts before asserting that the request was honored.
A configured fallback is not proof that the requested model ran. If strict
selection was requested and the resolved model or thinking differs, report the
mismatch as failed acceptance; never silently credit the substitute.

## Two scouts working together

```text
$ask use Pi-native subagents as two read-only scouts for Battle.
One traces CLI-to-Judge wiring. The other compares saved generated files
with the hashes recorded in their manifests. Give both the Battle goal,
the current assessment, and the no-edit/no-campaign constraints.
Run them concurrently, return both reports, then propose one repair plan.
Do not implement the plan yet.
```

After discovery, use **one** top-level async workflow. This is illustrative
host-tool JavaScript; Pi executes it, not Node or the Ask shell CLI. Supply the
actual assessment path in the shared context when one has been produced.

```js
subagent({
  async: true,
  context: "fresh",
  worktree: false,
  globalConcurrencyLimit: 2,
  maxSubagentSpawnsPerRun: 2,
  workflowScript: `
    const shared = "Read skills/battle/SKILL.md and GOAL_ADAPTIVE_LINEAGE.md. Work only in the primary checkout on main. Read-only: no edits, worktrees, target execution, or Battle launch. Report observed evidence separately from inference.";
    const results = await runs.all([
      { key: "wiring", agent: "scout", task: shared + " Trace the ordinary CLI through Red, Blue, Judge and scoring; cite file:line evidence.", output: "wiring.md" },
      { key: "integrity", agent: "scout", task: shared + " Compare the saved adaptive-lineage generated files to their manifest hashes. List expected and actual hashes; do not repair them.", output: "integrity.md" }
    ]);
    return results.map(result => ({
      outputReference: result.outputReference,
      artifactPaths: result.artifactPaths
    }));
  `
})
```

`runs.all` returns an **ordered array**. Do not use `results.wiring`. Return
runtime output references: saying "write wiring.md" in task prose does not
bind the output path. Read both reports before claiming the work is complete.
The parent may synthesize factual scout findings; this is not a roundtable,
a competition, or an independently accepted implementation.

## One writer after the plan is approved

```text
$ask pi worker apply the approved documentation correction only to
skills/ask/docs/PI_NATIVE_SUBAGENTS.md. Use primary main, no worktrees,
and no other writers. Run the plan's named check and read back its output.
Return changed paths, exact commands, results and remaining uncertainty.
Do not change the test expectation just to obtain a pass.
```

Use a single native child, not a writer fanout. The parent must not edit the
same checkout while the child writes. Existing creator/reviewer repair loops
still run through `$ask tau-dag` and Tau; a native worker or review opinion does
not manufacture Tau acceptance. A persistent development team can retain one
Pi mission with decisions, run IDs, and artifact references.

## Follow up without starting a second team

Use the actual run ID returned by the tool:

```js
subagent({ action: "status", id: "<actual-run-id>" })
subagent({ action: "steer", id: "<active-run-id>", message: "Limit the investigation to Judge wiring; do not edit." })
subagent({ action: "children.list" })
subagent({ action: "resume", id: "<resumable-child-run-id>", message: "Check this specific caller against your earlier finding." })
```

Resume only a child reported resumable. Use native `subagent_supervisor` to
answer a child's `contact_supervisor` request. Use `pi-intercom` for a separate
project's Pi session, not as a second parent/child protocol. Ordinary async
completion wakes Pi; interactive callers yield instead of polling or sleeping.

## What must not change routes

| Request | Owner |
| --- | --- |
| `$ask pi reviewer ...` | Native Pi `subagent` tool |
| `$ask use Pi-native scouts ...` | One native async `workflowScript` |
| `$ask webgpt ...` / `$ask webkimi ...` | Existing Ask/Tau browser-handler path |
| `$ask tau-dag ...` / `$ask roundtable ...` / `$ask compete ...` | Existing Ask/Tau workflow |
| Native tool missing | `PI_SUBAGENTS_UNAVAILABLE`; no substitute |
| Named native agent missing or disabled | `PI_SUBAGENT_NOT_EXECUTABLE`; no substitute |

Do not invent `./run.sh pi reviewer`, call SciLLM directly, or use an external
CLI as a hidden fallback. A startup failure must retain its actual error and
run directory. Repair and retry the same protocol, or request explicit owner
approval to change execution mode.

Fresh context does not isolate files or Memory. Read-only task instructions
are not an OS sandbox. Battle target/probe/patch execution remains authorized,
Docker-isolated, and judged by Battle—not by a model's PASS statement.

## Retained agentic evals

**Live validation, 2026-09-05:** all six cases passed both trials (12 trials),
with all three declared critical claims proven. The team ran
`openai-codex/gpt-6-astra:low` and `openai-codex/gpt-5.5:high` concurrently.
The checker read each child's session, model/thinking, nonce and computed sum;
it did not accept the parent's summary. Five altered-evidence cases were
rejected: missing dispatch, missing discovery, wrong nonce, wrong model and
wrong reasoning. These counterfactual mutations are deterministic checks over
real run evidence; provider outputs in the live cases are not mocked.

Local report:
`/mnt/storage12tb/skills/ask/outputs/pi-subagents-evals/distinct-model-report.json`.
The earlier failure reports remain beside it for diagnosis; do not report them
as the current result.

### Runtime repairs used by that proof

Pi 0.85.1 lists its server/client packages as devDependencies, so the normal
npm installation lacked modules required by background children. Installing
the matching published runtime packages restored the public SDK import:

```bash
npm install -g --ignore-scripts @earendil-works/pi-server@0.85.1 @earendil-works/pi-client@0.85.1
```

This is a version-specific installation repair, not permission to mix arbitrary
Pi package versions. Recheck SDK import and the live suite after Pi upgrades.

Native discovery also traversed 236,105 paths through this host's `~/.agents`
monorepo symlink. The fix prunes skill/provider subtrees **before** descent and
fingerprinting; explicitly configured roots remain supported. The symlink was
not changed. The small source patch and fail-before/pass-after regression are
retained in [pi-subagents-skill-tree-pruning.patch](../patches/pi-subagents-skill-tree-pruning.patch),
based on upstream `379a0daa`. Apply only after `git apply --check` in the primary
Pi-subagents checkout; do not apply it blindly after an upstream change.

Pi's user `packages` entry now points to
`/home/graham/workspace/experiments/pi-subagents`, the repaired primary checkout,
rather than the disposable Git package clone. No source was copied into another
runtime. Existing Pi sessions need `/reload`; newly launched hosts read that
configured path, including this eval. Upstream push permission was unavailable,
so the patch is retained in agent-skills rather than claimed as merged upstream.

From the primary repository root:

```bash
# Select a different, available second model from `pi --list-models`.
ASK_PI_EVAL_TEAM_MODEL=openai-codex/gpt-5.5 \
  skills/agentic-evals/run.sh run skills/ask/fixtures/agentic_eval_pi_subagents.json \
  --output /mnt/storage12tb/skills/ask/outputs/pi-subagents-evals/report.json \
  --timeout-seconds 600
```

Prerequisites: installed `pi`, authenticated model, and Nico's `pi-subagents`
package. The probe reads the configured local or canonical Git package from
Pi's user settings. `ASK_PI_SUBAGENTS_EXTENSION` explicitly overrides that path.
`ASK_PI_EVAL_PROVIDER` and `ASK_PI_EVAL_MODEL` override the current Pi model.
`ASK_PI_EVAL_TEAM_MODEL` must name a **different** available `provider/model`
without a reasoning suffix; the second child uses high. The example above was
selected from this host's catalog; replace it if unavailable or if it equals
your primary model. An unset/equal second model fails before dispatch so losing
per-child model overrides cannot pass unnoticed.
Generated evidence belongs under `ASK_PI_EVAL_ROOT` (defaults to the storage
path above), never in committed source. No automatic dependency installation,
provider substitution, or fixture-response fallback is permitted.

The suite drives real Pi with the current Ask skill and inspects actual tool
calls and child output. Each positive run uses new random input values and a
nonce so an old result cannot satisfy it. Negative cases exercise absent tools,
unknown agents, and missing/tampered execution evidence. The single child uses
explicit low reasoning; the team uses different model IDs at low and high and
checks each resolved model/thinking value in the child-owned native status,
not the workflow summary or just the requested arguments. It also checks the
existing WebGPT compile-only route without submitting to a browser.

Proof boundary: this validates Ask's **in-Pi routing instructions and native
child execution** in the bounded cases, not an Ask Python-to-Pi bridge,
universal agent reliability, arbitrary writing tasks, sandbox security, or
Battle acceptance. A live failure leaves the feature unproven even when the
documentation checks pass. The retained checks catch the named regressions;
no finite suite makes all future regressions impossible.
