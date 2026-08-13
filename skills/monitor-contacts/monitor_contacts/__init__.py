"""monitor-contacts runtime package.

Thin re-exports only; logic lives in named modules so an agent searching for
`store.py` or `freshness.py` finds it (best-practices-skills: thin __init__).
"""

from .freshness import detect_changes, stale_contacts
from .store import COLLECTION, contact_key, count, load, save

__all__ = [
    "COLLECTION", "contact_key", "count", "load", "save",
    "detect_changes", "stale_contacts",
]
