#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# assistant-lab — Self-improvement workbench for /assistant
# Wraps ModelFactory with CLI diagnostics, reporting, and orchestration.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ASSISTANT_DIR="${SCRIPT_DIR}/../assistant"
COMMON_DIR="${SCRIPT_DIR}/../common"
METRICS_DIR="${ASSISTANT_METRICS_DIR:-${HOME}/.pi/assistant}"
LAB_METRICS="${METRICS_DIR}/lab_metrics.jsonl"

# Ensure metrics dir exists
mkdir -p "${METRICS_DIR}"

SKILLS_DIR="${SCRIPT_DIR}/.."
# NOTE: ops-runpod is kept for the `serve` command (persistent inference endpoints).
# Training uses FlashTrainer (flash_trainer.py) — NOT ops-runpod SSH pipeline.
OPS_RUNPOD="${SKILLS_DIR}/ops-runpod/run.sh"
CREATE_GPT="${SKILLS_DIR}/create-gpt/run.sh"
MODELS_DIR="/mnt/storage12tb/models"

usage() {
    cat <<'EOF'
assistant-lab — Self-improvement workbench for /assistant

Usage:
  ./run.sh diagnose        --task TASK              What does this task need?
  ./run.sh auto-improve    --task TASK              Full autonomous loop for one task
  ./run.sh auto-improve    --all                    Auto-improve all shadow_mode tasks
  ./run.sh train           --task TASK --type TYPE [--target local|flash]  Train a model
  ./run.sh evaluate        --task TASK --type TYPE   Evaluate a model
  ./run.sh promote         --task TASK --type TYPE   Promote to live registry
  ./run.sh harvest         --task TASK [--since 24h] Extract teacher labels
  ./run.sh status                                    Shadow agreement for all tasks
  ./run.sh self-test                                 End-to-end test cycle

  # Remote training (FlashTrainer — for models too large for local A5000)
  ./run.sh estimate-remote --task TASK --size SIZE   Cost estimate via FlashTrainer
  ./run.sh train-remote    --task TASK --size SIZE   Train on RunPod via FlashTrainer (3B-13B)

Options:
  --task TASK      Task name from model_registry.json
  --type TYPE      Model type: gpt, classifier, regressor
  --target TARGET  Training target: local (default) or flash (FlashTrainer/RunPod)
  --size SIZE      Model size: 3B, 7B, 8B, 13B (for remote training)
  --base-model ID  HuggingFace model ID (default: from TaskSpec)
  --max-cost USD   Hard budget cap in dollars (default: 15.00)
  --quantize Q     GGUF quantization level (default: Q4_K_M)
  --priority PRI   GPU selection: cost, speed, balanced (default: cost)
  --confirm        Skip cost confirmation prompt
  --since SINCE    Time window for harvest (default: 7d)
  --json           Output as JSON
EOF
}

# Parse arguments
CMD="${1:-help}"
shift || true

TASK=""
MODEL_TYPE="gpt"
SINCE="7d"
JSON_OUTPUT=0
MODEL_SIZE=""
BASE_MODEL=""
MAX_COST="15.00"
QUANTIZE="Q4_K_M"
PRIORITY="cost"
CONFIRM=0
ALL_TASKS=0
TARGET="local"  # 'local' = local GPU via /create-gpt; 'flash' = FlashTrainer/RunPod

while [[ $# -gt 0 ]]; do
    case "$1" in
        --task) TASK="$2"; shift 2 ;;
        --type) MODEL_TYPE="$2"; shift 2 ;;
        --since) SINCE="$2"; shift 2 ;;
        --json) JSON_OUTPUT=1; shift ;;
        --size) MODEL_SIZE="$2"; shift 2 ;;
        --base-model) BASE_MODEL="$2"; shift 2 ;;
        --max-cost) MAX_COST="$2"; shift 2 ;;
        --quantize) QUANTIZE="$2"; shift 2 ;;
        --priority) PRIORITY="$2"; shift 2 ;;
        --confirm) CONFIRM=1; shift ;;
        --all) ALL_TASKS=1; shift ;;
        --target) TARGET="$2"; shift 2 ;;  # 'local' or 'flash' (FlashTrainer)
        *) shift ;;
    esac
