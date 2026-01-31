import os
import httpx
import csv
from io import StringIO
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
            "Accept": "application/json", # Default accept
            "User-Agent": "OpsChutes/1.0"
        }
        self.timeout = 30.0

    def get_invocation_count(self) -> int:
        """
        Count invocations since the last daily reset (7PM EST).
        Uses: GET /invocations/exports/recent (CSV)
        """
        reset_time = self.get_day_reset_time() - timedelta(days=1)
        
        # Request CSV explicitly
        headers = self.headers.copy()
        headers["Accept"] = "text/csv"
        
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=headers, timeout=self.timeout) as client:
            try:
                resp = client.get("/invocations/exports/recent")
                resp.raise_for_status()
                
                # Parse CSV
                csv_text = resp.text
                reader = csv.DictReader(StringIO(csv_text))
                
                count = 0
                for row in reader:
                    # 'started_at' format: 2026-01-31T15:54:55.123456Z (roughly)
                    started_at_str = row.get("started_at")
                    if not started_at_str:
                        continue
                    try:
                        # Handle potential fractional seconds or lack thereof
                        # ISO 8601 parsing
                        started_at = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                        
                        if started_at >= reset_time:
                            count += 1
                    except ValueError:
                        continue # Skip malformed dates
                        
                return count
            except httpx.HTTPStatusError as e:
                # If auth fails or 404, we can't count
                if e.response.status_code in (401, 403):
                    raise RuntimeError(f"Auth failed fetching invocations: {e}")
                raise e
            except Exception as e:
                 raise RuntimeError(f"Failed to parse invocations: {e}")

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
                    return [] # Return empty list if auth fails
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
