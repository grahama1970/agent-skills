# Unsloth Studio — Project Knowledge

## Architecture

```text
dataset-builder subagent (worker)     unsloth-studio subagent (monitor)
───────────────────────────────       ──────────────────────────────
documents → QRA → alpaca.jsonl        training.jsonl → GGUF
prompt reviewed by prompt-reviewer    self-improving loop (max 5 iter)
```

## Known API Fields (Verified)

| API | Field | Value |
|-----|-------|-------|
| `POST /api/auth/login` | body | `{"username":"unsloth","password":"<env>"}` |
| `POST /api/train/start` | `model_name` | HF model ID |
| | `training_type` | `"LoRA/QLoRA"`, `"Full Finetuning"`, `"Continued Pretraining"` |
| | `hf_dataset` | HF dataset name |
| | `format_type` | `"alpaca"`, `"chatml"`, `"sharegpt"`, `"auto"` |
| | `eval_split` | Split name (e.g. `"test"`) — dataset must have it |
| | `eval_steps` | Evaluate every N steps |
| | `subset` | Dataset subset (e.g. `"train_sft"` for ultrachat) |

## Known Issues

| Issue | Workaround |
|-------|------------|
| Container recreate resets Studio auth | Password must be re-set via UI at `/change-password` |
| GPU memory fragmented by host processes | Kill orpheus-infer, whisper, zed, stale inference servers |
| Datasets without split can't use eval | Use `eval_split: "train"` or dataset with `test`/`validation` split |
| Chutes model goes cold in ~2 min | Warm via direct API call before batch |
| doc2qra scillm batch times out | Model cold + 30s scillm timeout. Warm model first or use longer timeout |

## ToM Teacher-Student Pipeline

### Overview
Teacher-student distillation pipeline for theory-of-mind (ToM) classification.
**Teacher:** `deepseek-ai/DeepSeek-V3.2-TEE` (31B) via scillm chutes (`localhost:4001`).
**Student:** Qwen2.5-3B fine-tuned on teacher labels via LoRA.

### Teacher Labels (v4)
- **Model:** `deepseek-ai/DeepSeek-V3.2-TEE` via scillm (NOT direct chutes API)
- **Call pattern:** `POST /v1/chat/completions` with `model: "deepseek-ai/DeepSeek-V3.2-TEE"`, `response_format: {"type": "json_object"}`, `_scillm_allow_cold_chutes: true`
- **Headers:** `Authorization: Bearer sk-dev-proxy-123`, `X-Caller-Skill: tom-teacher`
- **Prompt:** `/mnt/storage12tb/tom_prompts/tom_system_v4.txt` + `tom_user_v4.txt`
- **Full prompt ask:** `/home/graham/workspace/experiments/agent-skills/scratch.md`
- **Output:** `/mnt/storage12tb/teacher_labels_v4.jsonl` (281 records, 100% parse rate)
- **HF dataset:** `grahamaco/tom-teacher-labels-v4` (private)
- **Key design:** Question-conditioned classifier with tie-break rules, no `knowledge_gap` fallback, clean sentence-boundary context extraction, stripped rationale header

### Student Model Comparison
Fine-tuned on v4 teacher labels via LoRA (r=8, lr=2e-4, 3 epochs):

| Model | Accuracy | Size | VRAM | Train Time |
|---|---|---|---|---|
| **Qwen2.5-3B** (tom-student) | **80%** | 6.2GB | 6GB | 5.7 min |
| Qwen2.5-1.5B | 76% | 3.1GB | 3GB | 2 min |
| Qwen3-8B | 75% | 16GB | 9GB | 7.5 min |
| Base models zero-shot | 7-39% | — | — | — |
| Gemma3-4B (text-only, gghfez) | pending | ~6GB | ~6GB | downloading |

### Deployed Ollama Model
- **Name:** `tom-student:latest` (not `tom-teacher`)
- **Base:** Qwen/Qwen2.5-3B-Instruct
- **GGUF:** `/mnt/storage12tb/tom_qwen3b_fp16/tom_teacher.gguf`
- **Adapters:** `/mnt/storage12tb/tom_student_qwen3b_final`
- **Training data:** `/mnt/storage12tb/tom_finetune_v4.jsonl`
- **Usage:** always include system prompt `"You are a theory-of-mind classifier."`

### Split Manifest
- `/mnt/storage12tb/split_manifest.json`
- Grouped by persona+source document (7 groups across 2 personas)
- Train 165 / Val 44 / Test 72 (approximately 60/20/20)
- Seed 42, deterministic grouping prevents leakage

### Known Issues

| Issue | Workaround |
|-------|------------|
| Gemma3-4B multimodal processor prevents standard PEFT/trl training | Use `gghfez/gemma-3-4b-novision` (text-only version) — currently downloading |
| GGUF conversion from 4-bit safetensors fails | Merge LoRA in FP16 first, then convert via llama.cpp's convert_hf_to_gguf.py |
| Ollama model needs system prompt for best accuracy | Always include system message with the training system prompt |
| Qwen3-8B underperformed 3B on same data | May need more epochs or different LR |
| `knowledge_gap` fallback produces false labels | Question-conditioned prompt with explicit rule: never use knowledge_gap because dataset asks a question |

### Unsloth Studio Auth
- **UI:** `http://localhost:8000`
- **JWT login:** `POST /api/auth/login` with `{"username":"unsloth","password":"<UNSLOTH_STUDIO_PASSWORD from ~/.zshrc>"}`
- **Model Arena URL:** `http://localhost:8000/chat?compare=<session-id>`
- **API endpoints limited** — `/api/models/` returns 404 on this version

## Bugs Fixed (doc2qra)

- `model: "text"` → model alias in 3 files (summary.py, qra_batch.py, qra_llm.py)
- `stream:false` → stream:true + SSE parsing
- `choices: []` IndexError → `if choices:` guard
- `delta.get("content")` returning None → `or ""`
- `DEFAULT_CONCURRENCY=6→4`, `DEFAULT_TIMEOUT=60→300`
- `cli.py` hardcoded `timeout=60` → `DEFAULT_TIMEOUT`
- Indentation error in qra_llm.py

## Sibling Subagents

- `dataset-builder` — converts documents to training datasets via doc2qra + prompt-reviewer + convert-to-alpaca
- `model-trainer` — trains task-specific small GPTs/classifiers (separate from unsloth-studio)

## RunPod Fallback

When local GPU VRAM < required (model_params_GB + 2GB), escalate:
```bash
$ask devops to provision RunPod with ops-runpod@v1 --template unsloth-base
```
Then set `UNSLOTH_HOST=<pod-ip>` and proceed identically.
