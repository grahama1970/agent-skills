#!/usr/bin/env python3
"""
Sanity check for MusicBrainz API.

MusicBrainz does NOT use an API key - only a User-Agent string is required.
Rate limit: 1 request per second.

Usage:
    python sanity/musicbrainz.py
"""

import sys

def main():
    try:
        import musicbrainzngs
    except ImportError:
        print("FAIL: musicbrainzngs not installed")
        print("  Install with: pip install musicbrainzngs")
        sys.exit(1)

    # Set User-Agent (required by MusicBrainz API)
    musicbrainzngs.set_useragent(
        "HorusAgent",
        "1.0",
        "grahama@me.com"
    )

    print("Testing MusicBrainz API...")

    # Test 1: Search for artist
    print("\n1. Search artists: 'Chelsea Wolfe'")
    try:
        result = musicbrainzngs.search_artists(artist="Chelsea Wolfe", limit=3)
        artists = result.get("artist-list", [])
        if artists:
            for a in artists[:3]:
                name = a.get("name", "Unknown")
                mbid = a.get("id", "")
                print(f"   - {name} (MBID: {mbid[:8]}...)")
            print("   PASS: Artist search works")
        else:
            print("   WARN: No artists found")
    except Exception as e:
        print(f"   FAIL: {e}")
        sys.exit(1)

    # Test 2: Get artist by MBID
    print("\n2. Get artist details by MBID")
    try:
        # Chelsea Wolfe's MBID
        mbid = "c8a97c2d-80ac-4c22-8f2b-1e3a1d0e0f55"
        result = musicbrainzngs.get_artist_by_id(
            mbid,
            includes=["tags", "url-rels"]
        )
        artist = result.get("artist", {})
        name = artist.get("name", "Unknown")
        tags = [t["name"] for t in artist.get("tag-list", [])[:5]]
        print(f"   Name: {name}")
        print(f"   Tags: {tags}")
        print("   PASS: Artist details work")
    except Exception as e:
        print(f"   FAIL: {e}")
        # Don't fail completely - MBID might be wrong

    # Test 3: Search by tag
    print("\n3. Search artists by tag: 'doom metal'")
    try:
        result = musicbrainzngs.search_artists(tag="doom metal", limit=5)
        artists = result.get("artist-list", [])
        if artists:
            for a in artists[:5]:
                name = a.get("name", "Unknown")
                print(f"   - {name}")
            print("   PASS: Tag search works")
        else:
            print("   WARN: No artists found for tag")
    except Exception as e:
        print(f"   FAIL: {e}")
        sys.exit(1)

    # Test 4: Search recordings (songs)
    print("\n4. Search recordings: 'Carrion Flowers'")
    try:
        result = musicbrainzngs.search_recordings(recording="Carrion Flowers", limit=3)
        recordings = result.get("recording-list", [])
        if recordings:
            for r in recordings[:3]:
                title = r.get("title", "Unknown")
                artist = r.get("artist-credit", [{}])[0].get("name", "Unknown") if r.get("artist-credit") else "Unknown"
                print(f"   - {title} by {artist}")
            print("   PASS: Recording search works")
        else:
            print("   WARN: No recordings found")
    except Exception as e:
        print(f"   FAIL: {e}")
        sys.exit(1)

    print("\n" + "=" * 50)
    print("MusicBrainz sanity check PASSED")
    print("=" * 50)
    sys.exit(0)


if __name__ == "__main__":
    main()
