#!/usr/bin/env python3
"""
Embedding Service - Docker-backed semantic search embeddings.

All callers go through the Docker container (memory-embedding) on port 8602.
If the service is down, we restart the container and retry once.
If that fails, we raise loudly — no silent local fallback.

Usage:
    python embed.py serve                    # Start HTTP server (inside container)
    python embed.py embed --text "query"     # Embed single text (via service)
    python embed.py embed-batch --file f.txt # Embed multiple texts (via service)
    python embed.py info                     # Show configuration and status
"""

import json
import os
import signal
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

import typer
from dotenv import load_dotenv, find_dotenv
from loguru import logger
load_dotenv(find_dotenv(usecwd=True), override=False)

# Server-side state (only used by `serve` command inside the container)
_model = None
_model_name = None
_device = None

CONTAINER_NAME = os.environ.get("EMBEDDING_CONTAINER", "memory-embedding")
CONTAINER_NAME_MM = os.environ.get("EMBEDDING_CONTAINER_MM", "embry-embedding-mm")


def get_config():
    """Get configuration from environment."""
    return {
        "model": os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        "device": os.environ.get("EMBEDDING_DEVICE", "auto"),
        "port": int(os.environ.get("EMBEDDING_PORT", "8602")),
        "host": os.environ.get("EMBEDDING_HOST", "0.0.0.0"),
        "service_url": os.environ.get("EMBEDDING_SERVICE_URL", "http://127.0.0.1:8602"),
        # Multimodal backend (SGLang + Qwen3-VL-Embedding-2B)
        "multimodal_url": os.environ.get("EMBEDDING_MULTIMODAL_URL", "http://127.0.0.1:8603"),
        "multimodal_dimensions": int(os.environ.get("EMBEDDING_MULTIMODAL_DIMENSIONS", "2048")),
    }


