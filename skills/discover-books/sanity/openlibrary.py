#!/usr/bin/env python3
"""OpenLibrary API connectivity test for discover-books skill."""

import os
import sys


def main():
    # Add parent to path for imports
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    try:
        from src import openlibrary_client as ol

        # Test API connectivity
        if not ol.check_api():
            print("FAIL: OpenLibrary API check failed")
            return 1

        # Test search
        results = ol.search_books("Dune Frank Herbert", limit=1)
        if not results:
            print("FAIL: Search returned no results")
            return 1

        book = results[0]
        print(f"OK: Found '{book.title}' by {book.authors}")

        # Test author search
        author_results = ol.search_by_author("Frank Herbert", limit=3)
        if author_results:
            print(f"OK: Found {len(author_results)} books by Frank Herbert")
        else:
            print("WARN: No author results found")

        # Test subject search
        subject_results = ol.search_by_subject("science fiction", limit=3)
        if subject_results:
            print(f"OK: Found {len(subject_results)} science fiction books")
        else:
            print("WARN: No subject results found")

        return 0

    except Exception as e:
        print(f"FAIL: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
