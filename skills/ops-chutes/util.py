import os
import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Inference API is distinct from management API for some tokens
INFERENCE_API_BASE = "https://llm.chutes.ai"
MANAGEMENT_API_BASE = "https://api.chutes.ai"

class ChutesClient:
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("CHUTES_API_TOKEN")
        if not self.token:
            raise ValueError("CHUTES_API_TOKEN not found in environment")
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "OpsChutes/1.0"
        }
        self.timeout = 30.0

    def get_chute_status(self, chute_id_or_name: str) -> Dict[str, Any]:
        """Get status of a specific chute via Management API."""
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get(f"/chutes/{chute_id_or_name}")
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                # 401/403 means token scope issue, but inference might still work
                if e.response.status_code in (401, 403):
                    return {"status": "unknown", "error": "Auth failed (Management API)", "detail": str(e)}
                raise e

    def list_chutes(self) -> List[Dict[str, Any]]:
        """List all accessible chutes via Management API."""
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get("/chutes")
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    return [] # Return empty list if auth fails, don't crash
                raise e
    
    def get_quota_usage(self, chute_id: str) -> Dict[str, Any]:
        """
        Get quota usage for a specific chute.
        """
        if not chute_id:
            raise ValueError("chute_id is required for quota usage")
        
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get(f"/users/me/quota_usage/{chute_id}")
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    return {"error": "Auth failed for quota endpoint"}
                raise e
            except Exception as e:
                return {"error": str(e)}

    def check_sanity(self, model: str = "Qwen/Qwen2.5-72B-Instruct") -> bool:
        """
        Run a real inference check.
        Management API might be 401, but Inference might allow it.
        """
        try:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "stream": False,
                "max_tokens": 5,
                "temperature": 0.1
            }
            # Use separate client for inference URL
            with httpx.Client(base_url=INFERENCE_API_BASE, headers=self.headers, timeout=self.timeout) as client:
                resp = client.post("/v1/chat/completions", json=payload)
                return resp.status_code == 200
        except Exception:
            return False

    def get_day_reset_time(self) -> datetime:
        """Get the next 7PM ET reset time (UTC-aware)."""
        eastern = ZoneInfo("America/New_York")
        now_est = datetime.now(tz=eastern)

        reset_today = now_est.replace(hour=19, minute=0, second=0, microsecond=0)

        if now_est >= reset_today:
            reset_today = reset_today + timedelta(days=1)

        return reset_today.astimezone(timezone.utc)

    def close(self):
        return
