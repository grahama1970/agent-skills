import sys
import os
import time
from rich.console import Console

# Add current dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sources.rss import RSSSource
from feed_storage import FeedStorage
from feed_config import FeedSource, SourceType
# from sanity.mock_server import start_mock_server, stop_mock_server

console = Console()

def test_rss_304_state():
    console.print("[bold blue]Testing RSS 304 State Logic...[/bold blue]")
    
    # 1. Setup mock server to return 304
    # We need a custom handler for 304 or just use the existing mock server with a tweak
    # Let's just mock the HttpClient in this test for simplicity, 
    # OR better, use the mock server properly.
    
    # Actually, let's just mock the client to avoid port conflicts and complex setup
    from unittest.mock import MagicMock, patch
    
    storage = FeedStorage()
    source_cfg = FeedSource(
        key="test_304",
        type=SourceType.RSS,
        rss_url="http://mock.test/feed.xml"
    )
    source = RSSSource(source_cfg, storage)
    
    # Initial state
    storage.save_state("test_304", {
        "etag": "v1",
        "last_fetch_at": 1000.0,
        "last_success_at": 1000.0
    })
    
    console.print("Initial state: last_fetch=1000, last_success=1000")
    
    # Mock HttpClient in base.py since RSSSource uses make_http_client which calls it
    with patch("sources.base.HttpClient") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.fetch_text.return_value = (304, "", {"ETag": "v1"})
        
        # Run fetch
        source.fetch(dry_run=False)
        
    # Check updated state
    new_state = storage.get_state("test_304")
    console.print(f"New state: last_fetch={new_state.get('last_fetch_at')}, last_success={new_state.get('last_success_at')}")
    
    # Assertions
    assert new_state["last_fetch_at"] > 1000.0, "last_fetch_at should have updated"
    assert new_state["last_success_at"] == 1000.0, "last_success_at should NOT have updated on 304"
    
    console.print("[green]✅ RSS 304 state logic verified! last_fetch_at updated, last_success_at preserved.[/green]")

if __name__ == "__main__":
    try:
        test_rss_304_state()
    except Exception as e:
        console.print(f"[red]❌ Test failed: {e}[/red]")
        sys.exit(1)