done

# Helper: run python with model_factory
run_factory() {
    python3 -c "
import sys
sys.path.insert(0, '${COMMON_DIR}')
from model_factory import ModelFactory
import json

factory = ModelFactory()
$1
"
}

case "${CMD}" in
    diagnose)
        [[ -z "${TASK}" ]] && { echo "ERROR: --task required"; exit 1; }
        run_factory "
result = factory.needs_model('${TASK}')
status = factory._shadow_status('${TASK}')
result['shadow'] = status
print(json.dumps(result, indent=2))
"
        ;;

    auto-improve)
        if [[ "${ALL_TASKS}" -eq 1 ]]; then
            echo "=== assistant-lab: auto-improve ALL shadow_mode tasks ==="
            run_factory "
import pathlib
registry = json.loads(pathlib.Path('${ASSISTANT_DIR}/model_registry.json').read_text())
results = []
for section in ['validators', 'classifiers', 'regressors']:
    for task_name, entry in registry.get(section, {}).items():
        if entry.get('shadow_mode', False):
            print(f'--- auto-improve: {task_name} ---')
            try:
                r = factory.auto_improve(task_name)
                results.append(r)
                print(json.dumps(r, indent=2))
            except Exception as e:
                print(f'ERROR: {task_name}: {e}')
                results.append({'task': task_name, 'error': str(e)})
print(f'\\n=== Processed {len(results)} shadow_mode tasks ===')
"
            echo "{\"action\":\"auto-improve-all\",\"ts\":$(date +%s)}" >> "${LAB_METRICS}"
        else
            [[ -z "${TASK}" ]] && { echo "ERROR: --task or --all required"; exit 1; }
            echo "=== assistant-lab: auto-improve task=${TASK} ==="
            run_factory "
result = factory.auto_improve('${TASK}')
print(json.dumps(result, indent=2))
"
            echo "{\"action\":\"auto-improve\",\"task\":\"${TASK}\",\"ts\":$(date +%s)}" >> "${LAB_METRICS}"
        fi
        ;;

    train)
        [[ -z "${TASK}" ]] && { echo "ERROR: --task required"; exit 1; }
        echo "=== assistant-lab: train ${MODEL_TYPE} for task=${TASK} (target=${TARGET}) ==="
        run_factory "
if '${MODEL_TYPE}' == 'gpt':
    # target='flash' routes to FlashTrainer/RunPod; 'local' uses local GPU via /create-gpt
    result = factory.train_gpt('${TASK}', target='${TARGET}')
elif '${MODEL_TYPE}' == 'classifier':
    result = factory.train_classifier('${TASK}')
elif '${MODEL_TYPE}' == 'regressor':
    result = factory.train_regressor('${TASK}')
else:
    result = {'error': 'unknown type: ${MODEL_TYPE}'}
import dataclasses
print(json.dumps(dataclasses.asdict(result) if hasattr(result, '__dataclass_fields__') else result, indent=2))
"
        ;;

    evaluate)
        [[ -z "${TASK}" ]] && { echo "ERROR: --task required"; exit 1; }
        echo "=== assistant-lab: evaluate ${MODEL_TYPE} for task=${TASK} ==="
        run_factory "
if '${MODEL_TYPE}' in ('gpt', 'validator'):
    result = factory.evaluate_gpt('${TASK}')
elif '${MODEL_TYPE}' == 'classifier':
    result = factory.evaluate_classifier('${TASK}')
else:
    result = {'error': 'no evaluator for type: ${MODEL_TYPE}'}