def _restart_container_by_name(container_name: str, health_url: str, wait_seconds: int = 10):
    """Restart a Docker container and wait for health. Returns True if successful."""
    print(f"[embedding] Service down — restarting Docker container '{container_name}'...", file=sys.stderr)
    try:
        result = subprocess.run(
            ["docker", "restart", container_name],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print(f"[embedding] docker restart failed: {result.stderr.strip()}", file=sys.stderr)
            return False
        for attempt in range(wait_seconds):
            time.sleep(1)
            try:
                import httpx
                resp = httpx.get(health_url, timeout=2.0)
                if resp.status_code == 200:
                    print(f"[embedding] Container restarted and healthy after {attempt + 1}s", file=sys.stderr)
                    return True
            except Exception:
                continue
        print(f"[embedding] Container restarted but service not healthy after {wait_seconds}s", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[embedding] Failed to restart container: {e}", file=sys.stderr)
        return False


def _restart_container():
    """Restart the text embedding container."""
    return _restart_container_by_name(CONTAINER_NAME, f"{get_config()['service_url']}/health")


def _restart_container_mm():
    """Restart the multimodal embedding container (SGLang takes longer to load)."""
    return _restart_container_by_name(CONTAINER_NAME_MM, f"{get_config()['multimodal_url']}/health", wait_seconds=60)


def _call_service(endpoint: str, payload: dict, timeout: float = 10.0) -> dict:
    """Call the embedding service. Restart container on failure. Raise on total failure."""
    import httpx
    config = get_config()
    url = f"{config['service_url']}{endpoint}"

    # First attempt
    try:
        resp = httpx.post(url, json=payload, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
        raise ConnectionError(f"Service returned {resp.status_code}: {resp.text[:200]}")
    except Exception as first_err:
        # Restart and retry once
        if _restart_container():
            try:
                resp = httpx.post(url, json=payload, timeout=timeout)
                if resp.status_code == 200:
                    return resp.json()
                raise ConnectionError(f"Service returned {resp.status_code} after restart")
            except Exception as retry_err:
                raise RuntimeError(
                    f"Embedding service failed after container restart: {retry_err}\n"
                    f"Container: {CONTAINER_NAME} | URL: {url}\n"
                    f"Run: docker logs {CONTAINER_NAME}"
                ) from retry_err
        else:
            raise RuntimeError(
                f"Embedding service unreachable and container restart failed.\n"
                f"Original error: {first_err}\n"
                f"Container: {CONTAINER_NAME} | URL: {url}\n"
                f"Run: docker ps -a | grep {CONTAINER_NAME}"
            ) from first_err


# ============================================================================
# Multimodal service call (vLLM on :8603)
#   Text:  /v1/embeddings → single pooled vector per input
#   Image: /pooling        → per-token vectors, mean-pooled client-side
# ============================================================================

def _mean_pool_and_normalize(token_vectors: list[list[float]]) -> list[float]:
    """Mean-pool per-token vectors and L2-normalize."""
    import numpy as np
    arr = np.array(token_vectors, dtype=np.float32)
    pooled = arr.mean(axis=0)
    norm = np.linalg.norm(pooled)
    return (pooled / norm).tolist() if norm > 0 else pooled.tolist()


def _call_multimodal_text(texts: list[str], timeout: float = 60.0) -> list[list[float]]:
    """Embed texts via vLLM /v1/embeddings (returns pooled vectors directly)."""
    import httpx
    config = get_config()
    url = f"{config['multimodal_url']}/v1/embeddings"

    payload = {
        "model": "Qwen/Qwen3-VL-Embedding-2B",
        "input": texts,
        "encoding_format": "float",
    }

    try:
        resp = httpx.post(url, json=payload, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
        raise ConnectionError(f"vLLM returned {resp.status_code}: {resp.text[:200]}")
    except Exception as first_err:
        if _restart_container_mm():
            try:
                resp = httpx.post(url, json=payload, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
                raise ConnectionError(f"vLLM returned {resp.status_code} after restart")
            except Exception as retry_err:
                raise RuntimeError(
                    f"Multimodal text embedding failed after container restart: {retry_err}\n"
                    f"Container: {CONTAINER_NAME_MM} | URL: {url}\n"
                    f"Run: docker logs {CONTAINER_NAME_MM}"
                ) from retry_err
        else:
            raise RuntimeError(
                f"Multimodal embedding unreachable and container restart failed.\n"
                f"Original error: {first_err}\n"
                f"Container: {CONTAINER_NAME_MM} | URL: {url}"
            ) from first_err


def _call_multimodal_image(image_uri: str, timeout: float = 60.0) -> list[float]:
    """Embed a single image via vLLM /pooling endpoint, mean-pool the per-token output.

    image_uri: data:image/png;base64,... or a file:// URI.
    """
    import httpx
    config = get_config()
    url = f"{config['multimodal_url']}/pooling"

    payload = {
        "model": "Qwen/Qwen3-VL-Embedding-2B",
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": image_uri}},
        ]}],
    }

    try:
        resp = httpx.post(url, json=payload, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            token_vectors = data["data"][0]["data"]
            return _mean_pool_and_normalize(token_vectors)
        raise ConnectionError(f"vLLM pooling returned {resp.status_code}: {resp.text[:200]}")
    except Exception as first_err:
        if _restart_container_mm():
            try:
                resp = httpx.post(url, json=payload, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    token_vectors = data["data"][0]["data"]
                    return _mean_pool_and_normalize(token_vectors)
                raise ConnectionError(f"vLLM pooling returned {resp.status_code} after restart")
            except Exception as retry_err:
                raise RuntimeError(
                    f"Multimodal image embedding failed after container restart: {retry_err}\n"
                    f"Container: {CONTAINER_NAME_MM} | URL: {url}\n"
                    f"Run: docker logs {CONTAINER_NAME_MM}"
                ) from retry_err
        else:
            raise RuntimeError(
                f"Multimodal embedding unreachable and container restart failed.\n"
                f"Original error: {first_err}\n"
                f"Container: {CONTAINER_NAME_MM} | URL: {url}"
            ) from first_err


# ============================================================================
# Public API — all callers use these
# ============================================================================

def embed_text(text: str) -> list[float]:
    """Embed a single text string via the Docker service."""
    data = _call_service("/embed", {"text": text})
    return data["embedding"]


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts via the Docker service."""
    data = _call_service("/embed/batch", {"texts": texts}, timeout=60.0)
    return data["vectors"]


def embed_text_multimodal(text: str) -> list[float]:
    """Embed a single text via the multimodal vLLM service (2048 dims)."""
    vectors = _call_multimodal_text([text])
    return vectors[0]


def embed_batch_multimodal(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts via the multimodal vLLM service (2048 dims)."""
    return _call_multimodal_text(texts)


def embed_image_multimodal(image_uri: str) -> list[float]:
    """Embed an image via the multimodal vLLM service (2048 dims).

    image_uri: data:image/png;base64,... or file:///path/to/image.png
    """
    return _call_multimodal_image(image_uri)


# ============================================================================
# Server internals (only used by `serve` command inside the container)
# ============================================================================

def _load_model():
    """Load sentence-transformers model (server-side only, lazy, cached)."""
    global _model, _model_name, _device

    if _model is not None:
        return _model

    config = get_config()
    model_name = config["model"]
    device = config["device"]

    print(f"[embedding] Loading model: {model_name}...", file=sys.stderr)
    start = time.time()

    from sentence_transformers import SentenceTransformer

    if device == "auto":
        import torch
        if torch.cuda.is_available():
            device = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

    _model = SentenceTransformer(model_name, device=device)
    _model_name = model_name
    _device = device

    elapsed = time.time() - start
    print(f"[embedding] Model loaded in {elapsed:.1f}s (device: {device})", file=sys.stderr)
    return _model


def _embed_text_local(text: str) -> list[float]:
    """Server-side local embedding."""
    model = _load_model()
    return model.encode(text, convert_to_numpy=True).tolist()


def _embed_batch_local(texts: list[str]) -> list[list[float]]:
    """Server-side local embedding."""
    model = _load_model()
    return model.encode(texts, convert_to_numpy=True, show_progress_bar=len(texts) > 10).tolist()


# ============================================================================
# CLI Commands
# ============================================================================

app = typer.Typer(help="Embedding Service")


@app.command()
def serve():
    """Start FastAPI server (runs forever until Ctrl+C). Used inside Docker container."""
    import uvicorn
    from fastapi import FastAPI
    from pydantic import BaseModel

    @asynccontextmanager
    async def lifespan(app):
        _load_model()
        config = get_config()
        print(f"[embedding] Service ready on http://127.0.0.1:{config['port']}", file=sys.stderr)
        print(f"[embedding] Model: {_model_name}, Device: {_device}", file=sys.stderr)
        yield
        print("[embedding] Shutting down...", file=sys.stderr)

    api = FastAPI(title="Embedding Service", version="2.0.0", lifespan=lifespan)

    class EmbedRequest(BaseModel):
        text: str

    class EmbedBatchRequest(BaseModel):
        texts: list[str]

    @api.post("/embed")
    async def embed_endpoint(req: EmbedRequest):
        vector = _embed_text_local(req.text)
        return {"embedding": vector, "model": _model_name, "dimensions": len(vector)}

    @api.post("/embed/batch")
    async def embed_batch_endpoint(req: EmbedBatchRequest):
        vectors = _embed_batch_local(req.texts)
        return {
            "vectors": vectors, "model": _model_name,
            "count": len(vectors),
            "dimensions": len(vectors[0]) if vectors else 0,
        }

    @api.get("/info")
    async def info_endpoint():
        return {
            "model": _model_name, "device": _device,
            "dimensions": _load_model().get_sentence_embedding_dimension(),
            "status": "ready",
        }

    @api.get("/health")
    async def health():
        return {"status": "ok"}

    @api.post("/shutdown")
    async def shutdown():
        print("[embedding] Shutdown requested via API", file=sys.stderr)
        import asyncio
        asyncio.get_event_loop().call_later(0.5, lambda: os._exit(0))
        return {"status": "shutting_down"}

    @api.post("/reload")
    async def reload():
        global _model, _model_name, _device
        _model = None
        _model_name = None
        _device = None
        _load_model()
        return {"status": "reloaded", "model": _model_name, "device": _device}

    config = get_config()

    def handle_signal(signum, frame):
        print("\n[embedding] Received shutdown signal", file=sys.stderr)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    uvicorn.run(api, host=config["host"], port=config["port"], log_level="info")


@app.command("embed")
def cmd_embed(
    text: Optional[str] = typer.Option(None, "-t", "--text", help="Text to embed"),
    file: Optional[str] = typer.Option(None, "-f", "--file", help="File to embed (entire content)"),
    multimodal: bool = typer.Option(False, "-m", "--multimodal", help="Use multimodal backend (SGLang, 2048d)"),
    pretty: bool = typer.Option(False, "-p", "--pretty", help="Pretty print JSON"),
):
    """Embed single text via Docker service."""
    _text = text
    if file:
        with open(file, "r") as f:
            _text = f.read()
    if not _text:
        print("Error: --text or --file required", file=sys.stderr)
        sys.exit(1)

    vector = embed_text_multimodal(_text) if multimodal else embed_text(_text)
    result = {"embedding": vector, "dimensions": len(vector)}
    print(json.dumps(result, indent=2) if pretty else json.dumps(result))


@app.command("embed-batch")
def cmd_embed_batch(
    file: Optional[str] = typer.Option(None, "-f", "--file", help="File with texts (one per line)"),
    texts: Optional[list[str]] = typer.Option(None, "-t", "--texts", help="Texts to embed"),
    multimodal: bool = typer.Option(False, "-m", "--multimodal", help="Use multimodal backend (SGLang, 2048d)"),
    pretty: bool = typer.Option(False, "-p", "--pretty", help="Pretty print JSON"),
):
    """Embed multiple texts via Docker service."""
    _texts = []
    if file:
        with open(file, "r") as f:
            _texts = [line.strip() for line in f if line.strip()]
    elif texts:
        _texts = list(texts)
    if not _texts:
        print("Error: --file or --texts required", file=sys.stderr)
        sys.exit(1)

    print(f"[embedding] Embedding {len(_texts)} texts via {'multimodal' if multimodal else 'text'} backend...", file=sys.stderr)
    vectors = embed_batch_multimodal(_texts) if multimodal else embed_batch(_texts)
    result = {
        "vectors": vectors, "count": len(vectors),
        "dimensions": len(vectors[0]) if vectors else 0,
    }
    print(json.dumps(result, indent=2) if pretty else json.dumps(result))


@app.command()
def info():
    """Show configuration and service status for all backends."""
    import httpx
    config = get_config()

    # Text backend
    text_status = "not running"
    try:
        resp = httpx.get(f"{config['service_url']}/health", timeout=2.0)
        if resp.status_code == 200:
            text_status = "running"
    except Exception as e:
        logger.debug("Text backend health check failed: {}", e)

    # Multimodal backend
    mm_status = "not running"
    try:
        resp = httpx.get(f"{config['multimodal_url']}/health", timeout=2.0)
        if resp.status_code == 200:
            mm_status = "running"
    except Exception as e:
        logger.debug("Multimodal backend health check failed: {}", e)

    print(json.dumps({
        "text_backend": {
            "model": config["model"],
            "device": config["device"],
            "port": config["port"],
            "service_url": config["service_url"],
            "status": text_status,
            "container": CONTAINER_NAME,
            "dimensions": 384,
        },
        "multimodal_backend": {
            "model": "Qwen/Qwen3-VL-Embedding-2B",
            "service_url": config["multimodal_url"],
            "status": mm_status,
            "container": CONTAINER_NAME_MM,
            "dimensions": config["multimodal_dimensions"],
        },
    }, indent=2))


if __name__ == "__main__":
    app()
