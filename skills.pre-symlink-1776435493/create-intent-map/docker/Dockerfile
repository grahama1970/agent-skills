# Intent Mapper LoRA Training Container
# Base: DeepSeek-R1-Distill-Qwen-7B
#
# Build:
#   docker build -t intent-mapper-train -f docker/Dockerfile .
#
# Run:
#   docker run --gpus all -v $(pwd):/workspace intent-mapper-train train

FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

LABEL maintainer="create-intent-map skill"
LABEL description="LoRA training for SPARTA intent mapper"

# Set working directory
WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY docker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Pre-download the base model (optional - speeds up first run)
# Uncomment to bake model into image (adds ~14GB to image size)
# ARG HF_TOKEN
# RUN huggingface-cli login --token $HF_TOKEN && \
#     python -c "from transformers import AutoModelForCausalLM, AutoTokenizer; \
#                AutoTokenizer.from_pretrained('deepseek-ai/DeepSeek-R1-Distill-Qwen-7B'); \
#                AutoModelForCausalLM.from_pretrained('deepseek-ai/DeepSeek-R1-Distill-Qwen-7B', torch_dtype='auto')"

# Copy training scripts
COPY scripts/ /workspace/scripts/

# Create directories
RUN mkdir -p /workspace/data/sft /workspace/models /workspace/logs

# Environment
ENV PYTHONUNBUFFERED=1
ENV TRANSFORMERS_CACHE=/workspace/.cache/huggingface
ENV HF_HOME=/workspace/.cache/huggingface

# Default command
ENTRYPOINT ["python", "/workspace/scripts/train.py"]
CMD ["--help"]