import dataclasses
print(json.dumps(dataclasses.asdict(result) if hasattr(result, '__dataclass_fields__') else result, indent=2))
"
        ;;

    promote)
        [[ -z "${TASK}" ]] && { echo "ERROR: --task required"; exit 1; }
        echo "=== assistant-lab: promote ${MODEL_TYPE} for task=${TASK} ==="
        run_factory "
ok = factory.promote('${TASK}', '${MODEL_TYPE}')
print(json.dumps({'promoted': ok, 'task': '${TASK}', 'type': '${MODEL_TYPE}'}))
"
        ;;

    harvest)
        [[ -z "${TASK}" ]] && { echo "ERROR: --task required"; exit 1; }
        echo "=== assistant-lab: harvest labels for task=${TASK} ==="
        run_factory "
path = factory._harvest_labels('${TASK}', '${MODEL_TYPE}')
print(json.dumps({'labels_path': str(path) if path else None, 'task': '${TASK}'}))
"
        ;;

    status)
        echo "=== assistant-lab: shadow agreement status ==="
        python3 -c "
import sys, json
sys.path.insert(0, '${COMMON_DIR}')
from model_factory import ModelFactory

factory = ModelFactory()
REGISTRY_PATH = factory.config.registry_path
registry = json.loads(REGISTRY_PATH.read_text()) if REGISTRY_PATH.exists() else {}

tasks = set()
for section in ('validators', 'classifiers', 'regressors'):
    tasks.update(registry.get(section, {}).keys())

print(f'Tasks in registry: {len(tasks)}')
print()
print(f'{\"Task\":<35} {\"Shadow\":<10} {\"Samples\":<10} {\"Status\":<15}')
print('-' * 70)
for task in sorted(tasks):
    status = factory._shadow_status(task)
    agreement = status['agreement_rate']
    samples = status['sample_count']

    if samples < 50:
        label = 'need-data'
    elif agreement >= 0.90:
        label = 'ready-to-promote'
    elif agreement >= 0.80:
        label = 'plateau'
    elif agreement >= 0.70:
        label = 'needs-retrain'
    else:
        label = 'low-agreement'

    print(f'{task:<35} {agreement:>7.1%}   {samples:>7}   {label}')
"
        ;;

    estimate-remote)
        [[ -z "${TASK}" ]] && { echo "ERROR: --task required"; exit 1; }
        [[ -z "${MODEL_SIZE}" ]] && { echo "ERROR: --size required (3B, 7B, 8B, 13B)"; exit 1; }
        echo "=== assistant-lab: estimate-remote task=${TASK} size=${MODEL_SIZE} (FlashTrainer) ==="

        echo ""
        echo "--- Flash GPU Selection (priority: ${PRIORITY}) ---"
        python3 -c "
import sys, json
sys.path.insert(0, '${COMMON_DIR}')
from flash_trainer import estimate_gpu, estimate_cost, _GPU_SPECS

size_str = '${MODEL_SIZE}'.upper().replace('B', '')
model_size_b = float(size_str)
hours = 4.0  # default estimate window

gpu = estimate_gpu(model_size_b, method='lora')
cost = estimate_cost(gpu, hours)
spec = _GPU_SPECS[gpu]

print(f'  GPU:        {gpu}')
print(f'  VRAM:       {spec[\"vram_gb\"]} GB')
print(f'  Rate:       \${spec[\"price_hr\"]}/hr')
print(f'  Est. hours: {hours:.1f}')
print(f'  Est. cost:  \${cost:.2f}')
if ${JSON_OUTPUT}:
    print()
    print(json.dumps({
        'gpu_type': gpu,
        'vram_gb': spec['vram_gb'],
        'price_hr': spec['price_hr'],
        'estimated_hours': hours,
        'estimated_cost': cost,
        'backend': 'flash',
    }, indent=2))
