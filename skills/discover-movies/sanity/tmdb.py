#!/usr/bin/env python3
"""TMDB API connectivity test for discover-movies skill."""

import os
import sys


def main():
    # Check API key is set
    api_key = os.environ.get("TMDB_API_KEY", "")
    if not api_key:
        print("SKIP: TMDB_API_KEY not set")
        # Return success but note it's skipped
        return 0

    # Add parent to path for imports
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    try:
        from src import tmdb_client as tmdb

        # Test API connectivity
        if not tmdb.check_api():
            print("FAIL: TMDB API check failed")
            return 1

        # Test search
        results = tmdb.search_movies("The Matrix", limit=1)
        if not results:
            print("FAIL: Search returned no results")
            return 1

        movie = results[0]
        print(f"OK: Found '{movie.title}' ({movie.year})")

        # Test similar movies
        similar = tmdb.get_similar_movies(movie.id, limit=3)
        if similar:
            print(f"OK: Found {len(similar)} similar movies")
        else:
            print("WARN: No similar movies found (may be normal)")

        # Test trending
        trending = tmdb.get_trending("week", limit=3)
        if trending:
            print(f"OK: Found {len(trending)} trending movies")
        else:
            print("WARN: No trending movies found")

        return 0

    except Exception as e:
        print(f"FAIL: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
