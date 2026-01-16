#!/usr/bin/env python3
"""Shared dotenv loader for skills."""

try:
    from dotenv import load_dotenv, find_dotenv
except Exception:
    load_dotenv = None
    find_dotenv = None


def load_env() -> None:
    if not load_dotenv or not find_dotenv:
        return
    path = find_dotenv(usecwd=True)
    load_dotenv(path or None, override=False)


if __name__ == "__main__":
    load_env()
