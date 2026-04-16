# Thunderdome Implementation Plan for Codex 5.3

Codebase: /home/node/workspace
READ ALL FILES REFERENCED BEFORE CHANGING ANYTHING.
DO NOT SKIP ANY STEP.

## What exists now

- `.pi/skills/thunderdome/` — skill skeleton with manifest schema, scoring, tracking, diagnosis, dispatch modules
- `.pi/skills/thunderdome/ARCHITECTURE.md` — Mermaid flowchart of the correct architecture
- `.pi/skills/classifier-lab/scripts/e2e_pipeline.py` — self-improvement loop with 10-step HP escalation
- `.pi/skills/classifier-lab/scripts/tracking.py` — /memory + /dogpile tracking helpers
- `.pi/skills/thunderdome/scripts/dispatch.py` — SSE stream dispatch to /subagent-service
- `.pi/skills/thunderdome/scripts/scoring.py` — metric extraction + plateau detection
- `.pi/skills/thunderdome/scripts/diagnosis.py` — persona review + /dogpile research
- `.pi/skills/thunderdome/scripts/thunderdome.py` — main CLI orchestrator

## What is WRONG with the current code

The current thunderdome.py has hardcoded strategies in YAML manifests. The correct architecture (see ARCHITECTURE.md) requires:

1. Strategies are GENERATED from /dogpile research, not hardcoded
2. /analytics runs FIRST to analyze the actual dataset
3. /dogpile gets the analytics output and recommends N approaches with specific HPs
4. Each round regenerates strategies based on new /dogpile + persona insights
5. Every round (pass or fail) sends full context to /dogpile
6. The manifest defines ONLY: task, data_dir, gate_threshold, reviewers — NOT strategies

## Implementation Steps

### Step 1: Add /analytics integration to thunderdome.py

File: `.pi/skills/thunderdome/scripts/thunderdome.py`

Before the convergence loop, add a `_analyze_dataset()` function that:
1. Calls `/analytics` skill via subprocess: `cd /home/node/skills/analytics && ./run.sh auto-discover --input {data_dir} --json`
2. If /analytics is not available, do basic analysis: count files per class dir, check image dimensions, compute class balance
3. Returns a dict with: total_samples, n_classes, class_counts, image_size (if images), balanced (bool), data_format (images/jsonl/csv)

### Step 2: Add strategy generation from /dogpile research

File: `.pi/skills/thunderdome/scripts/diagnosis.py`

Add function `generate_strategies_from_research(dogpile_output: str, manifest: ThunderdomeManifest, analytics: dict) -> list[Strategy]`:
1. Parse the /dogpile markdown output for recommended approaches
2. For each recommendation, create a Strategy object with:
   - name: from the recommendation
   - model: sonnet (default)
   - prompt: Jinja2 template that tells the subagent exactly what to run with the recommended HPs
   - timeout_s: from manifest default or 1800
3. The prompt template must include:
   - The exact benchmark command to run
   - The specific HPs recommended by /dogpile
   - The data_dir and output path
   - Instructions to return ONLY the JSON output
4. If parsing fails, fall back to manifest.strategies (backward compat)

### Step 3: Modify the convergence loop in thunderdome.py

File: `.pi/skills/thunderdome/scripts/thunderdome.py`

The `run()` command should now:

```python
# 1. Analyze dataset
analytics = _analyze_dataset(manifest)

# 2. Pre-tournament /dogpile with analytics
dogpile_query = f"""
Training classifier for: {manifest.description}
Dataset analysis: {json.dumps(analytics)}
Target: {manifest.scoring.metric_path} >= {manifest.scoring.gate_threshold}
What are the best {len(manifest.strategies) or 3} approaches to reach this target?
For each approach provide:
- Backbone model name
- Learning rate, batch size, epochs
- Augmentation strategy (mixup alpha, cutmix alpha, random erasing prob)
- Regularization (dropout, weight decay, label smoothing)
- Rationale for why this will work for this dataset size and type
"""
dogpile_insights = dogpile_research_direct(dogpile_query, manifest)

# 3. Generate strategies from research (or use manifest fallback)
strategies = generate_strategies_from_research(dogpile_insights, manifest, analytics)
if not strategies:
    strategies = manifest.strategies  # fallback

# 4. Convergence loop
for round_num in range(1, max_rounds + 1):
    # a. Feed insights into strategy prompts
    round_state = _build_round_state(round_num, all_rounds, diagnosis, dogpile_insights)

    # b. Dispatch strategies concurrently via SSE
    results = dispatch_strategies(strategies, manifest.variables, round_state, port, on_event)

    # c. Score
    round_result = score_round(...)

    # d. Check gate
    if round_result.gate_passed:
        break

    # e. /dogpile with FULL context (all rounds, all scores, all HPs)
    dogpile_insights = dogpile_research(round_result, all_rounds, manifest)

    # f. Persona reviewers
    persona_insights = persona_review(...)

    # g. REGENERATE strategies from new insights
    strategies = generate_strategies_from_research(
        dogpile_insights + "\n" + persona_insights, manifest, analytics
    )
    if not strategies:
        strategies = manifest.strategies  # fallback
```

