"""Query engine for SFX search."""

from typing import Optional
from .memory_bridge import SFXMemoryBridge


class SFXQueryEngine:
    """High-level interface for querying SFX catalog."""
    
    def __init__(self, scope: str = "horus_lore"):
        """Initialize query engine.
        
        Args:
            scope: Memory scope for queries (default: horus_lore)
        """
        self.scope = scope
        self.bridge = SFXMemoryBridge()
    
    def search(
        self, 
        query: str, 
        k: int = 5,
        categories: Optional[list[str]] = None,
        duration_range: Optional[tuple[float, float]] = None
    ) -> list[dict]:
        """Search for SFX files matching query.
        
        Args:
            query: Search query string
            k: Number of results to return
            categories: Optional list of categories to filter by
            duration_range: Optional (min, max) duration in seconds
            
        Returns:
            List of matching SFX entries
        """
        return self.bridge.search_sfx(
            query=query,
            categories=categories,
            duration_range=duration_range,
            k=k
        )
