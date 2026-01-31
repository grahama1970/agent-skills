import sys
import os
import time
from typing import Dict, Any, List, Optional
from rich.console import Console

# Add memory skill to path to import connection logic
MEMORY_SKILL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../memory"))
if MEMORY_SKILL_PATH not in sys.path:
    sys.path.append(MEMORY_SKILL_PATH)

try:
    from db import get_db
except ImportError:
    # Hard fail to avoid bespoke wrappers; this skill must reuse Memory's connection.
    raise ImportError("Memory skill connection 'get_db' not available. Ensure Memory skill is installed and on PYTHONPATH.")

console = Console()

class FeedStorage:
    def __init__(self, url: str = None, db_name: str = "feed_db", auth: dict = None):
        # We exclusively use the memory skill's connection logic
        try:
            self.db = get_db()
            self.db_name = self.db.name
        except Exception as e:
            console.print(f"[red]Failed to connect to ArangoDB via Memory skill: {e}[/red]")
            raise

        self._init_schema()

    def _init_schema(self):
        """Ensure collections and views exist (Idempotent)."""
        collections = [
            "feed_items",
            "feed_state", 
            "feed_deadletters",
            "feed_runs"
        ]
        
        for col in collections:
            if not self.db.has_collection(col):
                self.db.create_collection(col)
        
        # Indexes
        self.db.collection("feed_items").add_hash_index(["source_key"], unique=False)
        self.db.collection("feed_items").add_persistent_index(["published_at"], unique=False)
        self.db.collection("feed_items").add_persistent_index(["type"], unique=False)

        # View
        view_name = "feed_items_view"
        existing_views = [v['name'] for v in self.db.views()]
        
        if view_name not in existing_views:
            console.print(f"[green]Creating ArangoSearch view {view_name}...[/green]")
            self.db.create_arangosearch_view(
                name=view_name,
                properties={
                    "links": {
                        "feed_items": {
                            "fields": {
                                "title": {"analyzers": ["text_en"]},
                                "summary": {"analyzers": ["text_en"]},
                                "tags": {"analyzers": ["identity"]},
                                "entities": {"analyzers": ["text_en"]}
                            }
                        }
                    }
                }
            )

    def upsert_items(self, items: List[Dict[str, Any]]) -> int:
        if not items:
            return 0
        col = self.db.collection("feed_items")
        result = col.import_bulk(items, on_duplicate="update", halt_on_error=False)
        
        created = int(result.get("created", 0))
        updated = int(result.get("updated", 0))
        return created + updated

    def get_state(self, source_key: str) -> Dict[str, Any]:
        col = self.db.collection("feed_state")
        if col.has(source_key):
            return col.get(source_key)
        return {"_key": source_key}

    def save_state(self, source_key: str, state: Dict[str, Any]):
        state["_key"] = source_key
        state["updated_at"] = time.time()
        self.db.collection("feed_state").insert(state, overwrite=True, silent=True)

    def log_deadletter(self, doc: Dict[str, Any]):
        doc["logged_at"] = time.time()
        self.db.collection("feed_deadletters").insert(doc, silent=True)
        
    def log_run(self, run_stats: Dict[str, Any]):
        run_stats["logged_at"] = time.time()
        self.db.collection("feed_runs").insert(run_stats, silent=True)
