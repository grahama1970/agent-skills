FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        git \
        libgl1 \
        libglib2.0-0 \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/comfyui

COPY requirements.txt /tmp/comfyui-requirements.txt

RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip wheel setuptools \
    && /opt/venv/bin/pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126 \
    && /opt/venv/bin/pip install -r /tmp/comfyui-requirements.txt

COPY custom_nodes/ComfyUI-WanVideoWrapper/requirements.txt /tmp/wanvideo-wrapper-requirements.txt

RUN /opt/venv/bin/pip install -r /tmp/wanvideo-wrapper-requirements.txt

ENV PATH="/opt/venv/bin:${PATH}"

EXPOSE 8188

CMD ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188"]
