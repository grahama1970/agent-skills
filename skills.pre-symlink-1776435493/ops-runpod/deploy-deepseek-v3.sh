#!/bin/bash
# deploy-deepseek-v3.sh - Deploy Deepseek V3 FP8 on RunPod
#
# Usage:
#   ./deploy-deepseek-v3.sh [--estimate-only] [--hours N] [--fast]
#
# Options:
#   --estimate-only  Show cost estimate without deploying
#   --hours N        Expected runtime (default: 12 for overnight)
#   --fast           Use H100 instead of A100 (faster but more expensive)
#
# Requirements:
#   - RUNPOD_API_KEY environment variable
#   - 8x A100 80GB or 8x H100 80GB availability

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load RUNPOD_API_KEY from env file if not already set
if [[ -z "${RUNPOD_API_KEY:-}" ]]; then
    ENV_FILE="${RUNPOD_ENV_FILE:-$SCRIPT_DIR/.env}"
    if [[ -f "$ENV_FILE" ]]; then
        export RUNPOD_API_KEY=$(grep -E "^RUNPOD_API_KEY=" "$ENV_FILE" | head -1 | cut -d'=' -f2-)
    fi
fi

if [[ -z "${RUNPOD_API_KEY:-}" ]]; then
    echo "ERROR: RUNPOD_API_KEY not set"
    echo "Set via: export RUNPOD_API_KEY=your_key"
    exit 1
fi

# Default configuration
HOURS=12  # Overnight job
GPU_TYPE="A100_80GB"  # Cost-optimized default
GPU_COUNT=8
VOLUME_SIZE=750
ESTIMATE_ONLY=false
MODEL_ID="deepseek-ai/DeepSeek-V3"
DOCKER_IMAGE="lmsysorg/sglang:latest"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --estimate-only)
            ESTIMATE_ONLY=true
            shift
            ;;
        --hours)
            HOURS="$2"
            shift 2
            ;;
        --fast)
            GPU_TYPE="H100"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--estimate-only] [--hours N] [--fast]"
            echo ""
            echo "Deploy Deepseek V3 FP8 on RunPod for large-scale inference."
            echo ""
            echo "Options:"
            echo "  --estimate-only  Show cost estimate without deploying"
            echo "  --hours N        Expected runtime (default: 12 for overnight)"
            echo "  --fast           Use H100 instead of A100 (faster, ~1.6x cost)"
            echo ""
            echo "Example: $0 --estimate-only --hours 8"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# GPU pricing (spot, approximate)
if [[ "$GPU_TYPE" == "H100" ]]; then
    HOURLY_PER_GPU=2.99
    THROUGHPUT_TPS=250
else
    HOURLY_PER_GPU=1.89
    THROUGHPUT_TPS=150
fi

HOURLY_TOTAL=$(echo "$HOURLY_PER_GPU * $GPU_COUNT" | bc)
TOTAL_COST=$(echo "$HOURLY_TOTAL * $HOURS" | bc)

echo "============================================================"
echo "DEEPSEEK V3 FP8 DEPLOYMENT"
echo "============================================================"
echo ""
echo "Model: $MODEL_ID"
echo "Size: 671B MoE (37B active), ~350GB FP8"
echo ""
echo "GPU Configuration:"
echo "  Type: $GPU_TYPE"
echo "  Count: ${GPU_COUNT}x"
echo "  Tensor Parallel: TP=8"
echo "  NVLink: Required"
echo ""
echo "Storage:"
echo "  Volume: ${VOLUME_SIZE}GB (persistent)"
echo "  Mount: /models"
echo ""
echo "Performance Estimate:"
echo "  Throughput: ~${THROUGHPUT_TPS} tokens/sec"
echo "  QRAs/hour: ~$((THROUGHPUT_TPS * 3600 / 1000)) (at ~1K tokens each)"
echo ""
echo "Cost Estimate (spot pricing):"
echo "  Hourly: \$${HOURLY_TOTAL}/hr"
echo "  ${HOURS}h job: \$${TOTAL_COST}"
echo ""
echo "Time Breakdown:"
echo "  Model download (first run): ~45 min"
echo "  Inference time: ~${HOURS}h"
echo ""

