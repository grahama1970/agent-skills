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

    def get_quota(self, chute_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get quota usage for a specific chute or global usage if chute_id is None.
        Endpoint: GET /users/me/quota_usage/{chute_id|me}
        """
        target = chute_id if chute_id else "me"
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get(f"/users/me/quota_usage/{target}")
                resp.raise_for_status()
                data = resp.json()
                
                # Strict Validation
                if "used" not in data or "quota" not in data:
                    raise RuntimeError(f"API response missing 'used' or 'quota' fields for {target}: {data}")
                
                return data
            except httpx.HTTPStatusError as e:
                msg = f"Quota check failed for {target}: {e.response.status_code} {e.response.text}"
                raise RuntimeError(msg)
            except Exception as e:
                raise RuntimeError(f"Error fetching quota for {target}: {e}")

    def get_user_info(self) -> Dict[str, Any]:
        """
        Get current user info, including balance.
        Strictly validates the presence of 'balance'.
        """
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get("/users/me")
                resp.raise_for_status()
                data = resp.json()
                
                if "balance" not in data:
                    raise RuntimeError(f"API response missing 'balance' field: {data}")
                
                return data
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"User info failed: {e.response.status_code} {e.response.text}")
            except Exception as e:
                raise RuntimeError(f"Error fetching user info: {e}")

    def list_chutes(self) -> List[Dict[str, Any]]:
        """
        List all accessible chutes.
        No longer silently swallows auth errors.
        """
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get("/chutes")
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"Failed to list chutes: {e.response.status_code} {e.response.text}")
            except Exception as e:
                raise RuntimeError(f"Error listing chutes: {e}")

    def list_models(self) -> List[Dict[str, Any]]:
        """
        List all available models via the Inference API.
        """
        with httpx.Client(base_url=INFERENCE_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get("/v1/models")
                resp.raise_for_status()
                data = resp.json()
                return data.get("data", [])
            except Exception as e:
                raise RuntimeError(f"Failed to list models: {e}")
    
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
