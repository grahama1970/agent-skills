#!/usr/bin/env python3
"""
Embedding Service - Standalone FastAPI server for semantic search embeddings.

Usage:
    python embed.py serve                    # Start HTTP server (runs forever)
    python embed.py embed --text "query"     # Embed single text
    python embed.py embed-batch --file f.txt # Embed multiple texts (one per line)
    python embed.py info                     # Show configuration
"""

import argparse
import json
import os
import signal
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

# Lazy imports for heavy deps
_model = None
_model_name = None
_device = None


def get_config():
    """Get configuration from environment."""
    return {
        "model": os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        "device": os.environ.get("EMBEDDING_DEVICE", "auto"),
        "port": int(os.environ.get("EMBEDDING_PORT", "8602")),
        "host": os.environ.get("EMBEDDING_HOST", "0.0.0.0"),
        "service_url": os.environ.get("EMBEDDING_SERVICE_URL", "http://127.0.0.1:8602"),
    }


def load_model():
    """Load sentence-transformers model (lazy, cached)."""
    global _model, _model_name, _device
    
    if _model is not None:
        return _model
    
    config = get_config()
    model_name = config["model"]
    device = config["device"]
    
    print(f"[embedding] Loading model: {model_name}...", file=sys.stderr)
    start = time.time()
    
    try:
        from sentence_transformers import SentenceTransformer
        
        # Handle device selection
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
    
    except Exception as e:
        print(f"[embedding] ERROR loading model: {e}", file=sys.stderr)
        raise


