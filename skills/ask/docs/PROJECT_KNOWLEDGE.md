# ask Docs Project Knowledge

Current state as of 2026-07-29: `$ask` owns Tau browser-handler orchestration
for supported web seats, including `webgpt`, through `$surf` and
`$browser-oracle` command specs. Direct `$ask ask` WebGPT/ChatGPT oracle flags
remain fail-closed, but Tau handler names such as `webgpt`, `webclaude`,
`webkimi`, `webgemini`, and `webgrok` are valid browser lanes.

Ask docs should describe these Tau browser-handler lanes:

- `webgpt`
- `webclaude`
- `webkimi`
- `webgemini`
- `webgrok`

Normal executed roundtables and competitions should use Ask-owned fresh browser
windows via `--browser-tab-lifecycle auto`; manual `--handler-project`
bindings are fallback only. Local evidence should flow through `--attach-file`
so Surf can attach readable files and fail closed when a provider cannot accept
the file shape.

WebGPT recovery evidence now includes orphaned Surf artifacts when a browser
lane stalls before a final node receipt: `response.md.receipt.json`,
`webgpt_inflight.json`, and `webgpt_heartbeat.json`. Ask should synthesize a
lane-local `node-receipt.json` and `browser-recovery-packet.json` from those
artifacts, preserving submitted state, sentinel, requested tab id, heartbeat
phase/page state, provider-throttle evidence, and an actionable `next_command`
when available.

Do not document `--webgpt-*`, `webgpt-project`, `--oracle-backend webgpt`,
`$ask webgpt`, or `$ask chatgpt` as supported direct `ask` oracle flows except
in explicit fail-closed handoff notes that route the user to Tau browser
handlers or Surf debugging.
