#!/usr/bin/env python3
"""Sanity test for whoosh library - full-text search indexing."""
import tempfile
import os
import shutil


def test_whoosh_index():
    """Test that whoosh can create and search an index."""
    try:
        from whoosh import index
        from whoosh.fields import Schema, TEXT, ID
        from whoosh.qparser import QueryParser
    except ImportError:
        print("FAIL: whoosh library not installed")
        print("Install with: pip install whoosh")
        return False

    # Create a temporary directory for the index
    temp_dir = tempfile.mkdtemp()

    try:
        # Define schema
        schema = Schema(
            id=ID(stored=True),
            content=TEXT(stored=True)
        )

        # Create index
        ix = index.create_in(temp_dir, schema)

        # Add documents
        writer = ix.writer()
        writer.add_document(id="1", content="The quick brown fox jumps over the lazy dog")
        writer.add_document(id="2", content="The fox is quick and brown")
        writer.add_document(id="3", content="A lazy dog sleeps all day")
        writer.commit()

        # Search
        with ix.searcher() as searcher:
            query = QueryParser("content", ix.schema).parse("fox")
            results = searcher.search(query)

            assert len(results) == 2, f"Expected 2 results for 'fox', got {len(results)}"

            query2 = QueryParser("content", ix.schema).parse("lazy dog")
            results2 = searcher.search(query2)

            assert len(results2) == 2, f"Expected 2 results for 'lazy dog', got {len(results2)}"

        print(f"PASS: Created index, added 3 documents, searched successfully")
        print(f"  - Search 'fox': {len(results)} results")
        print(f"  - Search 'lazy dog': {len(results2)} results")
        return True

    except Exception as e:
        print(f"FAIL: Error with whoosh: {e}")
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    success = test_whoosh_index()
    exit(0 if success else 1)