def embed_text(text: str) -> list[float]:
    """Embed a single text string."""
    model = load_model()
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts."""
    model = load_model()
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=len(texts) > 10)
    return embeddings.tolist()


def get_dimensions() -> int:
    """Get embedding dimensions for current model."""
    model = load_model()
    return model.get_sentence_embedding_dimension()


def try_service_embed(text: str) -> Optional[list[float]]:
    """Try to use running service for embedding."""
    config = get_config()
    service_url = config["service_url"]
    
    try:
        import httpx
        resp = httpx.post(
            f"{service_url}/embed",
            json={"text": text},
            timeout=5.0
        )
        if resp.status_code == 200:
            return resp.json()["vector"]
    except Exception:
        pass
    
    return None


def try_service_embed_batch(texts: list[str]) -> Optional[list[list[float]]]:
    """Try to use running service for batch embedding."""
    config = get_config()
    service_url = config["service_url"]
    
    try:
        import httpx
        resp = httpx.post(
            f"{service_url}/embed/batch",
            json={"texts": texts},
            timeout=60.0  # Longer timeout for batch
        )
        if resp.status_code == 200:
            return resp.json()["vectors"]
    except Exception:
        pass
    
    return None


# ============================================================================
# CLI Commands
# ============================================================================

def cmd_serve(args):
    """Start FastAPI server (runs forever until Ctrl+C)."""
    import uvicorn
    from fastapi import FastAPI
    from pydantic import BaseModel
    
    @asynccontextmanager
    async def lifespan(app):
        """Modern FastAPI lifespan handler."""
        # Startup: pre-load model
        load_model()
        config = get_config()
        print(f"[embedding] Service ready on http://127.0.0.1:{config['port']}", file=sys.stderr)
        print(f"[embedding] Model: {_model_name}, Device: {_device}", file=sys.stderr)
        print(f"[embedding] Press Ctrl+C to stop", file=sys.stderr)
        yield
        # Shutdown
        print("[embedding] Shutting down...", file=sys.stderr)
    
    app = FastAPI(title="Embedding Service", version="1.0.0", lifespan=lifespan)
    
    class EmbedRequest(BaseModel):
        text: str
    
    class EmbedBatchRequest(BaseModel):
        texts: list[str]
    
    @app.post("/embed")
    async def embed_endpoint(req: EmbedRequest):
        vector = embed_text(req.text)
        return {
            "vector": vector,
            "model": _model_name,
            "dimensions": len(vector)
        }
    
    @app.post("/embed/batch")
    async def embed_batch_endpoint(req: EmbedBatchRequest):
        vectors = embed_batch(req.texts)
        return {
            "vectors": vectors,
            "model": _model_name,
            "count": len(vectors),
            "dimensions": len(vectors[0]) if vectors else 0
        }
    
    @app.get("/info")
    async def info_endpoint():
        config = get_config()
        return {
            "model": _model_name,
            "device": _device,
            "dimensions": get_dimensions(),
            "status": "ready"
        }
    
    @app.get("/health")
    async def health():
        return {"status": "ok"}
    
    @app.post("/shutdown")
    async def shutdown():
        """Gracefully shutdown the service."""
        print("[embedding] Shutdown requested via API", file=sys.stderr)
        import asyncio
        asyncio.get_event_loop().call_later(0.5, lambda: os._exit(0))
        return {"status": "shutting_down"}
    
    @app.post("/reload")
    async def reload():
        """Reload the embedding model (useful after changing EMBEDDING_MODEL env)."""
        global _model, _model_name, _device
        print("[embedding] Reload requested via API", file=sys.stderr)
        _model = None  # Clear cached model
        _model_name = None
        _device = None
        load_model()  # Reload
        return {"status": "reloaded", "model": _model_name, "device": _device}
    
    config = get_config()
    
    # Handle graceful shutdown
    def handle_signal(signum, frame):
        print("\n[embedding] Received shutdown signal", file=sys.stderr)
        sys.exit(0)
    
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    uvicorn.run(app, host=config["host"], port=config["port"], log_level="info")


def cmd_embed(args):
    """Embed text via CLI."""
    text = args.text
    
    if args.file:
        with open(args.file, "r") as f:
            text = f.read()
    
    if not text:
        print("Error: --text or --file required", file=sys.stderr)
        sys.exit(1)
    
    # Try service first (if running)
    if not args.local:
        vector = try_service_embed(text)
        if vector:
            result = {
                "vector": vector,
                "dimensions": len(vector),
                "source": "service"
            }
            print(json.dumps(result, indent=2) if args.pretty else json.dumps(result))
            return
    
    # Fall back to local embedding
    vector = embed_text(text)
    result = {
        "vector": vector,
        "model": _model_name,
        "dimensions": len(vector),
        "source": "local"
    }
    print(json.dumps(result, indent=2) if args.pretty else json.dumps(result))


def cmd_embed_batch(args):
    """Embed multiple texts via CLI (batch mode)."""
    texts = []
    
    if args.file:
        with open(args.file, "r") as f:
            texts = [line.strip() for line in f if line.strip()]
    elif args.texts:
        texts = args.texts
    
    if not texts:
        print("Error: --file or --texts required", file=sys.stderr)
        sys.exit(1)
    
    print(f"[embedding] Embedding {len(texts)} texts...", file=sys.stderr)
    
    # Try service first
    if not args.local:
        vectors = try_service_embed_batch(texts)
        if vectors:
            result = {
                "vectors": vectors,
                "count": len(vectors),
                "dimensions": len(vectors[0]) if vectors else 0,
                "source": "service"
            }
            print(json.dumps(result, indent=2) if args.pretty else json.dumps(result))
            return
    
    # Fall back to local
    vectors = embed_batch(texts)
    result = {
        "vectors": vectors,
        "model": _model_name,
        "count": len(vectors),
        "dimensions": len(vectors[0]) if vectors else 0,
        "source": "local"
    }
    print(json.dumps(result, indent=2) if args.pretty else json.dumps(result))


def cmd_info(args):
    """Show configuration and status."""
    config = get_config()
    
    # Check if service is running
    service_status = "not running"
    try:
        import httpx
        resp = httpx.get(f"{config['service_url']}/health", timeout=2.0)
        if resp.status_code == 200:
            service_status = "running"
    except Exception:
        pass
    
    info = {
        "model": config["model"],
        "device": config["device"],
        "port": config["port"],
        "service_url": config["service_url"],
        "service_status": service_status
    }
    
    print(json.dumps(info, indent=2))


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Embedding Service")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # serve
    serve_parser = subparsers.add_parser("serve", help="Start embedding server (runs forever)")
    serve_parser.set_defaults(func=cmd_serve)
    
    # embed
    embed_parser = subparsers.add_parser("embed", help="Embed single text")
    embed_parser.add_argument("--text", "-t", help="Text to embed")
    embed_parser.add_argument("--file", "-f", help="File to embed (entire content)")
    embed_parser.add_argument("--local", "-l", action="store_true", help="Force local embedding (don't use service)")
    embed_parser.add_argument("--pretty", "-p", action="store_true", help="Pretty print JSON")
    embed_parser.set_defaults(func=cmd_embed)
    
    # embed-batch
    batch_parser = subparsers.add_parser("embed-batch", help="Embed multiple texts")
    batch_parser.add_argument("--file", "-f", help="File with texts (one per line)")
    batch_parser.add_argument("--texts", "-t", nargs="+", help="Texts to embed")
    batch_parser.add_argument("--local", "-l", action="store_true", help="Force local embedding")
    batch_parser.add_argument("--pretty", "-p", action="store_true", help="Pretty print JSON")
    batch_parser.set_defaults(func=cmd_embed_batch)
    
    # info
    info_parser = subparsers.add_parser("info", help="Show configuration")
    info_parser.set_defaults(func=cmd_info)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
