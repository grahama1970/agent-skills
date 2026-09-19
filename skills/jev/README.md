# Jev for the agent harness

**Let a small typed model make routine choices. Let the main model do work that
actually needs generation or substantial reasoning.**

This skill now includes a native TypeScript Pi extension and a native Python API
with a tool-registration decorator for Tau adapters. The two runtimes share
question definitions, input/decision contracts and conformance tests—not a
subprocess bridge. No Needle model is required.

## Why this exists

A coding agent should not repeatedly read a large skill catalog, consume irrelevant
memory, write prose just to pick a handler, or use a reasoning model merely to run
an already specified command. Jev handles bounded semantic decisions. Code handles
known rules, resource accounting, argument validation and execution.

The Needle-inspired part is the developer experience: declare an action, expose
its validated candidates, and get a typed selection back. Jev still does not invent
free-form arguments or execute the selected action.

## What is implemented, and what is not established

| Area | Current implementation |
|---|---|
| Pi | Off/shadow/active modes; scoped local Memory recall; one batched relevance call for memory + a bounded skill catalog; source-linked context; old own-context removal; cancellation/session isolation; metadata/usage receipts. |
| Python/Tau | Importable async client, typed decisions, classification, candidate ranking/selection, registration decorator and deterministic routing helpers. The owning Tau adapter must import/wire it. |
| Tool calls | Validated, already-bound candidate proposals. No second execution loop and no automatic side effects. |
| Model choice | Intent/capability classification and a deterministic recommendation helper over qualified, authorized, fresh capacity/cost snapshots. No live quota collection, reservation or automatic provider switching. |
| Memory outcomes | Shared consumer reducer distinguishes respond/continue/await-human/blocked. Pi preserves explicit backend human checkpoints. A complete direct-answer/QRA review UI is not claimed. |
| Proof | Offline contract and host-double tests. No claimed live semantic accuracy, production Pi/Tau qualification, or measured speed/token improvement. |

The immutable goal remains **NOT_ESTABLISHED** until retained live evidence proves
the outcome. See [IMMUTABLE_GOAL.md](IMMUTABLE_GOAL.md) and the machine-readable
[goal](immutable_goal.json). [SKILL.md](SKILL.md) governs agent behavior.

## How it fits

For a bug-fix request:

```text
ingest-code -> governed Memory code projection
                         |
Pi request -> scoped recall of code symbols + relevant lessons
                         |
             Jev ranks a bounded candidate set
                         |
             compact evidence with source locators
                         |
             current-source/freshness check
                         |
             existing Pi/Tau diagnose -> patch -> test workflow
```

Memory can return current indexed symbols, source spans, resolved relationships,
tests and previous fixes. Jev ranks usefulness to the investigation, not certainty
that a function contains the bug. A prior failure or contradictory fact may be
more useful than a passage that agrees with the current theory.

The extension does not run ingestion per prompt. It requests lifecycle-current,
repository-scoped recall. That does not establish working-tree freshness: the
executor still uses `code-node` or `ingest-code ensure-current` before edits.
Missing or stale indexing is not a reason to deflect legitimate coding work.

### Intent, answer, clarify, deflect and draft

The pipeline belongs to Memory, not to SPARTA alone and not to a duplicate Pi
implementation. The Pi adapter may consume `/intent` in fast mode and retrieve
context. Shared reducers map a host-validated Memory outcome to a harness decision.

An answer to a question can finish an informational request. An answer about a
bug does not finish a request to fix it. A real human checkpoint must pause further
tool execution. A provider error is not an empty memory result. A policy denial is
not a domain no-match.

Memory's `/draft` is the governed QRA product. Ordinary document/code drafts use
the appropriate skill. Neither this extension nor a decorator signs QRA records.
SPARTA retains its evidence/review interface and domain-specific presentation.

## Pi installation

From this skill directory:

```bash
npm install
npm test
npm run typecheck
pi -e ./typescript/pi.ts
```

For normal use, install the skill directory as a Pi package or add the absolute
path of `typescript/pi.ts` to your existing Pi extension settings. This package's
`pi.extensions` entry exposes the extension. Do not replace your whole settings file.

Copy `examples/jev.pi.json` to the target project's `.pi/jev.json`. It starts off,
with Memory disabled and no egress permission. Missing/invalid configuration also
disables the extension. Do not enable duplicate Memory First injectors.

To prepare a **synthetic/public pilot**, set `mode` to `shadow`, explicitly set
`policy.allow_egress` and `policy.data_class`, then optionally replace `memory:null`:

```json
{
  "url": "http://127.0.0.1:8601",
  "scope": "code",
  "repo": "YOUR_REGISTERED_REPOSITORY_ID",
  "useIntent": true,
  "allowedModels": ["YOUR_PROVIDER/YOUR_MODEL_ID"]
}
```

`allowedModels` explicitly authorizes retrieved source for the active Pi model.
An empty/missing list or unknown model withholds source; the context hook rechecks
the allowlist on each request, including provider switches. Jev egress authorization
is separate and does not authorize every main-model provider.