if [[ "$ESTIMATE_ONLY" == "true" ]]; then
    echo "============================================================"
    echo "[ESTIMATE ONLY - No deployment performed]"
    echo ""
    echo "To deploy, run without --estimate-only:"
    echo "  $0 --hours $HOURS"
    exit 0
fi

echo "============================================================"
echo "DEPLOYING POD..."
echo "============================================================"

# Create the pod using RunPod API
# Note: This uses the runpod Python SDK via our CLI wrapper

POD_CONFIG=$(cat <<EOF
{
    "name": "deepseek-v3-fp8-sparta",
    "imageName": "$DOCKER_IMAGE",
    "gpuTypeId": "$GPU_TYPE",
    "gpuCount": $GPU_COUNT,
    "volumeInGb": $VOLUME_SIZE,
    "containerDiskInGb": 50,
    "ports": "8000/http,22/tcp",
    "startSsh": true,
    "env": {
        "MODEL_ID": "$MODEL_ID",
        "TP_SIZE": "8",
        "DTYPE": "fp8",
        "MAX_MODEL_LEN": "32768",
        "HF_HOME": "/models",
        "TRANSFORMERS_CACHE": "/models"
    },
    "dockerArgs": "python -m sglang.launch_server --model-path $MODEL_ID --host 0.0.0.0 --port 8000 --tp 8 --dtype fp8 --max-model-len 32768 --trust-remote-code --download-dir /models"
}
EOF
)

echo "Pod configuration:"
echo "$POD_CONFIG" | jq .

# Call RunPod API to create pod
RESPONSE=$(curl -s -X POST "https://api.runpod.io/graphql" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $RUNPOD_API_KEY" \
    -d "{
        \"query\": \"mutation { podFindAndDeployOnDemand(input: { cloudType: SECURE, gpuCount: $GPU_COUNT, volumeInGb: $VOLUME_SIZE, containerDiskInGb: 50, minVcpuCount: 16, minMemoryInGb: 128, gpuTypeId: \\\"$GPU_TYPE\\\", name: \\\"deepseek-v3-fp8-sparta\\\", imageName: \\\"$DOCKER_IMAGE\\\", ports: \\\"8000/http,22/tcp\\\", startSsh: true, env: [{key: \\\"MODEL_ID\\\", value: \\\"$MODEL_ID\\\"}, {key: \\\"TP_SIZE\\\", value: \\\"8\\\"}, {key: \\\"DTYPE\\\", value: \\\"fp8\\\"}] }) { id machineId gpuCount } }\"
    }")

echo ""
echo "API Response:"
echo "$RESPONSE" | jq .

# Extract pod ID
POD_ID=$(echo "$RESPONSE" | jq -r '.data.podFindAndDeployOnDemand.id // empty')

if [[ -z "$POD_ID" ]]; then
    echo ""
    echo "ERROR: Failed to create pod"
    echo "Check the API response above for details."
    echo ""
    echo "Common issues:"
    echo "  - GPU type not available (try different region or time)"
    echo "  - Insufficient quota/credits"
    echo "  - Invalid API key"
    exit 1
fi

echo ""
echo "============================================================"
echo "POD CREATED SUCCESSFULLY"
echo "============================================================"
echo ""
echo "Pod ID: $POD_ID"
echo ""
echo "Next steps:"
echo "  1. Wait for model download (~45 min first time)"
echo "  2. Check server status:"
echo "     $SCRIPT_DIR/run.sh monitor $POD_ID"
echo ""
echo "  3. Once ready, inference endpoint will be at:"
echo "     https://$POD_ID-8000.proxy.runpod.net"
echo ""
echo "  4. Test with:"
echo "     curl https://$POD_ID-8000.proxy.runpod.net/v1/chat/completions \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -d '{\"model\": \"deepseek-v3\", \"messages\": [{\"role\": \"user\", \"content\": \"Hello\"}]}'"
echo ""
echo "  5. When done, terminate:"
echo "     $SCRIPT_DIR/run.sh terminate $POD_ID"
echo ""
echo "============================================================"
echo "Saving pod info to: /tmp/deepseek-v3-pod.json"
echo "$RESPONSE" > /tmp/deepseek-v3-pod.json
