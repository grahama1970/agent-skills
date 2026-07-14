---
name: artifact-reader
description: >
  Render a local Markdown, text, or HTML artifact as a mobile-friendly reader,
  then serve it on an OS-selected open port with Copy and Download controls.
  Use when a user needs to read a generated transcript or report from another
  device, asks to start a local artifact server, or asks for a reusable reader
  surface that ingest-youtube, create-report, or another producer can compose.
triggers:
  - serve this artifact
  - open this report on my phone
  - read this transcript on my ipad
  - add a copy button to this page
  - create a mobile artifact reader
  - find an open port and serve this file
provides:
  - artifact-reader
  - local-artifact-serving
  - clipboard-copy-surface
composes:
  - ops-workstation
complies:
  - best-practices-skills
  - best-practices-python
runtime_self_improvement: basic
taxonomy:
  - artifact
  - accessibility
  - composition
  - validation
---

# Artifact Reader

Turn one local Markdown, text, or HTML file into a self-contained reading
surface. Keep artifact production in the producer skill; use this skill only
for rendering, local serving, and server lifecycle evidence.

## Render

```bash
./run.sh render /absolute/path/to/transcript.md
./run.sh render report.html --out /tmp/report-reader --title "Review report"
```

The command prints JSON containing the generated directory and manifest. The
default output root is `/mnt/storage12tb/skills/artifact-reader/outputs`.

## Serve

Loopback is the default:

```bash
./run.sh start /tmp/report-reader
```

Allow another device on the local network to connect:

```bash
./run.sh start /tmp/report-reader --lan
```

Do not search for a port manually. The runtime asks the operating system to
bind an available port and uses `$ops-workstation net --json` to resolve the
active LAN interface and share address. The start result and
`artifact-reader-server-receipt.json` contain the exact URL, PID, bind address,
port, source hash, and network observation.

Stop or inspect the server with its receipt:

```bash
./run.sh status /tmp/report-reader/artifact-reader-server-receipt.json
./run.sh stop /tmp/report-reader/artifact-reader-server-receipt.json
```

## Composition Contract

Producer skills pass an accepted file path to `render`, then optionally call
`start --lan`. They must not duplicate the reader HTML or port-selection logic.

```text
producer artifact
  -> artifact-reader render
  -> artifact-reader start [--lan]
  -> URL + lifecycle receipt
```

The reader serves only the declared generated directory. It rejects symlinks,
does not expose directory listings, and sanitizes HTML input before rendering.

## Proof Boundary

The receipt proves that a local HTTP server bound the recorded address and port
and served the hash-bound generated reader. It does not prove internet
reachability, durable hosting, source correctness, safe handling of sensitive
material, or future server availability.

## Verify

```bash
./sanity.sh
```

The sanity check uses real local files, the real `ops-workstation` network
report, a live HTTP server, and positive and negative safety controls.
