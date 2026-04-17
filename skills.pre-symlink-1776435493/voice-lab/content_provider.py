"""Jellyfin-backed content provider for voice-lab content browser.

Provides QAbstractListModel for search results and episode drill-down,
with threaded HTTP requests to avoid blocking the QML event loop.
"""
from __future__ import annotations

import os
import threading
from typing import Optional

import httpx
from loguru import logger
from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Qt,
    Property,
    Signal,
    Slot,
)


JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "http://localhost:8096")
JELLYFIN_API_KEY = os.environ.get("JELLYFIN_API_KEY", "")


class ContentSearchModel(QAbstractListModel):
    """List model for Jellyfin search results (movies, series, or episodes)."""

    TitleRole = Qt.UserRole + 1
    YearRole = Qt.UserRole + 2
    RuntimeRole = Qt.UserRole + 3
    GenresRole = Qt.UserRole + 4
    ThumbnailUrlRole = Qt.UserRole + 5
    FilePathRole = Qt.UserRole + 6
    ItemTypeRole = Qt.UserRole + 7
    SeriesNameRole = Qt.UserRole + 8
    SeasonEpisodeRole = Qt.UserRole + 9
    JellyfinIdRole = Qt.UserRole + 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[dict] = []

    def roleNames(self):
        return {
            self.TitleRole: b"title",
            self.YearRole: b"year",
            self.RuntimeRole: b"runtime",
            self.GenresRole: b"genres",
            self.ThumbnailUrlRole: b"thumbnailUrl",
            self.FilePathRole: b"filePath",
            self.ItemTypeRole: b"itemType",
            self.SeriesNameRole: b"seriesName",
            self.SeasonEpisodeRole: b"seasonEpisode",
            self.JellyfinIdRole: b"jellyfinId",
        }

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._items):
            return None
        item = self._items[index.row()]
        role_map = {
            self.TitleRole: "title",
            self.YearRole: "year",
            self.RuntimeRole: "runtime",
            self.GenresRole: "genres",
            self.ThumbnailUrlRole: "thumbnailUrl",
            self.FilePathRole: "filePath",
            self.ItemTypeRole: "itemType",
            self.SeriesNameRole: "seriesName",
            self.SeasonEpisodeRole: "seasonEpisode",
            self.JellyfinIdRole: "jellyfinId",
        }
        key = role_map.get(role)
        return item.get(key, "") if key else None

    def set_items(self, items: list[dict]):
        self.beginResetModel()
        self._items = items
        self.endResetModel()


def _ticks_to_display(ticks: int) -> str:
    """Convert Jellyfin RunTimeTicks (100ns units) to human display like '2h 44m'."""
    if not ticks:
        return ""
    total_minutes = ticks // 600_000_000
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes} min"


def _ticks_to_minutes(ticks: int) -> str:
    """Convert ticks to minutes display for episodes."""
    if not ticks:
        return ""
    return f"{ticks // 600_000_000} min"


def _thumbnail_url(item_id: str) -> str:
    """Build Jellyfin thumbnail URL with query-param auth for direct QML Image loading."""
    if not JELLYFIN_API_KEY:
        return ""
    return f"{JELLYFIN_URL}/Items/{item_id}/Images/Primary?maxWidth=180&api_key={JELLYFIN_API_KEY}"


def _parse_item(item: dict) -> dict:
    """Parse a Jellyfin API item into our flat dict format."""
    item_type = item.get("Type", "")
    ticks = item.get("RunTimeTicks", 0)

    # Season/episode label
    season_ep = ""
    if item_type == "Episode":
        s = item.get("ParentIndexNumber", 0)
        e = item.get("IndexNumber", 0)
        if s and e:
            season_ep = f"S{s:02d}E{e:02d}"

    return {
        "title": item.get("Name", ""),
        "year": str(item.get("ProductionYear", "")),
        "runtime": _ticks_to_display(ticks) if item_type != "Episode" else _ticks_to_minutes(ticks),
        "genres": ", ".join(item.get("Genres", [])),
        "thumbnailUrl": _thumbnail_url(item.get("Id", "")),
        "filePath": item.get("Path", ""),
        "itemType": item_type,
        "seriesName": item.get("SeriesName", ""),
        "seasonEpisode": season_ep,
        "jellyfinId": item.get("Id", ""),
    }