" 2>/dev/null || echo "  (flash_trainer unavailable — ensure COMMON_DIR is set)"
        ;;

    train-remote)
        [[ -z "${TASK}" ]] && { echo "ERROR: --task required"; exit 1; }
        [[ -z "${MODEL_SIZE}" ]] && { echo "ERROR: --size required (3B, 7B, 8B, 13B)"; exit 1; }
        echo "=== assistant-lab: train-remote task=${TASK} size=${MODEL_SIZE} (FlashTrainer) ==="

        # Step 1: Cost estimate via FlashTrainer.estimate_cost()
        echo ""
        echo "Step 1/6: Cost estimate (FlashTrainer)..."
        ESTIMATE=$(python3 -c "
import sys, json
sys.path.insert(0, '${COMMON_DIR}')
from flash_trainer import estimate_gpu, estimate_cost, _GPU_SPECS

size_str = '${MODEL_SIZE}'.upper().replace('B', '')
model_size_b = float(size_str)
hours = max(2.0, model_size_b * 0.5)  # heuristic: ~0.5h per billion params

gpu = estimate_gpu(model_size_b, method='lora')
cost = estimate_cost(gpu, hours)
spec = _GPU_SPECS[gpu]

print(json.dumps({
    'gpu_type': gpu,
    'estimated_hours': hours,
    'estimated_cost': cost,
    'vram_gb': spec['vram_gb'],
    'price_hr': spec['price_hr'],
}))
") || { echo "ERROR: Could not estimate cost via FlashTrainer"; exit 1; }

        EST_COST=$(echo "${ESTIMATE}" | python3 -c "import sys,json; print(json.load(sys.stdin)['estimated_cost'])")
        EST_GPU=$(echo "${ESTIMATE}" | python3 -c "import sys,json; print(json.load(sys.stdin)['gpu_type'])")
        EST_HOURS=$(echo "${ESTIMATE}" | python3 -c "import sys,json; print(json.load(sys.stdin)['estimated_hours'])")

        echo "  GPU:       ${EST_GPU}"
        echo "  Est. time: ${EST_HOURS} hours"
        echo "  Est. cost: \$${EST_COST}"
        echo "  Max cost:  \$${MAX_COST}"
        echo ""

        # Budget gate
        OVER_BUDGET=$(python3 -c "print('yes' if float('${EST_COST}') > float('${MAX_COST}') else 'no')")
        if [[ "${OVER_BUDGET}" == "yes" ]]; then
            echo "ERROR: Estimated cost \$${EST_COST} exceeds --max-cost \$${MAX_COST}"
            echo "  Increase --max-cost or use a smaller model size."
            exit 1
        fi

        # Confirmation gate
        if [[ "${CONFIRM}" -ne 1 ]]; then
            echo "This will provision a RunPod GPU via FlashTrainer and incur real costs."
            echo "Re-run with --confirm to proceed, or use --max-cost to set a budget."
            echo ""
            echo "  ./run.sh train-remote --task ${TASK} --size ${MODEL_SIZE} --max-cost ${MAX_COST} --confirm"
            exit 0
        fi

        # Step 2: Submit training job via FlashTrainer (provision + launch in one call)
        echo "Step 2/6: Submitting FlashTrainer job (GPU: ${EST_GPU})..."
        # Locate dedicated create-gpt LoRA training script; fall back to bootstrap
        CREATE_GPT_TRAIN="${SKILLS_DIR}/create-gpt/scripts/train_lora.py"
        if [[ ! -f "${CREATE_GPT_TRAIN}" ]]; then
            CREATE_GPT_TRAIN="/tmp/flash_train_${TASK}_$(date +%s).py"
            cat > "${CREATE_GPT_TRAIN}" <<'PYEOF'
#!/usr/bin/env python3
"""FlashTrainer bootstrap: installs training deps for the remote pod."""
import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q",
    "transformers", "peft", "datasets", "trl", "accelerate"], check=True)
