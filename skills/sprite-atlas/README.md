# sprite-atlas

Profile-driven sprite atlas compiler. Named `<animation>/<frame>.png` files are
the preferred authoring truth; fixed-grid atlas PNG/JSON pairs are generated
runtime compatibility outputs.

Job output defaults to `skills/sprite-atlas/jobs/<sprite-id>/` unless `--job-dir` is set.
Production paths are written only by `promote` after a passing receipt.

Typical repair flow:

```bash
./run.sh plan-repair --atlas atlas.png --profile profile.json --sprite-id runner --job-dir jobs/runner
./run.sh extract-frames --atlas atlas.png --profile profile.json --output-dir frames/runner
./run.sh apply-frame-patch --atlas atlas.png --profile profile.json --sprite-id runner \
  --repair-plan jobs/runner/frame-repair-plan.json --patch-dir generated/runner --job-dir jobs/runner-patched
./run.sh promote --job-dir jobs/runner-patched --out-png runtime/runner.png --out-json runtime/runner.json
```
