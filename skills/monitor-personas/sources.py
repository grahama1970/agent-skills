#!/usr/bin/env python3
"""
Multi-source handlers for persona monitoring.

Abstracts source checking and ingestion across:
- YouTube channels
- RSS feeds
- arXiv queries
- Books (Readarr)
- Movies (NZBGeek)
- Music (YouTube History)
- Code repositories

Each handler implements check() and ingest() methods.
"""

import json
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import canonical ingest-youtube channel listing
_SKILLS_DIR = Path(__file__).resolve().parent.parent
_IY_DIR = str(_SKILLS_DIR / "ingest-youtube")
if _IY_DIR not in sys.path:
    sys.path.insert(0, _IY_DIR)
from youtube_transcripts.downloader import list_channel_video_ids


@dataclass
class SourceConfig:
    """Configuration for a content source."""
    type: str  # youtube, rss, arxiv, book, movie, music, code
    handle: str  # URL, channel handle, query, etc.
    priority: str = "MEDIUM"  # HIGH, MEDIUM, LOW
    search_terms: Optional[List[str]] = None  # Filter by title keywords
    extra: Dict[str, Any] = None  # Type-specific config

    def __post_init__(self):
        if self.extra is None:
            self.extra = {}


@dataclass
class SourceStatus:
    """Status of a content source."""
    total: int  # Total items available
    ingested: int  # Items already ingested
    new: int  # New items to ingest
    last_checked: str  # ISO timestamp
    error: Optional[str] = None


@dataclass
class IngestResult:
    """Result of ingesting content."""
    success: bool
    ingested_count: int
    message: str
    items: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.items is None:
            self.items = []


