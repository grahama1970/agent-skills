# Base image with PyTorch and CUDA support
FROM pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
# Copy requirements first to leverage cache
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy skill code
COPY . /app/

# Set PYTHONPATH
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default entrypoint
ENTRYPOINT ["/bin/bash", "run.sh"]
