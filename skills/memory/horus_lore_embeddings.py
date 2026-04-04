"""
Horus Lore Ingest - Embeddings Module
Embedding generation using graph_memory (preferred), embedding service, or Docker container.

Delegates to the canonical embedding skill at .pi/skills/embedding/embed.py
rather than importing SentenceTransformer directly.
"""
import os
import sys
import time
from pathlib import Path
from typing import Callable, List

from loguru import logger

# Make the embedding skill importable
_SKILLS_DIR = Path(__file__).resolve().parent.parent
_EMBED_DIR = str(_SKILLS_DIR / "embedding")
if _EMBED_DIR not in sys.path:
    sys.path.insert(0, _EMBED_DIR)


def get_embedder() -> Callable[[List[str]], List[List[float]]]:
    """
    Get embedding function (prefers graph_memory, falls back to service/local).

    Resolution order:
    1. graph_memory.embeddings.encode_texts (canonical, handles service→local internally)
    2. EMBEDDING_SERVICE_URL (direct HTTP to embedding skill)
    3. Embedding skill Docker service (embed_batch with auto-restart)

    Returns a function that takes a list of strings and returns a list of embedding vectors.
    """
    # Prefer graph_memory canonical embedding
    try:
        from graph_memory.embeddings import encode_texts
        logger.debug("Using graph_memory.embeddings for Horus lore")

        def embed_via_graph_memory(texts: List[str]) -> List[List[float]]:
            return encode_texts(texts, normalize=True)

        return embed_via_graph_memory
    except ImportError:
        pass

    # Fallback: direct embedding service
    service_url = os.getenv("EMBEDDING_SERVICE_URL")
    api_key = os.getenv("EMBEDDING_API_KEY")
    auth_header_name = os.getenv("EMBEDDING_AUTH_HEADER_NAME", "Authorization")

    if service_url:
        try:
            import httpx
        except ImportError:
            service_url = None  # force local fallback if httpx missing

    if service_url:
        logger.debug(f"Using embedding service at {service_url}")

        def embed_via_service(texts: List[str]) -> List[List[float]]:
            headers = {}
            if api_key:
                if auth_header_name.lower() == "authorization":
                    headers[auth_header_name] = f"Bearer {api_key}"
                else:
                    headers[auth_header_name] = api_key
            payload = {"texts": texts}

            # Retry with backoff
            for attempt in (1, 2):
                try:
                    resp = httpx.post(
                        f"{service_url}/embed/batch",
                        json=payload,
                        headers=headers,
                        timeout=60,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return data["vectors"]
                except Exception:
                    if attempt == 2:
                        break
                    time.sleep(0.5)

            # Fallback to embedding skill (Docker service with auto-restart)
            from embed import embed_batch
            logger.warning(
                "Custom embedding service HTTP call failed; falling back to "
                "embedding skill Docker service"
            )
            return embed_batch(texts)

        return embed_via_service

    # Last resort: embedding skill Docker service (no custom URL, no graph_memory)
    logger.debug("Using embedding skill Docker service for Horus lore")

    from embed import embed_batch

    def embed_via_skill(texts: List[str]) -> List[List[float]]:
        return embed_batch(texts)

    return embed_via_skill