class ContentProvider(QObject):
    """Bridge between QML content browser and Jellyfin API.

    Provides search for movies/series/episodes with threaded HTTP requests.
    Model updates are dispatched to the main thread via internal signals
    to avoid modifying QAbstractListModel from background threads.
    """

    searchModelChanged = Signal()
    episodeModelChanged = Signal()
    isSearchingChanged = Signal()

    # Internal signals for thread-safe model updates (list[dict] as QVariantList)
    _searchResultsReady = Signal(list)
    _episodeResultsReady = Signal(list)
    _searchingDone = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_model = ContentSearchModel(self)
        self._episode_model = ContentSearchModel(self)
        self._is_searching = False

        # Connect internal signals to model updates (runs on main thread)
        self._searchResultsReady.connect(self._search_model.set_items)
        self._episodeResultsReady.connect(self._episode_model.set_items)
        self._searchingDone.connect(self._set_searching)

    @Property(QObject, constant=True)
    def searchModel(self):
        return self._search_model

    @Property(QObject, constant=True)
    def episodeModel(self):
        return self._episode_model

    @Property(bool, notify=isSearchingChanged)
    def isSearching(self):
        return self._is_searching

    def _set_searching(self, val: bool):
        if self._is_searching != val:
            self._is_searching = val
            self.isSearchingChanged.emit()

    @Slot(str, str)
    def search(self, query: str, item_type: str):
        """Search Jellyfin for items. item_type: 'Movie' or 'Series'.

        Runs in a background thread to avoid blocking QML.
        """
        self._set_searching(True)
        thread = threading.Thread(
            target=self._do_search, args=(query, item_type), daemon=True
        )
        thread.start()

    def _do_search(self, query: str, item_type: str):
        try:
            params = {
                "IncludeItemTypes": item_type,
                "Fields": "Path,Overview,Genres,RunTimeTicks,ProductionYear,SeriesName,ParentIndexNumber,IndexNumber,ImageTags",
                "Recursive": "true",
                "Limit": "50",
                "SortBy": "SortName",
                "SortOrder": "Ascending",
            }
            if query.strip():
                params["SearchTerm"] = query

            headers = {}
            if JELLYFIN_API_KEY:
                headers["X-Emby-Token"] = JELLYFIN_API_KEY

            resp = httpx.get(
                f"{JELLYFIN_URL}/Items",
                params=params,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            items = [_parse_item(i) for i in data.get("Items", [])]
            self._searchResultsReady.emit(items)
            logger.debug(f"Jellyfin search '{query}' ({item_type}): {len(items)} results")
        except Exception as e:
            logger.error(f"Jellyfin search failed: {e}")
            self._searchResultsReady.emit([])
        finally:
            self._searchingDone.emit(False)

    @Slot(str)
    def loadEpisodes(self, series_id: str):
        """Load all episodes for a series, grouped by season."""
        self._set_searching(True)
        thread = threading.Thread(
            target=self._do_load_episodes, args=(series_id,), daemon=True
        )
        thread.start()

    def _do_load_episodes(self, series_id: str):
        try:
            headers = {}
            if JELLYFIN_API_KEY:
                headers["X-Emby-Token"] = JELLYFIN_API_KEY

            resp = httpx.get(
                f"{JELLYFIN_URL}/Shows/{series_id}/Episodes",
                params={
                    "Fields": "Path,RunTimeTicks,ParentIndexNumber,IndexNumber,ImageTags,SeriesName",
                },
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            items = [_parse_item(i) for i in data.get("Items", [])]
            self._episodeResultsReady.emit(items)
            logger.debug(f"Loaded {len(items)} episodes for series {series_id}")
        except Exception as e:
            logger.error(f"Jellyfin episode load failed: {e}")
            self._episodeResultsReady.emit([])
        finally:
            self._searchingDone.emit(False)

    @Slot(str, result=str)
    def getItemPath(self, item_id: str) -> str:
        """Resolve a Jellyfin item ID to its filesystem path (synchronous)."""
        try:
            headers = {}
            if JELLYFIN_API_KEY:
                headers["X-Emby-Token"] = JELLYFIN_API_KEY

            resp = httpx.get(
                f"{JELLYFIN_URL}/Items/{item_id}",
                params={"Fields": "Path"},
                headers=headers,
                timeout=5,
            )
            resp.raise_for_status()
            return resp.json().get("Path", "")
        except Exception as e:
            logger.error(f"Jellyfin getItemPath failed: {e}")
            return ""
