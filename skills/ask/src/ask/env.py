"""Environment loading helpers for /ask modules."""

from __future__ import annotations

from functools import lru_cache

from dotenv import find_dotenv, load_dotenv


@lru_cache(maxsize=1)
def load_dotenv_once() -> None:
    """Load the nearest dotenv file once without overriding existing values."""
    load_dotenv(find_dotenv(usecwd=True), override=False)
