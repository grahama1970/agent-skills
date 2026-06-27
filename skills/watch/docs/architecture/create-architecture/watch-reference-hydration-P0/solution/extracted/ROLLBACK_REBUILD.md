# Rollback and Rebuild

## Rollback

The P0 package only adds files and creates planned payloads. It should not mutate Qdrant, Arango, `$memory`, or Watch UI files.

```bash
rm -f skills/watch/scripts/watch_reference_hydration.py
rm -f skills/watch/scripts/build_watch_reference_hydration_plan.py
rm -f skills/watch/scripts/validate_watch_reference_hydration_contract.py
rm -f skills/watch/scripts/build_watch_memory_trace_plan.py
rm -f skills/watch/docs/architecture/watch_reference_hydration_P0.md
rm -rf skills/watch/docs/architecture/schemas
rm -rf skills/watch/docs/architecture/state_machines
rm -rf skills/watch/tests/fixtures/reference_hydration_P0
rm -f skills/watch/tests/test_watch_reference_hydration_P0.py
```

If the optional docs patch was applied, reverse it:

```bash
git apply -R skills/watch/docs/architecture/patches/watch_reference_hydration_P0_docs.patch
```

## Rebuild

```bash
cp -a /path/to/watch-reference-hydration-P0-solution/repo/. .
python3 -m py_compile skills/watch/scripts/watch_reference_hydration.py
pytest -q skills/watch/tests/test_watch_reference_hydration_P0.py
```

## Future live-write rollback requirement

A later implementation that writes Qdrant or Arango must produce pre-mutation rollback receipts:

- Qdrant created point ids;
- Arango document keys and previous pointer state;
- memory/evidence-case write receipt ids;
- exact rollback command and dry-run proof;
- recall negative control after rollback.
