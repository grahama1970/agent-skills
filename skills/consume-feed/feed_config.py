from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
import yaml
from pathlib import Path

# CONFIG_PATH = Path("configs/feeds.yaml")
SKILL_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = SKILL_ROOT / "configs" / "feeds.yaml"

class SourceType(str, Enum):
    RSS = "rss"
    GITHUB = "github"
    NVD = "nvd"

class FeedSource(BaseModel):
    key: str = Field(..., description="Unique identifier for the source")
    type: SourceType
    enabled: bool = True
    tags: List[str] = Field(default_factory=list)
    
    # Source-specific config (loose schema for flexibility, validated at runtime by Source impl)
    rss_url: Optional[str] = None
    
    gh_owner: Optional[str] = None
    gh_repo: Optional[str] = None
    gh_include_issues: bool = True
    gh_include_releases: bool = True
    gh_include_discussions: bool = True
    
    nvd_query: Optional[str] = None
    nvd_cvss_min: float = 0.0

    @field_validator("key")
    @classmethod
    def validate_key(cls, v: str) -> str:
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Key must be alphanumeric (dash/underscore allowed)")
        return v

class RunOptions(BaseModel):
    timeout_seconds: int = 30
    concurrency: int = 5
    user_agent: str = "FeedParser/1.0 (Agentic)"

class FeedConfig(BaseModel):
    version: int = 1
    arango_url: Optional[str] = None
    arango_db: str = "feed_db"
    run_options: RunOptions = Field(default_factory=RunOptions)
    sources: List[FeedSource] = Field(default_factory=list)

    def save(self, path: Path = CONFIG_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            # Dump to dict, then YAML
            # exclude_none=True keeps it clean
            yaml.dump(self.model_dump(exclude_none=True, mode='json'), f, sort_keys=False)

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "FeedConfig":
        if not path.exists():
            return cls()
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
            return cls(**data)