import os
task = os.environ.get("FLASH_TASK", "unknown")
print(f"FlashTrainer: training environment ready for task={task}")
print(f"Checkpoint directory: /runpod-volume/checkpoints")
PYEOF
        fi
        BASE_MODEL_ARG="${BASE_MODEL:-Qwen/Qwen2.5-1.5B-Instruct}"
        TIMEOUT_HOURS=$(python3 -c "import math; print(math.ceil(float('${EST_HOURS}') * 1.5 + 1))")

        POD_ID=$(python3 -c "
import sys
sys.path.insert(0, '${COMMON_DIR}')
from flash_trainer import FlashTrainer, estimate_gpu

size_str = '${MODEL_SIZE}'.upper().replace('B', '')
model_size_b = float(size_str)
gpu = estimate_gpu(model_size_b, method='lora')

trainer = FlashTrainer()
job_id = trainer.submit_training_job(
    script_path='${CREATE_GPT_TRAIN}',
    args=['--task', '${TASK}', '--base-model', '${BASE_MODEL_ARG}'],
    gpu_type=gpu,
    timeout_hours=${TIMEOUT_HOURS},
)
print(job_id)
") 2>&1 || { echo "ERROR: FlashTrainer job submission failed."; exit 1; }

        # Extract just the pod ID (last line, strip whitespace)
        POD_ID=$(echo "${POD_ID}" | tail -1 | tr -d '[:space:]')
        if [[ -z "${POD_ID}" ]]; then
            echo "ERROR: FlashTrainer returned empty pod ID."
            exit 1
        fi
        echo "  Pod ID: ${POD_ID}"

        # Ensure teardown on exit (trap)
        cleanup_flash() {
            echo ""
            echo "Auto-teardown: Terminating FlashTrainer pod ${POD_ID}..."
            python3 -c "
import sys
sys.path.insert(0, '${COMMON_DIR}')
from flash_trainer import FlashTrainer
FlashTrainer().terminate('${POD_ID}')
" 2>/dev/null || true
        }
        trap cleanup_flash EXIT

        # Step 3: Monitor training job until terminal state
        echo "Step 3/6: Monitoring FlashTrainer job ${POD_ID}..."
        python3 -c "
import sys, time
sys.path.insert(0, '${COMMON_DIR}')
from flash_trainer import FlashTrainer

trainer = FlashTrainer()
terminal = frozenset({'EXITED', 'TERMINATED', 'FAILED', 'DEAD'})
for _ in range(480):  # max 8h at 60s intervals
    status = trainer.poll_status('${POD_ID}')
    state = status.get('state', 'UNKNOWN').upper()
    print(f'  [{time.strftime(\"%H:%M:%S\")}] state={state}', flush=True)
    if state in terminal:
        break
    time.sleep(60)
logs = trainer.get_logs('${POD_ID}', tail_lines=50)
if logs:
    print('--- last 50 log lines ---')
    print(logs)
" 2>/dev/null || echo "  WARNING: Monitor loop error — pod may still be running."

        # Step 4: Download model weights via FlashTrainer
        echo "Step 4/6: Downloading trained model (FlashTrainer)..."
        REMOTE_MODEL_DIR="${MODELS_DIR}/${TASK}"
        mkdir -p "${REMOTE_MODEL_DIR}"
        echo "  Destination: ${REMOTE_MODEL_DIR}"
        python3 -c "
import sys
sys.path.insert(0, '${COMMON_DIR}')
from flash_trainer import FlashTrainer

dest = FlashTrainer().download_checkpoint(
    '${POD_ID}',
    '${REMOTE_MODEL_DIR}',
    remote_checkpoint_dir='/runpod-volume/checkpoints',
)
print(f'  Downloaded to: {dest}')
" 2>/dev/null || {
            echo "  WARNING: Checkpoint download failed. Weights may remain on pod volume."
            echo "  Download manually: python3 -c \"from flash_trainer import FlashTrainer; FlashTrainer().download_checkpoint('${POD_ID}', '${REMOTE_MODEL_DIR}')\""
        }

        # Step 5: Export to GGUF
        echo "Step 5/6: Exporting to GGUF (${QUANTIZE})..."
        "${CREATE_GPT}" export --task "${TASK}" --quantize "${QUANTIZE}" 2>&1 || {
            echo "WARNING: GGUF export failed. Model weights are at ${REMOTE_MODEL_DIR}"
            echo "  Run manually: create-gpt/run.sh export --task ${TASK} --quantize ${QUANTIZE}"
        }

        # Step 6: Evaluate and optionally promote
        echo "Step 6/6: Evaluating trained model..."
        run_factory "
