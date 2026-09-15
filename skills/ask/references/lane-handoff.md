# Ask → Subagent Lane Handoff

Read before turning any ask output (one-shot, roundtable, compete, clean-room)
into pi-subagents worker lanes. This is the recipe that keeps strategic
consults and mechanical execution on one traceable pipeline instead of a
manual copy-paste between them.

## The one non-negotiable step

**Parent verification between ask output and lane spec.** Seats cannot read
the repo. Observed 2026-09-16: one seat's "PsychoAgent" claim was wrong (name
collision) while another seat's ten findings were right — the only way to know
was grepping each claim against disk before encoding it. The rule:

> Nothing enters `lane-specs.json` that the parent has not confirmed against
> disk or a receipt.

Skip that and you have built a machine for executing hallucinations at scale.

## The three carriers

Choose by payload size and program shape; they compose.

### 1. Task-text embedding (small, verified content, ≤ ~5KB per lane)

Parent reads the ask artifacts, verifies the load-bearing claims, then bakes
the distilled spec directly into each lane's task string:

```js
const LANE1 = `...CONTEXT: <verified findings, verbatim>...
THEN PATCH <exact files/functions from the seat's answer>...`;
await runs.run('pd_gate', { agent: 'worker', task: LANE1 });
```

Right for a single findings→repair lane where the verified digest is short.

### 2. File handoff (large evidence)

Workers have `read`/`bash` and run in the parent's cwd, so the parent writes a
durable packet and the lane task says `READ FIRST: <path>`. The browser prompt
preflight constraint does NOT apply here — that is browser-only. This is how a
lane receives a 90KB roundtable synthesis or a compete winner's full artifact
tree:

```text
/mnt/storage12tb/.../strategy-<date>/
  synthesis.md            <- parent-verified digest (the authority)
  seat-webgpt.md          <- raw answers (reference, not authority)
  lane-specs.json         <- the machine contract (below)
```

### 3. Mission state (multi-workflow programs)

Mission-attached workflows get `await state.get/set` — durable JSON shared
across workflows on the same mission. Store the strategy packet once; the
fanout workflow, the repair workflow, and the proof workflow all read the same
contract. Right when one strategic consult drives several workflow rounds.

## The contract: lane-specs.json

The seam artifact the parent synthesizes from the ask output:

```json
{
  "source_run": "<ask run dir>",
  "verified_by": "parent grep/receipt check",
  "lanes": [{
    "key": "pd_gate",
    "agent": "worker",
    "mode": "mutation",
    "scope_paths": ["skills/persona-dream/"],
    "claims": ["derived records excluded from recall"],
    "derived_from": {"seat": "webgpt", "finding": "1. CRITICAL — recursion..."},
    "first_patch": "...",
    "red_first": "...",
    "checks": ["py_compile ..."],
    "out_of_scope": ["MIN_DISTINCT_EVENTS policy"]
  }]
}
```

From this one file generate both the `preflight.lanes` block *and* the lane
task strings — so the declared plan and the executed plan cannot drift.
`derived_from` is the traceability link: every mutation names the strategic
finding it implements.

## Per-mode synthesis rules

| Ask mode | What you feed forward | Watch out |
|---|---|---|
| **one-shot** | Parent-made synthesis of N independent answers | No join exists — the synthesis is YOUR verified work, not a seat's |
| **roundtable** | The join synthesis + attributed dissent | Dissent goes into lane `out_of_scope`/risk notes; do not drop it |
| **compete** | Winner's artifact + judge verdict | The lane job is *harvest/apply* the winner, not re-derive it — hand the artifact path |
| **clean-room** | The produced spec/implementation | The lane verifies-and-integrates; never let a lane "improve" it unreviewed |

## Synthesis is a list of $tickets to orchestrate

The synthesis's terminal form is not prose - it is the TICKET LIST. Each
parent-verified finding becomes one focused `$ticket` sized for the configured
code runner (zai/glm-5.3-flash): one independently verifiable acceptance
criterion, named scoped-files, proof as a deterministic local command,
context-file/required-skill bootstrap, route/agent metadata, and `derived_from`
naming the seat finding it implements. That list IS the orchestration unit:
`ticket fleet --dry-run` review -> `--apply` files them -> `$project-watchdog`
leases one at a time -> flash executes -> verify command passes -> close ->
forced iteration stays watchdog-owned on failure. Analysis/harvest findings
that need no repo repair run as direct pi-subagents lanes under the parent
instead - verify immediately, do not ticket. Rule of thumb: repair work that
must survive the session is a ticket; work you will verify now is a lane.
Everything upstream exists to make the ticket list correct; everything
downstream exists to execute it.

## End-to-end: research seats -> synthesis -> workflowScript

The standard program: web models research, the parent synthesizes and
verifies, pi-subagents executes. The workflowScript is generated FROM
`lane-specs.json` so declared and executed plans cannot drift:

```js
// subagent({ workflowScript, async: true, preflight: <from lane-specs> })
// Parent already wrote /mnt/storage12tb/.../strategy-<date>/{synthesis.md,lane-specs.json}
const PACKET = "/mnt/storage12tb/.../strategy-<date>";
const results = await runs.all([
  { key: "pd_gate", agent: "worker", task: `READ FIRST: ${PACKET}/lane-specs.json (your lane: pd_gate)
and ${PACKET}/synthesis.md. Implement ONLY your lane: first_patch, then red_first,
then run checks[]. Stay inside scope_paths; out_of_scope items are forbidden.
Cite derived_from in your output.` },
  { key: "recall_fix", agent: "worker", task: `READ FIRST: ${PACKET}/lane-specs.json (your lane: recall_fix)...` },
]);
return results.map(r => r.output).join("\n---\n");
```

Rules the example encodes:

- The browser research happened BEFORE this script, through `$ask` (one-shot/
  roundtable/compete) - web seats are never children of the workflow.
- Lanes read the packet from disk (carrier 2); small verified digests may be
  baked into task strings instead (carrier 1); multi-workflow programs move
  the packet into mission `state` (carrier 3).
- One writer per scope: lanes' `scope_paths` must not overlap, or use
  `isolation: "worktree"`.
- Seat PASS is advisory; lane completion is not closure; the parent still
  runs deterministic local proof after the workflow returns.

## Checklist

1. Run the ask mode; read node receipts and answers from the run dir.
2. Grep/receipt-check every load-bearing claim against disk. Discard or
   annotate what fails.
3. Write `lane-specs.json` (+ `synthesis.md` and raw seat answers for file
   handoff) under a durable storage root.
4. Generate `preflight.lanes` and lane task strings from `lane-specs.json`;
   pick carrier 1, 2, or 3 by payload and program shape.
5. Launch one top-level `{ workflowScript, async: true }`; lanes cite
   `derived_from` in their outputs.
6. Local closure still requires deterministic parent-side proof — seat PASS
   and lane completion are never sufficient on their own.