Use the repository identifier registered in Memory; optional `branch` is an exact
filter. `useIntent` invokes only the existing fast intent path. The initial adapter
blocks terminal deflect/error outcomes conservatively; scope-only rerouting still
requires a qualified backend reason contract. It does not execute arbitrary
returned query-plan endpoints. Native calls use
`JEV_API_KEY` or `TYPESAFE_API_KEY`; never place keys in the project JSON.

`skillNames` bounds the pilot catalog drawn from Pi's existing loaded skill
metadata. Unlisted skills remain unchanged. `requiredSkills` and an explicit
`/skill:name` selection are retained. If the available candidate set is too large,
the extension preserves the baseline instead of arbitrarily taking the first
skills. A production catalog shortlister should come from shared Memory/catalog
infrastructure, not a new vector database inside this extension.

`/jev-status` shows the current mode and latest counts. In shadow mode the
extension retains baseline candidates while recording what Jev would exclude.
In active mode it removes only confident negative candidates, never uncertain or
pinned ones. Context-size budgeting is deterministic and reports omissions.

The `context` hook only prunes this extension's old custom messages. It does not
remove user instructions, unrelated memory, or unmatched tool-result messages.
An unchanged turn reuses its prepared context instead of making another Jev call
before every model request. New turns and session switches invalidate that state.

## Python/Tau use

```bash
uv sync --extra live --extra test
uv run --no-sync python examples/tau_adapter.py
```

The example deliberately uses a blocked default policy. The API is ordinary Python:

```python
from jev_runtime import Candidate, Jev, Policy, rank

async def choose_evidence(task, scoped_candidates):
    # Use only after the owner has authorized this entire request for egress.
    async with Jev(Policy(allow_egress=True, data_class="public")) as jev:
        return await rank(jev, task, scoped_candidates)
```

`@tool(...)` attaches a `.jev` registration to a function without wrapping or
calling it. `.jev.candidate(...)` validates supplied arguments with a strict
Pydantic model. Generate alternative candidates for known argument choices;
missing free-form arguments require the existing resolver or a generative path.
`select` returns IDs and a content-bound decision, not execution authority.

Tau must bind the selection back to the unchanged task/catalog, revalidate current
arguments/schema, obtain policy and capacity admission, execute through its normal
path, and retain a separate execution receipt. Do not call the decorated function
just because a classifier selected its ID.

The TypeScript library has equivalent `Jev`, `classify`, `select`, `rank`, a `tool`
registration helper, and `chooseModel`/`memoryDisposition` reducers.

## Model cost, rates and monitoring

`classify` batches intent and required-capability questions. `choose_model` and
`chooseModel` recommend the cheapest qualified option within supplied deadline,
cost, capability, authorization, freshness and cooldown constraints. The owning
provider adapter must then atomically reserve capacity and recheck it. A snapshot
is not a quota reservation, and unknown/exhausted capacity is not unlimited.

`monitor-skills` supplies catalog health/version evidence and can ingest Jev's
receipts. Its existing model-health probe is not live provider quota monitoring.
Do not infer skill readiness from newest modification time: in the reviewed
version, its newest-copy scan also omits TypeScript/JSON changes. That monitor
integration needs a content-hashed qualified manifest before broad rollout; this
change does not silently rewrite the monitor or its sync policy.

## Validation and rollout

```bash
./sanity.sh
./sanity.sh --live   # explicitly authorizes one synthetic live probe
```

Offline tests exercise typed boundaries, complete-payload egress rejection,
probabilities/options, abstention, native parity, source-preserving context,
clock/capacity constraints, human checkpoints and Pi lifecycle behavior. Host
and transport doubles are labeled as such. They do not establish installed Pi
compatibility, live Jev quality, server availability or performance.

Compare matched real tasks across existing behavior, deterministic cleanup, and
cleanup plus Jev. Include Jev input, main-model input/output/cache use, all retries,
provider waiting, wall time, required-evidence retention and independently verified
success. Pi session entries `jev-routing-receipt` and `jev-main-model-usage` capture
available measurements without injecting that telemetry into model context.
Character counts are not token savings. Do not promote from shadow on fewer tokens
alone, or count a synthetic test as a successful live task.

Dependency installation/locking and live SDK/Pi/Tau/Memory qualification must be
performed in the target environment. Runtime `run.sh` uses `uv --no-sync` so it
does not install dependencies before the egress gate. No result here certifies
privacy regulation compliance or substitutes for OS/network confinement.

## Design references

Original implementation of the integration logic; no Needle model or runtime is
vendored. Useful upstream concepts and contracts:

- [Needle Python function registration](https://github.com/cactus-compute/needle/blob/main/needle/agent/tools.py)
- [TypeSafe JavaScript SDK](https://docs.typesafe.ai/sdk/javascript) and [Python SDK](https://docs.typesafe.ai/sdk/python)
- [Typed function selection](https://docs.typesafe.ai/cookbooks/function_calling) and [reranking](https://docs.typesafe.ai/cookbooks/rerank_typesafe)
- [Pi extension lifecycle](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md)

The SDK boundary was checked against JavaScript SDK v0.6.0 and the current Python
SDK documentation. The target Pi build still needs an installed-host smoke test.
