"""jellyfin_client - consume-movie.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import os
import httpx
from typing import Optional, Dict, Any, List
from rich.console import Console

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=False)

console = Console()

class JellyfinClient:
    """Basic client for Jellyfin API interaction."""

    def __init__(self, base_url: str = "http://localhost:8096", api_key: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key or os.environ.get("JELLYFIN_API_KEY")
        headers = {}
        if self.api_key:
            headers["X-Emby-Token"] = self.api_key
        self.session = httpx.Client(headers=headers)

    def get_system_info(self) -> Dict[str, Any]:
        """Get public system information."""
        resp = self.session.get(f"{self.base_url}/system/info/public")
        resp.raise_for_status()
        return resp.json()

    def search_items(self, term: str, include_item_types: List[str] = ["Movie"]) -> List[Dict[str, Any]]:
        """Search for items in Jellyfin library."""
        if not self.api_key:
            console.print("[yellow]Warning: JELLYFIN_API_KEY not set. Search may be limited.[/yellow]")
            
        params = {
            "SearchTerm": term,
            "IncludeItemTypes": ",".join(include_item_types),
            "Recursive": True,
            "Fields": "Path,MediaSources"
        }
        resp = self.session.get(f"{self.base_url}/Items", params=params)
        resp.raise_for_status()
        return resp.json().get("Items", [])

    def get_item_path(self, title: str) -> Optional[str]:
        """Resolve a title to its absolute file system path."""
        items = self.search_items(title)
        if not items:
            return None
        
        # Best match - simple equality check on title
        for item in items:
            if item.get("Name").lower() == title.lower():
                return item.get("Path")
                
        # Fallback to first result
        return items[0].get("Path")

if __name__ == "__main__":
    client = JellyfinClient()
    try:
        info = client.get_system_info()
        print(f"Connected to: {info.get('ServerName')}")
        path = client.get_item_path("There Will Be Blood")
        print(f"Path for 'There Will Be Blood': {path}")
    except Exception as e:
        print(f"Error: {e}")
