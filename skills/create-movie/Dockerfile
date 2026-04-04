# Horus Movie Sandbox
# Docker-isolated environment for building custom movie tools
#
# Security: Non-root user, limited capabilities

FROM python:3.11-slim

LABEL maintainer="Horus"
LABEL description="Sandbox for movie tool development"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

# Python packages for video/image processing
RUN pip install --no-cache-dir \
    pillow>=10.0.0 \
    numpy>=1.24.0 \
    opencv-python-headless>=4.8.0 \
    moviepy>=1.0.3 \
    imageio>=2.31.0 \
    imageio-ffmpeg>=0.4.8

# Create non-root user for security
RUN useradd -m -s /bin/bash horus && \
    mkdir -p /workspace && \
    chown -R horus:horus /workspace

USER horus
WORKDIR /workspace

# Default command
CMD ["python", "--version"]
