---
name: ops-wiim
description: >
  WiiM Amp local-network diagnostics for low sound output triage. Discovers the
  amp on the LAN, snapshots getStatusEx/getPlayerStatus/EQ/output-mode state
  over the local LinkPlay HTTP API, monitors state deltas while a fault is
  reproduced, and emits a low-volume triage report with heuristic findings
  (mute, low volume, EQ engaged, fixed-output, source gain-staging). Read-mostly:
  every mutating command (volume, EQ) is gated behind --execute. Use for "wiim
  low volume", "debug wiim amp", "wiim status", "why is the wiim quiet",
  "ops-wiim".
triggers:
  - wiim low volume
  - wiim amp quiet
  - debug wiim amp
  - wiim status
  - wiim diagnostics
  - why is the amp so quiet
  - monitor wiim
  - ops wiim
allowed-tools: Bash
runtime_self_improvement: basic
metadata:
  short-description: WiiM Amp local API diagnostics for low-volume triage
provides:
  - ops-wiim
  - wiim-diagnostics
composes:
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - observability
  - resilience
---

# ops-wiim

Debug low sound output on a WiiM Amp using its local LinkPlay HTTP API
(`https://<ip>/httpapi.asp?command=...`, HTTP fallback). LAN only — never
port-forward this interface.

## Find the amp

```bash
./run.sh discover --json          # SSDP M-SEARCH for LinkPlay/MediaRenderer devices
```

Or read the IP from WiiM Home → device settings → Network Status, then export
`WIIM_IP=<ip>` (or repo-root `.env`).

## Diagnose low volume

```bash
./run.sh status --json                        # raw getStatusEx + getPlayerStatus snapshot
./run.sh diagnose --json                      # ops_wiim.diagnosis.v1 with heuristic findings
./run.sh monitor --seconds 60                 # NDJSON deltas while you reproduce the fault
```

`diagnose` flags the states that commonly explain "the amp is quiet":
mute engaged, volume ceiling low, EQ enabled (band cuts), fixed/line-out
output mode, and which input is active (so you can compare HDMI ARC vs
streaming vs Line In). It cannot see power-stage health, clipping/protection
events, or TV-side digital attenuation — the report says so explicitly.

## Triage workflow (source-by-source differential)

1. `diagnose` for a baseline; note source, volume, mute, EQ.
2. Play a known reference track via WiiM streaming; note perceived loudness at 40/60/80% (`set-volume` is gated).
3. Switch to the suspect source (e.g. HDMI ARC) and re-run `diagnose`.
4. Compare the two reports: if reported volume/EQ/output-mode are identical but loudness differs, the problem is upstream gain-staging (TV PCM output level, passthrough) — not amp config.

## Gated mutations

```bash
./run.sh set-volume 60 --execute     # refuses without --execute
./run.sh set-eq-off --execute        # bypass EQ to rule out band cuts
```

## Exit codes

- `0` reachable, report emitted
- `2` amp unreachable (fails closed with `status: "down"`)
- `3` mutation attempted without `--execute`

## Reporting bugs upstream

WiiM has no official GitHub issue tracker; firmware/app/hardware issues go to
the WiiM Community Forum. Third-party layer trackers (mjcumming/wiim,
Home Assistant Core, Music Assistant, pywiim) and the high-signal report
recipe are in `references/support-channels.md`.

## Proof boundary

Command surface (`getStatusEx`, `getPlayerStatus`, `EQGetStat`, `EQOn/Off`,
`setPlayerCmd:vol:N`) is community-documented and firmware-dependent; unknown
commands return `unknown command` and are reported as `not_supported`, never
inferred. Sanity checks that require a live amp are skipped (not passed) when
`WIIM_IP` is unset.
