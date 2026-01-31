import os
import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

INFERENCE_API_BASE = "https://llm.chutes.ai"
MANAGEMENT_API_BASE = "https://api.chutes.ai"

class ChutesClient:
    def __init__(self, token: Optional[str] = None):
        # Support both naming conventions for robustness
        self.token = token or os.environ.get("CHUTES_API_TOKEN") or os.environ.get("CHUTES_API_KEY")
        if not self.token:
            raise ValueError("CHUTES_API_TOKEN or CHUTES_API_KEY not found in environment")
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "OpsChutes/1.0"
        }
        self.timeout = 30.0

    def get_global_quota(self) -> Dict[str, Any]:
        """
        Get the global subscription quota usage for the authenticated user/token.
        Endpoint: GET /users/me/quota_usage/me
        """
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                # The 'me' pseudo-ID returns the global subscription quota across all public models
                resp = client.get("/users/me/quota_usage/me")
                resp.raise_for_status()
                return resp.json() 
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    return {"error": "Auth failed (Management API)"}
                raise e
            except Exception as e:
                return {"error": str(e)}

    def get_user_info(self) -> Dict[str, Any]:
        """Get current user info, including balance."""
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get("/users/me")
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    return {"error": "Auth failed (Management API)"}
                raise e
            except Exception as e:
                return {"error": str(e)}

    def list_chutes(self) -> List[Dict[str, Any]]:
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get("/chutes")
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    return [] 
                return [] 
    
    def check_sanity(self, model: str = "Qwen/Qwen2.5-72B-Instruct") -> bool:
        """Run a real inference check."""
        try:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "stream": False,
                "max_tokens": 5,
                "temperature": 0.1
            }
            with httpx.Client(base_url=INFERENCE_API_BASE, headers=self.headers, timeout=self.timeout) as client:
                resp = client.post("/v1/chat/completions", json=payload)
                return resp.status_code == 200
        except Exception:
            return False

    def get_day_reset_time(self) -> datetime:
        """Get the NEXT 7PM ET reset time (UTC-aware)."""
        eastern = ZoneInfo("America/New_York")
        now_est = datetime.now(tz=eastern)
        reset_target = now_est.replace(hour=19, minute=0, second=0, microsecond=0)
        if now_est >= reset_target:
            reset_target = reset_target + timedelta(days=1)
        return reset_target.astimezone(timezone.utc)

    def close(self):
        return
