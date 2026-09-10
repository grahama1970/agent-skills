---
name: ops-obs
description: >
  Monitor, diagnose, and optimize OBS Studio on KDE Plasma Ubuntu. Use when the
  user says "obs health", "obs stats", "monitor obs", "obs dropped frames",
  "optimize obs", "obs stream control", "start/stop obs recording", "obs doctor",
  "obs websocket", or wants OBS buttons on the Stream Deck.
triggers:
  - obs health
  - obs stats
  - monitor obs
  - obs dropped frames
  - optimize obs
  - obs stream control
  - start obs recording
  - stop obs recording
  - obs doctor
  - obs websocket
provides:
  - obs-monitoring
  - obs-control
  - obs-streamdeck-bindings
composes:
  - agentic-evals
  - ops-streamdeck
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - observability-operations
runtime_self_improvement: none
---

# ops-obs

Typer CLI that monitors and optimizes OBS Studio on KDE Plasma Ubuntu through
two surfaces:

1. **Live** (needs OBS running with its obs-websocket v5 server enabled,
   default port 4455): stats, health findings, stream/record control, scene
   switching. Flatpak and native installs both supported; the password is
   read from `--password` > `OBS_WS_PASSWORD` > the OBS websocket plugin
   config (never logged).
2. **Local** (no OBS needed): `doctor` detects the install kind, websocket
   server state, GPU encoders (NVENC/VAAPI), session/capture guidance
   (Wayland+PipeWire vs X11/XSHM), log error scan, and disk headroom.

All output is JSON on stdout. Success is `{"ok": true, ...}`; every failure is
a typed envelope `{"ok": false, "code", "cause", "next_command"}` with exit 1 —
never a bare traceback or generic timeout.

## Commands

| Command | Surface | Description |
| --- | --- | --- |
| `run.sh status [--host --port --password --timeout]` | live | Version + GetStats + stream/record state + health findings |
| `run.sh watch [--interval N]` | live | Continuous NDJSON monitoring, Ctrl+C to stop |
| `run.sh stream start\|stop\|toggle\|status` | live | Stream control (start/stop tolerate wrong-state errors 500/501) |
| `run.sh record start\|stop\|toggle\|status` | live | Record control; `stop` prints the output path |
| `run.sh scene list` / `run.sh scene set NAME` | live | List scenes / switch program scene |
| `run.sh streamdeck bindings` | local | Emit `ops-obs.streamdeck_bindings.v1` button definitions |
| `run.sh streamdeck status` | live | One-token state: `OFFLINE` / `LIVE` / `REC` / `LIVE+REC` / `ERR:<code>` (exit 1) |
| `run.sh doctor` | local | Install, ws server, GPU encoder, session, disk, log scan |
| `run.sh paths` | local | Resolve config root (flatpak/native), logs dir, ws config |
| `run.sh selftest` | local | Protocol auth-vector regression check |
| `run.sh verify` | eval | Run `fixtures/agentic_eval.json` via `../agentic-evals/run.sh` |

Config roots detected in order: Flatpak
`~/.var/app/com.obsproject.Studio/config/obs-studio`, then native
`~/.config/obs-studio`.

## Health thresholds (from `status`/`watch`)

| Check | warn | crit | Hint |
| --- | --- | --- | --- |
| render skipped/total | ≥5% | ≥10% | Fewer sources/filters; Wayland+PipeWire over XSHM |
| output skipped/total | ≥1% | ≥5% | Lower resolution/fps/bitrate; hardware encoder (NVENC/VAAPI) |
| stream congestion | ≥0.05 | — | Lower bitrate; fix network |
| disk free | <5 GB | <1 GB | Clean recording target |
| active output at 0 fps | — | any | Encoder stalled; run `doctor` |

## Failure codes

| code | cause | next_command |
| --- | --- | --- |
| `obs_ws_connection_refused` | no server at host:port | start OBS; enable Tools → WebSocket Server Settings |
| `obs_ws_server_disabled` | local config says server off (port matches config) | Tools → WebSocket Server Settings → Enable |
| `obs_ws_timeout` | connect/handshake/request timeout | raise `--timeout`; restart OBS |
| `obs_ws_password_required` | auth challenge but no password | `OBS_WS_PASSWORD` / `--password` |
| `obs_ws_auth_failed` | handshake rejected | verify password in OBS settings |
| `obs_ws_request_failed` | RequestResponse result=false (code+comment surfaced) | run `stream/record status` or `doctor` |
| `obs_ws_protocol_error` | unexpected/malformed message | check obs-websocket ≥ 5.0 |

## Stream Deck integration

`run.sh streamdeck bindings` emits validated button definitions whose commands
invoke this skill (runnability of `run.sh` is checked before emission). Merge
them into the ops-streamdeck daemon config (`~/.streamdeck/daemon.json`
buttons) — do NOT edit `~/.streamdeck_ui.json` while `streamdeck.service`
runs, and never embed these commands into a
`streamdeck.dynamic_page_request.v1` request (that boundary rejects raw
commands; a catalog recipe would be required first).
`run.sh streamdeck status` emits a one-token state line designed for icon
renderer widgets (exit 0 + token, or exit 1 + `ERR:<code>`).

## Evaluation

`fixtures/agentic_eval.json` (3 trials/case) proves: CLI wiring, live local
`doctor`/`paths`, the typed connection-refused path, usage validation, the
protocol auth vector, and streamdeck bindings emission. Live websocket
control is NOT proven while the local OBS has its websocket server disabled
(the optional `status-live` case reports BLOCKED with the marker). Proof
scope is stated in the fixture `claims` block.
