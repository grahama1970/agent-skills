import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    wait_random,
    retry_if_exception
)
from typing import Optional, Dict, Any

def is_retryable(e: Exception) -> bool:
    """Retry on network errors or 5xx server errors."""
    if isinstance(e, (httpx.RequestError, httpx.TimeoutException, httpx.RemoteProtocolError)):
        return True
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code >= 500
    return False

# Retry Configuration
# Wait 2^x * 1s, plus random jitter up to 2s
# Stop after 5 attempts
RETRY_CONFIG = dict(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60) + wait_random(0, 2),
    retry=retry_if_exception(is_retryable),
    reraise=True
)

class HttpClient:
    def __init__(self, user_agent: str = "ConsumeFeed/1.0", timeout: float = 30.0):
        self.headers = {"User-Agent": user_agent}
        self.client = httpx.Client(timeout=timeout)

    def close(self):
        """Explicitly close the underlying httpx client."""
        try:
            self.client.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    @retry(**RETRY_CONFIG)
    def fetch_text(self, url: str, etag: Optional[str] = None, last_modified: Optional[str] = None) -> tuple[int, str, Dict[str, str]]:
        """
        Fetch text with conditional GET support and retries.
        Returns: (status_code, text, headers)
        """
        headers = self.headers.copy()
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        resp = self.client.get(url, headers=headers)
        
        # We handle 304 specifically
        if resp.status_code == 304:
            return 304, "", dict(resp.headers)
            
        resp.raise_for_status()
        return resp.status_code, resp.text, dict(resp.headers)

    @retry(**RETRY_CONFIG)
    def fetch_json(self, url: str, headers: Dict[str, str] = {}) -> Any:
        full_headers = self.headers.copy()
        full_headers.update(headers)
        resp = self.client.get(url, headers=full_headers)
        resp.raise_for_status()
        return resp.json()
