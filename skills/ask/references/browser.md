# Ask: Browser Rules

Full browser transport rules: tab lifecycle, stale-binding refresh, rollover,
rate-limit/cooldown classification, capacity vs transport failures, and
compete join rules. Read before executing any browser-handler DAG.

## Browser Rules

### MANDATORY prompt/bundle preflight (run before EVERY browser submit)

surf's webgpt submit **rejects** any prompt or attached bundle that references
an unreadable local filesystem path (schema `surf.webgpt_prompt_preflight.v1`,
reason `web_review_bundle_unreadable`) or a `~<digits>` token (agent-skills#973),
failing late with `browser_submit_not_accepted` after tab binding and wasted
cycles. This is a *recurring* mistake — a comprehensive-context bundle naturally
contains paths (`/run/...`, `/home/...`, `/mnt/...`, `~/...`) and shorthand like
`~20 pages`. Do not rely on eyeballing it.

Before any `tau-dag`/`compete`/`webgpt`-shortcut submit with a web* handler, run
the fail-closed preflight on your prompt AND every `--attach-file`, and fix what
it names (describe paths/sockets as prose; write "about 20", not "~20"):

```bash
python3 skills/ask/scripts/browser_prompt_preflight.py --prompt "<prompt>" <each --attach-file>
# exit 0 = safe to submit; exit 2 = offending tokens listed, fix them first
```

Direct WebGPT/ChatGPT browser oracle workflows have moved out of `$ask ask`.
`$ask webgpt`, `$ask chatgpt`, `--oracle-backend webgpt`, `--webgpt-*`, and
`webgpt-project` must fail closed.

Do not confuse that direct-oracle restriction with Tau roundtable handlers:
`webgpt`, `webclaude`, `webkimi`, `webgemini`, and `webgrok` are supported as peer Tau
browser handlers through `$surf`/`$browser-oracle` command specs.

- A browser tab cannot inspect bare local paths unless the runtime attaches file
  contents or serves an artifact URL. Include readable target content in the
  bundle when needed.
- Use the configured tab id when available. If the tab is missing, wrong, stale,
  or cannot be proven to match the requested reviewer, stop with
  `NEEDS_ATTENTION`.
- Project agents should not manually remember or perform stale-tab rebinding
  during normal Ask runs. Browser-oracle bindings are starting hints. If Surf
  reports a stale/wrong provider tab, missing composer, or auth-like stale-tab
  failure, `$ask` scans already-open same-provider tabs, retries a bounded
  candidate set, and updates the browser-oracle binding only after a successful
  submit. The proof appears in `node-receipt.json` as
  `browser_oracle_binding_refresh` plus command entries such as
  `<handler>_stale_binding_scan_live_tabs` and
  `<handler>_stale_binding_submit_existing_tab`. If no candidate succeeds, the
  lane stays `NEEDS_ATTENTION` with a recovery packet.
- **Browser tab lifecycle for browser handlers**:
  - Default mode is `--browser-tab-lifecycle auto`. For executed roundtables
    and competitions with browser seats, auto behaves as `fresh-temporary`.
    For non-browser DAGs, it behaves as `reuse-bound`/skipped.
  - `fresh-temporary` asks `$surf` to create one Chrome window, records the
    returned `windowId`, creates one provider tab in that window with
    `tab.new --window-id`, binds temporary browser-oracle projects for each
    handler, runs Tau, then closes only the Ask-created window. Existing user
    tabs and pre-existing browser-oracle bindings are not closed by this
    lifecycle.
  - Use `--browser-tab-lifecycle fresh-keep` when the human or project agent
    needs to inspect the provider tabs after the run. It creates and binds the
    same fresh window/tabs but leaves them open.
  - Ask writes `<run_dir>/browser-tab-lifecycle.json` with `window_id`,
    `created_tabs`, temporary `handler_projects`, command receipts, and cleanup
    attempts. If fresh provisioning or binding fails, Ask records
    `browser_tab_lifecycle_failed`, does not launch Tau, and exits with a
    recovery packet.
  - Manual tab binding remains a fallback only: create/list/bind with `$surf`
    and `$browser-oracle`, then pass `--handler-project <handler>=<project>`.
    Do not make project agents manually rebind stale tabs when the Ask lifecycle
    can own the window.
- If a WebGPT/Tau browser-handler receipt or Surf metadata reports
  `conversation_max_length_detected` or `conversation_max_length_rollover`, treat
  it as Surf's controlled-tab conversation rollover path. Do not reclassify it
  as a generic reviewer failure, browser-oracle mismatch, download failure, or
  sentinel parser defect. If rollover succeeded, continue from the returned
  controlled tab and preserve the `from_tab_id`, `to_tab_id`, and `action`
  fields in the Ask/Tau artifacts. If rollover failed, mark only that handler
  node `NEEDS_ATTENTION` and route the next attempt through the same Surf
  `Start new chat`/fresh-tab recovery contract.
- If a WebGPT/Tau browser-handler receipt or Surf metadata reports
  `chatgpt_too_many_requests_detected` or `chatgpt_rate_limit`, treat it as
  Surf's provider-throttle cooldown path. Surf waits
  `SURF_WEBGPT_RATE_LIMIT_WAIT_SECONDS` (default `300`) before it clicks
  **Got it**, because dismissing the modal during the throttle restarts the
  limit window. Ask browser workers opt WebGPT into one automatic retry by
  setting `SURF_WEBGPT_RATE_LIMIT_RETRY_ATTEMPTS=1`; raw Surf defaults still do
  not retry unless their caller opts in. Do not
  reclassify it as a reviewer failure, browser-oracle mismatch, download
  failure, or sentinel parser defect. Mark only that browser handler node
  `NEEDS_ATTENTION` or rate-limited, preserve the throttle metadata, continue
  with other available participants, and let the outer scheduler back off. Do
  not launch parallel WebGPT attempts to bypass the throttle.
- If a WebGPT handler leaves orphaned submit artifacts but no final
  `node-receipt.json`, treat those artifacts as terminal recovery evidence, not
  as a silent hang. Preserve and read `response.md.receipt.json`,
  `webgpt_inflight.json`, and `webgpt_heartbeat.json`; Ask should synthesize a
  lane-local `node-receipt.json` plus `browser-recovery-packet.json` that
  promotes submitted state, sentinel, requested tab id, heartbeat phase/page
  state, provider-throttle evidence, and an actionable `next_command` when one
  exists. If those synthesized receipts are missing or collapse rate-limit
  metadata into a generic timeout, file a `$ticket` to `$ask` at
  `agent-skills@main` with the Ask run directory and all three orphaned
  artifacts.
- If a WebKimi/Tau browser-handler receipt or Surf metadata reports
  `kimi_provider_capacity_busy`, `BLOCKED_KIMI_PROVIDER_CAPACITY`, or
  `proof_status: provider_capacity_limited`, classify only that browser handler
  as `browser_provider_rate_limited`. Preserve the recovery packet and use a
  different handler or rerun later; do not keep submitting Kimi prompts into a
  capacity-busy tab.
- If WebKimi or WebGrok reports `System is currently busy`, `capacity is busy`,
  `BLOCKED_KIMI_PROVIDER_CAPACITY`, `BLOCKED_GROK_PROVIDER_CAPACITY`, or
  `proof_status: provider_capacity_limited`, treat it as a lane-local provider
  capacity limit. Surf may wait a bounded cooldown and retry that one lane, but
  the project agent must not pause, cancel, or rerun healthy roundtable or
  competition participants because another participant is cooling down.
- Concurrent browser handlers remain independent Tau nodes. Their active Surf
  commands queue on the shared browser lock, but provider cooldown sleeps do
  not hold that lock and must not become DAG dependencies between participants.
- A missing Surf socket, native-host disconnect, or `Surf connection closed
  before response` is local transport failure
  `surf_browser_connection_unavailable`, not provider throttling. Recover the
  Surf host/socket and rerun only the affected lane; do not apply a provider
  cooldown.
- `stale_socket_no_listener` is the specific Surf native-host case where the
  socket path exists but has no listener. Ask preflight reports
  `recovery_kind: surf_stale_socket_no_listener` and should stop before Tau
  dispatch. Preserve the preflight artifact and follow the Surf runbook rather
  than submitting a browser-handler job.
- Competition joins preserve every terminal candidate receipt, including
  blocked lanes, but populate `winner_handler` and `winner_node_id` only when
  the scorecard is blocker-free `PASS`. A `NEEDS_ATTENTION` scorecard never
  names a winner.
- Do not use raw `surf` as a substitute for `$ask`; use it only for transport
  debugging, direct project-level WebGPT workflows, or Tau command specs emitted
  by `./run.sh tau-dag`.
- Browser review output is reviewer evidence. It still must be reconciled
  against repository state and deterministic local checks before closure.

