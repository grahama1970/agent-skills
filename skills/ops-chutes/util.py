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
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "OpsChutes/1.0"
        }
        # Use per-call clients to avoid leaking sockets
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
    
    def get_user_usage(self) -> Dict[str, Any]:
        """
        Attempt to get usage metrics. 
        """
        try:
            with httpx.Client(base_url=API_BASE, headers=self.headers, timeout=self.timeout) as client:
                resp = client.get("/invocations/exports/recent")
                if resp.status_code == 200:
                    return resp.json()
                return {"type": "unknown", "msg": "No standard usage endpoint"}
        except Exception as e:
            return {"error": str(e)}

    def check_sanity(self) -> bool:
        """API reachability check via /ping."""
        try:
            with httpx.Client(base_url=API_BASE, headers=self.headers, timeout=self.timeout) as client:
                resp = client.get("/ping")
                return resp.status_code == 200
        except Exception:
            return False

    def get_day_reset_time(self) -> datetime:
        """Return the next 7PM US/Eastern reset time as an aware UTC datetime, DST-safe."""
        eastern = ZoneInfo("America/New_York")
        now_est = datetime.now(tz=eastern)
        
        # Reset is 7PM EST (19:00)
        reset_est = now_est.replace(hour=19, minute=0, second=0, microsecond=0)
        
        if now_est >= reset_est:
             # If strictly after 19:00, reset is tomorrow
             reset_est = (reset_est + timedelta(days=1)).replace(tzinfo=eastern)
        
        return reset_est.astimezone(timezone.utc)

    def close(self):
        return
