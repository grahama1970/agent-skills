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

    def get_daily_usage(self) -> int:
        """
        Calculate daily usage by summing hourly buckets since the last 7PM EST reset.
        Endpoint: GET /users/me/usage
        """
        # Determine the cutoff time (Last Reset)
        # Reset is 7PM EST (19:00 America/New_York)
        eastern = ZoneInfo("America/New_York")
        now_est = datetime.now(tz=eastern)
        
        # If currently past 19:00, reset was today at 19:00. 
        # But usually we engage usage FOR the day starting yesterday 19:00.
        # Wait, if now is 11AM, the "Day" started yesterday at 7PM.
        # If now is 8PM, the "Day" started today at 7PM.
        
        if now_est.hour >= 19:
            last_reset = now_est.replace(hour=19, minute=0, second=0, microsecond=0)
        else:
            last_reset = (now_est - timedelta(days=1)).replace(hour=19, minute=0, second=0, microsecond=0)
            
        last_reset_utc = last_reset.astimezone(timezone.utc)

        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                # Fetch usage
                resp = client.get("/users/me/usage")
                resp.raise_for_status()
                data = resp.json()
                
                total_count = 0
                for item in data.get("items", []):
                    # bucket format: "2026-01-31T15:00:00" (Implicit UTC)
                    bucket_str = item.get("bucket")
                    if not bucket_str:
                        continue
                    try:
                        # Parse as naive then set to UTC
                        bucket_dt = datetime.fromisoformat(bucket_str).replace(tzinfo=timezone.utc)
                        
                        if bucket_dt >= last_reset_utc:
                            total_count += item.get("count", 0)
                    except ValueError:
                        continue
                        
                return total_count

            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    raise RuntimeError(f"Auth failed fetching usage: {e}")
                raise e
            except Exception as e:
                 raise RuntimeError(f"Failed to fetch usage: {e}")

    def get_user_info(self) -> Dict[str, Any]:
        """
        Get current user info, including balance.
        Endpoint: GET /users/me
        """
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
        """List all accessible chutes via Management API."""
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get("/chutes")
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    return [] 
                return [] 
    
    def get_quota_usage(self, chute_id: str) -> Dict[str, Any]:
        """Get quota usage for a specific chute."""
        if not chute_id:
            raise ValueError("chute_id is required for quota usage")
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get(f"/users/me/quota_usage/{chute_id}")
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (404, 401, 403):
                    return {"error": str(e)}
                return {"error": str(e)}
            except Exception as e:
                return {"error": str(e)}

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
