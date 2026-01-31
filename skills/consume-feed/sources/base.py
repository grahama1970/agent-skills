from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import time

from feed_config import FeedSource
from feed_storage import FeedStorage
from util.http import HttpClient

class SourceStats(BaseModel):
    source_key: str
    parsed_count: int = 0
    upserted_count: int = 0
    errors: int = 0
    status: str = "ok" # ok, failed, skipped_304

class BaseSource(ABC):
    def __init__(self, config: FeedSource, storage: FeedStorage, user_agent: str = "ConsumeFeed/1.0"):
        self.config = config
        self.storage = storage
        self.key = config.key
        self.user_agent = user_agent

    def make_http_client(self) -> HttpClient:
        """Centralized factory to ensure all sources use consistent User-Agent and timeouts."""
        return HttpClient(user_agent=self.user_agent)

    @abstractmethod
    def fetch(self, dry_run: bool = False, limit: int = 0) -> SourceStats:
        """
        Main entrypoint.
        Should:
        1. Load state
        2. Fetch data (conditional)
        3. Parse data
        4. Upsert to storage
        5. Save state
        6. Return stats
        """
        pass

    def load_state(self) -> Dict[str, Any]:
        return self.storage.get_state(self.key)

    def save_state(self, state: Dict[str, Any]):
        self.storage.save_state(self.key, state)
