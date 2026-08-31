---
name: ops-lgtv
description: >
  LG webOS TV local control and audio gain-staging diagnostics over the same
  LAN WebSocket API the LG iOS app uses (ports 3000/3001). Pair with the TV,
  read sound output route and volume, change sound output (gated behind
  --execute), and run a combined gain-staging check that composes ops-wiim to
  compare TV-side output state against the amp's reported state. Use for
  "lg tv sound output", "pair with the LG TV", "is the TV sending quiet audio",
  "lg webos control", "ops-lgtv".
triggers:
  - lg tv sound output
  - pair with the lg tv
  - lg webos control
  - tv audio quiet
  - check tv sound settings
  - lg tv gain staging
  - ops lgtv
allowed-tools: Bash
runtime_self_improvement: basic
metadata:
  short-description: LG webOS TV sound-path control and gain-staging diagnostics
provides:
  - ops-lgtv
  - lgtv-sound-control
composes:
  - ops-wiim
  - brave-search
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - observability
  - resilience
---

# ops-lgtv

Control and inspect LG webOS TVs over the local network (same SSAP WebSocket
API the LG mobile app uses). Built for the WiiM-Amp low-volume case: the TV is
usually the quiet half of the gain-staging chain. LAN only.

## Pair first (one time per TV)

```bash
./run.sh pair --ip 192.168.86.42     # a permission prompt appears ON THE TV — accept it
```

The client key is stored locally by bscpylgtv; subsequent commands reuse it.
Set `LGTV_IP` (or repo-root `.env`) to skip `--ip`.

## Read the sound path

```bash
./run.sh sound --json                # sound output route + volume (read-only)
./run.sh gain-staging --json         # composes ops-wiim: TV route/volume vs amp vol/mute/EQ/source in one report
```

`gain-staging` calls `../ops-wiim/run.sh diagnose` and merges both sides so a
quiet-output complaint can be attributed in one command: if the amp reports
high volume/unmuted/EQ-off while the TV routes audio elsewhere or holds a low
output state, the TV side is the culprit.

## Gated mutation

```bash
./run.sh set-sound-output external_arc --execute   # refused with exit 3 without --execute
```

Digital Sound Out (PCM vs Pass Through) and Auto Volume are not exposed by the
sound-output API on all firmwares; when this skill cannot read them it says
`not_observable` — change them in the TV's Settings → Sound menu.

## Exit codes

- `0` reachable, report emitted
- `2` TV unreachable/unpaired (fails closed, `status: "down"`)
- `3` mutation attempted without `--execute`

## Proof boundary

bscpylgtv's SSAP surface is community-maintained and firmware-dependent.
Pairing requires a human to accept the on-TV prompt; sanity/eval live cases are
skipped (NOT_TESTED), not passed, when no paired TV is available.
