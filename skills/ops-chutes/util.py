import os
import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

API_BASE = "https://api.chutes.ai"

class ChutesClient:
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("CHUTES_API_TOKEN")
        if not self.token:
            raise ValueError("CHUTES_API_TOKEN not found in environment")
        
        # Support both standard header formats for robustness
        # Research indicates Authorization: Bearer <key> is standard, 
        # but X-API-Key is also cited. We'll use Authorization as primary
        # and X-API-Key as fallback/redundant if needed, but typically standardizing on one is best.
        # We will use Authorization: Bearer as it's the more modern standard cited.
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "OpsChutes/1.0"
        }
        # Use per-call clients to avoid leaking sockets
        # Increased timeout for potentially slow endpoints
        self.timeout = 30.0

    def get_chute_status(self, chute_id_or_name: str) -> Dict[str, Any]:
        """Get status of a specific chute."""
        with httpx.Client(base_url=API_BASE, headers=self.headers, timeout=self.timeout) as client:
            resp = client.get(f"/chutes/{chute_id_or_name}")
            resp.raise_for_status()
            try:
                return resp.json()
            except Exception as e:
                raise RuntimeError(f"Non-JSON response for chute {chute_id_or_name}: {e}")

    def list_chutes(self) -> List[Dict[str, Any]]:
        """List all accessible chutes."""
        with httpx.Client(base_url=API_BASE, headers=self.headers, timeout=self.timeout) as client:
            resp = client.get("/chutes")
            resp.raise_for_status()
            try:
                return resp.json()
            except Exception as e:
                raise RuntimeError(f"Non-JSON response when listing chutes: {e}")
    
    def get_quota_usage(self, chute_id: str) -> Dict[str, Any]:
        """
        Get quota usage for a specific chute.
        Endpoint: GET /users/me/quota_usage/{chute_id}
        """
        if not chute_id:
            raise ValueError("chute_id is required for quota usage")
        
        with httpx.Client(base_url=API_BASE, headers=self.headers, timeout=self.timeout) as client:
            resp = client.get(f"/users/me/quota_usage/{chute_id}")
            resp.raise_for_status()
            try:
                return resp.json()
            except Exception as e:
                raise RuntimeError(f"Non-JSON response from quota endpoint: {e}")

    def check_sanity(self) -> bool:
        """API reachability check via /ping."""
        try:
            with httpx.Client(base_url=API_BASE, headers=self.headers, timeout=self.timeout) as client:
                resp = client.get("/ping")
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
