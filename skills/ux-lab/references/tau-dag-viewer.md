# Tau DAG Viewer Delegation

Tau owns the DAG viewer implementation, schemas, live-state projection, HTTP
server, and packaged React assets. UX Lab only locates Tau, validates the
read-only capability contract, and forwards arguments unchanged.

```bash
skills/ux-lab/run.sh tau-dag-view --run-dir /path/to/tau-run
```

Set `TAU_BIN` when Tau is not installed on `PATH`:

```bash
TAU_BIN=/path/to/tau skills/ux-lab/run.sh tau-dag-view \
  --run-dir /path/to/tau-run
```

The wrapper requires `tau.dag_viewer_capabilities.v1` with `read_only: true`.
It does not parse SQLite, project runtime events, or contain a second viewer.