class SourceHandler(ABC):
    """Base class for source handlers."""

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Return the source type identifier."""
        pass

    @abstractmethod
    def check(self, config: SourceConfig, state_dir: Path) -> SourceStatus:
        """Check for new content.

        Args:
            config: Source configuration
            state_dir: Directory to store state files

        Returns:
            SourceStatus with counts and status
        """
        pass

    @abstractmethod
    def ingest(
        self,
        config: SourceConfig,
        output_dir: Path,
        max_new: int = 50,
        state_dir: Optional[Path] = None,
    ) -> IngestResult:
        """Ingest new content.

        Args:
            config: Source configuration
            output_dir: Directory to store ingested content
            max_new: Maximum items to ingest
            state_dir: Directory for state files

        Returns:
            IngestResult with ingestion status
        """
        pass


class YouTubeHandler(SourceHandler):
    """Handler for YouTube channel sources."""

    @property
    def source_type(self) -> str:
        return "youtube"

    def _list_filtered_ids(self, handle: str, search_terms: List[str]) -> List[str]:
        """List video IDs from a channel, filtered by title search terms.

        Uses yt-dlp --match-title with regex OR pattern.
        """
        url = handle if handle.startswith("http") else f"{handle}/videos"
        # Build regex: term1|term2|term3 (case insensitive via yt-dlp default)
        pattern = "|".join(search_terms)
        cmd = [
            "yt-dlp", "--flat-playlist", "--print", "id",
            "--match-title", pattern,
            url,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=180,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if result.returncode != 0:
                return []
            return [vid.strip() for vid in result.stdout.strip().split("\n") if vid.strip()]
        except Exception:
            return []

    def check(self, config: SourceConfig, state_dir: Path) -> SourceStatus:
        """Check YouTube channel for video count.

        When search_terms are set, filters by title keywords.
        Otherwise delegates to canonical list_channel_video_ids().
        """
        try:
            if config.search_terms:
                video_ids = self._list_filtered_ids(config.handle, config.search_terms)
            else:
                video_ids = list_channel_video_ids(config.handle, max_results=0)
            total = len(video_ids)

            # Load ingested state
            ingested_file = state_dir / f"{config.handle.replace('/', '_')}_ingested.json"
            ingested = set()
            if ingested_file.exists():
                try:
                    ingested = set(json.loads(ingested_file.read_text()))
                except json.JSONDecodeError:
                    pass

            new_count = len([v for v in video_ids if v not in ingested])

            return SourceStatus(
                total=total,
                ingested=len(ingested),
                new=new_count,
                last_checked=datetime.now().isoformat(),
            )

        except subprocess.TimeoutExpired:
            return SourceStatus(
                total=0, ingested=0, new=0,
                last_checked=datetime.now().isoformat(),
                error="Timeout fetching YouTube channel",
            )
        except Exception as e:
            return SourceStatus(
                total=0, ingested=0, new=0,
                last_checked=datetime.now().isoformat(),
                error=str(e),
            )

    def ingest(
        self,
        config: SourceConfig,
        output_dir: Path,
        max_new: int = 50,
        state_dir: Optional[Path] = None,
    ) -> IngestResult:
        """Ingest YouTube videos using ingest-youtube skill."""
        # This delegates to the ingest-youtube skill
        # The actual implementation is in the ingest command
        return IngestResult(
            success=True,
            ingested_count=0,
            message="YouTube ingestion delegated to ingest-youtube skill",
        )


class RSSHandler(SourceHandler):
    """Handler for RSS feed sources."""

    @property
    def source_type(self) -> str:
        return "rss"

    def check(self, config: SourceConfig, state_dir: Path) -> SourceStatus:
        """Check RSS feed for new items."""
        try:
            # Use consume-feed skill to check
            project_root = Path(__file__).parent.parent.parent.parent
            consume_feed = project_root / ".pi/skills/consume-feed/run.sh"

            if not consume_feed.exists():
                return SourceStatus(
                    total=0, ingested=0, new=0,
                    last_checked=datetime.now().isoformat(),
                    error="consume-feed skill not available",
                )

            result = subprocess.run(
                [str(consume_feed), "check", "--url", config.handle, "--json"],
                capture_output=True,
                text=True,
                timeout=60,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    return SourceStatus(
                        total=data.get("total", 0),
                        ingested=data.get("ingested", 0),
                        new=data.get("new", 0),
                        last_checked=datetime.now().isoformat(),
                    )
                except json.JSONDecodeError:
                    pass

            return SourceStatus(
                total=0, ingested=0, new=0,
                last_checked=datetime.now().isoformat(),
                error="Failed to parse RSS feed status",
            )

        except Exception as e:
            return SourceStatus(
                total=0, ingested=0, new=0,
                last_checked=datetime.now().isoformat(),
                error=str(e),
            )

    def ingest(
        self,
        config: SourceConfig,
        output_dir: Path,
        max_new: int = 50,
        state_dir: Optional[Path] = None,
    ) -> IngestResult:
        """Ingest RSS feed using consume-feed skill."""
        return IngestResult(
            success=True,
            ingested_count=0,
            message="RSS ingestion delegated to consume-feed skill",
        )


class ArXivHandler(SourceHandler):
    """Handler for arXiv paper sources."""

    @property
    def source_type(self) -> str:
        return "arxiv"

    def _load_ingested(self, state_dir: Path, query: str) -> set:
        """Load set of ingested arXiv paper IDs for a query."""
        state_file = state_dir / f"arxiv_{query.replace(' ', '_')[:40]}_ingested.json"
        if state_file.exists():
            try:
                return set(json.loads(state_file.read_text()))
            except json.JSONDecodeError:
                pass
        return set()

    def _save_ingested(self, state_dir: Path, query: str, ingested: set):
        """Save set of ingested arXiv paper IDs."""
        state_file = state_dir / f"arxiv_{query.replace(' ', '_')[:40]}_ingested.json"
        state_file.write_text(json.dumps(list(ingested)))

    def check(self, config: SourceConfig, state_dir: Path) -> SourceStatus:
        """Check arXiv for new papers matching query."""
        try:
            project_root = Path(__file__).parent.parent.parent.parent
            arxiv_skill = project_root / ".pi/skills/arxiv/run.sh"

            if not arxiv_skill.exists():
                return SourceStatus(
                    total=0, ingested=0, new=0,
                    last_checked=datetime.now().isoformat(),
                    error="arxiv skill not available",
                )

            result = subprocess.run(
                [str(arxiv_skill), "search", "--query", config.handle, "--json", "--max", "100"],
                capture_output=True,
                text=True,
                timeout=60,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    papers = data.get("papers", [])
                    paper_ids = {p.get("id", p.get("arxiv_id", "")) for p in papers if p}
                    ingested = self._load_ingested(state_dir, config.handle)
                    new_ids = paper_ids - ingested
                    return SourceStatus(
                        total=len(papers),
                        ingested=len(ingested & paper_ids),
                        new=len(new_ids),
                        last_checked=datetime.now().isoformat(),
                    )
                except json.JSONDecodeError:
                    pass

            return SourceStatus(
                total=0, ingested=0, new=0,
                last_checked=datetime.now().isoformat(),
                error="Failed to search arXiv",
            )

        except Exception as e:
            return SourceStatus(
                total=0, ingested=0, new=0,
                last_checked=datetime.now().isoformat(),
                error=str(e),
            )

    def ingest(
        self,
        config: SourceConfig,
        output_dir: Path,
        max_new: int = 50,
        state_dir: Optional[Path] = None,
    ) -> IngestResult:
        """Ingest arXiv papers using arxiv skill."""
        return IngestResult(
            success=True,
            ingested_count=0,
            message="arXiv ingestion delegated to arxiv skill",
        )


class BookHandler(SourceHandler):
    """Handler for book sources via Readarr."""

    @property
    def source_type(self) -> str:
        return "book"

    def check(self, config: SourceConfig, state_dir: Path) -> SourceStatus:
        """Check for new books from author/series."""
        try:
            project_root = Path(__file__).parent.parent.parent.parent
            ingest_book = project_root / ".pi/skills/ingest-book/run.sh"

            if not ingest_book.exists():
                return SourceStatus(
                    total=0, ingested=0, new=0,
                    last_checked=datetime.now().isoformat(),
                    error="ingest-book skill not available",
                )

            result = subprocess.run(
                [str(ingest_book), "status", "--json"],
                capture_output=True,
                text=True,
                timeout=60,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    return SourceStatus(
                        total=data.get("total", 0),
                        ingested=data.get("ingested", 0),
                        new=data.get("new", 0),
                        last_checked=datetime.now().isoformat(),
                    )
                except json.JSONDecodeError:
                    pass

            return SourceStatus(
                total=0, ingested=0, new=0,
                last_checked=datetime.now().isoformat(),
            )

        except Exception as e:
            return SourceStatus(
                total=0, ingested=0, new=0,
                last_checked=datetime.now().isoformat(),
                error=str(e),
            )

    def ingest(
        self,
        config: SourceConfig,
        output_dir: Path,
        max_new: int = 50,
        state_dir: Optional[Path] = None,
    ) -> IngestResult:
        """Ingest books using ingest-book skill."""
        return IngestResult(
            success=True,
            ingested_count=0,
            message="Book ingestion delegated to ingest-book skill",
        )


class MovieHandler(SourceHandler):
    """Handler for movie sources via NZBGeek/ingest-movie."""

    @property
    def source_type(self) -> str:
        return "movie"

    def check(self, config: SourceConfig, state_dir: Path) -> SourceStatus:
        """Check for new movies."""
        try:
            project_root = Path(__file__).parent.parent.parent.parent
            ingest_movie = project_root / ".pi/skills/ingest-movie/run.sh"

            if not ingest_movie.exists():
                return SourceStatus(
                    total=0, ingested=0, new=0,
                    last_checked=datetime.now().isoformat(),
                    error="ingest-movie skill not available",
                )

            # Movies don't have a "count" in the same way
            # This would need integration with movie watchlist
            return SourceStatus(
                total=0, ingested=0, new=0,
                last_checked=datetime.now().isoformat(),
            )

        except Exception as e:
            return SourceStatus(
                total=0, ingested=0, new=0,
                last_checked=datetime.now().isoformat(),
                error=str(e),
            )

    def ingest(
        self,
        config: SourceConfig,
        output_dir: Path,
        max_new: int = 50,
        state_dir: Optional[Path] = None,
    ) -> IngestResult:
        """Ingest movies using ingest-movie skill."""
        return IngestResult(
            success=True,
            ingested_count=0,
            message="Movie ingestion delegated to ingest-movie skill",
        )


class MusicHandler(SourceHandler):
    """Handler for music sources via YouTube history."""

    @property
    def source_type(self) -> str:
        return "music"

    def check(self, config: SourceConfig, state_dir: Path) -> SourceStatus:
        """Check for new music from YouTube history."""
        # Music is typically manual or from ingest-yt-history
        return SourceStatus(
            total=0, ingested=0, new=0,
            last_checked=datetime.now().isoformat(),
        )

    def ingest(
        self,
        config: SourceConfig,
        output_dir: Path,
        max_new: int = 50,
        state_dir: Optional[Path] = None,
    ) -> IngestResult:
        """Ingest music using ingest-yt-history skill."""
        return IngestResult(
            success=True,
            ingested_count=0,
            message="Music ingestion delegated to ingest-yt-history skill",
        )


class CodeHandler(SourceHandler):
    """Handler for code repository sources."""

    @property
    def source_type(self) -> str:
        return "code"

    def check(self, config: SourceConfig, state_dir: Path) -> SourceStatus:
        """Check code repository for changes."""
        try:
            project_root = Path(__file__).parent.parent.parent.parent
            ingest_code = project_root / ".pi/skills/ingest-code/run.sh"

            if not ingest_code.exists():
                return SourceStatus(
                    total=0, ingested=0, new=0,
                    last_checked=datetime.now().isoformat(),
                    error="ingest-code skill not available",
                )

            # Check for new commits or files
            repo_path = Path(config.handle).expanduser()
            if repo_path.exists():
                # Count source files
                source_files = list(repo_path.glob("**/*.py")) + \
                               list(repo_path.glob("**/*.ts")) + \
                               list(repo_path.glob("**/*.js"))
                return SourceStatus(
                    total=len(source_files),
                    ingested=0,
                    new=len(source_files),
                    last_checked=datetime.now().isoformat(),
                )

            return SourceStatus(
                total=0, ingested=0, new=0,
                last_checked=datetime.now().isoformat(),
            )

        except Exception as e:
            return SourceStatus(
                total=0, ingested=0, new=0,
                last_checked=datetime.now().isoformat(),
                error=str(e),
            )

    def ingest(
        self,
        config: SourceConfig,
        output_dir: Path,
        max_new: int = 50,
        state_dir: Optional[Path] = None,
    ) -> IngestResult:
        """Ingest code using ingest-code skill."""
        return IngestResult(
            success=True,
            ingested_count=0,
            message="Code ingestion delegated to ingest-code skill",
        )


# Handler registry
HANDLERS: Dict[str, SourceHandler] = {
    "youtube": YouTubeHandler(),
    "rss": RSSHandler(),
    "arxiv": ArXivHandler(),
    "book": BookHandler(),
    "movie": MovieHandler(),
    "music": MusicHandler(),
    "code": CodeHandler(),
}


def get_handler(source_type: str) -> Optional[SourceHandler]:
    """Get handler for a source type."""
    return HANDLERS.get(source_type)


def check_all_sources(
    sources: List[SourceConfig],
    state_dir: Path,
) -> Dict[str, SourceStatus]:
    """Check all sources for new content.

    Args:
        sources: List of source configurations
        state_dir: Directory for state files

    Returns:
        Dict mapping source handles to status
    """
    results = {}
    for config in sources:
        handler = get_handler(config.type)
        if handler:
            status = handler.check(config, state_dir)
            results[config.handle] = status
        else:
            results[config.handle] = SourceStatus(
                total=0, ingested=0, new=0,
                last_checked=datetime.now().isoformat(),
                error=f"Unknown source type: {config.type}",
            )
    return results
