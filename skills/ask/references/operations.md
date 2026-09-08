# Ask: Operational Runbooks

Unblock competitions, blocker ledger/drift, model provenance, run pruning,
browser-window ownership/reaping, tab age, provider payload matrix, and
mandatory Tau JSON stream monitoring. Read before executing or supervising
any live run.

### Unblocking: one singular MVP, or nothing

A spiralling agent does not need more options. It needs exactly one small thing
that demonstrably moves the wall, chosen by somebody other than itself.

```bash
skills/ask/run.sh unblock                                  # compile from the top open blocker
skills/ask/run.sh unblock --target T --failure-code F      # a specific wall
skills/ask/run.sh unblock ... --execute                    # dispatch isolated candidates
skills/ask/run.sh unblock --judge resp.md --run-proof      # score responses
```

It reads the open blocker from the ledger, grounds it with `/brave-search`
(queries built from the recorded `failure_code` and message, never from the
agent's own theory — that framing is what produced the spiral), and competes it
across isolated browser models that run their own web search. Candidates never
see each other: two models that read each other converge into one, and the
whole point is an outside view.

**The gate that does the real work: `PROOF_COMMAND` must fail right now.**

That single requirement kills the failure class this exists for. Work produced
to avoid a blocker has a proof that passes immediately — tests over your own
code, contracts for a path that never runs, a suite that was already green
while the wall stood. If a proposal's proof already passes, it does not address
anything currently broken, whatever its prose claims. `--run-proof` executes it
and requires a non-zero exit before the proposal can win.

Singularity is enforced mechanically, not requested politely, because "keep it
minimal" in a prompt is advice and advice is what an agent under pressure
rationalises away. Refused: a second deliverable (`and also`, `follow-up`,
`phase 2`), more than one change surface, a chained proof command, and a
whole-suite proof such as bare `pytest` or `./sanity.sh`.

If no candidate returns a singular proposal with a proof that fails now, the
result is `NEEDS_ATTENTION` and no winner. An unblocking step that does not
unblock is the spiral, not the exit. "This needs a human decision or an
upstream change" is an explicitly valid answer — without that escape the
candidates invent a fix.

### Blocked, or avoiding the blocker?

Ask emitted `BLOCKED` in 58 places and persisted **none** of it across runs, so
a blocker lasted exactly one process. That is why nothing could ever detect the
failure this guards: hit a wall on the load-bearing part, do not say "blocked",
and produce a stream of defensible deterministic work beside it -- tests over
your own code, contracts for a path that cannot run, greps instead of the live
call. Every artifact real, none of them touching the wall.

`goal-drift` cannot see this and is not meant to. It grades work against the
registered human goal, and this work *serves* the goal; it is the hard half
being routed around. goal-drift reports clean, exactly as the knowledge-drift
auditor did in the incident goal-drift itself was written for.

```bash
skills/ask/run.sh drift blockers                  # what is still in the way
skills/ask/run.sh drift check <target> --work "…" # was work done beside it?
skills/ask/run.sh drift acknowledge <target> <failure_code>
skills/ask/run.sh drift clear <target> <failure_code> --live-proof "…"
```

The ledger (`~/.ask/blockers.jsonl`) is written at Ask's own execution choke
point, not by an agent choosing to file a report -- the agent this detects is
by construction the one who would not have filed it. Identity is
`(target, failure_code)`, so one wall hit three times is one blocker.

Verdicts:

| verdict | meaning |
| --- | --- |
| `AVOIDANCE_DRIFT` | work landed on a target whose blocker is open and unacknowledged, and that work states its own live path did not run |
| `BLOCKED_DECLARED` | the blocker was acknowledged, attempted live, or nothing was built beside it — the honest cases |
| `CLEARED` | closed with live proof |
| `CLEAN` | no blocker, or no claim of a missing live path |

Two rules keep it honest. **Clearing requires live proof** — "it should work
now" is what an avoiding agent also says. **Attempting and failing is never
drift** — the detector must never punish going at the wall and losing.

The tell it keys on is the agent's own words. The output contract already
forces a statement of what was live and what was fixture-backed, so an avoiding
agent writes its own indictment voluntarily; selecting what to work on is
easy to rationalise, fabricating a live run is not.

Limitations, stated because they change how you read a verdict: it matches
phrases, so novel wording for "I did not run this live" slips through, and it
assesses whatever work items you hand it — feeding one commit that mixes
live-proven and fixture-only work yields a single coarse verdict. It reports
and never gates; a detector that can block work becomes one more lane to drift
into.

### Which model actually answered

Every browser lane receipt carries a `model_provenance` block. Ask requests a
reasoning tier (`Pro` by default) but Surf cannot always confirm the dropdown
took, and before this the receipt recorded `model: null` for every browser
handler -- so a panel could ask three seats for `Pro` and leave no evidence of
what answered.

`provenance_status` is one of:

| value | meaning |
| --- | --- |
| `confirmed` | an observation matched the request; `reasoning_proven: true` |
| `unconfirmed` | a tier was requested and nothing confirmed it -- the shape a silently-failing dropdown produces |
| `mismatch` | the provider was observed on a different tier than requested |
| `selection_failed` | Surf reported a selector error |
| `not_requested` | no tier was asked for |

Absence of evidence is never confirmation. Read `reasoning_proven` before
claiming a panel ran at a given tier; every real webgpt receipt on disk as of
2026-08-16 reads `unconfirmed`.

### Reclaiming finished runs

```bash
skills/ask/run.sh prune-outputs            # dry-run
skills/ask/run.sh prune-outputs --apply
```

Installed daily at 05:41. `run_state.prune_runs` covers runtime runs; this
covers the DAG output tree, a different directory shape it could not see --
which is why that tree reached 2.2 GB across 332 runs with nothing pruning it.

It removes a directory only when it carries `dag.json` or `compile-status.json`,
its newest file is older than 14 days, and any `execution-status.json` is
terminal. A non-terminal run is pinned regardless of age: a BLOCKED run is the
evidence for why it blocked. A stale `webgpt_inflight.json` is not liveness --
1,226 of them exist because completed submits leave the marker behind.

### Who owns a window Ask opened

Every window Ask causes to exist is recorded in `~/.ask/browser-windows.jsonl`
with the owning pid and a creation time. That ledger, not the lifecycle
receipt, is what makes a window closable later: closing was never the broken
part, ownership was. Measured 2026-08-14, 9 provider windows were open and none
appeared in any of 351 `browser-tab-lifecycle.json` receipts, because the
roundtable worker's recovery paths (`--create-tab`, `open-bind`) create windows
below the lifecycle layer. They now register through `ask.browser_windows` at
the transport choke point, so a window is claimed the moment it exists.

Three things close a window, in order of preference:

1. **In-run teardown.** A `fresh-temporary` run closes its own seat windows when
   Tau finishes. This works and always did.
2. **Provisioning-time reap.** The next Ask run reclaims windows whose owning
   process is gone and whose TTL has passed.
3. **The cron backstop**, for when there is no next run:

   ```bash
   skills/ask/run.sh reap-windows           # dry-run
   skills/ask/run.sh reap-windows --apply
   ```

   Installed at `*/30`. It closes only ledger-owned windows, and only when the
   owner is dead AND the TTL has passed -- both conditions, never either. A live
   owner means a run is still using the window; a young entry means a run may
   have died holding output that exists only in-tab.

TTLs by mode: `fresh-temporary` 15 min, `fresh-keep` 4 h, `pending-recovery`
12 h. Retention is an obligation with a clock, not an exemption -- 28 of those
351 receipts sat at `cleanup_status: skipped_pending_recovery`, keeping a window
open for a recovery nobody ever performed.

For tabs bound through `~/.pi/<backend>-projects/ask-*.json` rather than
windows, `skills/ask/run.sh close-stale-tabs` is the matching reaper.

Ask-created browser seat windows land on **Desktop 2** (wmctrl index 1). They
are reviewer windows Ask provisioned, not windows the human asked for, so they
belong on the reviewer desktop rather than on top of current work. Override with
`ASK_REVIEWER_DESKTOP=<index>`; set it empty to disable placement and leave
windows wherever Chrome puts them.

Placement is cosmetic and never fails a run. It reuses `browser-oracle
place-window` — the same logic `open-bind` uses — rather than reimplementing
it, because two details there are easy to get wrong: wmctrl output order is not
creation order (a last-sorts heuristic moved the wrong window), so the window is
identified by diffing a snapshot taken before creation; and `wmctrl` returning 0
does not mean the move stuck, because KDE can bounce a freshly-mapped window
back to the active desktop, so the move is verified by readback and retried.

Pass local evidence a browser seat must actually see with `--attach-file <path>`
(repeatable) on `tau-dag run` or `compete`. Ask forwards each file to Surf as
`--attach-file` for browser handlers and records `requested_attachment_paths`
plus `browser_attachment_paths` in the node receipt. A missing file or a handler
that cannot attach fails the lane closed rather than answering from prose.
Attachment delivery needs an extension build that handles
`AI_UPLOAD_FILE_TO_TAB`; older extensions reject the upload and the lane reports
`browser_submit_not_accepted` with that message.

### How old is this tab?

Stale reviewer tabs are the usual cause of a browser lane that used to work:
conversation state accumulates, rate-limit banners persist, and bindings drift.
Check age before blaming the transport.

```bash
cd skills/surf
./run.sh tab.age                  # every tab, oldest first
./run.sh tab.list --with-age      # ages on a normal listing
```

Read `age_source`, not just the number. `observed` is accurate; `at_least`
(shown with a `>=` prefix) means the tab predates the ledger and its real age
is unknown — Chrome exposes no creation time, so age is observed and
remembered, never read from the browser. `$surf` owns the ledger and the
contract; see its **Tab Age** section.

For a lane that is failing, the useful sequence is age first, then
`lane-diagnostics.json`, then the provider receipt — an old tab explains more
failures than anything in the code path does.

Browser providers do not share one payload contract. Before building or
repairing a browser roundtable packet, apply this matrix:

| Handler | Preferred review payload | Attachment rule | Explicit gotcha |
| --- | --- | --- | --- |
| `webgpt` | Short prompt plus one readable bundle | One attachment only; zip is allowed when the task needs a bundle | Multiple attachments fail before submission. Do not infer file creation from prose; download and verify generated artifacts. |
| `webgemini` | Short prompt plus one readable Markdown/text bundle | Ask inlines Markdown/text bundles for current Gemini tabs; do not rely on upload unless Surf records attachment metadata | Current Gemini UI may expose `Upload & tools` without an `input[type=file]`; stale page text can look like a response if sentinel capture is not strict. |
| `webkimi` | Short prompt plus one plain readable Markdown/text bundle | Do not use zip; Ask passes the Markdown/text bundle through Surf `kimi.submit --attach-file` | Kimi's Lexical composer can corrupt large inline payloads; do not paste or inline full review bundles into the composer. |
| `webclaude` | Prompt plus readable files | Multiple attachments are supported | Codex can stage a prompt without submitting it; require submit-acceptance and sentinel proof, not only a prepared prompt file. |
| `webdeepseek` / `deepseek` | Inline text or short prompt only | Attachments and zip files are unsupported | If local evidence is required, route through another handler or summarize the evidence into the prompt within size limits. |

Do not automatically convert every evidence set into a zip. For one-attachment
providers, choose the provider-compatible single file: usually Markdown for
Kimi and README/code review packets, and inline Markdown/text for Gemini when
the current tab lacks a file input; zip only when the provider is known to
accept it and the task actually needs an archive.

Failure classification must use the Ask browser failure-code registry in
`scripts/tau_roundtable_worker.py`, not bespoke prose. A lane is usable only
when its node receipt has `ok: true`, a non-empty response, and provider-specific
sentinel/attachment proof in metadata. `.submitted.md`, prepared prompts,
scheduler `node_completed`, and an Ask/Tau process exit code are not provider
acceptance proof.

Provider recovery must also be provider-specific. Ask must never turn a failed
browser lane into a generic `surf read`, `surf text`, page-text scrape, or
cross-provider extractor. If a submitted WebGrok lane misses the sentinel, the
recovery packet must name `surf grok.extract`; WebGPT uses
`surf webgpt.extract`; Gemini uses `surf gemini.extract` where applicable.
Handlers without a provider-owned extractor must fail closed with a ticket
instruction instead of pretending a generic page read is equivalent.

Browser lanes queue on the shared Surf browser lock. Ask derives the wait from
handler count and topology; pass `--browser-lock-timeout <seconds>` on `tau-dag
run` or `compete` to widen it for a busy browser. The resolved value is recorded
as `lock_timeout_seconds` in `browser-tab-lifecycle.json` and reaches each
browser handler's dispatch command.

After execution, read the returned `run_dir` and inspect:

- `dag.json`
- `command-specs/<node>/tau-dispatch-command.json`
- `node-artifacts/handler-*/node-receipt.json`
- `node-artifacts/handler-*/response.md`
- `node-artifacts/handler-*/browser-recovery-packet.json` when present
- `node-artifacts/handler-*/handler-recovery-packet.json` when present
- `node-artifacts/join/node-receipt.json` for roundtable
- `node-artifacts/join/compete-scorecard.json` for competition

Treat `PASS` as model/reviewer evidence only. Local closure still requires the
project's deterministic proof command or artifact validation. Treat `DEGRADED`,
`NEEDS_ATTENTION`, and provider rate limits as lane-local states: keep usable
peer receipts, read the recovery packet, and rerun only the affected lane or
launch a new round when appropriate.

### Monitor Tau JSON Streams

Executed Ask/Tau DAGs must be watched from dispatch until Tau reaches a
terminal `PASS`, `FAIL`, `BLOCKED`, or `NEEDS_ATTENTION` verdict. The caller
must read the run's JSON stream artifacts, not infer progress from a submitted
command, a quiet terminal, or a later prose summary.

Read these artifacts while the run is active and again before reporting:

- `events.jsonl`
- `dag-progress.json`
- `node-artifacts/*/node-receipt.json`
- Tau receipt files under `tau-receipts/`
- `execution-status.json`

`--no-poll` is a compatibility flag only. With `--execute`, Ask forces polling
on and records `tau_stream_monitoring_policy` in the CLI JSON output. A caller
that cannot read the stream must preserve the run directory and report the
last event id/timestamp, current node/status, elapsed time, and unreadable path
as the blocker. Do not launch a long-running Ask/Tau DAG and stop monitoring
it.

Before launching a costly live browser panel, Ask runs a standard read-only
provider availability probe automatically. It inspects existing provider tabs
for visible rate-limit or capacity banners and writes
`<run_dir>/browser-provider-availability.json`; it does not submit prompts. If
the report is `ERROR`, or `NEEDS_ATTENTION` without specific provider cooldown
metadata, Ask exits before creating fresh browser tabs or dispatching Tau, with
`blocked_reason: browser_provider_unavailable_preflight`, `failure_code`, and
`next_command` in the top-level execution receipt. If `NEEDS_ATTENTION` names
provider-limited lanes, Ask treats that as lane-local: it records
`limited_providers` and `cooldown_policy` in the availability artifact, writes
`<run_dir>/browser-provider-selection.json`, removes unavailable requested
providers, and selects the next best available browser provider when the
workflow still has enough participants. WebGPT cooldowns opt the WebGPT worker
into one bounded Surf retry after 300 seconds only when that WebGPT lane is
still intentionally run.

Project agents can also run the same probe manually before a planned panel:

```bash
./run.sh browser-availability \
  --provider webgpt \
  --provider webclaude \
  --provider webkimi \
  --provider webgemini \
  --output /tmp/ask-provider-availability.json \
  --json
```

If this probe returns `ERROR` with `recovery_kind:
surf_stale_socket_no_listener`, `/tmp/surf.sock` exists but no Surf native host
is listening. This is local browser transport failure, not WebGPT provider
throttling. Follow the reported `next_command`; if it repeats, collect
`browser-provider-availability.json`, `/tmp/surf-host.log`, the native host
manifest, and `ss -xlpn | grep /tmp/surf.sock`, then file a `$ticket` to
`$surf`. Do not launch a browser roundtable, retry provider lanes, or classify
the failure as provider cooldown until Surf `tab.list` works again.

If the report is `NEEDS_ATTENTION` with `cooldown_policy.status:
LANE_LOCAL_RETRY`, do not cancel healthy peers. Treat only the named providers
as cooling down, preserve the policy, and use the adjusted handler list from
`browser-provider-selection.json`. If Ask cannot keep enough participants after
filtering unavailable providers, it exits with
`blocked_reason: browser_provider_selection_insufficient_participants`. This
preflight is not completion proof; it only prevents obvious provider throttle
loops from becoming whole-panel failures.

Failures must be non-silent. A failed browser/API/subagent lane must expose
`failure_code`, `recovery_packet_path`, `next_command` or an explicit
fail-closed reason, and `ticket_instruction`. If a recovery packet is missing,
misclassified, hides Surf/CDP/SciLLM stderr, gives no actionable recovery, or
still blocks the project after its recovery instruction is followed, file a
`$ticket` to `$ask` at `agent-skills@main`. Include the Ask `run_dir`,
`dag.json`, the failing node receipt, recovery packet, `response.meta.json`,
raw response, and exact command stderr.