result = factory.evaluate_gpt('${TASK}')
import dataclasses
data = dataclasses.asdict(result) if hasattr(result, '__dataclass_fields__') else result
print(json.dumps(data, indent=2))
passing = data.get('passing', False)
if passing:
    print()
    print('Model PASSED evaluation — promoting to live registry...')
    factory.promote('${TASK}', 'gpt')
    print('Promoted.')
else:
    print()
    print('Model did NOT pass evaluation. Review results above.')
    print('  Promote manually: ./run.sh promote --task ${TASK} --type gpt')
"

        # Log to metrics
        echo "{\"action\":\"train-remote\",\"task\":\"${TASK}\",\"size\":\"${MODEL_SIZE}\",\"gpu\":\"${EST_GPU}\",\"cost_est\":${EST_COST},\"backend\":\"flash\",\"ts\":$(date +%s)}" >> "${LAB_METRICS}"

        echo ""
        echo "=== train-remote complete (FlashTrainer) ==="
        echo "  Task:    ${TASK}"
        echo "  Size:    ${MODEL_SIZE}"
        echo "  GPU:     ${EST_GPU}"
        echo "  Model:   ${REMOTE_MODEL_DIR}"
        echo "  Pod ${POD_ID} will be terminated automatically."
        ;;

    self-test)
        echo "=== assistant-lab: self-test ==="
        echo "Step 1: Check model_factory + flash_trainer imports..."
        python3 -c "
import sys
sys.path.insert(0, '${COMMON_DIR}')
from model_factory import ModelFactory, TrainResult, EvalResult
print('  ModelFactory imported OK')
factory = ModelFactory()
print(f'  Registry loaded: {len(factory._registry.get(\"validators\", {}))} validators, {len(factory._registry.get(\"classifiers\", {}))} classifiers, {len(factory._registry.get(\"regressors\", {}))} regressors')
from flash_trainer import FlashTrainer, estimate_gpu, estimate_cost
print('  FlashTrainer imported OK')
gpu = estimate_gpu(7.0, method='lora')
cost = estimate_cost(gpu, 4.0)
print(f'  FlashTrainer estimate: {gpu} ~\${cost:.2f} for 4h')
" || { echo "FAIL: model_factory or flash_trainer import"; exit 1; }

        echo "Step 2: Check composed skills exist..."
        for skill in create-gpt create-classifier create-regressor gpt-lab classifier-lab prompt-lab ops-runpod; do
            if [[ -d "${SCRIPT_DIR}/../${skill}" ]]; then
                echo "  /${skill} found"
            else
                echo "  WARNING: /${skill} not found at ${SCRIPT_DIR}/../${skill}"
            fi
        done

        echo "Step 3: Check shadow.jsonl..."
        if [[ -f "${METRICS_DIR}/shadow.jsonl" ]]; then
            lines=$(wc -l < "${METRICS_DIR}/shadow.jsonl")
            echo "  shadow.jsonl: ${lines} entries"
        else
            echo "  shadow.jsonl: not yet created (no shadow mode data)"
        fi

        echo ""
        echo "assistant-lab self-test PASSED"
        ;;

    gui|app)
        shift
        uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/app.py" "$@"
        ;;

    help|--help|-h)
        usage
        ;;

    *)
        echo "Unknown command: ${CMD}"
        usage
        exit 1
        ;;
esac
