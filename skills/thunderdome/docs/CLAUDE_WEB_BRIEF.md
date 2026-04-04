# Thunderdome — Fresh Implementation Brief for Claude Web

You are implementing `/thunderdome`, a tournament skill that trains N classifier strategies concurrently, scores them, and iterates until F1 >= 0.90 or max rounds exhausted.

## Architecture (this is the truth — implement this exactly)

```
1. Load manifest (task, data_dir, gate_threshold, reviewers)
2. /analytics — analyze actual dataset (class counts, image sizes, balanced?)
3. /dogpile — with analytics: "what N approaches reach F1>=0.90?"
4. Build N exact benchmark commands in Python from a strategy pool (different HPs each)
5. Run all N concurrently via asyncio subprocess (direct bash, no LLM agent)
6. Read results from output JSON files on disk
7. Score — extract F1 via jsonpath
8. If gate passed → CONVERGED, stop
9. If not → /dogpile with FULL context (all rounds, all scores, diagnosis)
10. Pick next N strategies from pool (different HPs)
11. Repeat from step 5
12. If exhausted → FAILED with diagnosis, dogpile insights, gap to gate
```

## Key Design Decisions

- **Strategies are bash commands, not LLM prompts.** Each strategy is `cd /path/to/classifier-lab && ./run.sh benchmark [exact flags] --output-json /tmp/thunderdome-{name}-r{round}.json --store-memory`
- **No LLM agent in the dispatch loop.** The benchmark runs as a direct `asyncio.create_subprocess_shell()`. The LLM agent was unreliable — 1/15 success rate at actually running the command.
- **Results read from disk.** The `--output-json` flag writes a JSON file. The orchestrator reads it after the process exits. No SSE parsing, no stdout parsing, no "return the JSON" prompt.
- **Strategy pool with different HPs.** Each round picks the next N strategies from a predefined pool. Each strategy has different backbone, lr, epochs, augmentation, regularization.
- **`/dogpile` on every round** with full context: all prior rounds, all scores, all HPs, diagnosis.
- **`/memory` tracking** — every round and every dogpile stored to ArangoDB via Unix socket.

## File Structure

```
.pi/skills/thunderdome/
├── SKILL.md          # frontmatter + docs
├── run.sh            # uv run --project . python -m scripts.thunderdome "$@"
├── pyproject.toml    # typer, httpx, loguru, pyyaml, pydantic, jinja2, pillow, rich
├── sanity.sh         # 18 tests
├── examples/
│   └── classifier-table-merge.yaml  # manifest (no hardcoded strategies)
└── scripts/
    ├── __init__.py
    ├── manifest.py     # Pydantic schema for manifests
    ├── research.py     # /analytics + /dogpile + strategy pool + build_strategies()
    ├── dispatch.py     # asyncio subprocess dispatch, read results from disk
    ├── scoring.py      # jsonpath metric extraction, plateau/regression detection
    ├── tracking.py     # /memory via Unix socket (store rounds + dogpile)
    ├── diagnosis.py    # diagnose failures, persona review, /dogpile research
    └── thunderdome.py  # main typer CLI: run, status, report, list
```

## Manifest Format (no strategies section — they're generated)

```yaml
name: table-merge-classifier
description: "Classify whether adjacent PDF tables should merge"
data_dir: /home/graham/workspace/experiments/pi-mono/.pi/skills/create-table-classifier/data/merge_images/split
skill: classifier-lab

scoring:
  metric_path: "$.selected_metrics.macro_f1"
  gate_threshold: 0.90
  direction: higher_better

convergence:
  max_rounds: 5
  n_strategies: 3
  plateau_window: 3
  plateau_epsilon: 0.02

reviewers:
  - name: brandon-bailey
  - name: tim-blazytko

dogpile_on_failure: true
memory_scope: classifier-lab
```

## Strategy Pool (in research.py)

Each strategy is a dict with exact HP values:

```python
STRATEGY_POOL = [
    {"name": "paired-effnet-baseline", "modality": "paired", "backbones": "efficientnet_b0",
     "epochs": 20, "lr": 2e-4, "batch_size": 32, "mixup_alpha": 0.0, "cutmix_alpha": 0.0,
     "random_erasing": 0.0, "dropout": 0.1, "weight_decay": 1e-4, "label_smoothing": 0.0},
    {"name": "paired-effnet-augmented", "modality": "paired", "backbones": "efficientnet_b0",
     "epochs": 30, "lr": 1e-4, "batch_size": 16, "mixup_alpha": 0.3, "cutmix_alpha": 1.0,
     "random_erasing": 0.25, "dropout": 0.2, "weight_decay": 1e-3, "label_smoothing": 0.1},
    # ... more strategies with different backbones, HPs, augmentation
]
```

