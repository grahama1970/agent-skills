# Thunderdome + Classifier Lab Bug Fix Plan

Codebase: /home/node/workspace

Read ALL files referenced before changing anything.

## Bug 1: Benchmark commands have quoted paths that break in bash

**File**: `.pi/skills/classifier-lab/scripts/e2e_pipeline.py` lines 395-404

The `bench_cmd` f-strings wrap paths in inner double quotes. These get passed to `tracking.py` `run_skill()` which wraps in `bash -lc`, double-quoting again. Typer receives garbled args → rc=2.

**Fix**: Remove inner quotes from all 4 `bench_cmd` assignments. Change `"{state.data_dir}"` to `{state.data_dir}`. Same for `backbones_str` and `output_file`. Paths have no spaces.

## Bug 2: HP changes computed but never passed to benchmark CLI

**File**: `.pi/skills/classifier-lab/scripts/e2e_pipeline.py`

`get_strategy_hps()` (line 120) returns different hyperparameters per escalation strategy:
- `lr_halved_more_epochs`: lr=1e-4, epochs=20
- `augmentation`: mixup_alpha=0.3, cutmix_alpha=1.0, random_erasing=0.25
- `regularization`: dropout+0.1, weight_decay*2, label_smoothing=0.1

But the benchmark command (line 396) ONLY uses `hps.get("epochs", 10)`. It never passes lr, mixup_alpha, cutmix_alpha, random_erasing, dropout, weight_decay, or label_smoothing to the CLI.

**Fix**:
1. Read `.pi/skills/classifier-lab/scripts/app.py` to find what CLI flags benchmark accepts
2. Read `.pi/skills/classifier-lab/scripts/paired_benchmark.py` to find what training params it accepts
3. If the CLI doesn't accept these flags, ADD them to `app.py` and wire them through to the training function
4. Modify `e2e_pipeline.py` lines 395-404 to pass ALL relevant HPs from the `hps` dict to the benchmark command

## Bug 3: All dispatch must go through SSE stream — no subprocess

**File**: `.pi/skills/thunderdome/scripts/dispatch.py`

The `_dispatch_one()` function must send ALL strategies through `/subagent-service` SSE stream (`POST /chat/stream`). No `subprocess.run` or `subprocess.Popen` for strategy execution.

When `strategy.skill` is set, convert it to a prompt for the subagent:
```
Run this exact command and return ONLY the final JSON output:
cd /home/node/skills/{strategy.skill} && ./run.sh {rendered_prompt}

After the command completes, output the full JSON result. Nothing else.
```

Then fall through to the SSE stream path. Remove all subprocess-based dispatch code.

## Bug 4: Sanity test assertion count mismatch

**File**: `.pi/skills/thunderdome/sanity.sh`

The `classifier-table-merge.yaml` manifest has 2 strategies. Line ~53 of sanity.sh asserts `len(m.strategies) == 3`. Fix to `== 2`.

## Bug 5: Failure report incomplete

**File**: `.pi/skills/thunderdome/scripts/thunderdome.py`

When `converged=false`, the JSON output must include:
- `"status": "FAILED"` (not just `"converged": false`)
- `"gap_to_gate"`: gate_threshold minus best_score
- `"failure_report"` dict with: diagnosis, plateau_detected, regression_detected, dogpile_insights, persona_reviews

Verify the `logger.error` block near line 280 fires so the human sees TOURNAMENT FAILED prominently.

## Verification

After all fixes:

1. `cd /home/node/workspace/.pi/skills/thunderdome && bash sanity.sh` — all tests pass
2. `cd /home/node/workspace/.pi/skills/classifier-lab && uv run --project . python scripts/e2e_pipeline.py --task "table merge" --project-id codex-verify --data-dir /home/node/workspace/.pi/skills/create-table-classifier/data/merge_images/split --modality paired --gate-f1 0.90 --max-rounds 2 --skip-research`
   - `round_f1s` MUST be non-zero (~0.80)
   - `strategies_tried` must show different strategies per round (baseline, lr_halved_more_epochs)
3. Verify the HP flags are actually different between rounds by checking the benchmark commands in the log output
