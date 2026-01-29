"""
Horus Lore Ingest - Embeddings Module
Embedding generation using local models or embedding service.
"""
import os
import time
from typing import Callable, List

_LOCAL_MODEL = None  # cached SentenceTransformer model


def _get_local_model():
    """Get cached local embedding model."""
    global _LOCAL_MODEL
    if _LOCAL_MODEL is None:
        from sentence_transformers import SentenceTransformer  # type: ignore
        _LOCAL_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _LOCAL_MODEL


def get_embedder() -> Callable[[List[str]], List[List[float]]]:
    """
    Get embedding function (uses embedding service if available).

    Environment variables:
    - EMBEDDING_SERVICE_URL: URL of embedding service
    - EMBEDDING_API_KEY: API key for embedding service (optional)
    - EMBEDDING_AUTH_HEADER_NAME: Header name for API key (default: Authorization)

    Returns a function that takes a list of strings and returns a list of embedding vectors.
    """
    service_url = os.getenv("EMBEDDING_SERVICE_URL")
    api_key = os.getenv("EMBEDDING_API_KEY")
    auth_header_name = os.getenv("EMBEDDING_AUTH_HEADER_NAME", "Authorization")

    if service_url:
        try:
            import requests  # type: ignore
        except ImportError:
            service_url = None  # force local fallback if requests missing

    if service_url:
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
                    resp = requests.post(
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

            # Fallback to local model if service fails
            try:
                model = _get_local_model()
                embeddings = model.encode(texts, show_progress_bar=False)
                return [vec.tolist() for vec in embeddings]
            except Exception as e:
                raise RuntimeError(f"Embedding service failed and local fallback unavailable: {e}")

        return embed_via_service

    # Local embedding (no service URL)
    try:
        model = _get_local_model()
    except Exception as e:
        raise RuntimeError(
            "Local embedding model is not available and EMBEDDING_SERVICE_URL is not set. "
            "Install 'sentence-transformers' or configure an embedding service."
        ) from e

    def embed_local(texts: List[str]) -> List[List[float]]:
        embeddings = model.encode(texts, show_progress_bar=False)
        return [e.tolist() for e in embeddings]

    return embed_local
