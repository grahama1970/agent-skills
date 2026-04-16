# ACE-Step Music Generation Server
#
# Base: NVIDIA PyTorch with CUDA support
# Target: A5000 24GB (FP8/FP4 modes)

FROM pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Clone ACE-Step (or install from pip when available)
RUN pip install --no-cache-dir \
    ace-step \
    || git clone https://github.com/ace-step/ACE-Step.git /opt/ace-step \
    && pip install --no-cache-dir -e /opt/ace-step

# Copy server code
COPY app.py engine.py ./

# Create outputs directory
RUN mkdir -p /app/outputs

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=300s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# Run server
CMD ["python", "app.py"]
