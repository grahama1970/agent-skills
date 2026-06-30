# Sanity Report: watch-realtime-identity-memory-loop-P1-solution.zip

## Download

- Downloaded from WebGPT tab: `837356822`
- Local source path: `${HOME}/Downloads/watch-realtime-identity-memory-loop-P1-solution.zip`
- Stored path: `skills/watch/docs/architecture/create-architecture/watch-realtime-identity-memory-loop-P1/solution/watch-realtime-identity-memory-loop-P1-solution.zip`

## Transport Proof

- Surf status: `recovered_focus_changed`
- Proof status: `degraded_focus`
- Requested tab id: `837356822`
- Controlled tab id: `837356822`
- Raw response contains sentinel: `true`
- Clean response contains sentinel: `false`
- Response source: `assistant-dom`

This is degraded WebGPT transport evidence because browser focus changed during `--no-activate` mode. The response still came from the requested controlled tab.

## Bundle Integrity

- WebGPT stated sha256: `577adeb7a7cbfc6c7ee656ab29446ecb845bde008d7ec057bc3da401db61a72b`
- Local downloaded sha256: `8a2845c64767d1861a9228ad967321d07096080c9e193b182f356db60dfd92bc`
- Zip file count: `36`
- Internal manifest entries: `35`
- Internal manifest hash check: `35/35` matched, `0` missing, `0` mismatched

The outer zip checksum differs from WebGPT prose, so the prose checksum is not treated as proof. The local zip is preserved with its actual checksum and internal manifest validation.

## Local Contract Checks

The zip was temporarily extracted for validation and the extracted scratch tree was removed afterward to avoid committing duplicate files and `__pycache__`.

Commands run from:

```text
skills/watch/docs/architecture/create-architecture/watch-realtime-identity-memory-loop-P1/solution
```

Commands run:

```bash
rm -rf extracted && mkdir extracted
unzip -q watch-realtime-identity-memory-loop-P1-solution.zip -d extracted
python3 extracted/repo/skills/watch/scripts/validate_watch_realtime_identity_memory_loop_P1.py --root extracted/repo
PYTHONPATH=extracted/repo PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q extracted/repo/skills/watch/tests/test_watch_realtime_identity_memory_loop_P1.py
rm -rf extracted
```

Results:

```text
p1_contracts_ok
7 passed in 0.03s
```

These checks prove bundle contract/fixture wiring only. They do not prove live YOLO/ByteTrack tracking, identity support, Qdrant writes, Arango writes, or `$memory recall`.