Each gets built into: `cd {SKILLS_DIR}/classifier-lab && ./run.sh benchmark --data-dir {data_dir} --modality {modality} --backbones {backbones} --epochs {epochs} --lr {lr} ... --output-json /tmp/thunderdome-{name}-r{round}.json --store-memory`

## The Benchmark Command

The classifier-lab benchmark CLI accepts these flags:
```
./run.sh benchmark
  --data-dir PATH        # directory with train/{class1,class2}/ val/{class1,class2}/
  --modality MODE        # vision | paired | tabular | text
  --backbones NAMES      # comma-separated backbone names
  --epochs N
  --lr FLOAT
  --batch-size N
  --weight-decay FLOAT
  --dropout FLOAT
  --label-smoothing FLOAT
  --mixup-alpha FLOAT
  --cutmix-alpha FLOAT
  --random-erasing FLOAT
  --output-json PATH     # writes JSON result file here
  --store-memory         # stores result to ArangoDB /memory
```

Output JSON format:
```json
{
  "status": "ok",
  "selected_backbone": "efficientnet_b0",
  "selected_metrics": {
    "macro_f1": 0.8108,
    "accuracy": 0.8100,
    "wilson_score_lower": 0.7900
  },
  "results": [...],
  "source": {"mode": "paired", "data_dir": "..."}
}
```

## /memory Integration

Track via Unix socket at `/run/user/1000/embry/memory.sock`:

```python
import httpx
transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
client = httpx.Client(transport=transport, base_url="http://localhost")

# Store round result
client.post("/learn", json={
    "problem": "THUNDERDOME:tournament-name:round1 — winner=X score=0.81",
    "solution": json.dumps(round_data),
    "tags": ["thunderdome", "tournament-round"],
    "scope": "classifier-lab",
})

# Recall prior tournaments
resp = client.post("/recall", json={"q": "THUNDERDOME:tournament-name", "k": 10})
```

## /dogpile Integration

Call via subprocess:
```python
skill_dir = SKILLS_DIR / "dogpile"
cmd = f'cd {skill_dir} && ./run.sh "query text here"'
proc = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=180,
                      env={**os.environ, "VIRTUAL_ENV": ""})
result = proc.stdout
```

## What "Done" Looks Like

1. `bash sanity.sh` — all tests pass
2. Run `bash run.sh run examples/classifier-table-merge.yaml` with `--max-rounds 2`
3. Round 1: 3 strategies run concurrently, each trains for 2-10 minutes on GPU
4. All 3 produce F1 scores (non-zero, ~0.75-0.85)
5. /dogpile fires with all 3 results
6. Round 2: next 3 strategies from pool with different HPs
7. All 3 produce F1 scores
8. Tournament reports FAILED (F1 < 0.90) with gap, diagnosis, dogpile insights
9. All rounds stored to /memory

## Data Location

- Training images: `/home/graham/workspace/experiments/pi-mono/.pi/skills/create-table-classifier/data/merge_images/split/`
  - `train/merge/` (891 images), `train/separate/` (812 images)
  - `val/merge/`, `val/separate/`
  - Images are 224x224 PNG
- Skills directory: `/home/graham/workspace/experiments/pi-mono/.pi/skills/`

## Python Rules

- Logging: `from loguru import logger` (NOT `import logging`)
- CLI: `typer` (NOT argparse)
- HTTP: `httpx` (NOT requests)
- Max 800 lines per file
- Every import must be in pyproject.toml

## Known Working Verification

This command produces F1~0.80 when run on the host:
```bash
cd /home/graham/workspace/experiments/pi-mono/.pi/skills/classifier-lab && \
  bash run.sh benchmark \
    --data-dir /home/graham/workspace/experiments/pi-mono/.pi/skills/create-table-classifier/data/merge_images/split \
    --modality paired \
    --backbones efficientnet_b0 \
    --epochs 2 \
    --output-json /tmp/test-verify.json \
    --store-memory
```

After running: `cat /tmp/test-verify.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'F1: {d[\"selected_metrics\"][\"macro_f1\"]:.4f}')"` → prints `F1: 0.7972`
