#!/usr/bin/env python3
"""Sanity test for ebooklib - EPUB reading."""
import tempfile
import os


def test_ebooklib():
    """Test that ebooklib can create and read EPUB files."""
    try:
        import ebooklib
        from ebooklib import epub
    except ImportError:
        print("FAIL: ebooklib not installed")
        print("Install with: pip install ebooklib")
        return False

    temp_path = None
    try:
        # Create a minimal EPUB file
        book = epub.EpubBook()
        book.set_identifier('test-id')
        book.set_title('Test Book')
        book.set_language('en')

        # Add chapter
        c1 = epub.EpubHtml(title='Chapter 1', file_name='chap_01.xhtml', lang='en')
        c1.content = '<html><body><h1>Chapter 1</h1><p>This is test content.</p></body></html>'
        book.add_item(c1)

        # Add nav
        nav = epub.EpubNav()
        book.add_item(nav)

        # Add to spine (without 'nav' string reference)
        book.spine = [c1]

        # Set toc
        book.toc = [c1]

        # Add default NCX and Nav
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # Write to temp file
        with tempfile.NamedTemporaryFile(suffix='.epub', delete=False) as f:
            temp_path = f.name

        epub.write_epub(temp_path, book)

        # Read it back
        read_book = epub.read_epub(temp_path)

        # Verify metadata
        title = read_book.get_metadata('DC', 'title')
        assert title, "No title found"
        assert title[0][0] == 'Test Book', f"Unexpected title: {title}"

        # Get items
        items = list(read_book.get_items())
        assert len(items) > 0, "No items in EPUB"

        # Find HTML content
        html_items = [item for item in items if isinstance(item, epub.EpubHtml)]
        assert len(html_items) > 0, "No HTML documents found"

        # Check content
        content = html_items[0].get_content().decode('utf-8')
        assert 'Chapter 1' in content, f"Expected 'Chapter 1' in content"
        assert 'test content' in content, f"Expected 'test content' in content"

        print(f"PASS: Created and read EPUB successfully")
        print(f"  - Title: {title[0][0]}")
        print(f"  - Items: {len(items)}")
        print(f"  - HTML documents: {len(html_items)}")
        return True

    except Exception as e:
        print(f"FAIL: Error with ebooklib: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


if __name__ == "__main__":
    success = test_ebooklib()
    exit(0 if success else 1)