### Step 4: Update manifest schema

File: `.pi/skills/thunderdome/scripts/manifest.py`

Make `strategies` optional (not required). Add fields:
- `auto_strategies: bool = True` — generate strategies from /dogpile research
- `n_strategies: int = 3` — how many strategies to generate
- `data_dir: str` — moved from variables to top-level (required for /analytics)

The manifest becomes:
```yaml
name: table-merge-classifier
description: "Classify whether adjacent PDF tables should merge"
data_dir: /path/to/data

scoring:
  metric_path: "$.selected_metrics.macro_f1"
  gate_threshold: 0.90
  direction: higher_better

convergence:
  max_rounds: 5
  n_strategies: 3

reviewers:
  - name: brandon-bailey
  - name: tim-blazytko

dogpile_on_failure: true
memory_scope: classifier-lab
```

No `strategies:` section — they are generated from research.

### Step 5: Update dispatch.py for dynamic strategies

File: `.pi/skills/thunderdome/scripts/dispatch.py`

The `_dispatch_one()` function already handles both `skill:` (converted to prompt) and `prompt:` strategies via SSE stream. No changes needed here — the dynamically generated Strategy objects use the same prompt field.

### Step 6: Update example manifests

File: `.pi/skills/thunderdome/examples/classifier-table-merge.yaml`

Remove the hardcoded strategies. Use the new minimal format with just task, data, gate, reviewers.

### Step 7: Update sanity.sh

File: `.pi/skills/thunderdome/sanity.sh`

Update assertions to match new manifest schema (strategies may be empty/optional).

### Step 8: Fix the subagent container for ML training

File: `.pi/skills/subagent-service/Dockerfile`

The subagent container does NOT have PyTorch. Training runs on the HOST via the `skill:` dispatch path (converted to a prompt that tells the subagent to run `./run.sh benchmark`). But the subagent's Claude Code sandbox blocks paths outside /home/node/workspace.

Current workaround: `--add-dir /mnt/storage12tb` in server.py + skills mounted read-write.

For a proper fix, add to Dockerfile:
```
RUN pip install torch torchvision timm --index-url https://download.pytorch.org/whl/cpu
```
(CPU-only to keep image small — GPU training happens on host)

And add `--gpus all` to the docker run command in run.sh line ~306 for GPU passthrough.

## Verification

After ALL steps:

1. `cd /home/node/workspace/.pi/skills/thunderdome && bash sanity.sh` — all tests pass
2. `cd /home/node/workspace/.pi/skills/thunderdome && bash run.sh run examples/classifier-table-merge.yaml --dry-run` — shows: analytics output, /dogpile research, generated strategies
3. Full run (if GPU available): strategies should be DIFFERENT from what was hardcoded — they come from /dogpile research based on actual dataset analysis

## NON-NEGOTIABLE rules

- ALL /dogpile calls include FULL context (all prior rounds, scores, HPs, diagnosis)
- Strategies are GENERATED from research, not hardcoded
- /analytics runs FIRST before any /dogpile
- EVERY round sends results to /dogpile, not just failures
- EVERY round stores to /memory via tracking.py
- When tournament FAILS, report: best score, gap, dogpile insights, persona reviews, next steps
- No subprocess.run with timeouts — use SSE stream for all dispatch
- Max 800 lines per Python file
- loguru for logging, typer for CLI, httpx for HTTP
