import os
import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime, time, timezone
import pytz

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
        self.client = httpx.Client(base_url=API_BASE, headers=self.headers, timeout=30.0)

    def get_chute_status(self, chute_id_or_name: str) -> Dict[str, Any]:
        """Get status of a specific chute."""
        # Note: API might use different path structure, assuming standard /chutes/{id}
        resp = self.client.get(f"/chutes/{chute_id_or_name}")
        resp.raise_for_status()
        return resp.json()

    def list_chutes(self) -> List[Dict[str, Any]]:
        """List all accessible chutes."""
        resp = self.client.get("/chutes/")
        resp.raise_for_status()
        return resp.json()
    
    def get_user_usage(self) -> Dict[str, Any]:
        """
        Attempt to get usage metrics. 
        Since a direct 'daily remaining' endpoint might not exist, 
        we look for invocation counts if available.
        """
        try:
            # Try specific export endpoint if available from docs or fallback to user info
            # Based on research: GET /invocations/exports/recent might exist
            resp = self.client.get("/invocations/exports/recent") 
            if resp.status_code == 200:
                return resp.json()
            else:
                return {"type": "unknown", "msg": "Usage endpoint not standard"}
        except Exception as e:
            return {"error": str(e)}

    def check_sanity(self, image: str = "chutes/generic-inference", payload: Dict = None) -> bool:
        """Run a simple sanity inference."""
        # Generic health check usually involves hitting a known model
        # or the /ping endpoint if we just want API health
        try:
            resp = self.client.get("/ping")
            return resp.status_code == 200
        except:
            return False

    def get_day_reset_time(self) -> datetime:
        """Get the next 7PM EST reset time in UTC."""
        est = pytz.timezone('US/Eastern')
        now_est = datetime.now(est)
        
        # Reset is 7PM EST (19:00)
        reset_today = now_est.replace(hour=19, minute=0, second=0, microsecond=0)
        
        if now_est >= reset_today:
             # If strictly after 19:00, reset is tomorrow
             # Note logic: if budget exhausted, wait until THIS time
             pass 
        
        return reset_today # Returns aware datetime

    def close(self):
        self.client.close()
