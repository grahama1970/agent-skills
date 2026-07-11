# Commands

From the repository root after extracting this patch bundle:

```bash
python scripts/verify_manifest.py MANIFEST.json
python - <<'PY'
import json, pathlib
for path in sorted(pathlib.Path('schemas').glob('*.schema.json')):
    json.loads(path.read_text())
print('schemas parse')
PY
python scripts/validate_pipeline_spine.py fixtures/blocked_missing_input
python scripts/validate_pipeline_spine.py fixtures/provider_ready_dry_run
pytest -q tests/test_pipeline_spine.py
```

Expected fixture statuses:

```text
BLOCKED_MISSING_INPUT
DRY_RUN_NOT_LIVE_SUBMITTABLE
```
